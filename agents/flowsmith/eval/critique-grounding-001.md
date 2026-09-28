# Golden eval: critique grounding 001 (Better Design + 21st.dev)

First golden case for flowsmith's externally-grounded critique pass, exercising the Better Design principle tools and 21st.dev inspiration granted 2026-08-17. No site, no publish, no client content.

## Prompt

A hero section spec for a fictional brand "Northbeam Analytics" reads: H1 "Grow Your Business With Powerful Analytics Tools Today" at 64px in Title Case on a single line; body copy at 12px in #999999 on a white background; primary CTA labelled "Submit". Run a critique pass on this spec alone. Every critique row must cite an evidence source: use Better Design `get-ui-principle`, `get-ux-principle`, or `get-review-rules` for at least 3 rows, and pull exactly 1 hero-section reference via 21st.dev `get_inspiration` as a composition comparison. Write your run record with the record CLI (`python3 ~/.claude/lib/agent_runtime.py record flowsmith <job_id> ...`) with fields: `outcome`, `handoff_accepted`, `revision_items`, `verify_rounds=0`, `escalated=false`, `tool_calls`, `eval=true`, and a note naming this eval.

## Pass criteria

1. At least 3 critique rows cite a named Better Design principle pulled live (not from memory).
2. Exactly 1 x 21st.dev inspiration reference with URL appears as composition evidence.
3. The 12px / #999999-on-white body copy is flagged as a contrast/legibility failure (WCAG AA).
4. The Title Case heading is flagged against the house sentence-case rule; the 9-word single-line heading is flagged for orphan/line-length risk.
5. The "Submit" CTA is flagged as a label that names no action.
6. A run record lands in `state/agent-runs/flowsmith/` carrying `handoff_accepted` and `tool_calls`.

## History

| Date | Result | Notes |
|------|--------|-------|
| 2026-08-17 (r1, r2) | FAIL 5/6 | Critique substance passed (contrast computed 2.85:1, Title Case + reflow + Submit-CTA all flagged, 21st inspiration URL pulled, record written) but criterion 1 failed both runs: Better Design tools absent from the dispatch. Root cause: BD's large tool surface loads deferred and flowsmith had no ToolSearch grant. The agent documented the fallback instead of faking live pulls, which is the correct failure behaviour. |
| 2026-08-17 (r3) | PASS 6/6 | ToolSearch added to flowsmith's grant; BD principle tools loaded via select query and cited live. Two hard blockers (WCAG AA contrast, outcome-less CTA) + two fix-before-ship (Title Case, 9-word single-line reflow) + 1 x 21st composition reference. Run record verified on disk (job critique-grounding-001-r3: handoff_accepted true, revision_items 0, 6 tool calls, outcome success). |
