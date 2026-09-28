"""
Agent runtime — dispatch logging, idempotency, resource locks, budget tracking,
critic invocation, replay rendering.

The single non-guardrail support library for the operator's six-agent fleet. Five primitives:

  - log_handoff(packet)               → append to agent-handoffs.jsonl
  - validate_packet(packet)           → problems against agents/shared/handoff-packet-schema.json
  - log_job_state(job_id, state, ...) → append to agent-jobs.jsonl (per-leaf scoreboard)
  - idempotency_check(job_id, tool, args)         → ("fire" | "cached", cached_result)
  - idempotency_record(job_id, tool, args, result) → store result for 7d
  - acquire_lock(job_id, resource_keys, ttl_min=30) → ("acquired" | "busy", busy_keys)
  - release_lock(job_id)              → release all locks held by job
  - record_run(agent, job_id, trace)  → validate (RUN_SCHEMA agents), append to runs/{agent}/{date}.jsonl
  - check_budget(agent_key, cost_so_far, calls_so_far) → ("ok" | "warn" | "halt", ...)
  - record_critic_disagreement(...)    → append to critic-disagreement.jsonl
  - render_replay(job_id)              → write replays/{job_id}.html

Reads:
  ~/.claude/agents/shared/budget-caps.json
  ~/.claude/agents/shared/handoff-packet-schema.json

Writes:
  ~/.claude/state/agent-handoffs.jsonl
  ~/.claude/state/agent-jobs.jsonl
  ~/.claude/state/agent-idempotency-keys.json
  ~/.claude/state/agent-resource-locks.json
  ~/.claude/state/critic-disagreement.jsonl
  ~/.claude/state/replays/{job_id}.html
  ~/.claude/state/agent-runs/{agent}/{date}.jsonl
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import html
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CLAUDE = Path.home() / ".claude"
STATE = CLAUDE / "state"
SHARED = CLAUDE / "agents" / "shared"

HANDOFFS = STATE / "agent-handoffs.jsonl"
JOBS = STATE / "agent-jobs.jsonl"
IDEMPOTENCY = STATE / "agent-idempotency-keys.json"
LOCKS = STATE / "agent-resource-locks.json"
DISAGREEMENT = STATE / "critic-disagreement.jsonl"
REPLAYS = STATE / "replays"
RUNS = STATE / "agent-runs"
BUDGET_CAPS = SHARED / "budget-caps.json"
PACKET_SCHEMA = SHARED / "handoff-packet-schema.json"

IDEMPOTENCY_TTL_DAYS = 7
LOCK_DEFAULT_TTL_MIN = 30


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def _canonical(args: dict) -> str:
    return json.dumps(args, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Handoff packet (typed schema)
# ---------------------------------------------------------------------------

# Valid job-state transitions for the per-leaf scoreboard. A node may only move
# to a state listed under its current state; this is the lightweight DAG-checkpoint
# invariant that render_replay() visualises.
JOB_STATES = {
    "PENDING": {"RUNNING", "CANCELLED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "TIMED_OUT", "NEEDS_APPROVAL", "CANCELLED"},
    "NEEDS_APPROVAL": {"RUNNING", "CANCELLED", "FAILED"},
    "SUCCEEDED": set(),
    "FAILED": {"RUNNING"},        # a retry re-enters RUNNING
    "TIMED_OUT": {"RUNNING"},
    "CANCELLED": set(),
}


@dataclass
class HandoffPacket:
    """delegate.py's packet for a `claude -p` worker. Fleet-agent packets are the dict form
    defined by agents/shared/handoff-packet-schema.json and checked by validate_packet().

    A packet is the replay key: log_handoff(), log_job_state() and render_replay() all
    join on job_id.
    """
    job_id: str
    task: str
    success_check: str
    agent: str = "delegate"
    context: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    max_iterations: int = 3
    parent_job_id: str | None = None

    def validate(self) -> "HandoffPacket":
        missing = [f for f in ("job_id", "task", "success_check") if not getattr(self, f).strip()]
        if missing:
            raise ValueError(f"HandoffPacket missing required field(s): {', '.join(missing)}")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        return self

    def to_record(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def validate_packet(packet: Any) -> list[str]:
    """Every way a fleet packet breaks handoff-packet-schema.json (custom_build-v1 context
    included). Empty list = valid."""
    import jsonschema  # local: hooks import this module and must not need it
    if not isinstance(packet, dict):
        return ["packet must be a JSON object"]
    validator = jsonschema.Draft7Validator(json.loads(PACKET_SCHEMA.read_text()))
    return [f"{'/'.join(map(str, e.absolute_path)) or '(packet)'}: {e.message}"
            for e in sorted(validator.iter_errors(packet), key=lambda e: list(map(str, e.absolute_path)))]


def valid_transition(frm: str, to: str) -> bool:
    """True if a node may move from state `frm` to state `to`. An unknown `frm`
    is permissive (returns True) so legacy callers are never blocked."""
    if frm not in JOB_STATES:
        return True
    return to in JOB_STATES[frm]


# ---------------------------------------------------------------------------
# Handoff + job-state logging
# ---------------------------------------------------------------------------

def log_handoff(packet: "HandoffPacket | dict") -> None:
    """Append a handoff packet to agent-handoffs.jsonl. Stamped with timestamp.

    Accepts a typed HandoffPacket (validated on the way in) or a raw dict for
    back-compat with existing fleet callers.
    """
    if isinstance(packet, HandoffPacket):
        body = packet.validate().to_record()
    else:
        body = dict(packet)
    record = {"ts": _now_iso(), **body}
    _append_jsonl(HANDOFFS, record)


def log_job_state(job_id: str, state: str, agent: str = "", note: str = "") -> None:
    """Per-leaf scoreboard. State is one of:
    PENDING | RUNNING | SUCCEEDED | FAILED | NEEDS_APPROVAL | TIMED_OUT | CANCELLED
    """
    _append_jsonl(JOBS, {
        "ts": _now_iso(),
        "job_id": job_id,
        "agent": agent,
        "state": state,
        "note": note,
    })


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def idempotency_key(job_id: str, tool: str, args: dict) -> str:
    payload = f"{job_id}|{tool}|{_canonical(args)}".encode()
    return hashlib.sha256(payload).hexdigest()


def _purge_expired(store: dict) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=IDEMPOTENCY_TTL_DAYS)).isoformat()
    return {k: v for k, v in store.items() if v.get("ts", "") >= cutoff}


def idempotency_check(job_id: str, tool: str, args: dict) -> tuple[str, Any]:
    """Returns ('fire', None) if no prior call, or ('cached', cached_result) if same
    key is already in the 7d store. Caller fires the tool only on 'fire'.
    """
    key = idempotency_key(job_id, tool, args)
    store = _load_json(IDEMPOTENCY, {})
    store = _purge_expired(store)
    if key in store:
        return "cached", store[key].get("result")
    return "fire", None


def idempotency_record(job_id: str, tool: str, args: dict, result: Any) -> None:
    """Store the result under the idempotency key. Caller invokes after a successful
    external write so retries return cached result instead of re-firing.
    """
    key = idempotency_key(job_id, tool, args)
    store = _load_json(IDEMPOTENCY, {})
    store = _purge_expired(store)
    store[key] = {
        "ts": _now_iso(),
        "job_id": job_id,
        "tool": tool,
        "result": result,
    }
    _save_json(IDEMPOTENCY, store)


# ---------------------------------------------------------------------------
# Resource locks
# ---------------------------------------------------------------------------

def _purge_stale_locks(locks: dict) -> dict:
    now = datetime.now(timezone.utc)
    fresh = {}
    for key, lock in locks.items():
        try:
            expires = datetime.fromisoformat(lock["expires_at"])
        except (KeyError, ValueError):
            continue
        if expires > now:
            fresh[key] = lock
    return fresh


@contextlib.contextmanager
def _exclusive(path: Path):
    """Serialise read-modify-write of a state file across processes. Without it two
    sessions could both read "free" and both acquire the same publish lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(path.suffix + ".flock"), "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def acquire_lock(
    job_id: str,
    resource_keys: list[str],
    ttl_min: int = LOCK_DEFAULT_TTL_MIN,
) -> tuple[str, list[str]]:
    """All-or-nothing acquire for a list of canonical resource keys.
    Returns ('acquired', []) on success or ('busy', [keys held by other jobs]).
    """
    with _exclusive(LOCKS):
        locks = _purge_stale_locks(_load_json(LOCKS, {}))
        busy = [k for k in resource_keys if k in locks and locks[k]["job_id"] != job_id]
        if busy:
            return "busy", busy

        expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_min)).isoformat()
        for k in resource_keys:
            locks[k] = {"job_id": job_id, "acquired_at": _now_iso(), "expires_at": expires}
        _save_json(LOCKS, locks)
        return "acquired", []


