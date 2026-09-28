#!/usr/bin/env python3
"""Outcome KPIs for the agent fleet, computed from run records.

The scorecard (lib/agent_scorecard.py) measures process wiring; this measures
what the wiring exists for: first-pass approval, revision load, verify-loop
convergence, defects found after handover, operator minutes, and agent effort.
Records come from state/agent-runs/<agent>/*.jsonl via agent_runtime.record_run.
Effort (tokens, active minutes) comes from transcript telemetry, not self-report,
and is never converted to dollars until verified per-model prices, including cache
rates, exist.

Field contract (add to every real dispatch record):
  first_pass_approved | handoff_accepted   bool, the headline
  revision_items                           int, edits required after handoff
  verify_rounds / design_review_rounds     int, convergence
  post_handover_defects                    int, found by client/CMO after accept
  operator_minutes                         float, human time consumed
  truth_status                             "asserted" | "auto" (auto = hook-written)

Usage:
  python3 lib/agent_kpis.py                 # per-agent table + fleet rollup
  python3 lib/agent_kpis.py --agent wright
  python3 lib/agent_kpis.py --json
  python3 lib/agent_kpis.py --receipts      # markdown summary (the sales evidence)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_telemetry import human, summary as telemetry_summary  # observed, not self-reported

RUNS = Path.home() / ".claude" / "state" / "agent-runs"
APPROVAL_FIELDS = ("first_pass_approved", "handoff_accepted")


def load(agent):
    recs = []
    d = RUNS / agent
    if d.is_dir():
        for f in sorted(d.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        recs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return recs


def is_eval(r):
    """Eval and smoke runs test the agent; they are not deliveries."""
    if r.get("eval") is True:
        return True
    jid = str(r.get("job_id", ""))
    note = " ".join(str(r.get(k, "")) for k in ("note", "notes", "summary", "task")).lower()
    return (jid.startswith(("eval-", "critique-grounding", "escalation-discipline"))
            or any(w in note for w in ("golden eval", "eval run", "emulated", "smoke")))


def kpis(agent):
    recs = load(agent)
    # First-pass approval is graded once per real job: evals and hook-written auto
    # records are excluded, a null verdict is ungraded, the job's FIRST true/false verdict counts, and "approved"
    # needs zero revision items (accepted after edits is not first-pass). Counting
    # nulls, evals and re-grades gave 17%, then 55%; the honest figure was 3 of 5.
    verdicts = {}
    for r in sorted(recs, key=lambda r: r.get("ts", "")):
        if (is_eval(r) or r.get("truth_status") == "auto"
                or not any(isinstance(r.get(f), bool) for f in APPROVAL_FIELDS)):
            continue
        verdicts.setdefault(r.get("job_id") or r.get("ts"), r)
    graded = list(verdicts.values())
    approved = [r for r in graded
                if any(r.get(f) is True for f in APPROVAL_FIELDS) and not r.get("revision_items")]
    autos = [r for r in recs if r.get("truth_status") == "auto"]
    rounds = [r[k] for r in recs for k in ("verify_rounds", "design_review_rounds")
              if isinstance(r.get(k), int)]

    def total(key):
        vals = [r[key] for r in recs if isinstance(r.get(key), (int, float))]
        return round(sum(vals), 2) if vals else None

    return {
        "records": len(recs),
        "graded_runs": len(graded),
        "first_pass_rate": round(len(approved) / len(graded), 3) if graded else None,
        "revision_items_total": total("revision_items"),
        "verify_rounds_max": max(rounds) if rounds else None,
        "verify_rounds_mean": round(sum(rounds) / len(rounds), 1) if rounds else None,
        "post_handover_defects": total("post_handover_defects"),
        "operator_minutes_total": total("operator_minutes"),
        "auto_records": len(autos),
        "dates": sorted({r.get("ts", "")[:10] for r in recs if r.get("ts")}),
        "observed": telemetry_summary(agent),
    }


def fmt(v, pct=False):
    if v is None:
        return "no data"
    if pct and isinstance(v, float):
        return f"{v * 100:.0f}%"
    return str(v)


def effort(o):
    if not o.get("dispatches"):
        return "no data"
    return (f"{o['active_hours']} active h over {o['dispatches']} dispatch(es) "
            f"(median {o['median_active_minutes']} min), output tokens {human(o['tokens']['tokens_out'])}, "
            f"cache read {human(o['tokens']['cache_read'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--receipts", action="store_true")
    args = ap.parse_args()

    agents = [args.agent] if args.agent else sorted(
        p.name for p in RUNS.iterdir() if p.is_dir() and any(p.glob("*.jsonl")))
    data = {a: kpis(a) for a in agents}

    if args.json:
        print(json.dumps(data, indent=1))
        return

    if args.receipts:
        print("# Fleet delivery receipts\n")
        print("Evidence computed from run records, not claimed. "
              "`auto` records (hook-written, ungraded) are counted but never "
              "contribute to approval rates.\n")
        for a, k in data.items():
            if not k["graded_runs"]:
                continue
            span = f"{k['dates'][0]} to {k['dates'][-1]}" if k["dates"] else ""
            print(f"## {a} ({span})")
            print(f"- First-pass approval: {fmt(k['first_pass_rate'], pct=True)} "
                  f"across {k['graded_runs']} graded run(s)")
            print(f"- Revision items total: {fmt(k['revision_items_total'])}; "
                  f"post-handover defects: {fmt(k['post_handover_defects'])}")
            print(f"- Verify-loop convergence: mean {fmt(k['verify_rounds_mean'])} "
                  f"round(s), max {fmt(k['verify_rounds_max'])}")
            o = k["observed"]
            print(f"- Operator minutes: {fmt(k['operator_minutes_total'])}; agent effort: "
                  f"{effort(o)}\n")
        print("Caveat line for any external use: rates below ~10 graded runs "
              "are directional, not statistical.")
        return

    for a, k in data.items():
        print(f"{a}: {k['records']} record(s), {k['graded_runs']} graded, "
              f"first-pass {fmt(k['first_pass_rate'], pct=True)}, "
              f"rounds mean {fmt(k['verify_rounds_mean'])}/max {fmt(k['verify_rounds_max'])}, "
              f"revisions {fmt(k['revision_items_total'])}, "
              f"defects-after-handover {fmt(k['post_handover_defects'])}, "
              f"operator-min {fmt(k['operator_minutes_total'])}, auto {k['auto_records']}")
        o = k["observed"]
        if o["dispatches"]:
            print(f"  observed over {o['dispatches']} dispatch(es): brief {fmt(o['brief_rate'], pct=True)} "
                  f"(text {fmt(o['brief_text_rate'], pct=True)}), handoff {fmt(o['handoff_rate'], pct=True)} "
                  f"(text {fmt(o['handoff_text_rate'], pct=True)}), effort {effort(o)}, "
                  f"webflow hidden errors {o['webflow_action_errors']}, "
                  f"chrome-down {o['chrome_connect_errors']}, path-denied {o['artefact_path_denied']}, "
                  f"schema errors {o['schema_errors']}")


if __name__ == "__main__":
    main()
