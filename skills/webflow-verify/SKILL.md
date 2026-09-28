---
name: webflow-verify
description: Mechanical verification gate for Webflow work. Publishes to staging under the publish lock, then verifies the PUBLISHED output with the webcheck runner (served HTML, layout across the canonical 320 to 1920 sweep, text, images, accessibility, open menu and form states, console, design completeness), a throttled mobile performance trace plus the Lighthouse CLI, visual fidelity against the design, the creative-code layer, reduced motion, the form submit path, an SEO sweep and launch-day production indexability. Loops fixes max 3 rounds then escalates. Use after ANY Webflow change worth trusting, before any handover, and as the exit condition of a production publish. Triggers on "/webflow-verify", "verify the site", "run the webflow gate", "is staging clean".
---

# webflow-verify: the gate

**Ledger:** never read `learned-rules.md` whole. In a flowsmith dispatch the preloaded `flowsmith-loop` brief has already pulled the `LEDGER-INDEX` entries that match; a standalone invocation runs `/flowsmith-loop brief --lite` first.

**Prime directive: the API response is not evidence. Only the published page is.** Every check runs against `https://<site>.webflow.io` (or the production domain in launch mode). The standards are `agents/flowsmith/dod.md`; this skill is how they are proven.

## Inputs
`site_id`, staging URL, page list (or "all"), job id, mode: `phase` (default) | `section` | `handover` | `launch`. **T2/T3 pages also need the experience tier and its budget** (dod.md §5), which selects §2d and the performance thresholds. `section` mode also takes a `section_id` and its reference slice. **`phase` and `launch` modes need the design inventory, `<pack>/design-inventory.json`** (figma-translation intake step 1; its path is in the manifest). Running them without it needs an explicit waiver in the honesty ledger: that refusal is the enforcement, the same way the ritual's missing-design-source hard stop works.

## The loop

Every publish here is a staging publish under the lock (flowsmith SYSTEM.md, L-109). Take the lock before the first publish and hold it until the loop ends, green or escalated, so no other session publishes between your rounds.

1. `python3 ~/.claude/lib/agent_runtime.py lock <job_id> webflow_publish:<site_id> --ttl 120`. On `busy`, wait and retry; never publish without it. The default TTL is 30 minutes, shorter than a 3-round loop, and a lapsed lock is freed for other sessions. The gate hook denies any publish without a live lock, and a flowsmith dispatch's unless the lock is under its own job id.
2. Note the live stamp: `curl -s -m 10 "https://<site>.webflow.io/?wcb=$RANDOM" | grep -o 'Last Published: [^>]*'`.
3. `publish_site` with `publishToWebflowSubdomain: true` and `customDomains: []`, both explicit. The gate hook also denies a publish within 60 s of the site's last landed one and, when that was under two hours ago, any publish before a webcheck `report.json` for this job (any job's, when the hook cannot tell the job) has been written since it: on a site another job published recently, run the runner once first (`--html-only` is enough). A non-empty `customDomains` is a production publish: the hook denies it without a fresh grant, so stop and raise the approval card (§5).
4. On 429, wait 30s, then 60s, then 120s with a polled loop (the harness blocks a bare `sleep`), then retry: `T=$(( $(date +%s) + 30 )); until [ $(date +%s) -ge $T ]; do sleep 2; done`. Steps 4 and 5 outrun the Bash tool's default 120000 ms timeout: pass `timeout: 180000` on those calls.
5. Wait for the new build instead of guessing an interval, bounded by the clock: `T=$(( $(date +%s) + 100 )); S=; while [ $(date +%s) -lt $T ]; do S=$(curl -s -m 10 "https://<site>.webflow.io/?wcb=$RANDOM$RANDOM" | grep -o 'Last Published: [^>]*'); [ -n "$S" ] && [ "$S" != "<stamp from step 2>" ] && break; sleep 2; done; [ -n "$S" ] && [ "$S" != "<stamp from step 2>" ] && echo "LIVE $S" || echo "NOT LIVE after 100s"`. NOT LIVE means the publish did not land: report it, do not verify a stale page.
6. Run the checks below; this round's runner `report.json` is also what lets the next round's publish through the hook. Defects: fix them in the Data API or custom code, batching every fix for ALL pages into the next round's single publish (never publish per edit), and go back to step 1: re-locking under the same `job_id` refreshes the TTL.
7. Stop when green, or after 3 rounds still red (STOP and escalate with evidence). Either way, `python3 ~/.claude/lib/agent_runtime.py unlock <job_id>`.