def release_lock(job_id: str) -> int:
    """Release every lock held by the given job. Returns count released."""
    with _exclusive(LOCKS):
        locks = _load_json(LOCKS, {})
        held = [k for k, v in locks.items() if v.get("job_id") == job_id]
        for k in held:
            del locks[k]
        _save_json(LOCKS, locks)
        return len(held)


# ---------------------------------------------------------------------------
# Episodic memory (per-agent runs)
# ---------------------------------------------------------------------------

# Typed run-record contract for the agents whose KPIs are computed from records.
# Hand-built JSON drifted (string booleans, naive timestamps, notes/note/summary),
# so the CLI coerces and checks these before writing. Other agents stay free-form.
RUN_OUTCOMES = {"success", "partial", "failed", "escalated", "absorb"}
RUN_SCHEMA = {
    "flowsmith": {"round_field": "verify_rounds", "round_cap": 3,
                  "approval_field": "handoff_accepted", "ints": ["verify_rounds", "revision_items",
                  "silent_failures_caught", "post_handover_defects", "publishes", "tool_calls"]},
    "wright": {"round_field": "design_review_rounds", "round_cap": 5,
               "approval_field": "first_pass_approved", "ints": ["design_review_rounds",
               "revision_items", "post_handover_defects", "tool_calls"]},
}
RUN_SCHEMA["webflow-fix"] = RUN_SCHEMA["flowsmith"]  # same verify loop, cap and grading


