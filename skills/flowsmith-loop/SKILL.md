---
name: flowsmith-loop
description: 'The self-improvement gate for FLOWSMITH Webflow builds. Three modes: `brief` runs the start-of-task ritual (read the ledger index, restate relevant lessons, inventory what exists, emit a build plan with risks and verification), `critique` runs the pre-handoff red-team against externally-grounded evidence and emits the handoff report, `absorb` converts developer feedback into a checkable ledger guardrail via root-cause diagnosis. Measured on first-pass approval rate. Triggers on "/flowsmith-loop", "start-of-task ritual", "run the critique pass", "absorb this feedback", "the developer sent feedback on the build", "before handoff", "add this to the ledger".'
version: 1.0.0
argument-hint: brief <task> | critique | absorb "<feedback>"
user-invocable: true
---

# flowsmith-loop: the compounding gate

FLOWSMITH is not measured on finishing tasks. It is measured on one thing: **the rate at which work passes human review with zero edits, trending to 100%.**

A mistake is a signal. Making the same mistake twice is the failure. This skill is the loop that makes the difference: understand, plan to standard, build, red-team, hand off, absorb the correction as a permanent guardrail. The critique step is never skipped and feedback is never treated as disposable.

**Standards live in `agents/flowsmith/dod.md`. This skill does not restate them.** It supplies the ritual, the red-team method, the report format, and the absorption protocol. Restating the standards would create a second source of truth that drifts, which has already happened once in this workspace between `reference_webflow_api_traps.md` and the agent ledger.

## When to Use

- **`brief`** before any FLOWSMITH job over 8 tool calls (the existing PlanArtifact threshold). Every phase of `/webflow-build` counts. A fix of 3 items or fewer that adds no section or page and touches no shared class, component or site-wide code may use **`brief --lite`** instead.

This skill is preloaded into FLOWSMITH through its `skills:` frontmatter, so the ritual is in context from the first turn; there is nothing to fetch. The 2026-09-27 audit found the brief in 3% of 126 dispatches while this file was unreachable by invocation (L-86).
- **`critique`** as the exit condition on every phase and every handover, after `/webflow-verify` is green and before anything is reported done.
- **`absorb`** the moment a developer, CMO or client returns feedback, and whenever you catch your own mistake mid-task.

Not for: mechanical verification (that is `/webflow-verify`), workspace-wide memory consolidation (`/consolidate`), or scoring a skill's output (`/agent-review`).

## The vocabulary (fixed, never improvised)

Every category tag and gate name comes from this closed set. Definitions and the full gate mapping live in `references/taxonomy.md`; these are the only valid values, in every mode, including when the references are unavailable:

- **Categories (15):** `OMIT` `STRUCT` `NAME` `RESP` `FID` `STATE` `MOTION` `A11Y` `PERF` `SEO` `CMS` `API` `LIVE` `PROC` `COMM`
- **Gates (3):** `RITUAL` `BUILD` `CRITIQUE`
- **Tag form:** `[CATEGORY|GATE]`, e.g. `[FID|CRITIQUE]` or `[STRUCT|BUILD,CRITIQUE]`

Do not invent tags (`STYLE`, `RESPONSIVE`, `COPY` are not categories: they are `FID`, `RESP`, and `FID`/`COMM` respectively). `ledger_lint.py` rejects anything outside this set.

## Modes

### `brief <task>`: start-of-task ritual

Non-negotiable, and done in working notes before a single class or element is created. Most repeat errors come from skipping this.

1. **Read the ledger index.** `agents/flowsmith/learned-rules.md`, the block between the `LEDGER-INDEX` markers. Map the task to categories via `references/taxonomy.md`, then read in full only the entries whose `fires:` gate and category match. Restate the 3 to 5 most relevant in one line each, naming how you will avoid each. If a past pattern could apply here, name it now.
2. **Restate the task** in your own words with its acceptance criteria. Where criteria are missing (breakpoints, states, CMS behaviour, motion spec), list your assumptions explicitly and labelled as assumptions.
3. **Inventory what exists.** Site variables, style classes, components, CMS collections, and both custom-code surfaces. Reuse before create. Introducing a duplicate style when one exists is a defect, not a shortcut.
3b. **Inventory what SHOULD exist.** Read `<pack>/design-inventory.json` (figma-translation intake step 1; its path is in the manifest) and restate the section count per page per viewport that this task touches. If no design inventory exists for a Figma-input project, generating it IS the first task: without it every gate counts only what was built, and a designed section that was never built passes them all. The webcheck runner's `completeness` check reads this file, so its section ids are the `section_[id]` classes the build must use.
4. **Hard stop on missing design source.** If you cannot see the Figma file or reference set at the fidelity needed to match spacing, type and colour exactly, stop and stage operator moment 3 or 3b. Guessing pixel values is a top cause of review failure. Do not proceed on a guess.
5. **Emit the BUILD PLAN block.**

