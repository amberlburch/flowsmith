#!/usr/bin/env python3
"""Mechanical gate for the FLOWSMITH ledger, build plans, and handoff reports.

Emits a pass rate so /autoresearch has a countable metric to optimise against.
Exit 0 = 100%, exit 1 = anything failed.
"""
import argparse
import json
import re
import sys
from pathlib import Path

LEDGER = Path.home() / ".claude" / "agents" / "flowsmith" / "learned-rules.md"
CATEGORIES = {"OMIT", "STRUCT", "NAME", "RESP", "FID", "STATE", "MOTION", "A11Y", "PERF",
              "SEO", "CMS", "API", "LIVE", "PROC", "COMM"}
GATES = {"RITUAL", "BUILD", "CRITIQUE"}

IDX_START = "<!-- LEDGER-INDEX:START -->"
IDX_END = "<!-- LEDGER-INDEX:END -->"

# A guardrail must not hide behind these.
VAGUE = re.compile(
    r"\b(be (more )?careful|make sure|try to|remember to|pay attention|keep in mind|"
    r"be mindful|be aware|take care|don't forget|do better|think about|"
    r"as needed|where appropriate|if possible|should work|looks? (right|fine|good))\b",
    re.I)
# ...and must anchor on something concrete: a number, a code token, or a named check.
ANCHOR = re.compile(
    r"(\d|`[^`]+`|published|curl|query_|breakpoint|getBoundingClientRect|dod\.md|"
    r"grep|assert|screenshot|token|variable|Lighthouse|contrast|axe|publish)", re.I)

LEGACY = re.compile(r"^(\d+)\.\s+\[([A-Z]+)\]\s+\[([A-Z0-9]+)\|([A-Z,]+)\]\s+(.+)$")
SUPERSEDED = re.compile(r"^(\d+)\.\s+\[SUPERSEDED\]")
# Separator is ":" (the SKILL.md template, and the house no-dash rule) or the legacy "—".
# Accepting only "—" meant a template-following absorb wrote an entry the parser skipped.
LHEAD = re.compile(r"^###\s+L-(\d+)\s*(?::|\s—)\s+(.+?)\s+\[([A-Z0-9]+)\|([A-Z,]+)\]\s*$")
FIELDS = ["Context", "What went wrong", "Root cause", "Guardrail", "Detection"]

# The runner's report.json is the verification evidence (webflow-verify section 1). lighthouse_audit
# has no performance category, so a performance number needs its own saved trace or Lighthouse JSON.
# A claim is a metric next to its value ("LCP 2.1s", "performance score: 94"), never a version or a
# page count, and a line saying "not measured" is the honest path, not a claim.
PERF_CLAIM = re.compile(r"\b(?:LCP|CLS|TBT)\b\s*(?:[:=<>]|is|of|was)?\s*\d"
                        r"|(?i:\b(?:lighthouse|performance)(?:\s+performance)?\s+score\b)"
                        r"\s*(?:[:=]|is|of|was)?\s*\d")
PERF_FILE = re.compile(r"_scratch/\S*?[^/\s]*(trace|lh|lighthouse)[^/\s]*\.json", re.I)
# A cited report.json that exists on disk is read (F1): absolute, ~ or $HOME, or relative from
# _scratch/. The newest one for the handoff's job must not be an ERROR run, and every check it
# fails or errored must be named under Known limitations (an escalation, or a layer not run).
REPORT_PATH = re.compile(r"(?:~|\$HOME|(?<![\w.])/|_scratch/)[^\s`'\"()<>\[\]]*report\.json")
JOB = re.compile(r"[a-z][a-z-]*-\d{8}-\d{4}-[0-9a-f]{4}")  # agent_runtime.py jobid

# The ledger is read through its LEDGER-INDEX, never whole (F16). These files route agents to it.
POINTER_GLOBS = ("skills/webflow-*/**/*.md", "skills/flowsmith-loop/**/*.md",
                 "agents/flowsmith/*.md", "agents/webflow-fix/*.md")
LEDGER_REF = re.compile(r"flowsmith/learned-rules\.md")
READ_VERB = re.compile(r"\bread\b", re.I)