**The round count is a recorded fact.** Every loop ends by writing `verify_rounds=<n>` into the run record (`python3 ~/.claude/lib/agent_runtime.py record <agent> <job_id> ... verify_rounds=<n>`, the CLI that validates it); over 3 needs `escalated=true` plus the escalation evidence below. A loop that ran 4+ rounds without escalating is itself a defect: absorb it (ledger L-77). The scorecard audits the pairing.

## 1. The runner (webcheck): the mechanical layers, every mode

One call replaces hand-written `evaluate_script` checks, and its `report.json` is the evidence the critique and handoff cite. Flags, check ids and the inventory format: `scripts/README.md`. Read-only: it never publishes, submits a form or writes to Webflow, and it starts the debug Chrome itself (L-107) in its own browser context.

```
# phase, handover: every page, with the design inventory and the approved copy map (drop --copy only when none exists)
node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs https://<site>.webflow.io/ https://<site>.webflow.io/<page> --inventory <pack>/design-inventory.json --copy <pack>/copy-map.md --job <job_id>-r<round>
# section mode or a lite fix: the touched page only
node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs https://<site>.webflow.io/<page> --job <job_id>-r<round>
# a write landed, no browser (also the fallback when Chrome is down)
node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs https://<site>.webflow.io/<page> --html-only --expect "<new text>" --job <job_id>-r<round>
```

- **Widths:** the runner's default `--widths` is the canonical sweep, ten widths from 320 to 1920. It is the one width list for every Webflow gate; never pass a shorter list to save time.
- **Evidence:** `~/.claude/_scratch/YYYY-MM-webcheck-<job_id>-r<round>/report.json`, plus a screenshot per failed width. Cite the path and the failing check ids.
- **Verdict and exit code:** `FAIL` (exit 1) if any check fails, else `ERROR` (exit 2) if any errored, else `PASS` (exit 0, warnings allowed). A browser that could not be used or stalled records `browser` errors (the report is still written, after about 15 s for a stall): alone that is `ERROR`, beside a failure it is `FAIL`. An `ERROR` report is never evidence: rerun once, then fall back to `--html-only`. Every errored check id in the report you cite is a layer not run, and the browser layers of an `--html-only` fallback are too: list them under Known limitations. `ledger_lint.py --handoff` reads the newest cited report for the job and fails the handoff when it is `ERROR`, or holds a failing or errored check id its Known limitations do not name.
- Add `--axe <path>` when a local `axe.min.js` exists (`ls ~/Code/*/*/node_modules/axe-core/axe.min.js`). `--ignore <css>` excludes an element deliberately: name the reason in the handoff. `--waive "<served check>|<text>|<reason>"` stops one known `served.*` problem counting: use it only for an operator-approved dod.md waiver, listed in the honesty ledger (`report.json` keeps it under `waivers`).

What it proves, by check family: `served` (200, cache-busted; template residue; staging noindex; lang; one h1 and heading order; title, description, canonical, OG and twitter tags; JSON-LD parses; labels; alt; SRI; links and link status; unique titles; real 404), `layout` (overflow, escape, per-element containment against the parent, clipped text, overlay collisions with 20px band sweeps), `text` (orphans, Sentence case, trailing full stops, residue, copy with no match in the copy map), `images` (retina floor, oversupply ceiling, broken, width/height, lazy LCP), `a11y` (landmarks, names, labels, focus visible and trap-free, sampled contrast), `state` (menus, accordions and dropdowns opened, re-measured and closed; negative states hidden on load; form field names at submit time and validation layout, never submitting: a control that fires a submission is blocked and warns `state.submit-blocked`), `console`, and `completeness` (§2c).