```
GOAL: <what the human actually wants, one sentence>
ACCEPTANCE CRITERIA: <what done looks like, including breakpoints and states>
LEDGER LESSONS IN PLAY: <L-numbers + the one-line guard for each>
STRUCTURE: <element tree, marking reused vs new classes>
RESPONSIVE PLAN: <the canonical sweep, 320 to 1920 (webcheck's default widths): what changes where, and which design frame each width answers to>
STATES & INTERACTIONS: <hover, focus, active, disabled, loading, empty, motion spec: motion is ALWAYS custom code (GSAP), never IX2 (no API can author it) and never IX3 (banned except its pilot on the eval fixture site, webflow-motion)>
CMS/DATA: <collections, bindings, empty-state handling>
RISKS: <what could break, what you are unsure about>
VERIFICATION: <exactly how each criterion gets proven before handoff>
DESIGN COVERAGE: <n of m design-inventory rows this phase satisfies, and which rows are deliberately out of scope with why>
```

A plan with an empty `RISKS`, `VERIFICATION` or `DESIGN COVERAGE` field is not a plan. `scripts/ledger_lint.py --plan <file>` rejects it. (`DESIGN COVERAGE` may read "no design inventory: reference-input project" on Path B builds: what it may never do is silently omit rows on a Figma-input build; an unnamed row is how a designed section quietly never gets built.)

### `brief --lite`: the small-fix ritual

Same purpose, three lines, still before the first write. It exists so a two-item fix gets a ritual instead of none; it is not a way around the full brief. If any item touches a shared class, a component, a global embed or site-wide custom code, the blast radius is site-wide and the full brief applies.

```
LESSONS IN PLAY: <L-numbers with a one-line guard each, or "none match" plus the categories checked>
ACCEPTANCE: <what done looks like for each item, naming breakpoints>
VERIFICATION: <the published-page check that proves each item>
```

### `critique`: pre-handoff red-team

1. Walk `references/critique.md` for every category the change touched. Each row names its evidence source. Fix what you find.
2. **Open with the category audit:** one line naming which of the 15 categories you walked, and which you skipped with a one-clause reason each. A skipped category without a stated reason is a `PROC` defect.
3. Re-read ledger entries tagged `fires:CRITIQUE` and prove non-repetition for each relevant one.
4. Anything you cannot honestly tick becomes an explicit known limitation with a reason, never a silent omission.
5. **Staged is not done.** A check verified only against staging, or any change not yet re-confirmed on the published URL, is never ticked complete: it is reported **"STAGED: NOT LIVE"** with the owed publish named. This applies inside the checklist rows, not only in the final report.
6. **Emit the HANDOFF REPORT block, with these eight headings exactly as written, all present, in this order.**

```
## What I built
## Decisions & reasoning        <non-obvious structural/naming/motion choices and why>
## Responsive behaviour         <one line per breakpoint>
## States & interactions        <what exists, how to trigger it>
## Self-critique results        <what the red-team caught and fixed: this is the proof the pass happened>
## Assumptions I made           <anything inferred because the spec was silent>
## Known limitations            <what could not be verified, what needs a human decision>
## Ledger lessons applied       <L-numbers actively guarded against>
```

The eight headings are literal strings, checked by grep in that order: keep the ampersand in `## Decisions & reasoning` and `## States & interactions` (never "and"), keep the British `behaviour`, and do not carry the angle-bracket guidance into the heading line.

An empty self-critique-results section means the pass did not happen. `scripts/ledger_lint.py --handoff <file>` fails it, fails a handoff that cites no webcheck `report.json` and carries no `STAGED` marker, fails one whose newest cited `report.json` on disk for its job is an `ERROR` run or holds a failing or errored check id that `## Known limitations` does not name as a whole id (an errored one is a layer not run), and fails a performance number (LCP, CLS or TBT next to a value, a Lighthouse or performance score) with no saved trace or Lighthouse JSON path beside it. A line that says "not measured" is the honest path, not a claim.