class Report:
    def __init__(self):
        self.passed = 0
        self.fails = []

    def check(self, ok, msg):
        if ok:
            self.passed += 1
        else:
            self.fails.append(msg)

    @property
    def total(self):
        return self.passed + len(self.fails)

    @property
    def rate(self):
        """Floored to one decimal place, so a run with any failed check never prints 100.0%."""
        return 100.0 if not self.total else (1000 * self.passed // self.total) / 10


def summarise(body, limit=95):
    """Index title: first clause of the rule, cut on a word boundary."""
    text = re.sub(r"\s+", " ", body).strip()
    text = re.sub(r"\s*\[promote\]\s*", " ", text)
    text = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}[^)]*\)\s*$", "", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def parse(path):
    """Return (entries, index_lines, raw_lines). Entry = dict with num/cat/gates/title/fields."""
    lines = path.read_text().splitlines()
    entries, index, in_index, i = [], [], False, 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == IDX_START:
            in_index = True
        elif line.strip() == IDX_END:
            in_index = False
        elif in_index:
            if line.strip():
                index.append(line.strip())
        elif m := LEGACY.match(line):
            entries.append({"num": int(m.group(1)), "cat": m.group(3),
                            "gates": m.group(4).split(","), "title": summarise(m.group(5)),
                            "guardrail": m.group(5), "fields": None, "line": i + 1,
                            "promote": "[promote]" in m.group(5)})
        elif m := SUPERSEDED.match(line):
            entries.append({"num": int(m.group(1)), "superseded": True, "line": i + 1})
        elif m := LHEAD.match(line):
            # Entries write fields either as "- Field: value" bullets or as
            # "**Field.** value" paragraphs (the style every entry L-41..L-75
            # actually uses; audited 2026-08-17). Accept both, and accumulate
            # continuation lines so multi-paragraph fields keep their anchors.
            fields, j, cur = {}, i + 1, None
            bold = re.compile(
                r"^\*\*(Context|What went wrong|Root cause|Guardrail|Detection)\.?\*\*\s*(.*)$")
            while j < len(lines) and not lines[j].startswith("###"):
                if fm := re.match(r"^-\s+([^:]+):\s*(.+)$", lines[j]):
                    cur = fm.group(1).strip()
                    fields[cur] = fm.group(2).strip()
                elif bm := bold.match(lines[j]):
                    cur = bm.group(1).strip()
                    fields[cur] = bm.group(2).strip()
                elif cur and lines[j].strip():
                    fields[cur] += " " + lines[j].strip()
                j += 1
            entries.append({"num": int(m.group(1)), "cat": m.group(3),
                            "gates": m.group(4).split(","), "title": m.group(2),
                            "guardrail": fields.get("Guardrail", ""), "fields": fields,
                            "line": i + 1, "promote": "[promote]" in "".join(fields.values())})
            i = j - 1
        i += 1
    return entries, index, lines


def index_line(e):
    return f"{e['num']} [{e['cat']}|{','.join(e['gates'])}] {e['title']}"


def lint_ledger(path, rep):
    if not path.exists():
        rep.check(False, f"ledger not found: {path}")
        return []
    entries, index, lines = parse(path)
    rep.check(bool(entries), "ledger has no parseable entries")

    live = [e for e in entries if not e.get("superseded")]
    for e in live:
        at = f"L-{e['num']} (line {e['line']})"
        rep.check(e["cat"] in CATEGORIES, f"{at}: unknown category '{e['cat']}'")
        rep.check(all(g in GATES for g in e["gates"]),
                  f"{at}: unknown gate in '{','.join(e['gates'])}'")
        g = e["guardrail"]
        rep.check(not VAGUE.search(g), f"{at}: guardrail is vague, not checkable")
        rep.check(bool(ANCHOR.search(g)),
                  f"{at}: guardrail names no concrete anchor (number, code token, or named check)")
        if e["fields"] is not None:
            for f in FIELDS:
                rep.check(f in e["fields"] and len(e["fields"][f]) > 10,
                          f"{at}: missing or stub field '{f}'")

    # Numbering: unique, and every gap in the run explicitly superseded.
    nums = [e["num"] for e in entries]
    rep.check(len(nums) == len(set(nums)), f"duplicate rule numbers: "
              f"{sorted({n for n in nums if nums.count(n) > 1})}")
    if nums:
        missing = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))
        rep.check(not missing, f"numbering gaps not marked [SUPERSEDED]: {missing}")

    # Near-duplicate guardrails should be merged into one stronger rule.
    def toks(s):
        return {w for w in re.findall(r"[a-z_]{4,}", s.lower())}
    for a in range(len(live)):
        for b in range(a + 1, len(live)):
            ta, tb = toks(live[a]["guardrail"]), toks(live[b]["guardrail"])
            if len(ta) < 8 or len(tb) < 8:
                continue
            j = len(ta & tb) / len(ta | tb)
            rep.check(j <= 0.62, f"L-{live[a]['num']} and L-{live[b]['num']}: "
                                 f"guardrails {j:.0%} overlapping, merge into one stronger rule")

    expected = [index_line(e) for e in live]
    detail = ""
    if index != expected:
        if len(index) != len(expected):
            detail = f" (have {len(index)} lines, expect {len(expected)})"
        else:
            i = next(k for k in range(len(expected)) if index[k] != expected[k])
            detail = f" (line {i + 1}: have {index[i]!r}, expect {expected[i]!r})"
    rep.check(index == expected,
              f"index block out of sync with entry bodies, run --reindex{detail}")
    return entries