## 1b. Custom-code surfaces (both surfaces, every mode)
- Enumerate the scripts registry (`get_registered_scripts`, `get_site_scripts`, `get_page_scripts`) and the freeform blocks (`get_site_freeform_code`, `get_page_freeform_code`).
- Diff against the manifest's expected custom-code list: everything present has a purpose; nothing unexpected ships.
- Anything retired is absent from BOTH surfaces AND from the published HTML: pass `--absent "<script filename or marker>"` to the runner. Freeform removal alone is not removal.
- No shim sets textContent on a non-leaf element (learned rule 19).
- IX3: `data_interactions_tool` `list_interactions` (read-only). Any IX3 interaction missing from the manifest's `interactions` list is a finding, because nothing in this gate verifies IX3 motion (webflow-motion bans writing it anywhere but the eval fixture site, for the pilot). With no manifest (a webflow-fix run on a legacy site), list them in the handoff's Known limitations instead of failing them.

## 2. Browser checks the runner does not cover
Use chrome-devtools on your own `new_page(isolatedContext: "<job_id>")`, passing its `pageId` on every call (L-36), after `bash ~/.claude/lib/debug_chrome.sh` (L-107). Files go under `~/.claude/_scratch/YYYY-MM-<job_id>/`. Scroll-reveal pages render black in full-page shots: geometry is primary evidence, screenshots secondary.
- Hover states fire and release; marquees run and pause; the booking or CTA element is clickable (`elementFromPoint` returns it); focus moves into an opened menu.
- **Handover mode: one test form submission.** Payload values prefixed `[FLOWSMITH-TEST]`, arrival confirmed with `data_forms_tool.list_form_submissions`, then `get_form_submission` shows the prefix before `delete_form_submission`, so nothing lands in the client's pipeline. Phase mode never submits.
- Reduced motion: emulate `prefers-reduced-motion: reduce`; the page renders complete and usable, static layers intact (dod.md §5).
- Motion lifecycle: after an internal navigation and back, `ScrollTrigger.getAll().length` does not grow, no duplicate `gsap.ticker` callbacks, no re-init warnings. Motion is inert in the editor (`html.w-editor` present, animations off).

### 2c. Completeness gate (the design-side denominator, BEFORE 2b, phase and launch modes)
Every other gate is indexed by what was built, so a designed section that was never built passes all of them. This one is indexed by the DESIGN: the runner's `completeness` check (on whenever `--inventory` is given) iterates the inventory rows, not the built sections.
- Each row must be present with a non-zero box, in design order, meeting its photo count and rendering every selector in its `elements` checklist, at every viewport the inventory names. The evidence is the `completeness.inventory` table in `report.json`: `row | viewport | selector | present | order | photos n/m | missing`. **Any failing row fails the gate.**
- `completeness.viewports` warns when a page has no mobile rows: the mobile twin was not checked, and the handoff says so.
- A section deliberately dropped is a waiver in the inventory with `reason` and `approver`, also listed in the honesty ledger. A waiver without both does not suppress the row.
- Existence and order, deliberately not a similarity score: none of 2b's four dimensions can fail for content that is absent.

### 2b. Visual fidelity: design-grounded (the perceptual gate geometry cannot see)
Geometry and token equality prove the boxes and values; they are perceptually blind. A page can pass and still read as un-designed. Per viewport the inventory names:
- **ΔE colour check (deterministic, first):** sample rendered key regions (background, text, accent, buttons) against the design's variable values via CIEDE2000, reusing the `/brand-fidelity` ΔE machinery. Fail any region ΔE > 3 (imperceptible is about 2.3).
- **VLM judge vs the REFERENCE for THAT viewport (grounded, never self-judged):** the published screenshot plus the design reference (`figma-remote get_screenshot` for Figma input, or the supplied reference) go to a vision model that scores fidelity and NAMES discrepancies. The desktop render at the desktop frame's width compares against the desktop frame; the mobile render at the mobile frame's width against the mobile frame, never the desktop frame at both. With no mobile frame, say the perceptual check was skipped for lack of a reference.
  - **Rubric (anchored):** four dimensions scored 0 to 25, total /100, gate ≥ 85 with no dimension below 18. **Spacing/rhythm** (25 optical spacing matches within a hair; 12 uneven but recognisable; 0 cramped or blown out), **hierarchy** (25 emphasis order identical; 12 readable but flattened; 0 wrong focal point), **type scale/weight** (25 sizes and weights match; 12 one step off; 0 wrong family or weight), **colour/contrast balance** (the number comes from ΔE; the judge reports perceived balance only). Low decode temperature; on a borderline 83 to 87, re-sample twice and take the median. Named discrepancies become fix-round tasks.
  - **Element completeness is a hard gate, not a score.** Walk the section's element checklist (from its `get_design_context`: chips, pills, markers, hairlines, ghost numerals, panel tints, patterns, bleeds, blend treatments, badges, dividers). Each item is present, a named approved deviation, or a FAIL, whatever the four scores say (L-59). The inventory's `elements` selectors make the presence half mechanical in 2c; no checklist on file means the check did not run, which is a waiver, not a pass.
