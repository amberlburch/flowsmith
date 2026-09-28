#!/usr/bin/env python3
"""Mechanical telemetry for fleet-agent dispatches, read from the subagent transcript.

Run records say what an agent believed it did. This says what it did: whether the
start-of-task brief and the handoff report were actually emitted, how many writes
and publishes landed, what the dispatch consumed in tokens and active minutes, and
which known failure classes fired. It exists because the 2026-09-27 audit found
flowsmith's gates in under 10% of 126 dispatches while every wiring check scored 10/10.

Rows go to state/agent-telemetry/<agent>/<date>.jsonl, one per dispatch, keyed by the
subagent's agent_id and filed under its last activity date. A resumed dispatch fires
SubagentStop again on the same transcript, so the row is replaced, never skipped.
Separate from state/agent-runs so self-reported KPIs and observed behaviour never mix.

Effort is reported in tokens and active minutes, never converted to dollars until
verified per-model prices, including cache rates, exist.

The gates are file evidence, as flowsmith SYSTEM.md defines them: brief_emitted and
handoff_emitted need brief.md / handoff.md written under ~/.claude/_scratch and a
passing ledger_lint (a lite brief file needs its three fields and no lint). The heading
markers stay as brief_text, lite_brief and handoff_text for trend continuity only.

Gate fires (denies and blocks) come from lib/agent_gates.py's log, state/agent-gates/
gate-events.jsonl, and are counted per agent in the summary; main-session fires count
under flowsmith-inline.

Usage:
  python3 lib/agent_telemetry.py hook                  # SubagentStop payload on stdin; silent
  python3 lib/agent_telemetry.py backfill              # recompute every historical transcript
  python3 lib/agent_telemetry.py backfill --inline     # main sessions with Webflow writes, as flowsmith-inline
  python3 lib/agent_telemetry.py summary [--agent A] [--days N] [--json]
"""

import argparse
import contextlib
import fcntl
import json
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path.home() / ".claude"
OUT = ROOT / "state" / "agent-telemetry"
PROJECTS = ROOT / "projects"
GATE_EVENTS = ROOT / "state" / "agent-gates" / "gate-events.jsonl"
INLINE = "flowsmith-inline"  # Webflow work done in a main session (F31b)
WIND_DOWN = 150  # flowsmith's cap warning (200 calls, warn at 75%): past it a run sets next_wave

WEBFLOW = "mcp__plugin_webflow-skills_webflow__"
WRITE_VERB = re.compile(r"^(create|update|set|remove|delete|add|bulk|register|publish|rename|"
                        r"clear|merge|upload|compress|apply|insert|move|duplicate)")
BUILDER_TOOLS = {"data_whtml_builder", "data_element_builder", "data_component_builder"}
TEST_CMD = re.compile(r"\b(pytest|vitest|jest|playwright test|npm (run )?test|pnpm (run )?test|"
                      r"yarn test|bun test|go test|cargo test|python3? -m (pytest|unittest))\b")

# Text markers tolerate markdown decoration (bold, headings, numbering) but stay anchored
# at line start, so a sentence that merely mentions "the BUILD PLAN" does not count.
FIELD = r"^[ \t>*#\d.-]{0,6}%s(?:\*\*)?:"
PLAN_START = re.compile(FIELD % "GOAL" + r"|^(?:#{1,4}[ \t]*|\*\*)BUILD PLAN\b", re.M)
VERIFY_FIELD = re.compile(FIELD % "VERIFICATION", re.M)
LITE = re.compile(r"LESSONS IN PLAY", re.I)
HANDOFF_HEAD = re.compile(r"^(?:#{2,4}[ \t]*|\*\*)Self-critique results|^#{1,4}[ \t]*HANDOFF REPORT\b", re.M)