def reindex(path):
    entries, _, lines = parse(path)
    live = [e for e in entries if not e.get("superseded")]
    block = [IDX_START, ""] + [index_line(e) for e in live] + ["", IDX_END]
    try:
        s = next(i for i, l in enumerate(lines) if l.strip() == IDX_START)
        e = next(i for i, l in enumerate(lines) if l.strip() == IDX_END)
        lines[s:e + 1] = block
    except StopIteration:
        print(f"no {IDX_START} markers in {path}", file=sys.stderr)
        return 1
    path.write_text("\n".join(lines) + "\n")
    print(f"reindexed {len(live)} entries in {path}")
    return 0


def lint_plan(path, rep):
    text = path.read_text()
    for field in ["GOAL", "ACCEPTANCE CRITERIA", "LEDGER LESSONS IN PLAY", "STRUCTURE",
                  "RESPONSIVE PLAN", "STATES & INTERACTIONS", "CMS/DATA", "RISKS", "VERIFICATION",
                  "DESIGN COVERAGE"]:
        # [ \t]* not \s*: \s crosses newlines, so an empty field would capture the next line.
        m = re.search(rf"^{re.escape(field)}:[ \t]*(.*)$", text, re.M)
        rep.check(m is not None, f"plan missing field '{field}'")
        if m:
            rep.check(len(m.group(1).strip()) > 12,
                      f"plan field '{field}' is empty or a stub")
    rep.check(not VAGUE.search(text), "plan contains vague, unverifiable language")


def cited_reports(path, text):
    """{report.json: (mtime, job, verdict, failing ids, errored ids)} for every cited report on
    disk. A relative _scratch/ path resolves beside the handoff's own _scratch, else in ~/.claude."""
    root = next((p.parent for p in path.resolve().parents if p.name == "_scratch"), LEDGER.parents[2])
    found = {}
    for cite in REPORT_PATH.findall(text):
        f = root / cite if cite.startswith("_scratch/") else Path(cite.replace("$HOME", "~", 1)).expanduser()
        try:
            mtime = f.stat().st_mtime if f.is_file() else None
        except OSError:
            mtime = None
        if mtime is None:
            continue
        try:
            data = json.loads(f.read_text())
            results = [r for r in data.get("results") or [] if isinstance(r, dict)]
            ids = [sorted({str(r.get("check")) for r in results if r.get("status") == s})
                   for s in ("fail", "error")]
            found[f] = (mtime, str(data.get("job") or ""), data.get("verdict"), *ids)
        except (OSError, ValueError, AttributeError):
            found[f] = (mtime, "", "unreadable", [], [])
    return found


def evidence_reports(path, reports):
    """The newest cited report for the handoff's job (its folder is YYYY-MM-<job_id>). When none
    is this job's, or the job is unknown, the newest per job, since any of them may be the evidence."""
    job = re.sub(r"^\d{4}-\d{2}-", "", path.resolve().parent.name)
    groups = {}
    for f, (mtime, rjob, *_) in reports.items():
        mine = JOB.fullmatch(job) and (rjob == job or rjob.startswith(job + "-") or job in f.parent.name)
        key = "mine" if mine else m.group(0) if (m := JOB.match(rjob)) else rjob or str(f.parent)
        groups.setdefault(key, []).append(f)
    if "mine" in groups:
        groups = {"mine": groups["mine"]}
    return sorted(max(fs, key=lambda f: reports[f][0]) for fs in groups.values())


