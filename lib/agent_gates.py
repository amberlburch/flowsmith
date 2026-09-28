#!/usr/bin/env python3
"""Hook gates for Webflow work (every route) and the flowsmith and wright dispatches.

Called through hooks/agent-gates.sh:
  pre-webflow         settings PreToolUse on every Webflow MCP tool
  post-webflow        settings PostToolUse on data_sites_tool: records landed publishes
  pre-grant           settings PreToolUse on Bash and file writes: subagents never write a grant
  pre-github          settings PreToolUse on GitHub MCP file writes: none reach the public flowsmith repo
  pre-agent <agent>   frontmatter PreToolUse (all tools) of flowsmith and wright
  stop-agent <agent>  frontmatter Stop of flowsmith and wright (runs as SubagentStop)

Gates:
  1  publish_site. A non-empty customDomains is a production publish: denied unless a grant
     written by the main session after the operator's yes is fresh. Staging must pass
     publishToWebflowSubdomain: true and customDomains: [] explicitly, and the site's publish
     lock must be live (held by this dispatch's job when its job id is known). A second publish
     needs 60 s since the last landed one and a webcheck report.json for this job written since
     it (inside a two-hour window).
  2  brief. A flowsmith dispatch's first Webflow write needs its own brief.md under _scratch
     written during the dispatch (a full brief must pass ledger_lint --plan). Main-session
     Webflow work gets one deny per session asking for a lite brief.
  3  stop. flowsmith cannot stop after Webflow writes without a handoff.md that passes
     ledger_lint --handoff; wright cannot stop without a Verification section (in its last
     message or its handed-back report) unless it returns an approval card or the packet.
     Each blocks once.
  4  tool-call cap per dispatch (budget-caps.json, else flowsmith 200 and wright 150): a warning
     at warn_at_pct, then only state-saving and report calls, then only report calls.
  5  remove_element and remove_style need a snapshot of that page (or a styles.json naming the
     style) under state/snapshots/<job_id>/, written during this dispatch or session.
  wright code writes inside a ~/Code repo need a specs/NNN-<slug>/spec.md or proposal.md first.
  GitHub MCP push_files and create_or_update_file to amberlburch/flowsmith are denied in every
  session: they skip the repo's pre-push scan, so the sync tool is the only path in.

Fails open on any internal error, except that a publish_site call with a non-empty
customDomains is denied whenever its grant cannot be verified.
"""
import fcntl
import json
import os
import re
import sys
import time
from contextlib import contextmanager, suppress
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("AGENT_GATES_ROOT") or Path.home() / ".claude")
CODE_HOME = Path(os.environ.get("AGENT_GATES_CODE_HOME") or Path.home() / "Code")
STATE = ROOT / "state" / "agent-gates"
LOCKS = ROOT / "state" / "agent-resource-locks.json"
PUBLISHES = ROOT / "state" / "webflow-publish-times.json"
GRANTS = ROOT / "state" / "approvals"
SNAPSHOTS = ROOT / "state" / "snapshots"
SCRATCH = ROOT / "_scratch"
CAPS_FILE = CODE / "agents" / "shared" / "budget-caps.json"
LINT = CODE / "skills" / "flowsmith-loop" / "scripts" / "ledger_lint.py"
LINT_CMD = "python3 ~/.claude/skills/flowsmith-loop/scripts/ledger_lint.py"

WEBFLOW = "mcp__plugin_webflow-skills_webflow__"
DEFAULT_CAPS = {"flowsmith": (200, 75), "wright": (150, 80)}
HARD_EXTRA = 40          # calls allowed past the cap for saving state
MIN_SPACING = 60         # publish_site rate limit, seconds
CHECK_WINDOW = 2 * 3600  # a publish older than this starts a new batch
GRANT_TTL = 30 * 60
MAIN_WINDOW = 12 * 3600  # how far back a main session's brief or snapshot may date
KEEP_DAYS = 14

