#!/usr/bin/env python3
"""FLOWSMITH checkpoint manifest — init/read/update/validate/resume-diff.

The manifest is the cold-resume contract for webflow-build: which phases
completed, what was created (ids), where custom code lives. Python cannot
call the Webflow MCP, so `resume-diff` compares the manifest against a
probe-results JSON the agent gathers via the API, and emits the reconciliation
report the resume protocol requires.

Usage:
  flowsmith_manifest.py init   <project> --site-id ID --staging-url URL
  flowsmith_manifest.py read   <project>
  flowsmith_manifest.py update <project> --phase N --status done|partial [--set key=json ...]
  flowsmith_manifest.py add    <project> --kind pages|styles|variables|collections|components|assets|custom_code|interactions --items '[...]'
  flowsmith_manifest.py validate <project>
  flowsmith_manifest.py resume-diff <project> --probe probe.json
"""
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / ".claude" / "state" / "flowsmith"
PHASES = ["bootstrap", "discovery", "design", "copy", "assets", "sections",
          "motion", "seo", "a11y", "verify", "revisions", "launch", "postlaunch"]
ID_KINDS = ["pages", "styles", "variables", "collections", "components", "assets", "custom_code", "cms_ledger", "schedule", "interactions"]

def path(project): return ROOT / project / "manifest.json"

def load(project):
    p = path(project)
    if not p.exists(): sys.exit(f"no manifest at {p} — run init")
    return json.loads(p.read_text())

def save(project, m):
    m["updated"] = datetime.now(timezone.utc).isoformat()
    p = path(project); p.parent.mkdir(parents=True, exist_ok=True)  # snapshots: state/snapshots/<job_id>/
    p.write_text(json.dumps(m, indent=2, ensure_ascii=False))
    return p

def cmd_init(a):
    if path(a.project).exists(): sys.exit("manifest exists — refusing to overwrite")
    m = {"project": a.project, "site_id": a.site_id, "staging_url": a.staging_url,
         "created": datetime.now(timezone.utc).isoformat(),
         "phases": {ph: {"status": "pending", "verified_published": False,
                         "budget": {"max_tool_calls": None, "cost_ceiling": None},
                         "spent": {"tool_calls": 0, "cost": 0.0}} for ph in PHASES},
         "created_ids": {k: [] for k in ID_KINDS},
         "operator_moments_fired": [], "audit": [], "notes": []}
    print(f"initialised {save(a.project, m)}")

def cmd_read(a): print(json.dumps(load(a.project), indent=2, ensure_ascii=False))

def cmd_update(a):
    m = load(a.project); ph = PHASES[a.phase] if a.phase < len(PHASES) else sys.exit("bad phase index")
    m["phases"][ph]["status"] = a.status
    if a.status == "done": m["phases"][ph]["verified_published"] = a.verified
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        m["phases"][ph][k] = json.loads(v)
    save(a.project, m); print(f"{ph} -> {a.status} (verified_published={m['phases'][ph]['verified_published']})")

def cmd_add(a):
    m = load(a.project)
    if a.kind not in ID_KINDS: sys.exit(f"kind must be one of {ID_KINDS}")
    items = json.loads(a.items)
    m["created_ids"].setdefault(a.kind, []).extend(items if isinstance(items, list) else [items])  # older manifests lack newer kinds
    save(a.project, m); print(f"added {len(items)} to {a.kind} (total {len(m['created_ids'][a.kind])})")

def cmd_validate(a):
    m = load(a.project); errs = []
    for key in ("project", "site_id", "staging_url"):
        if not m.get(key): errs.append(f"missing {key}")
    unknown = set(m.get("phases", {})) - set(PHASES)
    if unknown: errs.append(f"unknown phases: {unknown}")
    done_after_pending = False; seen_pending = False
    for ph in PHASES:
        st = m["phases"].get(ph, {}).get("status", "pending")
        if st == "pending": seen_pending = True
        elif st == "done" and seen_pending: done_after_pending = True
    if done_after_pending: errs.append("phase order violated: done phase after a pending one")
    for ph, d in m["phases"].items():
        if d.get("status") == "done" and not d.get("verified_published"):
            errs.append(f"{ph}: done but verified_published=false — a phase is complete only when its PUBLISHED output verified")
    print("VALID" if not errs else "INVALID:\n- " + "\n- ".join(errs))
    sys.exit(0 if not errs else 1)