def names(check, text):
    """A whole check id, not a substring: 'layout.overflow-xy' does not name 'layout.overflow-x'."""
    return re.search(rf"(?<![\w.-]){re.escape(check)}(?![\w-]|\.\w)", text) is not None


def lint_handoff(path, rep):
    text, limits = path.read_text(), ""
    for section in ["What I built", "Decisions & reasoning", "Responsive behaviour",
                    "States & interactions", "Self-critique results", "Assumptions I made",
                    "Known limitations", "Ledger lessons applied"]:
        m = re.search(rf"^##\s+{re.escape(section)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
        rep.check(m is not None, f"handoff missing section '{section}'")
        if m and section == "Known limitations":
            limits = m.group(1)
        if m and section == "Self-critique results":
            rep.check(len(m.group(1).strip()) > 30,
                      "handoff self-critique-results is empty: the pass did not happen")
    rep.check(not re.search(r"\bshould (work|be fine)\b|\blooks? (right|fine|good)\b", text, re.I),
              "handoff asserts instead of evidencing ('should work' / 'looks right')")
    # Structural, not lexical: a done/complete keyword check can't tell the verb "fixed"
    # from the adjective ("a fixed design constant"), and a lint that cries wolf gets ignored.
    # LIVE-category judgement stays with critique.md, where a reader applies it.
    rep.check(bool(re.search(r"report\.json|STAGED", text)),
              "handoff cites no webcheck report.json and carries no STAGED marker")
    reports = cited_reports(path, text)
    for f in evidence_reports(path, reports):
        _, _, verdict, failing, errored = reports[f]
        if verdict not in ("PASS", "FAIL"):
            rep.check(False, f"newest cited webcheck report {f} is {verdict}, not evidence: "
                             "rerun the runner and cite the new report.json")
            continue
        unnamed = ([f"fails {c}" for c in failing if not names(c, limits)]
                   + [f"errored {c}" for c in errored if not names(c, limits)])
        rep.check(not unnamed, f"newest cited webcheck report {f}: {', '.join(unnamed)}. Fix and "
                               "rerun the runner, or name each under Known limitations: a failing "
                               "check with its escalation evidence, an errored one as a layer not run")
    if any(PERF_CLAIM.search(line) for line in text.splitlines()
           if "not measured" not in line.lower()):
        rep.check(bool(PERF_FILE.search(text)),
                  "handoff states a performance number without its saved trace or Lighthouse JSON path")


def lint_pointers(root, rep):
    """Every instruction to read the flowsmith ledger goes through its LEDGER-INDEX."""
    ledger = root / "agents" / "flowsmith" / "learned-rules.md"
    for pattern in POINTER_GLOBS:
        for f in sorted(root.glob(pattern)):
            if f == ledger:
                continue
            text, bad, pos = f.read_text(errors="replace"), [], 0
            for para in re.split(r"\n[ \t]*\n", text):
                start = text.index(para, pos)
                pos = start + len(para)
                if LEDGER_REF.search(para) and READ_VERB.search(para) and "LEDGER-INDEX" not in para:
                    bad.append(text.count("\n", 0, start) + 1)
            rep.check(not bad, f"{f.relative_to(root)}:{','.join(map(str, bad))}: tells the agent to "
                               f"read the flowsmith ledger whole; point it at the LEDGER-INDEX selection "
                               f"(/flowsmith-loop brief)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="lint the ledger")
    p.add_argument("--ledger", type=Path, default=LEDGER)
    p.add_argument("--pointers", action="store_true",
                   help="lint Webflow skill and agent files for whole-ledger read instructions")
    p.add_argument("--reindex", action="store_true", help="regenerate the index block")
    p.add_argument("--plan", type=Path)
    p.add_argument("--handoff", type=Path)
    a = p.parse_args()

    if a.reindex:
        return reindex(a.ledger)

    rep = Report()
    if a.all or not (a.plan or a.handoff or a.pointers):
        lint_ledger(a.ledger, rep)
    if a.pointers:
        lint_pointers(LEDGER.parents[2], rep)
    if a.plan:
        lint_plan(a.plan, rep)
    if a.handoff:
        lint_handoff(a.handoff, rep)

    for f in rep.fails:
        print(f"FAIL  {f}")
    print(f"\npass_rate {rep.rate:.1f}%  ({rep.passed}/{rep.total} checks)")
    return 1 if rep.fails else 0


if __name__ == "__main__":
    sys.exit(main())