JOB_ID = re.compile(r"^[a-z][a-z-]*-\d{8}-\d{4}-[0-9a-f]{4}$")
PROD_RAW = re.compile(r'\\?"customDomains\\?"\s*:\s*\[\s*\\?"')  # plain or string-encoded actions
FULL_BRIEF = re.compile(r"^(GOAL:|#{0,4}\s*BUILD PLAN\b)", re.M)
LITE_FIELDS = ("LESSONS IN PLAY", "ACCEPTANCE", "VERIFICATION")
VERIFICATION_HEAD = re.compile(r"^#{1,3}\s*Verification\b", re.M)
RETURNED = re.compile(r"\b(SOP|workflow|skill)[- ]shaped\b", re.I)  # wright hands the packet back
SCRATCH_BRIEF = re.compile(r"_scratch/([^/\s'\"]+)/brief\.md")
GRANT_CMD = re.compile(r"state/approvals|webflow-production-")
HANDBACK = ("SubagentHandback", "StructuredOutput")  # the tools a subagent reports through
WRAPUP_BASH = re.compile(r"agent_runtime\.py|ledger_lint\.py|flowsmith_manifest\.py|"
                         r"\bgit\s+(add|commit|status|diff|log|push|stash)\b")
WRAPUP_FILES = {"continue.md", "handoff.md", "tasks.md"}
CODE_EXT = re.compile(r"\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|sql|css|html|vue|svelte)$")
FILE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
PUBLIC_REPO = ("amberlburch", "flowsmith")
GITHUB_WRITES = ("mcp__github__push_files", "mcp__github__create_or_update_file")


# --- small helpers ------------------------------------------------------------

def tilde(path) -> str:
    return str(path).replace(str(Path.home()), "~", 1)


def under(fp, folder) -> bool:
    fp = os.path.normpath(os.path.expanduser(str(fp)))
    return fp == str(folder) or fp.startswith(str(folder) + os.sep)


