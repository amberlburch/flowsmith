#!/usr/bin/env python3
"""Mechanical agent scorecard for the fleet improvement loop.

Scores wright and flowsmith 0-10 from checkable evidence only (files, run
records, hook registration). No LLM judgement. This file IS the rating; the
2026-08-17 hand ratings (flowsmith 8, wright 6) are its calibration anchors.

Usage:
  python3 lib/agent_scorecard.py            # both agents, dimension detail
  python3 lib/agent_scorecard.py --agent wright
  python3 lib/agent_scorecard.py --json
  python3 lib/agent_scorecard.py --min      # prints the lower score (loop metric)
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path.home() / ".claude"
CLAUDE_JSON = Path.home() / ".claude.json"
MCP_JSON = Path.home() / ".mcp.json"  # project-scope servers for sessions rooted at home
RUNS = ROOT / "state" / "agent-runs"
RECENT_DAYS = 14

# Connector-layer servers with stable names that are not in ~/.claude.json
CONNECTOR_ALLOW = {"scheduled-tasks", "claude-in-chrome"}
# claude.ai connectors surface as UUID-named servers (e.g. the Exa connector). They
# cannot be verified from disk, so a UUID segment is accepted rather than called dead.
CONNECTOR_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# Built-in skills that exist without a skills/<name>/ folder.
BUILTIN_SKILLS = {"code-review", "simplify", "loop", "schedule", "init", "security-review", "run"}
# Skills with a step that fans out to sub-agents. An agent without the Agent tool must say in
# its prompt, on a line naming the skill, that the step runs inline (wright rule 10, F27).
NEEDS_AGENT = {"agent-review": "three judge sub-agents", "security-review": "parallel finder sub-tasks",
               "writing-plans": "a plan-reviewer sub-agent"}
# Hook registrations that enforce each agent's gates (lib/agent_gates.py via hooks/agent-gates.sh):
# settings.json for Webflow publishes and grants, the agent's frontmatter for brief, handoff, cap
# and spec. subagent-stop.sh writes the run record every dispatch is scored from.
ENFORCEMENT = {
    "flowsmith": [("subagent-stop.sh", ""), ("agent-gates.sh", "pre-webflow"), ("agent-gates.sh", "post-webflow"),
                  ("agent-gates.sh", "pre-grant"), ("agent-gates.sh", "pre-agent flowsmith"),
                  ("agent-gates.sh", "stop-agent flowsmith")],
    "wright": [("subagent-stop.sh", ""), ("agent-gates.sh", "pre-agent wright"),
               ("agent-gates.sh", "stop-agent wright")],
}
ESCALATION_WINDOW_DAYS = 30

AGENTS = {
    "wright": {
        "kpi_fields": ["first_pass_approved", "design_review_rounds"],
        "round_field": "design_review_rounds",
        "round_cap": 5,
        "artifacts": [
            ROOT / "reference" / "common" / "spec-template",
            ROOT / "agents" / "shared" / "budget-caps.json",
        ],
    },
    "flowsmith": {
        "kpi_fields": ["handoff_accepted", "revision_items"],
        "round_field": "verify_rounds",
        "round_cap": 3,
        "artifacts": [
            ROOT / "agents" / "flowsmith" / "dod.md",
            ROOT / "agents" / "flowsmith" / "runbooks.md",
        ],
    },
}

# dimension -> weight (sums to 10.0). gates_run added 2026-09-27: every wiring
# dimension scored 10 while flowsmith emitted its brief in 3% of dispatches, so
# observed gate behaviour now carries weight taken from ledger_alive/gates_defined.
WEIGHTS = {
    "spec_integrity": 2.0,
    "grants_valid": 1.0,
    "ledger_alive": 1.0,
    "gates_defined": 1.0,
    "gates_run": 1.0,
    "records_recent": 1.0,
    "kpi_measured": 1.0,
    "escalation_integrity": 0.5,
    "eval_fresh": 0.5,
    "enforcement_wired": 0.5,
    "newtool_exercised": 0.5,
}


def frontmatter(agent):
    text = (ROOT / "agents" / agent / "SYSTEM.md").read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, text
    try:
        import yaml
        return yaml.safe_load(text.split("---")[1]), text
    except Exception:
        return None, text


def records(agent):
    out = []
    d = RUNS / agent
    if d.is_dir():
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return out


def registered_servers():
    names = set()
    try:
        cfg = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
        names |= set(cfg.get("mcpServers", {}))
        for proj in cfg.get("projects", {}).values():
            names |= set(proj.get("mcpServers", {}))
    except Exception:
        pass
    try:
        names |= set(json.loads(MCP_JSON.read_text(encoding="utf-8")).get("mcpServers", {}))
    except Exception:
        pass
    return names


def eval_cases(agent):
    d = ROOT / "agents" / agent / "eval"
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.md"))


def _installed_plugins():
    try:
        d = json.loads((ROOT / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        return {k.split("@")[0] for k in d.get("plugins", d)}
    except Exception:
        return set()


def _enabled_plugins():
    try:
        s = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))
        return {k.split("@")[0] for k, v in s.get("enabledPlugins", {}).items() if v}
    except Exception:
        return set()


def wiring_problems(fm, body):
    """What the prompt depends on but the agent cannot reach. Each of these was a live
    bug on 2026-09-27: skills named but Skill not granted, superpowers:* named while the
    plugin was disabled, an archived skill named, n8n-corient named but not granted."""
    tools = [str(x) for x in fm.get("tools", [])]
    text = body.split("---", 2)[-1]
    probs = []
    # A slash command stands alone: after whitespace, a backtick or "(", never mid-path.
    slash = set(re.findall(r"(?:(?<=\s)|(?<=[`(]))/([a-z][a-z0-9-]+)(?=[`\s:,)]|\.\s)", text))
    if slash and "Skill" not in tools:
        probs.append("skills referenced but Skill not granted")
    slash = {n for n in slash if not Path("/" + n).exists()}  # `/tmp` is a path, not a skill
    for name in sorted(slash):
        if name in BUILTIN_SKILLS or (ROOT / "skills" / name / "SKILL.md").exists():
            continue
        probs.append(f"/{name} is not an installed skill")
    if "Agent" not in tools:
        for name in sorted((slash | set(fm.get("skills") or [])) & set(NEEDS_AGENT)):
            if not any(name in ln and "inline" in ln.lower() for ln in text.splitlines()):
                probs.append(f"/{name} needs the Agent tool ({NEEDS_AGENT[name]}), which is not granted: "
                             "say on a line naming it that the step runs inline")
    installed = _installed_plugins()
    for plugin in sorted(set(re.findall(r"`([a-z0-9-]+):[a-z0-9-]+`", text)) & installed):
        if plugin not in _enabled_plugins():
            probs.append(f"{plugin}: skills referenced but the plugin is not enabled")
    for server in registered_servers():
        named = f"`{server}`" in text or f"mcp__{server}__" in text
        if named and not any(g.startswith(f"mcp__{server}") for g in tools):
            probs.append(f"{server} named in the prompt but not granted")
    for raw in re.findall(r"`(~/[^`\s]+|(?:agents|skills|reference|lib|brand)/[^`\s]+)`", text):
        if any(c in raw for c in "[]<>*{}") or "NNN" in raw or "/state/" in raw:
            continue  # templates, and runtime outputs the agent writes rather than reads
        path = Path(raw.replace("~", str(Path.home()), 1)) if raw.startswith("~") else ROOT / raw
        if not path.exists():
            probs.append(f"missing path {raw}")
    return probs


def check_spec_integrity(agent, fm, body):
    if fm is None or not fm.get("tools"):
        return False, "frontmatter missing or unparseable"
    low = body.lower()
    needed = ["tier 3", "kpi", "never do", "when stuck"]
    missing = [s for s in needed if s not in low]
    if missing:
        return False, "missing sections: " + ", ".join(missing)
    probs = wiring_problems(fm, body)
    return (not probs), ("; ".join(probs) if probs else "ok")


def check_grants_valid(agent, fm, body):
    if fm is None:
        return False, "no frontmatter"
    servers = registered_servers()
    bad = []
    for t in fm.get("tools", []):
        if not str(t).startswith("mcp__"):
            continue
        seg = str(t).split("__")[1]
        if (seg in servers or seg in CONNECTOR_ALLOW or seg.startswith("plugin_")
                or CONNECTOR_UUID.match(seg)):
            continue
        bad.append(str(t))
    return (not bad), ("dead grants: " + ", ".join(bad) if bad else "ok")


def check_ledger_alive(agent, fm, body):
    p = ROOT / "agents" / agent / "learned-rules.md"
    if not p.exists():
        return False, "no learned-rules.md"
    text = p.read_text(encoding="utf-8")
    entries = re.findall(r"(?m)^(?:\d+[\.\s]+\[?[A-Z]|### L-\d+)", text)
    if len(entries) < 5:
        return False, f"only {len(entries)} substantive entries (need >= 5)"
    lint = ROOT / "skills" / "flowsmith-loop" / "scripts" / "ledger_lint.py"
    if agent == "flowsmith" and lint.exists():
        r = subprocess.run([sys.executable, str(lint), "--all"], capture_output=True, text=True)
        if r.returncode != 0:
            return False, "ledger_lint --all failed"
    return True, f"{len(entries)} entries"


def check_gates_defined(agent, fm, body):
    missing = [str(a) for a in AGENTS[agent]["artifacts"] if not a.exists()]
    if missing:
        return False, "missing: " + ", ".join(missing)
    if agent == "wright":
        caps = json.loads((ROOT / "agents" / "shared" / "budget-caps.json").read_text())
        if "wright" not in caps.get("agents", caps):
            return False, "no wright budget cap"
    return True, "ok"


def check_records_recent(agent, fm, body):
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
    for r in records(agent):
        try:
            ts = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
            if ts.tzinfo is None:  # hand-written records carried naive UTC stamps
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                return True, f"latest {r['ts'][:10]}"
        except (KeyError, ValueError):
            pass
    return False, f"no run record in last {RECENT_DAYS} days"


def check_kpi_measured(agent, fm, body):
    fields = AGENTS[agent]["kpi_fields"]
    for r in records(agent):
        if any(f in r for f in fields):
            return True, "kpi fields present"
    return False, f"no record carries {fields}"


def check_escalation_integrity(agent, fm, body):
    """Current behaviour, not archaeology: records older than the window were absorbed
    as flowsmith L-77, and the record CLI now refuses an over-cap record that is not
    marked escalated."""
    field, cap = AGENTS[agent]["round_field"], AGENTS[agent]["round_cap"]
    recs = records(agent)
    acked = {r.get("job_id") for r in recs if r.get("escalation_ack") or r.get("escalated")}
    over = [r for r in recs
            if isinstance(r.get(field), int) and r[field] > cap
            and not r.get("escalated") and r.get("job_id") not in acked]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ESCALATION_WINDOW_DAYS)).isoformat()[:10]
    bad = [r for r in over if str(r.get("ts", ""))[:10] >= cutoff]
    older = len(over) - len(bad)
    tail = f" ({older} older, absorbed as L-77)" if older else ""
    if bad:
        return False, f"{len(bad)} over-cap record(s) without escalation in {ESCALATION_WINDOW_DAYS} days{tail}"
    return True, "ok" + tail


def check_gates_run(agent, fm, body):
    """Observed, from transcripts (lib/agent_telemetry.py): did the entry gate and the
    exit gate actually happen, as the agent's SYSTEM.md defines them (for flowsmith, the
    scratch brief.md and handoff.md with a passing lint, not a heading in the reply)?
    Needs 3+ qualifying dispatches in 30 days to pass, and fails on any dispatch in that
    window that published without taking the publish lock (F19)."""
    sys.path.insert(0, str(ROOT / "lib"))
    from agent_telemetry import summary
    s = summary(agent, days=30)
    unlocked = s.get("unlocked_publishes") or 0
    flag = f"; {unlocked} dispatch(es) published without the publish lock" if unlocked else ""
    if s["gate_pool"] < 3:
        all_time = summary(agent)
        hist = ""
        if all_time["brief_rate"] is not None or all_time["handoff_rate"] is not None:
            hist = (f"; all-time brief {all_time['brief_rate']}, handoff {all_time['handoff_rate']} "
                    f"over {all_time['dispatches']} dispatch(es)")
        return False, f"{s['gate_pool']} qualifying dispatch(es) in 30 days, need 3{hist}{flag}"
    ok = (s["brief_rate"] or 0) >= 0.8 and (s["handoff_rate"] or 0) >= 0.8 and not unlocked
    return ok, f"brief {s['brief_rate']}, handoff {s['handoff_rate']} over {s['gate_pool']} dispatch(es){flag}"


EVAL_ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})[^|]*\|\s*(PASS)?", re.M)


def eval_inputs_changed(agent, fm):
    """The newest file the agent runs on: SYSTEM.md, its ledger, its preloaded skills."""
    paths = [ROOT / "agents" / agent / "SYSTEM.md", ROOT / "agents" / agent / "learned-rules.md"]
    for name in (fm or {}).get("skills") or []:
        paths += [p for p in (ROOT / "skills" / name).rglob("*") if p.is_file()
                  and not {"__pycache__", "golden", "eval"} & set(p.parts) and not p.name.startswith(".")]
    newest = max((p for p in paths if p.exists()), key=lambda p: p.stat().st_mtime)
    return newest, datetime.fromtimestamp(newest.stat().st_mtime).date().isoformat()


def check_eval_fresh(agent, fm, body):
    """A PASS counts only if it is dated on or after the last change to what it tested.
    The old coverage check passed on August results after SYSTEM.md changed on 27 Sep
    (F40), so each case's latest dated row must be PASS and not older than the change."""
    newest, changed = eval_inputs_changed(agent, fm)
    latest = {}
    for p in eval_cases(agent):
        for day, verdict in EVAL_ROW.findall(p.read_text(encoding="utf-8")):
            if day >= latest.get(p.stem, ("",))[0]:
                latest[p.stem] = (day, verdict)
    if len(latest) < 2:
        return False, f"{len(latest)} dated eval case(s), need >= 2"
    stale = sorted(n for n, (day, verdict) in latest.items() if verdict != "PASS" or day < changed)
    where = newest.relative_to(ROOT)
    if stale:
        return False, (f"{len(stale)} of {len(latest)} case(s) not passed since {where} changed on "
                       f"{changed}: {', '.join(stale)}")
    return True, f"{len(latest)} case(s) passed on or after {changed} ({where})"