Then the one-line test: **would the reviewer approve this with zero edits?** If not confident, go back to step 1.

### `absorb "<feedback>"`: the compounding step

This is the most important work in the loop. Treat every correction as a permanent upgrade, not a patch.

1. **Acknowledge** without defensiveness, excuses or over-apology.
2. **Diagnose root cause, not symptom.** Why was that choice made? What rule or check was missing that let this through? The fix is almost never "do this one thing differently", it is "add or strengthen the check that catches this class of mistake."
3. **Categorise** against `references/taxonomy.md`. **Same category twice means escalate**: strengthen the existing entry and move its gate earlier, rather than appending a parallel rule. A recurrence after the entry exists means the entry was too weak.
4. **Dedup before writing.** `python3 ~/.claude/lib/memory_index.py --dupe "<the rule statement>"`. A flagged near-duplicate gets updated or superseded, never paralleled.
5. **Write the entry** in the five-field L-format below. Tag `[promote]` if it generalises beyond one site, so `/consolidate` sweeps it back to canonical memory.
6. **Re-scan open and related work** for the same pattern and fix it proactively. Do not wait to be told again about the same thing elsewhere.
7. **Close the loop:** restate the lesson, the new guardrail, and where in the process it now fires.
8. **Record the outcome** against the graded handoff's job id, so first-pass approval rate stays honest: `python3 ~/.claude/lib/agent_runtime.py record flowsmith <job_id> outcome=absorb verify_rounds=0 handoff_accepted=false revision_items=<n> note="<one line>"`, the CLI that types and validates the record.

Ledger entry format, appended to `agents/flowsmith/learned-rules.md` (the heading separator is a colon; `ledger_lint.py` also accepts the legacy dash):

```
### L-<n>: <short imperative title>   [CATEGORY|GATE]
- Context: <date, which project, which task>
- What went wrong: <the specific mistake>
- Root cause: <the missing rule or check>
- Guardrail: <the exact checkable rule, and which gate it fires at>
- Detection: <concretely how it gets caught next time>
```

A guardrail is a checkable rule, not a reflection. "Be more careful with spacing" fails lint. "Measure every gap against the Figma token; in critique, compare rendered spacing to the source value explicitly" passes.

**The absorb output is a fixed block, not prose.** Every absorb run emits all six parts, in order; omitting any of them is the `PROC` defect the mode exists to prevent:

1. One-line acknowledgement.
2. Root cause: the missing check, named.
3. The dedup command as run, verbatim: `python3 ~/.claude/lib/memory_index.py --dupe "<rule>"` and its outcome (new rule, or which existing entry it strengthens).
4. The full L-entry, with the `[CATEGORY|GATE]` tag in its heading line exactly as the format above shows.
5. `Re-scan:` the named open or related work checked for the same pattern, and what was found. "Nothing else open" is a valid finding; silence is not.
6. `Eval candidate:` a frozen test stub written to `agents/flowsmith/eval/candidates/<L-number>-<slug>.md` containing the smallest reproduction prompt and the pass criterion that would have caught this defect. Every absorbed defect becomes a test; the candidates directory is the backlog for promotion to full golden cases (History table added at promotion). Skip only when the defect is genuinely untestable without a live client site, and say so in the block.
7. `Loop closed:` lesson, guardrail, and the gate where it now fires, in one line.

## Output

`brief` and `critique` write their blocks to files in the job's scratch folder (`~/.claude/_scratch/YYYY-MM-<job_id>/brief.md` and `handoff.md`), lint them (`--plan`, `--handoff`), and carry them into the final report. A block that exists only in the agent's reasoning is invisible to the reviewer and to telemetry, so it did not happen. `absorb` writes to `agents/flowsmith/learned-rules.md` and regenerates the index via `python3 scripts/ledger_lint.py --reindex`.

Structured result to `~/.claude/results/flowsmith-loop/{YYMMDD-HHMM}.json` via `lib/skill_output.py` (`SkillRun`), carrying mode, lessons pulled, categories walked, defects self-caught, and for `absorb` the entry number, category, and whether it escalated an existing rule.

## Governance