def texts(node) -> str:
    """Every string inside a tool input, one per line (a handed-back report may be nested)."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        node = list(node.values())
    return "\n".join(texts(v) for v in node) if isinstance(node, list) else ""


def report_ok(text) -> bool:
    """A wright report that proves its work, or one that ends the dispatch before any build."""
    return bool(VERIFICATION_HEAD.search(text) or text.lstrip().startswith("APPROVAL NEEDED")
                or RETURNED.search(text))


def deny(gate, reason):
    return {"_gate": gate, "hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": reason}}


def context(text):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def parse_iso(value) -> float:
    from datetime import datetime
    return datetime.fromisoformat(str(value)).timestamp()


def hhmmss(epoch) -> str:
    return time.strftime("%H:%M:%S", time.localtime(epoch))


def actions(inp):
    acts = inp.get("actions") if isinstance(inp, dict) else None
    if isinstance(acts, str):
        try:
            acts = json.loads(acts)
        except ValueError:
            return []
    return [a for a in acts or [] if isinstance(a, dict)]


def publishes(acts):
    return [a["publish_site"] for a in acts if isinstance(a.get("publish_site"), dict)]


def key_of(p) -> str:
    raw = p.get("agent_id") or f"main-{p.get('session_id') or 'unknown'}"
    return re.sub(r"[^A-Za-z0-9_.-]", "", str(raw))[:80]


def job_of(folder: Path):
    job = re.sub(r"^\d{4}-\d{2}-", "", folder.name)
    return job if JOB_ID.match(job) else None


def is_write(tool, acts) -> bool:
    from agent_telemetry import BUILDER_TOOLS, WRITE_VERB
    return (tool[len(WEBFLOW):] in BUILDER_TOOLS
            or any(WRITE_VERB.match(k) for a in acts for k in a if k != "label"))


@contextmanager
def locked_state(key):
    """Per-dispatch (or per-session) state, serialised across parallel hook processes."""
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / f"{key}.json"
    new = not path.exists()
    with open(path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read()
        try:
            st = json.loads(raw) if raw.strip() else {}
        except ValueError:
            st = {}
        before = json.dumps(st, sort_keys=True)
        if new:
            st["started"] = time.time()
            prune()
        yield st
        after = json.dumps(st, sort_keys=True)
        if after != before:
            fh.seek(0)
            fh.truncate()
            fh.write(after)


def prune():
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in STATE.glob("*"):
        if f.suffix in (".json", ".calls") and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


def bump(key) -> int:
    """Count one tool call. O_APPEND keeps parallel calls from losing a count."""
    STATE.mkdir(parents=True, exist_ok=True)
    fd = os.open(STATE / f"{key}.calls", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, b".")
        return os.fstat(fd).st_size
    finally:
        os.close(fd)


def calls(key) -> int:
    try:
        return (STATE / f"{key}.calls").stat().st_size
    except OSError:
        return 0


def caps(agent):
    try:
        a = json.loads(CAPS_FILE.read_text())["agents"][agent]
        return int(a["tool_call_cap"]), int(a.get("warn_at_pct", 80))
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_CAPS.get(agent, (200, 75))


def birth(path: Path):
    try:
        s = path.stat()
    except OSError:
        return None
    return getattr(s, "st_birthtime", None) or s.st_ctime


def started(p, st) -> float:
    """When this dispatch or main session began: its transcript's birth, else its first
    counted tool call, else the first time a gate saw it."""
    t = None
    tp = p.get("agent_transcript_path") or p.get("transcript_path")
    if tp:
        tp = Path(os.path.expanduser(tp))
        aid = p.get("agent_id")
        if aid and "/subagents/" not in str(tp):
            sub = tp.with_suffix("") / "subagents"
            tp = sub / f"agent-{aid}.jsonl"
            if not tp.exists():  # workflow subagents nest one level deeper
                tp = next(sub.glob(f"*/*/agent-{aid}.jsonl"), tp)
        t = birth(tp)
    if t is None:
        t = birth(STATE / f"{key_of(p)}.calls") or st.get("started", time.time())
    if not p.get("agent_id"):
        t = max(t, time.time() - MAIN_WINDOW)
    return t


def fresh(path: Path, since: float) -> bool:
    try:
        s = path.stat()
    except OSError:
        return False
    return s.st_size > 2 and s.st_mtime >= since - 1


def fresh_docs(name, since) -> list:
    return [f for f in SCRATCH.glob(f"*/{name}") if fresh(f, since)]


def find_doc(name, since, prefer=None):
    """The newest _scratch/<dir>/<name> written since the dispatch or session began."""
    if prefer is not None and fresh(prefer / name, since):
        return prefer / name
    hits = fresh_docs(name, since)
    return max(hits, key=lambda f: f.stat().st_mtime) if hits else None


def lint(path: Path, kind: str) -> list:
    import importlib.util
    spec = importlib.util.spec_from_file_location("ledger_lint", LINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rep = mod.Report()
    (mod.lint_plan if kind == "plan" else mod.lint_handoff)(path, rep)
    return rep.fails


def brief_problems(path: Path) -> list:
    text = path.read_text(errors="replace")
    if FULL_BRIEF.search(text):
        return lint(path, "plan")
    return [f"lite brief has no '{f}:' line" for f in LITE_FIELDS
            if not re.search(rf"^[ \t>*#-]*{f}\**:[ \t]*\S", text, re.M)]


def log(entry):
    STATE.mkdir(parents=True, exist_ok=True)
    entry["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(STATE / "gate-events.jsonl", "a") as fh:
        fh.write(json.dumps(entry) + "\n")


# --- gate 1: publish_site ------------------------------------------------------

def grant_path(site) -> Path:
    return GRANTS / f"webflow-production-{site}.json"


def grant_ok(site, domains) -> bool:
    f = grant_path(site)
    if not f.exists():
        return False
    g = json.loads(f.read_text())
    want = set(domains) if isinstance(domains, list) else {str(domains)}
    age = time.time() - parse_iso(g["approved_at"])
    ok = (str(g.get("site_id")) == site and want <= set(g.get("domains") or [])
          and len(str(g.get("approval") or "").strip()) >= 3 and -60 <= age <= GRANT_TTL)
    if ok:
        log({"event": "production-grant-used", "site": site, "domains": sorted(want)})
    return ok


def production_reason(p, site, domains, unreadable=False) -> str:
    doms = ", ".join(map(str, domains)) if isinstance(domains, list) else str(domains)
    card = (f"APPROVAL NEEDED\nAction: publish Webflow site {site} live to {doms}\n"
            f"Reason: publication\nApprove: yes or no")
    grant = (f"{tilde(grant_path(site))} as JSON with site_id, domains, approved_at (ISO time, "
             "now) and approval (the operator's words); it is valid for 30 minutes")
    head = (f"Production publish blocked: customDomains [{doms}] makes this a live publish "
            f"(Tier 3), and no fresh approval grant exists. Do not retry or work around it. ")
    if unreadable:
        head += f"The grant file {tilde(grant_path(site))} could not be verified (bad JSON or a missing field). "
    if p.get("agent_id"):
        return (head + "Finish and verify the staging work, then end your report with this line "
                f"and, as the last four lines, this card:\nGrant after yes: the main session writes "
                f"{grant}, then resumes this dispatch to publish.\n{card}")
    return (head + f"Show the operator this card and wait:\n{card}\nOnly after the operator says yes to this exact "
            f"publish, write {grant}, then retry.")


def check_since(epoch, job) -> bool:
    """A webcheck report.json written since epoch: this job's when the job is known (its folder
    or its "job" field), otherwise any outside the webcheck selftest folders."""
    for pattern in ("*/report.json", "*/*/report.json", "*/*/*/report.json"):
        for f in SCRATCH.glob(pattern):
            rel = str(f.relative_to(SCRATCH))
            if f.stat().st_mtime <= epoch:
                continue
            if job is None:
                if "selftest" not in rel:
                    return True
            elif job in rel:
                return True
            else:
                data = load_json(f, {})
                if isinstance(data, dict) and data.get("job") == job:
                    return True
    return False


def publish_rule(pub, job, own_lock):
    """own_lock: a dispatch must hold the lock under its own job; the main session any live one."""
    site = str(pub.get("site_id") or "")
    now = time.time()
    if not pub.get("customDomains") and (
            "customDomains" not in pub or pub.get("publishToWebflowSubdomain") is not True):
        return (f"Staging publish of site {site} must pass publishToWebflowSubdomain: true and "
                "customDomains: [] explicitly (L-109): an omitted customDomains is how a site "
                "carrying production domains gets published live. Re-send with both parameters.")
    lock = load_json(LOCKS, {}).get(f"webflow_publish:{site}") or {}
    live = bool(lock) and parse_iso(lock.get("expires_at")) > now
    if not live:
        return (f"No live publish lock for site {site}. Run `python3 ~/.claude/lib/agent_runtime.py "
                f"lock {job or '<job_id>'} webflow_publish:{site}` (exit 0 is acquired; on busy, "
                "wait and retry), then publish, verify, and unlock.")
    if own_lock and job and lock.get("job_id") != job:
        return (f"The publish lock for site {site} is held by job {lock.get('job_id')}, not this "
                f"dispatch's job {job}. Take the lock under {job}; if another session holds it, "
                "wait for its unlock and never publish over it.")
    last = load_json(PUBLISHES, {}).get(site)
    if last:
        at = float(last.get("at", 0))
        if now - at < MIN_SPACING:
            return (f"Site {site} was published {int(now - at)} s ago and publish_site allows about "
                    f"one a minute. Batch the remaining edits and publish after {hhmmss(at + MIN_SPACING)}.")
        if now - at < CHECK_WINDOW and not check_since(at, job):
            return (f"Site {site} was published at {hhmmss(at)} and no check has run since"
                    f"{f' for job {job}' if job else ''}. Verify that publish first: `node "
                    "~/.claude/skills/webflow-verify/scripts/webcheck.mjs <urls> --job "
                    f"{job or '<job_id>'}` (`--html-only --expect \"<text>\"` is enough for a quick "
                    "check), then publish the next batch. Never publish per edit.")
    return None


# --- modes -----------------------------------------------------------------------

def pre_webflow(p):
    tool = p.get("tool_name", "")
    inp = p.get("tool_input") if isinstance(p.get("tool_input"), dict) else {}
    acts = actions(inp)
    pubs = publishes(acts)
    for pub in pubs:  # never fails open: an unverifiable grant denies
        site, doms = str(pub.get("site_id") or ""), pub.get("customDomains")
        if not doms:
            continue
        try:
            if grant_ok(site, doms):
                continue
            unreadable = False
        except Exception:
            unreadable = True
        return deny("production", production_reason(p, site, doms, unreadable))
    try:
        return pre_webflow_rest(p, tool, inp, acts, pubs)
    except Exception:
        return None


def pre_webflow_rest(p, tool, inp, acts, pubs):
    main_session = not p.get("agent_id")
    with locked_state(key_of(p)) as st:
        since = started(p, st)
        job = st.get("job_id")
        # gate 2, main session: one deny per session, never a validation
        # Any route without a job (main session, webflow-fix) takes it from its brief, so the
        # own-lock and per-job report checks in gate 1 apply there too. flowsmith gets its job
        # from brief_gate in the frontmatter hook.
        if not job and is_write(tool, acts):
            brief = find_doc("brief.md", since)
            if brief is not None:
                st["brief"], st["job_id"] = str(brief), job_of(brief.parent)
                job = st["job_id"]
            elif main_session and p.get("agent_type") != "flowsmith" and not st.get("brief_asked"):
                st["brief_asked"] = True
                return deny("brief-main", (
                    "First Webflow write in this session: flowsmith SYSTEM.md applies to inline work, "
                    "so write a brief first. Mint a job id (`python3 ~/.claude/lib/agent_runtime.py "
                    "jobid flowsmith`), write ~/.claude/_scratch/YYYY-MM-<job_id>/brief.md with "
                    "`LESSONS IN PLAY:`, `ACCEPTANCE:` and `VERIFICATION:` lines (the full brief for "
                    "build work), then retry. This gate asks once per session."))
        # gate 5: snapshots before destructive removals
        folder = tilde(SNAPSHOTS / (job or "<job_id>"))
        for a in acts:
            if "remove_element" in a:
                page = inp.get("pageId")
                if page and not any(fresh(f, since) for f in SNAPSHOTS.glob(f"*/{page}.json")):
                    return deny("snapshot", (
                        f"remove_element on page {page} needs a snapshot first: rollback is a rebuild "
                        f"from it. Save this page's get_all_elements tree to {folder}/{page}.json, "
                        "then retry."))
            if isinstance(a.get("remove_style"), dict) and a["remove_style"].get("style_name"):
                name = str(a["remove_style"]["style_name"])
                quoted = json.dumps(name)
                if not any(fresh(f, since) and quoted in f.read_text(errors="replace")
                           for f in SNAPSHOTS.glob("*/styles.json")):
                    return deny("snapshot", (
                        f"remove_style {quoted} needs a snapshot first. Save query_styles for it with "
                        "include_properties: true, include_breakpoints listing all seven breakpoints "
                        "(main, tiny, small, medium, large, xl, xxl), and include_base_pseudos and "
                        "include_breakpoints_pseudos each listing every pseudo state the schema allows "
                        "(the defaults return the base breakpoint only and no pseudo states), to "
                        f"{folder}/styles.json (add to the file if it exists), then retry."))
        # gate 1: staging parameters, lock and spacing
        for pub in pubs:
            reason = publish_rule(pub, job, not main_session)
            if reason:
                return deny("publish", reason)
    return None


def publish_results(response) -> dict:
    """{label: landed} for every publish_site entry in a Webflow MCP response."""
    found = {}

    def visit(node):
        if isinstance(node, dict):
            if node.get("action") == "publish_site":
                found[node.get("label")] = "result" in node and "error" not in node
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)
        elif isinstance(node, str) and "publish_site" in node:
            for chunk in [node] + node.splitlines():
                try:
                    visit(json.loads(chunk))
                    break
                except ValueError:
                    continue

    visit(response)
    return found


def post_webflow(p):
    acts = actions(p.get("tool_input"))
    pubs = [(a.get("label"), a["publish_site"]) for a in acts if isinstance(a.get("publish_site"), dict)]
    if not pubs:
        return None
    landed = publish_results(p.get("tool_response"))
    sites = [str(pub.get("site_id")) for label, pub in pubs if landed.get(label) is True]
    if not sites:
        return None
    PUBLISHES.parent.mkdir(parents=True, exist_ok=True)
    with open(PUBLISHES.with_suffix(".json.flock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        times = load_json(PUBLISHES, {})
        for site in sites:
            times[site] = {"at": time.time(), "by": key_of(p)}
        tmp = PUBLISHES.with_suffix(".tmp")
        tmp.write_text(json.dumps(times, indent=1))
        tmp.replace(PUBLISHES)
    return None


def wrapup(tool, inp) -> bool:
    """Calls that save state and hand back, allowed past the cap. Never an approval grant."""
    if tool == "Read" or tool in HANDBACK:
        return True
    if tool in FILE_TOOLS:
        fp = str(inp.get("file_path") or inp.get("notebook_path") or "")
        return not under(fp, GRANTS) and (under(fp, SCRATCH) or under(fp, ROOT / "state")
                                            or Path(fp).name in WRAPUP_FILES)
    return tool == "Bash" and bool(WRAPUP_BASH.search(str(inp.get("command") or "")))


def cap_message(agent, n, cap, st):
    folder = (tilde(Path(st["brief"]).parent) if st.get("brief")
              else "~/.claude/_scratch/YYYY-MM-<job_id>")
    if agent == "flowsmith":
        return (f"Tool-call cap reached ({n} of {cap} for this dispatch). Start nothing new: only "
                f"state-saving calls are allowed now. Write {folder}/continue.md (what is done and "
                "live, the pending diff, page and element ids in use, open defects with evidence "
                "paths, the exact scope for the next dispatch) and handoff.md, run `agent_runtime.py "
                "record flowsmith <job_id> outcome=partial ...` and `unlock <job_id>`, set "
                "`flowsmith_manifest.py update <project> --set next_wave=...`, then end with your "
                "report, STAGED: NOT LIVE at the top if writes are unpublished.")
    return (f"Tool-call cap reached ({n} of {cap} for this dispatch). Start nothing new: only "
            "state-saving calls are allowed now. Commit on the feature branch, update "
            "specs/NNN-<slug>/tasks.md (tick the done tasks; note the open task, blockers and next "
            "step under it), run `agent_runtime.py record wright <job_id> outcome=partial ...`, then "
            "end with your Final report.")


def warn_message(agent, n, cap):
    if agent == "flowsmith":
        return (f"{n} of {cap} tool calls used in this dispatch. Start no new item: finish the section "
                "in flight, run the wave's one staging publish, verify it, write handoff.md, unlock, "
                f"record outcome=partial and set next_wave. After {cap} calls only state-saving calls "
                "are allowed.")
    return (f"{n} of {cap} tool calls used in this dispatch. Finish the task in flight at its next "
            "green test, commit, update specs/NNN-<slug>/tasks.md, record outcome=partial and end "
            f"with your Final report. After {cap} calls only state-saving calls are allowed.")


def brief_gate(p, key):
    with locked_state(key) as st:
        if st.get("brief") and Path(st["brief"]).exists():
            st["wrote"] = True
            return None
        hits = fresh_docs("brief.md", started(p, st))
        mine = [f for f in hits if st.get("own_brief") == str(f.parent)]
        if not hits:
            return deny("brief", (
                "No brief for this dispatch yet. Run the flowsmith-loop ritual (`brief`, or `brief "
                "--lite` for a fix of 3 items or fewer) and write it with the Write tool to "
                "~/.claude/_scratch/YYYY-MM-<job_id>/brief.md; a full brief must pass "
                f"`{LINT_CMD} --plan <file>`. Then retry this write."))
        if not mine and len(hits) > 1:
            return deny("brief", (
                f"{len(hits)} briefs were written since this dispatch began "
                f"({', '.join(sorted(f.parent.name for f in hits))}), so the gate cannot tell which is "
                "yours. Write yours with the Write tool to ~/.claude/_scratch/YYYY-MM-<job_id>/brief.md "
                "under your own job id, then retry this write."))
        brief = (mine or hits)[0]
        problems = brief_problems(brief)
        if problems:
            return deny("brief", (
                f"{tilde(brief)} does not pass yet: {'; '.join(problems[:6])}. Fix it (a full brief "
                f"is checked by `{LINT_CMD} --plan {tilde(brief)}`), then retry this write."))
        st.update(brief=str(brief), job_id=job_of(brief.parent), wrote=True)
    return None


def spec_gate(inp):
    fp = str(inp.get("file_path") or inp.get("notebook_path") or "")
    if not CODE_EXT.search(fp):
        return None
    path, home = Path(fp).resolve(), CODE_HOME.resolve()
    if home not in path.parents:
        return None
    repo = next((d for d in path.parents if d != home and home in d.parents and (d / ".git").exists()), None)
    # packet.json lands in specs/ at intake, so the folder alone proves nothing; the spec is the gate.
    if repo is None or any(any((repo / "specs").glob(f"*/{n}")) for n in ("spec.md", "proposal.md")):
        return None
    return deny("spec", (
        f"Spec before code: {tilde(repo)} has no specs/NNN-<slug>/spec.md or proposal.md. Write "
        "specs/NNN-<slug>/proposal.md, spec.md and tasks.md from "
        f"~/.claude/reference/common/spec-template/ first, then write {path.name}."))


def own_brief(tool, inp):
    """The _scratch folder of a brief.md this call writes or names, else None."""
    if tool in FILE_TOOLS:
        fp = Path(os.path.normpath(str(inp.get("file_path") or "")))
        return str(fp.parent) if fp.name == "brief.md" and fp.parent.parent == SCRATCH else None
    m = SCRATCH_BRIEF.search(str(inp.get("command") or "")) if tool == "Bash" else None
    return str(SCRATCH / m.group(1)) if m else None


def pre_grant(p):
    """Subagents never write an approval grant: it records the operator's yes, so only the main session
    writes it after the operator gives it."""
    if not p.get("agent_id"):
        return None
    tool = p.get("tool_name", "")
    inp = p.get("tool_input") if isinstance(p.get("tool_input"), dict) else {}
    if tool in FILE_TOOLS:
        hit = under(inp.get("file_path") or inp.get("notebook_path") or "", GRANTS)
    else:
        hit = tool == "Bash" and bool(GRANT_CMD.search(str(inp.get("command") or "")))
    if not hit:
        return None
    return deny("grant", (
        f"Subagents cannot write or run commands under {tilde(GRANTS)}/: a grant there records "
        "the operator's yes, and only the main session writes it after the operator gives it. Read a grant with the "
        "Read tool. For a live publish, end your report with the APPROVAL NEEDED card instead."))


def pre_github(p):
    """The public flowsmith repo takes changes only through the sync tool and a git push, where
    its pre-push hook scans for client names, ids and domains. A GitHub MCP write skips that."""
    inp = p.get("tool_input") if isinstance(p.get("tool_input"), dict) else {}
    target = (str(inp.get("owner") or "").lower(), str(inp.get("repo") or "").lower().removesuffix(".git"))
    if p.get("tool_name") not in GITHUB_WRITES or target != PUBLIC_REPO:
        return None
    return deny("public-repo", (
        f"{p.get('tool_name')} to {'/'.join(PUBLIC_REPO)} is blocked: a GitHub MCP write skips the "
        "pre-push scan that keeps client names, site ids and domains out of the public repo. Use "
        "`python3 ~/.claude/scripts/flowsmith_public_sync.py --dry-run`, then `--apply` (it writes the "
        "sanitised package into ~/Code/tools/flowsmith and never commits), then commit and `git push` "
        "there, where the pre-push hook scans the push. The push is a public publish: it needs "
        "the operator's yes first."))


def pre_agent(p, agent):
    key = key_of(p)
    n = bump(key)
    cap, warn_pct = caps(agent)
    tool = p.get("tool_name", "")
    inp = p.get("tool_input") if isinstance(p.get("tool_input"), dict) else {}
    if n > cap + HARD_EXTRA and tool not in HANDBACK:
        return deny("cap", (
            f"Hard stop: {n} tool calls, {HARD_EXTRA} past the cap of {cap}. Make no more tool calls "
            "except the one that hands back your report. End now with that report: what is done, "
            "what is live, what is staged, and where the next dispatch starts."))
    if n > cap and not wrapup(tool, inp):
        with locked_state(key) as st:
            return deny("cap", cap_message(agent, n, cap, st))
    if agent == "wright" and tool in HANDBACK:
        with locked_state(key) as st:
            st["report_ok"] = report_ok(texts(inp))
    mine = own_brief(tool, inp) if agent == "flowsmith" else None
    if mine:
        with locked_state(key) as st:
            st["own_brief"] = mine
    if agent == "flowsmith" and tool.startswith(WEBFLOW) and is_write(tool, actions(inp)):
        out = brief_gate(p, key)
        if out:
            return out
    if agent == "wright" and tool in FILE_TOOLS:
        out = spec_gate(inp)
        if out:
            return out
    if n >= cap * warn_pct // 100:
        with locked_state(key) as st:
            if not st.get("warned"):
                st["warned"] = True
                return context(warn_message(agent, n, cap))
    return None


def stop_agent(p, agent):
    if p.get("stop_hook_active"):
        return None
    key = key_of(p)
    with locked_state(key) as st:
        if st.get("stop_blocked"):
            return None
        if agent == "flowsmith":
            cap, _ = caps(agent)
            if not st.get("wrote") or calls(key) > cap + HARD_EXTRA:
                return None
            prefer = Path(st["brief"]).parent if st.get("brief") else None
            handoff = find_doc("handoff.md", started(p, st), prefer)
            if handoff is None:
                folder = tilde(prefer) if prefer else "~/.claude/_scratch/YYYY-MM-<job_id>"
                reason = ("This dispatch made Webflow writes but wrote no handoff.md. Run the critique "
                          f"pass, write the HANDOFF REPORT with its eight headings to {folder}/handoff.md, "
                          f"run `{LINT_CMD} --handoff` on it until it passes, then finish your report "
                          "(unpublished work goes at the top as STAGED: NOT LIVE).")
            else:
                fails = lint(handoff, "handoff")
                if not fails:
                    return None
                reason = (f"{tilde(handoff)} fails the handoff lint: {'; '.join(fails[:6])}. Fix it, "
                          f"rerun `{LINT_CMD} --handoff {tilde(handoff)}` until it passes, then finish "
                          "your report.")
        elif agent == "wright":
            # a report handed back through SubagentHandback is not in last_assistant_message
            if st.get("report_ok") or report_ok(p.get("last_assistant_message") or ""):
                return None
            reason = ("Your final report has no `## Verification` section. Add it: each acceptance "
                      "criterion with the command, test run or screenshot that proves it, the security "
                      "pass and the fresh-clone install. Anything you could not verify goes there too. "
                      "Then finish.")
        else:
            return None
        st["stop_blocked"] = True
    return {"_gate": "stop", "decision": "block", "reason": reason}


def main(argv) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    raw = sys.stdin.read()
    p = {}
    try:
        p = json.loads(raw) if raw.strip() else {}
        if mode == "pre-webflow":
            out = pre_webflow(p)
        else:
            try:
                handler = {"post-webflow": post_webflow, "pre-grant": pre_grant, "pre-github": pre_github,
                           "pre-agent": pre_agent, "stop-agent": stop_agent}.get(mode)
                out = handler(p, *argv[2:3]) if handler else None
            except Exception:
                out = None
    except Exception:
        out = None
        if mode == "pre-webflow" and "publish_site" in raw and PROD_RAW.search(raw):
            out = deny("production", (
                "Production publish blocked: this call names customDomains and the gate could not "
                "verify an approval grant. Do not retry; raise the APPROVAL NEEDED card for the operator."))
    if out:
        gate = out.pop("_gate", None)
        if gate:
            p = p if isinstance(p, dict) else {}
            with suppress(Exception):  # the gate event log never decides anything
                log({"event": "block" if gate == "stop" else "deny", "gate": gate, "mode": mode,
                     "agent": p.get("agent_type") or "main", "key": key_of(p), "tool": p.get("tool_name")})
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