def check_enforcement_wired(agent, fm, body):
    """Every ENFORCEMENT registration is present in settings.json or the agent's frontmatter,
    and each script it runs exists and parses."""
    try:
        settings = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))
    except Exception:
        return False, "settings.json unreadable"
    found = {}  # (script name, args) -> script path
    for block in (settings.get("hooks") or {}, (fm or {}).get("hooks") or {}):
        for entries in block.values():
            for entry in entries or []:
                for h in entry.get("hooks", []):
                    parts = str(h.get("command", "")).split()
                    if parts:
                        found[(Path(parts[0]).name, " ".join(parts[1:]))] = parts[0].replace("~", str(Path.home()), 1)
    need = ENFORCEMENT[agent]
    missing = [" ".join(k).strip() for k in need if k not in found]
    if missing:
        return False, "not registered: " + ", ".join(missing)
    for script in sorted({found[k] for k in need}):
        if not Path(script).exists():
            return False, f"{script} missing"
        if subprocess.run(["bash", "-n", script], capture_output=True).returncode != 0:
            return False, f"{script} fails bash -n"
    return True, "registered: " + ", ".join(" ".join(k).strip() for k in need)


def check_newtool_exercised(agent, fm, body):
    for p in eval_cases(agent):
        t = p.read_text(encoding="utf-8")
        if "21st" in t and re.search(r"\|\s*PASS", t):
            return True, f"evidence in {p.name}"
    for r in records(agent):
        if "21st" in json.dumps(r):
            return True, "evidence in run record"
    return False, "no graded 21st.dev usage evidence"