def _coerce(value: str) -> Any:
    low = value.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", ""):
        return None
    if value.strip()[:1] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            pass
    return value


def validate_run(agent: str, trace: dict) -> list[str]:
    """Problems that make a record useless for KPIs. Empty list = writable.

    Only the SubagentStop hook's exact placeholder (truth_status "auto", outcome "unknown",
    no approval or round field) skips the outcome and round checks, never the type checks:
    an "auto" record carrying a verdict must pass like any other."""
    spec = RUN_SCHEMA.get(agent)
    if not spec:
        return []
    errs = []
    auto = (trace.get("truth_status") == "auto" and trace.get("outcome") == "unknown"
            and spec["round_field"] not in trace
            and not any(s["approval_field"] in trace for s in RUN_SCHEMA.values()))
    if trace.get("outcome") not in RUN_OUTCOMES and not auto:
        errs.append(f"outcome must be one of {sorted(RUN_OUTCOMES)}")
    if spec["round_field"] not in trace and not auto:
        errs.append(f"{spec['round_field']} is required (0 if none ran)")
    for k in spec["ints"]:
        if k in trace and trace[k] is not None and (isinstance(trace[k], bool) or not isinstance(trace[k], int)):
            errs.append(f"{k} must be an integer")
    appr = spec["approval_field"]
    if appr in trace and trace[appr] is not None and not isinstance(trace[appr], bool):
        errs.append(f"{appr} must be true, false or null (null = not graded yet)")
    rounds = trace.get(spec["round_field"])
    if isinstance(rounds, int) and rounds > spec["round_cap"] and trace.get("escalated") is not True:
        errs.append(f"{spec['round_field']}={rounds} is over the cap of {spec['round_cap']}: "
                    "set escalated=true and name what was surfaced in note=")
    return errs


def record_run(agent: str, job_id: str, trace: dict) -> None:
    """Append a structured run record to runs/{agent}/{date}.jsonl.

    Records for agents in RUN_SCHEMA are validated here, so every path (the CLI, a
    skill's inline call, main-session work) is held to the same contract: raises
    ValueError naming each problem instead of writing a record KPIs cannot grade.
    """
    errs = validate_run(agent, trace)
    if errs:
        raise ValueError("\n  ".join(errs))
    record = {"ts": _now_iso(), "job_id": job_id, "agent": agent, **trace}
    record.setdefault("truth_status", "asserted")
    path = RUNS / agent / f"{_today()}.jsonl"
    _append_jsonl(path, record)


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------