- **Section mode:** ΔE plus the VLM judge on one `section_[id]` against its reference slice. **It does NOT publish:** it reads the current wave's single staging publish (learned rule 20), or a live `element_snapshot` when the Designer bridge is up. Reference slice: the matching Figma frame via `get_metadata` plus `get_screenshot`; for reference input, the operator-tagged crop from the design-interpretation artifact, or, with none, the ΔE and geometry contract only, flagging that the perceptual section check was skipped.

### 2d. Creative-code layer (T2/T3 pages only: the canvas the other gates cannot see)
A WebGL canvas is one DOM node whose computed style says nothing, producing pixels that change every frame, so none of the checks above can fail for a shader that never ran. This layer is indexed by BEHAVIOUR, not presence (learned-rule 102).

**Precondition, always first:** assert `document.visibilityState === "visible"` in the driving tab. A backgrounded page throttles `requestAnimationFrame` to nothing and every liveness check reads as a false failure (learned-rules 100, 102). Front the page, confirm a non-zero `document.documentElement.clientWidth`, then measure.

- **Runtime present and pinned:** exactly one `corient-web-runtime` script tag, `type="module"`, in site head, pinned to a `@vX.Y.Z` tag (never a branch). `window.CT.debug()` returns the version, registered scenes, mounted count and ticker count. Record the version in the handoff.
- **Scenes mounted:** every `data-ct-scene` element also carries `data-ct-ready` listing the scenes that ran. A scene with no ready marker means the factory threw.
- **Liveness (the core assertion):** for each in-viewport `data-ct-gl="live"` surface, read `data-ct-frames` twice about a second apart and require growth. Frozen or absent is a defect regardless of the code.
- **Culling:** a surface scrolled out of view holds a static frame count; `window.CT.debug().tickers` stays near visible surfaces + 2. A count that scales with total surfaces means per-instance loops.
- **Poster path, forced:** load the published URL with `?ct-gl=off`: zero `<canvas>` elements, every `<img>` at full opacity with alt intact, `<html data-ct-gl-mode^="poster:">`, and the network log shows the WebGL chunk never fetched.
- **Reduced motion:** each surface renders at least one frame and holds (`data-ct-frames` present, not growing, canvas opacity 1). A surface that disappears under reduced motion is a defect.
- **Context hygiene:** navigate internally and back; the live GL context count does not grow and `tickers` returns to its pre-navigation value.
- **Frame budget:** performance-trace while scrolling past each surface; frame time within the tier budget (dod.md §5).
- **Poster is the LCP element:** read it from the §3 trace, not by inspection.
- **Quality marker:** `<html data-ct-quality>` exists on runtime GL pages (step 0 on healthy hardware). Step 3 on a capable machine means something is burning the main thread: find it.
- **Audio never autoplays:** no AudioContext before a gesture (patch the constructor and count), the toggle carries `aria-pressed`, and `[data-ct-scene="audio"]` reads `armed`, not `on`, at load even with a persisted preference.
- **View Transitions injected once:** one `#ct-vt-style`; every `data-ct-vt` name unique per page; `data-ct-vt-mode="off"` under reduced motion.
- **Ready markers are honest:** on the poster path, GL scene names are absent from `data-ct-ready`; a GL name there while `data-ct-gl-mode` says poster is a runtime bug.

## 3. Performance (throttled, per page: mobile, plus desktop on T2)
Fix-round re-runs repeat this layer only for pages whose fixes touched assets, scripts or layout. `lighthouse_audit` has no performance category (its own schema says so): never cite it for performance. Keep it for the accessibility, SEO and best-practice categories only.