CHECKS = {
    "spec_integrity": check_spec_integrity,
    "grants_valid": check_grants_valid,
    "ledger_alive": check_ledger_alive,
    "gates_defined": check_gates_defined,
    "gates_run": check_gates_run,
    "records_recent": check_records_recent,
    "kpi_measured": check_kpi_measured,
    "escalation_integrity": check_escalation_integrity,
    "eval_fresh": check_eval_fresh,
    "enforcement_wired": check_enforcement_wired,
    "newtool_exercised": check_newtool_exercised,
}


def score(agent):
    fm, body = frontmatter(agent)
    dims, total = {}, 0.0
    for name, fn in CHECKS.items():
        try:
            ok, note = fn(agent, fm, body)
        except Exception as e:
            ok, note = False, f"check error: {e}"
        pts = WEIGHTS[name] if ok else 0.0
        dims[name] = {"pass": ok, "points": pts, "weight": WEIGHTS[name], "note": note}
        total += pts
    return round(total, 1), dims


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=list(AGENTS))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min", action="store_true")
    args = ap.parse_args()

    results = {a: score(a) for a in ([args.agent] if args.agent else AGENTS)}

    if args.min:
        print(min(t for t, _ in results.values()))
        return
    if args.json:
        print(json.dumps({a: {"score": t, "dims": d} for a, (t, d) in results.items()}, indent=1))
        return
    for a, (t, d) in results.items():
        print(f"{a}: {t}/10")
        for name, info in d.items():
            mark = "PASS" if info["pass"] else "FAIL"
            print(f"  [{mark}] {name} ({info['weight']}): {info['note']}")


if __name__ == "__main__":
    main()