# File evidence (flowsmith SYSTEM.md): brief.md and handoff.md in the job's scratch folder,
# linted by ledger_lint.py --plan / --handoff. A lite brief file needs no lint, so it must
# carry the three lite fields and none of the full plan's: a failing full plan that merely
# mentions "LEDGER LESSONS IN PLAY" is not a lite brief.
LITE_FIELDS = [re.compile(FIELD % f, re.M | re.I) for f in ("LESSONS IN PLAY", "ACCEPTANCE", "VERIFICATION")]
FULL_FIELD = re.compile(FIELD % "(?:GOAL|STRUCTURE|RISKS|DESIGN COVERAGE)", re.M | re.I)
SCRATCH_DOC = re.compile(r"/\.claude/_scratch/\S+/(brief|handoff)\.md$")
LINT_ARG = re.compile(r"--(plan|handoff)[ =]+['\"]?([^\s'\";|&]+)")
LINT_DOC = {"plan": "brief.md", "handoff": "handoff.md"}
LINT_PASS = re.compile(r"pass_rate ([\d.]+)%")
RECORDED = re.compile(r"(?m)^recorded (\S+) (\S+)\s*$")  # the record CLI's success line
PY_RECORD = re.compile(r"(?:import agent_runtime|from agent_runtime import)[\s\S]*record_run\(")

RATE_LIMIT = re.compile(r"\b429\b|Too Many Requests|too_many_requests")
OVERSIZE = ("exceeds maximum allowed tokens", "<persisted-output>")
USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
TOKEN_FIELDS = ("tokens_in", "tokens_out", "cache_read", "cache_write")
FAMILIES = ("webflow", "chrome", "bash", "read", "edit", "other")
IDLE_GAP_S = 600  # a longer gap is the parent pausing the dispatch, not the agent working


def _records(transcript: Path):
    with transcript.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("message"), dict):
                yield rec


def _content(msg: dict) -> list:
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


def _result_text(block) -> str:
    c = block.get("content")
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    return str(c or "")


def _family(name: str) -> str:
    if name.startswith(WEBFLOW):
        return "webflow"
    if name.startswith("mcp__chrome-devtools__"):
        return "chrome"
    if name == "Bash":
        return "bash"
    if name in ("Read", "Grep", "Glob"):
        return "read"
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return "edit"
    return "other"