- **LCP and CLS: throttled trace.** `emulate(pageId, viewport: "390x844x3,mobile,touch", networkConditions: "Slow 4G", cpuThrottlingRate: 4)`, navigate, then `performance_start_trace(pageId, reload: true, autoStop: true, filePath: "<home>/.claude/_scratch/YYYY-MM-<job_id>/trace-<page>.json.gz")` (absolute path). Read LCP and CLS from its summary, and run `performance_analyze_insight` on each flagged insight (for example `LCPBreakdown`, `DocumentLatency`) so a miss becomes a named fix, not just a number. Reset with `emulate(pageId, cpuThrottlingRate: 1)` and no `networkConditions` afterwards.
- **Score, TBT and page weight: Lighthouse CLI** against the debug Chrome, mobile preset with simulated throttling: `npx -y lighthouse@13.5.0 <url> --port=9222 --only-categories=performance --output=json --output-path=$HOME/.claude/_scratch/YYYY-MM-<job_id>/lh-<page>.json --quiet`. Read `categories.performance.score`, and `audits` `largest-contentful-paint`, `cumulative-layout-shift`, `total-blocking-time` and `total-byte-weight`. T2 pages also need the desktop budget (dod.md §5): rerun with `--preset=desktop` and `--output-path=...lh-<page>-desktop.json`. If it cannot run, the score and TBT are "not measured" under Known limitations; never substitute another number.
- **Scripted interaction:** trace while driving the signature moment; interaction latency < 200ms. INP is field-only: never claim a lab INP.

## 4. SEO sweep
The runner's `served.*` checks cover titles and descriptions (present, unique), one h1 and heading order, canonical and OG/twitter presence, JSON-LD parsing, alt, image dimensions, broken links and the real 404. Add:
- Title and description length bounds and pattern per the meta contract; JSON-LD required fields per schema type
- Paginated collection-list variants self-canonicalise; OG image URLs return 200
- Naming-grammar audit: `python3 ~/.claude/lib/webflow_naming_audit.py <urls>` (FLOWSMITH-built sites; legacy sites report-only)
- Sitemap flags (`data_sitemap_tool`); money pages meet their inbound-link minimums from the discovery map; no orphan pages

## 5. Launch mode only: production indexability re-run
Against the custom domain, after the approved production publish (the operator's yes, then the grant the main session writes at `~/.claude/state/approvals/webflow-production-<site_id>.json`; the gate hook denies the publish without it), as the Tier 3 exit condition. That publish also needs the publish lock, taken again under the job's id (step 1; step 7 released it), and step 3's spacing and report rules, or the hook denies it. Then:
- `node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs https://<domain>/ --noindex forbid --sitemap --job <job_id>-launch`: pages 200 with no noindex meta or X-Robots-Tag, sitemap URLs served
- robots.txt fetched and sane (no stray `Disallow: /`); sitemap.xml and canonicals on the custom host
- favicon 200; migrations: spot-curl the top-N redirect map entries

## Handover-mode extra deliverable
Emit the **custom-code inventory**: every registered script and freeform block (site and page level) with purpose, injection point and retirement instructions. A dod.md §10 deliverable and the two-surface audit's paper trail.

## Escalation format
What was asserted, then what the published page showed (the `report.json` result, rect, computed style or curl excerpt), then the 3 fixes attempted, then the operator action needed.

## Overlap map (wraps, does not duplicate)
`safe-publish` and `pre-deploy-check` (publish flow) · `site-audit` (structure) · `accessibility-audit` (both themes, handover mode) · `link-checker` (post-launch smoke) · `asset-audit` (alt layer).

## Eval Criteria
Layer (a), gate-runnable (`eval_gate.py`, no MCP): given a fixture check plan, output MUST include the staging-noindex assertion, the console-zero gate, the canonical width sweep from 320 to 1920, the publish lock with `customDomains: []`, performance from a throttled trace or the Lighthouse CLI (never `lighthouse_audit`), TBT not INP as the lab metric, and the launch-mode robots/noindex re-run; MUST NOT claim a lab INP or trust any API response as verification evidence.
Layer (b), live fixture (outside the gate): `phase` mode against the eval fixture site pinned in `agents/flowsmith/eval/fixture.json` (nothing runs while its `site_id` is null) produces a webcheck `report.json`, a trace file and a Lighthouse JSON, and fails a page seeded with a deliberate defect (duplicate h1).