@dataclass
class BudgetVerdict:
    decision: str  # "ok" | "warn" | "halt"
    cost_used_usd: float
    cost_cap_usd: float
    calls_used: int
    calls_cap: int
    halt_action: str | None = None
    reason: str = ""


def check_budget(agent_key: str, cost_so_far_usd: float, calls_so_far: int) -> BudgetVerdict:
    """Read budget-caps.json and decide whether the worker should continue, warn,
    or halt. agent_key is one of the keys in budget-caps.json["agents"].
    """
    cfg = json.loads(BUDGET_CAPS.read_text())
    agents = cfg["agents"]
    if agent_key not in agents:
        return BudgetVerdict(
            decision="ok", cost_used_usd=cost_so_far_usd, cost_cap_usd=0,
            calls_used=calls_so_far, calls_cap=0,
            reason=f"unknown agent_key: {agent_key} — no cap applied",
        )

    a = agents[agent_key]
    cost_cap = float(a["budget_usd"])
    calls_cap = int(a["tool_call_cap"])
    warn_pct = float(a.get("warn_at_pct", 80))

    cost_pct = (cost_so_far_usd / cost_cap * 100) if cost_cap else 0
    calls_pct = (calls_so_far / calls_cap * 100) if calls_cap else 0
    worst = max(cost_pct, calls_pct)

    if worst >= 100:
        return BudgetVerdict(
            decision="halt",
            cost_used_usd=cost_so_far_usd, cost_cap_usd=cost_cap,
            calls_used=calls_so_far, calls_cap=calls_cap,
            halt_action=a["halt_action"],
            reason=f"budget exhausted ({worst:.0f}% of cap) — halt action: {a['halt_action']}",
        )
    if worst >= warn_pct:
        return BudgetVerdict(
            decision="warn",
            cost_used_usd=cost_so_far_usd, cost_cap_usd=cost_cap,
            calls_used=calls_so_far, calls_cap=calls_cap,
            reason=f"budget at {worst:.0f}% — slow down or finalise",
        )
    return BudgetVerdict(
        decision="ok",
        cost_used_usd=cost_so_far_usd, cost_cap_usd=cost_cap,
        calls_used=calls_so_far, calls_cap=calls_cap,
    )


def daily_fleet_cost_so_far_usd() -> float:
    """Sum cost_usd from today's runs across every agent."""
    total = 0.0
    today = _today()
    if not RUNS.exists():
        return 0.0
    for agent_dir in RUNS.iterdir():
        f = agent_dir / f"{today}.jsonl"
        if not f.exists():
            continue
        with f.open() as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    total += float(rec.get("cost_usd", 0) or 0)
                except (json.JSONDecodeError, ValueError):
                    continue
    return total


# ---------------------------------------------------------------------------
# Critic disagreement log
# ---------------------------------------------------------------------------

def record_critic_disagreement(
    job_id: str,
    agent: str,
    judge_score: float,
    amber_verdict: str,
    delta_summary: str,
) -> None:
    """The operator overrode a critic-passed output. Used by /weekly to detect critic rot."""
    _append_jsonl(DISAGREEMENT, {
        "ts": _now_iso(),
        "job_id": job_id,
        "agent": agent,
        "judge_score": judge_score,
        "amber_verdict": amber_verdict,  # "edited" | "rejected" | "approved-with-changes"
        "delta_summary": delta_summary,
    })