| Action | Tier |
|---|---|
| Read the ledger, run the lint, emit any of the three blocks | 1 |
| Append or strengthen a ledger entry | 1 |
| Re-scan and fix the same pattern in adjacent open work | 2, preview then execute |
| Anything the ritual's hard stop surfaces (missing design source) | stage the operator moment, do not proceed |

Publishing and spend gates are unchanged and owned by `SYSTEM.md`. This skill never publishes.

## Rules

- **The evidence rule.** Every critique row names an external signal: the published page, the design reference, a `dod.md` line. A check with no evidence source is not a check. This gate extends FLOWSMITH's existing anchor in external verification; it never becomes blind self-reflection.
- The standards are `dod.md`. Never restate them here or in the critique file; point at them.
- Assume the reviewer is right until proven otherwise. You may make the case once, concisely, with evidence, then defer.
- No invisible work. Structure, naming or behaviour changed means it goes in the handoff.
- Precision over speed. A slower correct build beats a fast one that bounces.
- A ledger entry that has not been made checkable has not been learned.

## Chaining

**From:** `/webflow-build` at each phase boundary, `/webflow-verify` once green.
**To:** `/webflow-verify` (the mechanical layer the critique cites), `/consolidate` (sweeps `[promote]` entries to canonical memory).
**Extends to:** `webflow-fix` by pointing the ledger path at `agents/webflow-fix/learned-rules.md`.

## Eval Criteria

Run `/eval flowsmith-loop`. Layer (a) is gate-runnable with no MCP; layer (b) needs a live site fixture.

### Test 1: ritual pulls the right lessons (a)
1. Given a motion task, the lessons restated are drawn from `MOTION` and `STRUCT`, not the whole ledger.
2. Between 3 and 5 lessons are restated, each with a stated avoidance.
3. The BUILD PLAN block emits all ten fields.
4. `RISKS` and `VERIFICATION` are non-empty and specific to the task.

### Test 2: ritual hard-stops without a design source (a)
1. Given a build task with no Figma URL and no reference set, the skill refuses to proceed.
2. It stages operator moment 3 or 3b rather than proposing values.
3. It does not emit a BUILD PLAN with guessed spacing or colour.

### Test 3: critique cannot pass on assertion alone (b)
1. Every ticked row cites an evidence source, not a judgement.
2. A category the change touched is never silently skipped; skipped categories are named with a reason.
3. The HANDOFF REPORT self-critique-results section is non-empty.
4. No completion claim appears for a change that is staged rather than live.

### Test 4: absorb diagnoses cause, not symptom (a)
1. Given feedback about one wrong spacing value, the entry's root cause names the missing check, not the value.
2. The category is drawn from `references/taxonomy.md`.
3. The guardrail passes `ledger_lint.py`: imperative, measurable, names its gate.
4. A dedup check ran before the write.
5. Feedback matching an existing entry strengthens that entry instead of adding a parallel one.

### Test 5: lint is a real gate (a)
1. `ledger_lint.py --all` returns 100% on the current ledger.
2. An entry with a vague guardrail ("be more careful") fails.
3. An entry missing any of the five fields fails.
4. A handoff with an empty self-critique-results section fails `--handoff`.
5. An index out of sync with the entry bodies fails.
6. A handoff with no webcheck `report.json` path and no `STAGED` marker fails `--handoff`, and so does a stated LCP or performance score with no saved trace or Lighthouse JSON path. A Known limitations line reading "performance score and TBT are not measured" passes. So does a failing or errored check in the job's newest cited `report.json` when Known limitations names its id; an unnamed one, an id named only inside a longer one (`layout.overflow-xy` for `layout.overflow-x`), or an `ERROR` report, fails, and a newer report from another job does not mask it.
7. `--pointers` fails while any Webflow skill or agent file tells the agent to read the flowsmith ledger without going through the `LEDGER-INDEX`. It is separate from `--all`, which lints the ledger alone because the scorecard and every absorb run it.

### Test 6: the lite brief is sized, not chosen (a)
1. Given a two-item copy fix on one page touching no shared class, the ritual emits the three-line lite brief, not the ten-field plan.
2. Given three items where one edits a shared class or component, it escalates to the full BUILD PLAN.

The layer-(a) cases live in `golden/baseline.json`; their plan and handoff regexes mirror `ledger_lint.py` `lint_plan` and `lint_handoff`, so change both together. The cited-report read needs the file on disk, so it runs live only and has no golden mirror.