def cmd_resume_diff(a):
    """probe.json: {"pages":[ids], "styles":[names], "variables":[ids], "collections":[ids],
    "registered_scripts":[ids], "site_freeform_present": bool, "staging_curl_ok": bool}"""
    m = load(a.project); probe = json.loads(Path(a.probe).read_text()); report = []
    if not probe.get("staging_curl_ok"): report.append("BLOCK: staging URL did not curl OK — resolve before resuming")
    for kind, probe_key in [("pages", "pages"), ("styles", "styles"), ("variables", "variables"), ("collections", "collections")]:
        claimed = {i.get("id") or i.get("name") for i in m["created_ids"].get(kind, []) if isinstance(i, dict)} | \
                  {i for i in m["created_ids"].get(kind, []) if isinstance(i, str)}
        live = set(probe.get(probe_key, []))
        missing = claimed - live
        if missing: report.append(f"{kind}: manifest claims {len(missing)} item(s) NOT live: {sorted(missing)[:5]}")
    claimed_code = {c.get("id") or c.get("name") for c in m["created_ids"].get("custom_code", []) if isinstance(c, dict)} | \
                   {c for c in m["created_ids"].get("custom_code", []) if isinstance(c, str)}
    live_code = set(probe.get("registered_scripts", []))
    ghost = live_code - claimed_code           # live but not in manifest
    stale = claimed_code - live_code           # manifest claims but gone from registry (half-done retirement?)
    if ghost: report.append(f"custom_code: {len(ghost)} registered script(s) LIVE but NOT in manifest (two-surface rule — investigate): {sorted(ghost)[:5]}")
    if stale: report.append(f"custom_code: {len(stale)} script(s) in manifest but NOT live in registry — confirm retirement is complete on BOTH surfaces + published HTML: {sorted(stale)[:5]}")
    ff = probe.get("freeform_blocks")
    if isinstance(ff, list):
        report.append(f"custom_code: {len(ff)} freeform block(s) live: {ff[:6]} — reconcile each against the manifest's expected list")
    elif probe.get("site_freeform_present"):
        report.append("custom_code: site freeform present (probe gave a bool, not a per-block list — pass freeform_blocks[] for a real diff)")
    first_unverified = next((ph for ph in PHASES if not m["phases"][ph].get("verified_published")), None)
    report.append(f"RESUME AT: phase '{first_unverified}' (first phase without verified published output)" if first_unverified
                  else "all phases verified — nothing to resume")
    print("\n".join(report))

def _phase(m, i):
    if i < 0 or i >= len(PHASES): sys.exit("bad phase index")
    return PHASES[i]

def cmd_budget(a):
    """Set an enforced budget for a phase. Guardrail DURING the run, not observed after."""
    m = load(a.project); ph = _phase(m, a.phase); b = m["phases"][ph].setdefault("budget", {})
    if a.max_calls is not None: b["max_tool_calls"] = a.max_calls
    if a.cost_ceiling is not None: b["cost_ceiling"] = a.cost_ceiling
    save(a.project, m); print(f"{ph} budget: {b}")

def cmd_spend(a):
    """Accumulate spend against a phase; exit 2 on breach so the caller escalates (like the 3-fix-round rule)."""
    m = load(a.project); ph = _phase(m, a.phase)
    s = m["phases"][ph].setdefault("spent", {"tool_calls": 0, "cost": 0.0})
    s["tool_calls"] += a.calls or 0; s["cost"] = round(s["cost"] + (a.cost or 0.0), 4)
    save(a.project, m)
    b = m["phases"][ph].get("budget", {}); breaches = []
    if b.get("max_tool_calls") and s["tool_calls"] > b["max_tool_calls"]:
        breaches.append(f"tool_calls {s['tool_calls']} > {b['max_tool_calls']}")
    if b.get("cost_ceiling") and s["cost"] > b["cost_ceiling"]:
        breaches.append(f"cost {s['cost']} > {b['cost_ceiling']}")
    if breaches:
        print(f"BREACH {ph}: " + "; ".join(breaches) + " — STOP + escalate (do not silently continue)"); sys.exit(2)
    print(f"{ph} spent: {s}")