def _epoch(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _is_error(d: dict) -> bool:
    return (bool(d.get("error")) or d.get("status") in ("error", False)
            or (d.get("name") == "Error" and ("message" in d or "error" in d)))


def _child_errors(e: dict) -> list[str]:
    out = []
    for c in e.get("child_results") or []:
        if isinstance(c, dict):
            out += ([json.dumps(c)] if c.get("status") == "error" else []) + _child_errors(c)
    return out


def _webflow_outcomes(tool: str, block) -> list[tuple[str, bool, str]]:
    """(action, ok, error text) per action inside a Webflow result that is not is_error.

    Shapes seen in flowsmith and webflow-fix transcripts to 2026-09-28: an entry with a
    truthy "error", status "error" or false (Designer closed), or name "Error" (an empty
    error dict on get_asset_preview); a "result" dict with the same markers (get_styles
    status "error", add_site_script 404 as name "Error"); a "result" list entry with
    status "error". A builder's failed child_results (nested) count as errors but leave
    the parent write credited; "partial_success" alone is only warnings. Unparseable
    content (oversize or plain text) yields nothing, so the attempted count stands."""
    c = block.get("content")
    items = [x.get("text", "") for x in c if isinstance(x, dict)] if isinstance(c, list) else [str(c or "")]
    out = []
    for item in items:
        try:
            parsed = json.loads(item)
        except (json.JSONDecodeError, TypeError):
            continue
        for e in parsed if isinstance(parsed, list) else [parsed]:
            if not isinstance(e, dict):
                continue
            res = e.get("result")
            failed = (_is_error(e) or (isinstance(res, dict) and _is_error(res))
                      or (isinstance(res, list)
                          and any(isinstance(x, dict) and x.get("status") == "error" for x in res)))
            action = str(e.get("action") or (tool if "build_label" in e else ""))
            out.append((action, not failed, json.dumps(e) if failed else ""))
            out += [(action, False, child) for child in _child_errors(e)]
    return out


def extract(transcript: Path, agent: str, agent_id: str = "") -> dict:
    row = {"agent": agent, "agent_id": agent_id or transcript.stem.removeprefix("agent-"),
           "transcript": str(transcript), "ts": "", "last_ts": "", "model": None, "tool_calls": 0,
           "active_minutes": 0.0, **dict.fromkeys(TOKEN_FIELDS, 0),
           "brief_emitted": False, "brief_file": False, "brief_text": False, "lite_brief": False,
           "handoff_emitted": False, "handoff_file": False, "handoff_text": False,
           "verification_section": False, "design_review_emitted": False,
           "skill_calls": 0, "agent_spawns": 0, "webflow_writes": 0, "publishes": 0,
           "webflow_action_errors": 0, "rate_limited": 0,
           "lock_used": False, "next_wave_set": False, "record_written": False, "record_job_ids": [],
           "spec_written": False,
           "code_writes": 0, "tests_run": 0, "errors_total": 0, "schema_errors": 0,
           "chrome_connect_errors": 0, "artefact_path_denied": 0, "page_closed_errors": 0,
           "oversize_results": 0}
    families = dict.fromkeys(FAMILIES, 0)
    authored = []  # assistant text plus content the agent wrote to files
    docs = {"brief": "", "handoff": ""}
    linted, stamps, usage, names, pending = set(), [], {}, {}, {}
    for rec in _records(transcript):
        msg = rec["message"]
        role = msg.get("role", "")
        if rec.get("timestamp"):
            stamps.append(rec["timestamp"])
        if msg.get("model") and msg["model"] != "<synthetic>":
            row["model"] = msg["model"]
        # Streamed messages repeat one id with growing output_tokens: keep the max per id.
        # Keeping the first entry undercounted output 3.3 times (F6, 2026-09-27 audit).
        if role == "assistant" and isinstance(msg.get("usage"), dict):
            cur = usage.setdefault(msg.get("id") or rec.get("uuid") or len(usage), [0] * len(USAGE))
            for i, f in enumerate(USAGE):
                cur[i] = max(cur[i], int(msg["usage"].get(f) or 0))
        for b in _content(msg):
            kind = b.get("type")
            if kind == "text" and role == "assistant":
                authored.append(b.get("text", ""))
            elif kind == "tool_use":
                row["tool_calls"] += 1
                name, inp, tid = b.get("name", ""), b.get("input") or {}, b.get("id")
                if not isinstance(inp, dict):
                    inp = {}
                names[tid] = name
                families[_family(name)] += 1
                if name == "SubagentHandback":  # the final report can arrive as a tool call
                    authored.append(str(inp.get("message", "")))
                elif name == "Skill":
                    row["skill_calls"] += 1
                elif name == "Agent":
                    row["agent_spawns"] += 1
                elif name in ("Write", "Edit"):
                    body = str(inp.get("content", "")) + str(inp.get("new_string", ""))
                    authored.append(body)
                    path = str(inp.get("file_path", ""))
                    if m := SCRATCH_DOC.search(path):
                        docs[m.group(1)] += body + "\n"
                    if "/specs/" in path:  # packet.json lands there first; the spec is the gate
                        row["spec_written"] |= path.rsplit("/", 1)[-1] in ("spec.md", "proposal.md")
                    elif re.search(r"\.(ts|tsx|js|jsx|py|go|rs|css|html|json|sql)$", path):
                        row["code_writes"] += 1
                elif name == "Bash":
                    cmd = str(inp.get("command", ""))
                    if "agent_runtime.py lock" in cmd:
                        row["lock_used"] = True
                    if "flowsmith_manifest.py" in cmd and "next_wave" in cmd:
                        row["next_wave_set"] = True
                    if TEST_CMD.search(cmd):
                        row["tests_run"] += 1
                    lints = [k for k, p in LINT_ARG.findall(cmd)
                             if "ledger_lint" in cmd and p.rsplit("/", 1)[-1] == LINT_DOC[k]]
                    pending[tid] = ("bash", lints, bool(PY_RECORD.search(cmd)))
                elif name.startswith(WEBFLOW):
                    tool = name[len(WEBFLOW):]
                    keys = [k for a in (inp.get("actions") or []) if isinstance(a, dict)
                            for k in a if k != "label"]
                    wrote = tool in BUILDER_TOOLS or any(WRITE_VERB.match(k) for k in keys)
                    pubs = sum(1 for k in keys if "publish" in k)
                    row["webflow_writes"] += int(wrote)
                    row["publishes"] += pubs
                    pending[tid] = ("webflow", tool, wrote, pubs)
            elif kind == "tool_result":
                tid, txt, err = b.get("tool_use_id"), _result_text(b), bool(b.get("is_error"))
                if err:
                    row["errors_total"] += 1
                    if "InputValidationError" in txt or "-32602" in txt:
                        row["schema_errors"] += 1
                    if "Could not connect to Chrome" in txt:
                        row["chrome_connect_errors"] += 1
                    if "Access denied" in txt and "workspace roots" in txt:
                        row["artefact_path_denied"] += 1
                    if "selected page has been closed" in txt:
                        row["page_closed_errors"] += 1
                mcp = names.get(tid, "").startswith("mcp__")
                if err and mcp and RATE_LIMIT.search(txt):  # a Bash traceback "line 429" is not a 429
                    row["rate_limited"] += 1
                if mcp and any(s in txt for s in OVERSIZE):
                    row["oversize_results"] += 1
                p = pending.pop(tid, None)
                if p and p[0] == "bash":
                    _, lints, py_record = p
                    rates = LINT_PASS.findall(txt)
                    if lints and rates and all(float(r) == 100.0 for r in rates):
                        linted.update(lints)
                    ids = [j for _, j in RECORDED.findall(txt)]
                    row["record_job_ids"] += ids
                    if ids or (py_record and not err and "Traceback" not in txt):
                        row["record_written"] = True
                elif p and p[0] == "webflow":
                    # Count only writes and publishes that landed (F39): undo the attempt
                    # when the call errored or every write inside it failed.
                    _, tool, wrote, pubs = p
                    outcomes = [] if err else _webflow_outcomes(tool, b)
                    if err or outcomes:
                        failed = [e for a, ok, e in outcomes if not ok]
                        row["webflow_action_errors"] += len(failed)
                        row["rate_limited"] += sum(1 for e in failed if RATE_LIMIT.search(e))
                        ok_write = any(ok and (tool in BUILDER_TOOLS or WRITE_VERB.match(a))
                                       for a, ok, _ in outcomes)
                        ok_pubs = sum(1 for a, ok, _ in outcomes if ok and "publish" in a)
                        if wrote and not ok_write:
                            row["webflow_writes"] -= 1
                        row["publishes"] -= max(0, pubs - ok_pubs)
    row["calls_by_family"] = families
    for i, f in enumerate(TOKEN_FIELDS):
        row[f] = sum(u[i] for u in usage.values())
    if stamps:
        row["ts"], row["last_ts"] = min(stamps), max(stamps)
        secs = sorted(s for s in map(_epoch, stamps) if s is not None)
        row["active_minutes"] = round(sum(g for g in (b - a for a, b in zip(secs, secs[1:]))
                                          if g < IDLE_GAP_S) / 60, 1)
    text = "\n".join(authored)
    row["brief_text"] = bool(PLAN_START.search(text) and VERIFY_FIELD.search(text))
    row["lite_brief"] = bool(LITE.search(text) and VERIFY_FIELD.search(text))
    brief = docs["brief"]
    row["brief_file"] = bool(brief)
    lite_file = all(p.search(brief) for p in LITE_FIELDS) and not FULL_FIELD.search(brief)
    row["brief_emitted"] = row["brief_file"] and ("plan" in linted or lite_file)
    row["handoff_text"] = bool(HANDOFF_HEAD.search(text))
    row["handoff_file"] = bool(docs["handoff"])
    row["handoff_emitted"] = row["handoff_file"] and "handoff" in linted
    row["verification_section"] = bool(re.search(r"^## Verification", text, re.M))
    row["design_review_emitted"] = "## Design review:" in text
    return row


@contextlib.contextmanager
def _locked():
    """The hook runs in the background, so two stops can upsert at once."""
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / ".lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def write(row: dict) -> None:
    """Upsert by agent_id, filed under the last activity date."""
    day = (row.get("last_ts") or row.get("ts") or datetime.now(timezone.utc).isoformat())[:10]
    d = OUT / row["agent"]
    marker = f'"agent_id": {json.dumps(row["agent_id"])}'
    with _locked():
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*.jsonl"):
            text = f.read_text(encoding="utf-8")
            if marker not in text:
                continue
            keep = [ln for ln in text.splitlines() if marker not in ln]
            if keep:
                f.write_text("\n".join(keep) + "\n", encoding="utf-8")
            else:
                f.unlink()
        with (d / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")


def hook() -> int:
    """SubagentStop entry point. Never prints, never raises: a hook that talks re-wakes the model."""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        agent = payload.get("agent_type") or payload.get("subagent_type") or ""
        tp = payload.get("agent_transcript_path") or ""
        if agent and tp and Path(tp).is_file():
            write(extract(Path(tp), agent, payload.get("agent_id") or ""))
    except Exception:
        pass
    return 0


def _calls_webflow(path: Path) -> bool:
    """Cheap pre-scan: main transcripts run to hundreds of MB and most never call Webflow."""
    call, tail = re.compile(rb'"name": ?"' + re.escape(WEBFLOW.encode())), b""
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 23):
            if call.search(tail + chunk):
                return True
            tail = chunk[-64:]
    return False


def backfill(inline: bool = False) -> int:
    """Recompute every fleet transcript, so a change to extract() reaches history. With
    inline, read main-session transcripts instead and write a flowsmith-inline row for each
    session with a landed Webflow write (F31b)."""
    n = 0
    if inline:
        for tp in PROJECTS.glob("*/*.jsonl"):
            if _calls_webflow(tp):
                row = extract(tp, INLINE, tp.stem)
                if row["webflow_writes"]:
                    write(row)
                    n += 1
        print(f"backfilled {n} main session(s) as {INLINE}")
        return 0
    for meta in PROJECTS.glob("*/*/subagents/*.meta.json"):
        try:
            agent = json.loads(meta.read_text(encoding="utf-8")).get("agentType", "")
        except (json.JSONDecodeError, OSError):
            continue
        if agent not in ("flowsmith", "wright", "webflow-fix", "build"):
            continue
        tp = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
        if tp.is_file():
            write(extract(tp, agent, tp.stem.removeprefix("agent-")))
            n += 1
    print(f"backfilled {n} dispatch(es)")
    return 0


def load(agent: str, days: int | None = None) -> list[dict]:
    rows, d = [], OUT / agent
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()[:10] if days else ""
    if d.is_dir():
        for f in sorted(d.glob("*.jsonl")):
            if cutoff and f.stem < cutoff:
                continue
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def gate_events(agent: str, days: int | None = None) -> dict:
    """{gate: fires} from agent_gates.py's log for this agent. Main-session fires count as inline
    only when they came from the Webflow modes (a pre-github deny there is not Webflow work)."""
    who = "main" if agent == INLINE else agent
    modes = ("pre-webflow", "post-webflow") if agent == INLINE else None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()[:10] if days else ""
    out = {}
    try:
        lines = GATE_EVENTS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (isinstance(e, dict) and e.get("event") in ("deny", "block") and e.get("agent") == who
                and (modes is None or e.get("mode") in modes) and str(e.get("ts", ""))[:10] >= cutoff):
            out[e.get("gate") or "?"] = out.get(e.get("gate") or "?", 0) + 1
    return dict(sorted(out.items()))


def summary(agent: str, days: int | None = None) -> dict:
    rows = load(agent, days)

    def rate(num, den):
        return round(num / den, 3) if den else None

    def total(key):
        return sum(r.get(key, 0) for r in rows)

    def median(key):
        return statistics.median(r.get(key, 0) for r in rows) if rows else None

    if agent == "wright":
        # Gate in = a spec before code; gate out = a named verification section.
        coded = [r for r in rows if r["code_writes"]]
        brief_rate = rate(sum(r["spec_written"] for r in coded), len(coded))
        handoff_pool = coded
        handoff_rate = rate(sum(r["verification_section"] for r in coded), len(coded))
        brief_text_rate = handoff_text_rate = None
    else:
        # The gate is the file evidence; the text markers are trend only (F37).
        sized = [r for r in rows if r["tool_calls"] > 8]
        brief_rate = rate(sum(r["brief_emitted"] for r in sized), len(sized))
        brief_text_rate = rate(sum(r["brief_text"] or r["lite_brief"] for r in sized), len(sized))
        handoff_pool = [r for r in rows if r["webflow_writes"]]
        handoff_rate = rate(sum(r["handoff_emitted"] for r in handoff_pool), len(handoff_pool))
        handoff_text_rate = rate(sum(r["handoff_text"] for r in handoff_pool), len(handoff_pool))
    return {
        "dispatches": len(rows),
        "brief_rate": brief_rate,
        "brief_text_rate": brief_text_rate,
        "handoff_rate": handoff_rate,
        "handoff_text_rate": handoff_text_rate,
        "gate_pool": len(handoff_pool),
        "record_rate": rate(sum(r.get("record_written", False) for r in rows), len(rows)),
        "median_tool_calls": median("tool_calls"),
        "active_hours": round(total("active_minutes") / 60, 1),
        "median_active_minutes": median("active_minutes"),
        "tokens": {f: total(f) for f in TOKEN_FIELDS},
        "median_tokens_out": median("tokens_out"),
        "median_cache_read": median("cache_read"),
        "calls_by_family": {k: sum(r.get("calls_by_family", {}).get(k, 0) for r in rows) for k in FAMILIES},
        "chrome_connect_errors": total("chrome_connect_errors"),
        "artefact_path_denied": total("artefact_path_denied"),
        "schema_errors": total("schema_errors"),
        "webflow_action_errors": total("webflow_action_errors"),
        "rate_limited": total("rate_limited"),
        "page_closed_errors": total("page_closed_errors"),
        "oversize_results": total("oversize_results"),
        "unlocked_publishes": sum(1 for r in rows if r.get("publishes") and not r.get("lock_used")),
        # Only flowsmith has the 150-call wind-down and a manifest to hold next_wave.
        "long_without_next_wave": (sum(
            1 for r in rows if r.get("tool_calls", 0) > WIND_DOWN and not r.get("next_wave_set"))
            if agent in ("flowsmith", INLINE) else None),
        "gate_events": gate_events(agent, days),
    }


def human(n) -> str:
    """4120000000 -> 4.12B. Token counts only."""
    if n is None:
        return "no data"
    for size, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= size:
            return f"{n / size:.3g}{unit}"
    return str(n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["hook", "backfill", "summary"])
    ap.add_argument("--agent", default=None)
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--inline", action="store_true", help=f"backfill main sessions as {INLINE}")
    a = ap.parse_args()
    if a.cmd == "hook":
        return hook()
    if a.cmd == "backfill":
        return backfill(a.inline)
    agents = [a.agent] if a.agent else sorted(p.name for p in OUT.iterdir() if p.is_dir()) if OUT.is_dir() else []
    out = {ag: summary(ag, a.days) for ag in agents}
    if a.json:
        print(json.dumps(out, indent=2))
        return 0

    def pct(v):
        return "no data" if v is None else f"{v * 100:.0f}%"

    for ag, s in out.items():
        if not s["dispatches"]:
            print(f"{ag}: 0 dispatch(es)")
            continue
        t, c = s["tokens"], s["calls_by_family"]
        print(f"{ag}: {s['dispatches']} dispatch(es), brief {pct(s['brief_rate'])} (text {pct(s['brief_text_rate'])}), "
              f"handoff {pct(s['handoff_rate'])} of {s['gate_pool']} (text {pct(s['handoff_text_rate'])}), "
              f"record {pct(s['record_rate'])}, median calls {s['median_tool_calls']:g}")
        print(f"  effort: {s['active_hours']} active h (median {s['median_active_minutes']} min); tokens out "
              f"{human(t['tokens_out'])} (median {human(s['median_tokens_out'])}), cache read "
              f"{human(t['cache_read'])} (median {human(s['median_cache_read'])}), cache write "
              f"{human(t['cache_write'])}, uncached in {human(t['tokens_in'])}")
        print("  calls: " + ", ".join(f"{k} {c[k]}" for k in FAMILIES))
        print(f"  failures: chrome-down {s['chrome_connect_errors']}, path-denied {s['artefact_path_denied']}, "
              f"schema {s['schema_errors']}, webflow hidden errors {s['webflow_action_errors']}, "
              f"rate-limited {s['rate_limited']}, page-closed {s['page_closed_errors']}, "
              f"oversize {s['oversize_results']}, published without lock {s['unlocked_publishes']}"
              + (f", over {WIND_DOWN} calls without next_wave {s['long_without_next_wave']}"
                 if s["long_without_next_wave"] is not None else ""))
        fired = s["gate_events"]
        print("  gates fired: " + (", ".join(f"{g} {n}" for g, n in fired.items()) if fired else "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