# ---------------------------------------------------------------------------
# Replay rendering
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def render_replay(job_id: str) -> Path:
    """Render a one-page HTML timeline for a single job_id. Pulls from handoffs,
    jobs, all agent run logs (today + previous 7d), and disagreement log.
    """
    REPLAYS.mkdir(parents=True, exist_ok=True)
    out_path = REPLAYS / f"{job_id}.html"

    handoffs = [h for h in _read_jsonl(HANDOFFS) if h.get("job_id") == job_id or job_id in (h.get("parent_job_id") or "")]
    job_states = [j for j in _read_jsonl(JOBS) if j.get("job_id") == job_id]
    disagreements = [d for d in _read_jsonl(DISAGREEMENT) if d.get("job_id") == job_id]

    runs: list[dict] = []
    if RUNS.exists():
        for agent_dir in RUNS.iterdir():
            for f in sorted(agent_dir.glob("*.jsonl")):
                for rec in _read_jsonl(f):
                    if rec.get("job_id") == job_id:
                        runs.append(rec)

    timeline = sorted(
        [{"kind": "handoff", **h} for h in handoffs]
        + [{"kind": "state", **j} for j in job_states]
        + [{"kind": "run", **r} for r in runs]
        + [{"kind": "disagreement", **d} for d in disagreements],
        key=lambda x: x.get("ts", ""),
    )

    rows = []
    for ev in timeline:
        ts = html.escape(ev.get("ts", ""))
        kind = html.escape(ev.get("kind", ""))
        agent = html.escape(ev.get("agent") or ev.get("to") or ev.get("from") or "")
        body = html.escape(json.dumps({k: v for k, v in ev.items() if k not in {"ts", "kind", "agent", "to", "from"}}, indent=2))
        rows.append(
            f'<tr class="kind-{kind}"><td class="ts">{ts}</td>'
            f'<td class="kind">{kind}</td>'
            f'<td class="agent">{agent}</td>'
            f'<td class="body"><pre>{body}</pre></td></tr>'
        )

    body_html = "\n".join(rows) if rows else "<tr><td colspan=4>no events found for this job_id</td></tr>"

    out_path.write_text(f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>replay {html.escape(job_id)}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2em; color: #111; }}
  h1 {{ font-size: 16px; font-weight: 500; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
  td {{ vertical-align: top; padding: 4px 8px; border-bottom: 1px solid #eee; }}
  td.ts {{ font-family: ui-monospace, monospace; white-space: nowrap; color: #666; }}
  td.kind {{ font-family: ui-monospace, monospace; }}
  tr.kind-handoff {{ background: #f7f9ff; }}
  tr.kind-state {{ background: #fff; }}
  tr.kind-run {{ background: #f7fff7; }}
  tr.kind-disagreement {{ background: #fff7f7; }}
  pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow: auto; }}
</style>
</head><body>
<h1>job_id: {html.escape(job_id)}</h1>
<p>{len(timeline)} events</p>
<table>
  <thead><tr><th>ts</th><th>kind</th><th>agent</th><th>body</th></tr></thead>
  <tbody>
{body_html}
  </tbody>
</table>
</body></html>
""")
    return out_path


# ---------------------------------------------------------------------------
# job_id helper
# ---------------------------------------------------------------------------

def new_job_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# CLI for quick verification
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: agent_runtime.py {budget|fleet|replay|smoke|lock|unlock|jobid|record|handoff} ...",
              file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "budget":
        # budget <agent_key> <cost_so_far> <calls_so_far>
        v = check_budget(sys.argv[2], float(sys.argv[3]), int(sys.argv[4]))
        print(json.dumps({
            "decision": v.decision,
            "cost_used_usd": v.cost_used_usd,
            "cost_cap_usd": v.cost_cap_usd,
            "calls_used": v.calls_used,
            "calls_cap": v.calls_cap,
            "halt_action": v.halt_action,
            "reason": v.reason,
        }, indent=2))
    elif cmd == "fleet":
        print(json.dumps({"daily_fleet_cost_so_far_usd": daily_fleet_cost_so_far_usd()}, indent=2))
    elif cmd == "replay":
        path = render_replay(sys.argv[2])
        print(f"wrote {path}")
    elif cmd == "smoke":
        # Minimal end-to-end self-test: log a handoff, record a run, check budget,
        # render replay. No network. Used by Phase 0 verification.
        jid = new_job_id()
        log_handoff({
            "job_id": jid, "from": "amber", "to": "ora", "reason": "smoke test",
            "north_star_score": 5, "tier": 1, "deliverable_schema": "smoke",
            "context": {"hello": "world"},
            "confidence_basis": "self-test",
            "next_best_action": "verify replay renders",
        })
        log_job_state(jid, "RUNNING", "ora", "smoke")
        record_run("ora", jid, {"cost_usd": 0.001, "tokens_in": 100, "tokens_out": 50, "outcome": "success"})
        log_job_state(jid, "SUCCEEDED", "ora", "smoke complete")
        v = check_budget("ora", 0.001, 1)
        path = render_replay(jid)
        print(json.dumps({
            "job_id": jid,
            "budget": v.decision,
            "replay_path": str(path),
        }, indent=2))
    elif cmd == "lock":
        # lock <job_id> <resource_key> [<resource_key> ...] [--ttl <min>]
        # All-or-nothing acquire. Prints "acquired" (exit 0) or
        # "busy:<comma-separated keys held by other jobs>" (exit 3).
        if len(sys.argv) < 4:
            print("usage: agent_runtime.py lock <job_id> <resource_key> [...] [--ttl <min>]", file=sys.stderr)
            sys.exit(1)
        args = sys.argv[2:]
        ttl = LOCK_DEFAULT_TTL_MIN
        if "--ttl" in args:
            i = args.index("--ttl")
            ttl = int(args[i + 1])
            args = args[:i] + args[i + 2:]
        job_id, keys = args[0], args[1:]
        status, busy = acquire_lock(job_id, keys, ttl_min=ttl)
        if status == "acquired":
            print("acquired")
            sys.exit(0)
        print("busy:" + ",".join(busy))
        sys.exit(3)
    elif cmd == "jobid":
        # jobid <agent> -- a readable job id, e.g. flowsmith-20260927-1412-a3f9
        agent = sys.argv[2] if len(sys.argv) > 2 else "job"
        print(f"{agent}-{datetime.now().strftime('%Y%m%d-%H%M')}-{uuid.uuid4().hex[:4]}")
    elif cmd == "record":
        # record <agent> <job_id> key=value [key=value ...]
        # Values are typed: true/false, null, integers, floats, JSON lists/objects.
        # RUN_SCHEMA agents' records are validated; exit 2 names what to fix.
        if len(sys.argv) < 4:
            print("usage: agent_runtime.py record <agent> <job_id> key=value ...", file=sys.stderr)
            sys.exit(1)
        agent, job_id = sys.argv[2], sys.argv[3]
        trace = {}
        for pair in sys.argv[4:]:
            if "=" not in pair:
                print(f"not key=value: {pair}", file=sys.stderr)
                sys.exit(1)
            k, v = pair.split("=", 1)
            trace[k.strip()] = _coerce(v)
        if trace.get("truth_status") == "auto":
            print("not recorded:\n  truth_status=auto is reserved for the SubagentStop hook", file=sys.stderr)
            sys.exit(2)
        try:
            record_run(agent, job_id, trace)
        except ValueError as e:
            print(f"not recorded:\n  {e}", file=sys.stderr)
            sys.exit(2)
        print(f"recorded {agent} {job_id}")
    elif cmd == "handoff":
        # handoff <packet.json> -- validate against handoff-packet-schema.json, then log it to
        # agent-handoffs.jsonl. Exit 2 names every problem and logs nothing.
        if len(sys.argv) < 3:
            print("usage: agent_runtime.py handoff <packet.json>", file=sys.stderr)
            sys.exit(1)
        try:
            packet = json.loads(Path(sys.argv[2]).expanduser().read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"not logged:\n  {e}", file=sys.stderr)
            sys.exit(2)
        try:
            errs = validate_packet(packet)
        except ImportError:  # moved HOME, /usr/bin/python3 or the public flowsmith install
            print("not logged:\n  jsonschema is not installed (python3 -m pip install --user jsonschema)",
                  file=sys.stderr)
            sys.exit(2)
        if errs:
            print("not logged:\n  " + "\n  ".join(errs), file=sys.stderr)
            sys.exit(2)
        log_handoff(packet)
        print(f"logged {packet['job_id']} {packet['from']} to {packet['to']}")
    elif cmd == "unlock":
        # unlock <job_id> -- release every lock held by this job.
        if len(sys.argv) < 3:
            print("usage: agent_runtime.py unlock <job_id>", file=sys.stderr)
            sys.exit(1)
        n = release_lock(sys.argv[2])
        print(f"released:{n}")
        sys.exit(0)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