def cmd_log(a):
    """Append a per-mutation audit-context line (15-25 words, what the write INTENDED) for legible post-mortems."""
    m = load(a.project)
    m["audit"].append({"phase": _phase(m, a.phase) if a.phase is not None else None,
                       "ts": datetime.now(timezone.utc).isoformat(), "context": a.context})
    save(a.project, m); print(f"logged ({len(m['audit'])} audit entries)")

def cmd_report(a):
    """Per-project handover economics: operator minutes + phase status + custom-code footprint.
    The KPI surface /insights can't produce (it aggregates by skill, not project)."""
    m = load(a.project)
    moments = m.get("operator_moments_fired", [])
    op_min = sum(x.get("minutes", 0) for x in moments if isinstance(x, dict))
    done = sum(1 for ph in PHASES if m["phases"][ph].get("verified_published"))
    cc = m["created_ids"].get("custom_code", [])
    tot_calls = sum(p.get("spent", {}).get("tool_calls", 0) for p in m["phases"].values())
    tot_cost = round(sum(p.get("spent", {}).get("cost", 0.0) for p in m["phases"].values()), 4)
    breached = [ph for ph, p in m["phases"].items()
                if (p.get("budget", {}).get("max_tool_calls") and p["spent"]["tool_calls"] > p["budget"]["max_tool_calls"])
                or (p.get("budget", {}).get("cost_ceiling") and p["spent"]["cost"] > p["budget"]["cost_ceiling"])]
    lines = [
        f"# FLOWSMITH project report — {a.project}",
        f"site: {m.get('site_id')}  staging: {m.get('staging_url')}",
        f"phases verified: {done}/{len(PHASES)}",
        f"spend: {tot_calls} tool-calls, ${tot_cost}  budget breaches: {breached or 'none'}",
        f"operator moments fired: {len(moments)}  (~{op_min} operator minutes)",
        f"audit entries: {len(m.get('audit', []))}",
        f"custom-code footprint: {len(cc)} registered/freeform items (must match the handover inventory)",
        f"created: " + ", ".join(f"{k}={len(v)}" for k, v in m['created_ids'].items() if v),
    ]
    for note in m.get("notes", []):
        lines.append(f"note: {note}")
    print("\n".join(lines))

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("project"); p.add_argument("--site-id", required=True); p.add_argument("--staging-url", required=True); p.set_defaults(f=cmd_init)
    p = sub.add_parser("read"); p.add_argument("project"); p.set_defaults(f=cmd_read)
    p = sub.add_parser("update"); p.add_argument("project"); p.add_argument("--phase", type=int, required=True); p.add_argument("--status", choices=["pending", "partial", "done"], required=True); p.add_argument("--verified", action="store_true"); p.add_argument("--set", nargs="*"); p.set_defaults(f=cmd_update)
    p = sub.add_parser("add"); p.add_argument("project"); p.add_argument("--kind", required=True); p.add_argument("--items", required=True); p.set_defaults(f=cmd_add)
    p = sub.add_parser("validate"); p.add_argument("project"); p.set_defaults(f=cmd_validate)
    p = sub.add_parser("resume-diff"); p.add_argument("project"); p.add_argument("--probe", required=True); p.set_defaults(f=cmd_resume_diff)
    p = sub.add_parser("report"); p.add_argument("project"); p.set_defaults(f=cmd_report)
    p = sub.add_parser("budget"); p.add_argument("project"); p.add_argument("--phase", type=int, required=True); p.add_argument("--max-calls", type=int, dest="max_calls"); p.add_argument("--cost-ceiling", type=float, dest="cost_ceiling"); p.set_defaults(f=cmd_budget)
    p = sub.add_parser("spend"); p.add_argument("project"); p.add_argument("--phase", type=int, required=True); p.add_argument("--calls", type=int); p.add_argument("--cost", type=float); p.set_defaults(f=cmd_spend)
    p = sub.add_parser("log"); p.add_argument("project"); p.add_argument("--phase", type=int); p.add_argument("--context", required=True); p.set_defaults(f=cmd_log)
    a = ap.parse_args(); a.f(a)

if __name__ == "__main__":
    main()
