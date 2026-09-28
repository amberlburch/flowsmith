# Pre-handoff red-team checklist

Switch roles. You are now the demanding developer reviewing this work, and your job is to reject it. Walk every category that applies to the change. Fix what you find. Report what you caught.

**The evidence rule: a check with no evidence source is not a check.** Every row below names how you prove it. "Looks right" and "should work" are not evidence. The standards themselves live in `agents/flowsmith/dod.md`; this file does not restate them, it tells you how to prove each one against an external signal.

**Where the webcheck runner measures a row, its `report.json` is the evidence:** cite the path and the check id (webflow-verify §1 has the commands; `scripts/README.md` defines every check). The runner sweeps the canonical widths, 320 to 1920; no row accepts a shorter list. A runner result you did not run this round is not evidence.

Skip categories the change cannot have touched. Skipping a category that it did touch is a `PROC` defect. **`OMIT` is never skippable on a build or a phase handoff**: a full build always touches it, and its whole point is catching what nothing else looks at.

---

## OMIT (first, because you cannot critique what is not there)

| Check | Evidence |
|---|---|
| Every design-inventory row is built, in design order, with its photos and element checklist | `completeness.inventory` table in `report.json` (`--inventory <pack>/design-inventory.json`): zero failing rows at every viewport |
| Every desktop frame's mobile twin was checked, or the gap is named | no `completeness.viewports` warning, or the missing twin stated in the handoff, never assumed absent by design |
| Anything dropped was dropped deliberately | a waiver in the inventory with `reason` and `approver`, also in the honesty ledger |
| No copy on the page that the copy map does not hold | `text.copy` with `--copy`: zero unmatched runs (an invented CTA or testimonial, L-91, L-93) |

## STRUCT

| Check | Evidence |
|---|---|
| No auto-generated names left (`Div Block 27`, `Heading 12`) | `query_elements` on the build root, scan `styleNames` |
| Every wrapper justified by layout, alignment or reuse | walk the element tree at `children_depth:2`, name the job of each div |
| Correct semantic tags; one `<h1>`; monotonic headings; landmarks | `served.headings`, `a11y.headings`, `a11y.landmarks` |
| No coupled reference broken by this change | grep BOTH custom-code surfaces (freeform + registered, head + footer) for the exact before-text, class or id you edited, then re-verify the dependent behaviour, not the text (ledger 18, 35, 38) |

## NAME

| Check | Evidence |
|---|---|
| No duplicate class created where one existed | `query_styles` on the name before creating; a duplicate is a defect |
| Max one combo class per element, genuine variants only | `query_elements` styleNames per interactive element |
| Class attachment actually landed | after any `whtml_builder` call defining >5 new classes, `query_elements` the root and assert `styleNames` is non-empty (ledger 27: "success" is not proof) |
| `update_style` hit the intended object | compare the returned style `id` against the `query_styles` id for that name; differing ids mean a name collision (ledger 31) |

## RESP

| Check | Evidence |
|---|---|
| No overflow, escape, clipping or element outside its parent at any width | `layout.overflow`, `layout.escape`, `layout.containment`, `layout.clipped` at every canonical width (L-90: `scrollWidth` alone never counts) |
| Full-range consistent, not just endpoints | `layout.overlap-band` (the 20px sweeps between widths, L-106) and `state.open-layout` (layout re-measured with each menu open): no width where a mobile control and its desktop equivalent are both visible (`dod.md` §9) |
| Cascade set in the right direction | base on `main`, override downward for `medium/small/tiny`, upward only for `xl+` (ledger 13) |
| Tap targets ≥44px, body text legible on mobile | `getBoundingClientRect()` per interactive element at 320 and 375 |

## FID

| Check | Evidence |
|---|---|
| Spacing, type, colour, radius, shadow match the source | measured against the Figma token or variable, never eyeballed. Per-viewport ΔE per key region <3 (`dod.md` §2) |
| Reads as the reference at a glance, not just numerically | VLM judge vs the reference image ≥85, named discrepancies resolved. Token equality alone is insufficient (`dod.md` §2) |
| Zero orphan lines; balance only on short headings | `text.orphans` at every width; computed `text-wrap` is `pretty`, not `balance`, on list items, labels and card bodies (`dod.md` §4b) |
| Sentence case and no trailing full stops on headings | `text.case` (strict with `--copy`) and `text.full-stop` |
| The brief is still intact, not just the contrast maths | pixel-sample the published screenshot at real text-adjacent coordinates. A scrim can clear 8:1 and erase the brand colour (ledger 32) |

## STATE

| Check | Evidence |
|---|---|
| Hover, active and disabled states exist and release | chrome-devtools: hover each button and link, read the computed style change; set `disabled` on each control that can be disabled and read its style |
| Focus visible on every stop, no trap | `a11y.focus-visible`, `a11y.focus-hidden`, `a11y.focus-trap` (`:focus-visible`, not `:focus`, per `dod.md` §8) |
| Menus, accordions and dropdowns open, report `aria-expanded` honestly, and close | `state.toggle`, `state.aria`, `state.menu-links`, `state.close` |
| No error, empty or success state visible on load; empty and loading states exist where the component can be empty or slow | `state.negative`, then trigger the empty case (empty collection, failed submit) and screenshot it |

## MOTION

| Check | Evidence |
|---|---|
| Correct easing, duration, trigger; within timing standards | `dod.md` §5; read the actual GSAP tween params in the published source |
| Zero console errors from motion at every width | the runner's `console` check |
| `prefers-reduced-motion` honoured, page fully usable with motion off | emulate reduce, then check EVERY motion surface separately: GSAP/Lenis init, native `<video autoplay>`, CSS `@keyframes` marquees (ledger 23) |
| Static layers still render for reduced-motion users | assert grain, gradients, colour states, focus rings are present under `reduce`, not merely that motion is absent (`dod.md` §5) |
| Text-reveal masks do not clip descenders at rest | screenshot g/y/p/j/q and `?`/`!` at rest, every width, including the reduced-motion resting state (`dod.md` §5) |
| Lifecycle: tears down on internal nav, inert in the editor | navigate away and back, count live ScrollTriggers; confirm the `w-editor` guard |
| No IX3 interaction the manifest does not list, and none written off the eval fixture site | `data_interactions_tool` `list_interactions` (webflow-verify §1b) |
| A reveal that looks broken may be a capture artefact | verify with a real `scrollIntoView` + settle wait and a viewport screenshot before flagging (ledger 22) |

## A11Y

| Check | Evidence |
|---|---|
| AA contrast on all text, across gradients and photos | `a11y.contrast` (pixel-sampled, never computed from tokens, ledger 32, 33); hover-state contrast sampled by hand |
| A shared class spanning a gradient can pass at neither end | compute `sqrt((L_light+0.05)/(L_dark+0.05))`; under ~2 means no flat colour works and the fix is geometric (ledger 33) |
| Keyboard operable in a sensible order | `a11y.focus-order`; focus moves into an opened menu (chrome-devtools, webflow-verify §2) |
| Accessible names, alt text, labels | `a11y.names`, `a11y.alt`, `a11y.labels` (decorative images marked, not missing) |
| WCAG 2.1 beyond the runner | `--axe` result when a local axe-core exists; `accessibility-audit` for both themes |

## PERF

| Check | Evidence |
|---|---|
| LCP <1.5s, CLS <0.05 | the throttled mobile trace file under the job's scratch folder (webflow-verify §3) |
| Performance score ≥90 (or the tier's budget), TBT <300ms, weight <3MB | the Lighthouse CLI JSON under the job's scratch folder. A `lighthouse_audit` result has no performance category and never counts here; not measured is stated as not measured (`dod.md` §6) |
| Image resolution within the floor and ceiling; LCP image not lazy | `images.floor`, `images.ceiling`, `images.lazy-lcp` (`dod.md` §6) |
| Compression kept the originals | each compressed asset in the manifest asset map as `{id, hostedUrl, local}`, with its original file under `~/.claude/state/snapshots/<job_id>/assets/`; CSS `url()` references re-pointed to the new file names (L-99) |
| No orphaned styles, elements or interactions left by this change | list what the change created and superseded; remove only your own orphans, never pre-existing ones on a "looks unused" basis |
| No `!important` or specificity hack | grep the diff. Reaching for one signals the structure is wrong; fix the structure |

## SEO

| Check | Evidence |
|---|---|
| Unique title and description per page, to pattern and length | `served.meta` and `served.unique`, then the length bounds by hand |
| Schema validates, required fields present | `served.meta` proves the JSON-LD parses; check required fields per type |
| No leftover schema from a prior stack | diff page-level freeform against the site-wide graph; un-briefed `AggregateRating` is a policy risk, not clutter (ledger 25) |
| Staging carried noindex throughout | `served.noindex` |
| Any JSON-LD field mirroring a visible heading matches it | compare `name`/`headline` against the rendered heading text (`dod.md` §4b) |

## CMS

| Check | Evidence |
|---|---|
| Template pages resolve every bound field | load a real item, not the template preview |
| Empty states handled | publish with an empty collection and look |
| Editor-safe: reference-linked, sensible names, no orphan fields | `cms-best-practices` pass |
| Forms: every field uniquely named in the SUBMITTED payload | `state.form-names` (names read at submit time, ledger 2); handover mode adds the one `[FLOWSMITH-TEST]` submission |

## API

| Check | Evidence |
|---|---|
| Every write confirmed on the published page | the golden rule. A success response is not proof of a write: `--html-only --expect "<new text>"` confirms it landed |
| Text-bearing creations carry the intended text | re-query `children_depth:1` after any `element_builder`/`whtml_builder` creation and assert the String child's `textContent`. `set_text` at creation time can silently fall back to placeholder copy (ledger 39) |
| Nothing faked that the API cannot do | site creation, backup restore, redirects, robots.txt, global canonical, favicon: staged operator moments, never claimed (ledger 17) |

## LIVE

| Check | Evidence |
|---|---|
| Every change reported done is LIVE on the published URL | the new `Last Published` stamp confirmed by the polled wait (webflow-verify loop step 5), then the runner on that build. Staged is not done (ledger 37) |
| Anything unpublished is reported "STAGED: NOT LIVE" with the owed publish | explicit in the handoff, never buried |
| Publish lock held, staging parameters explicit, a check between publishes | `agent_runtime.py lock` / `unlock` under the job's id around the publish; `publishToWebflowSubdomain: true` and `customDomains: []` on the call (L-109); a runner `report.json` for the job written after the previous publish. The gate hook denies a publish without the lock, without both staging parameters, or (within two hours of the last publish) without a report since it; the unlock is yours |
| Site-wide publish blast radius checked | under-construction pages still `draft:true` (ledger 16) |

## PROC and COMM

| Check | Evidence |
|---|---|
| Every category that the change touched was actually walked | name the ones you skipped and why |
| No ledger lesson repeated | re-read entries tagged `fires:CRITIQUE`; for each relevant one, state how this build guarded against it |
| Every assumption flagged as an assumption | the handoff's assumptions section is non-empty or the spec was genuinely complete |
| Every non-obvious decision documented | a reviewer should not have to reverse-engineer why |
| chrome-devtools checks used an isolated context with a re-asserted URL | own `new_page(isolatedContext)`, its `pageId` passed on every call, `location.href` asserted inside the same `evaluate_script` (ledger 36). The runner isolates itself |

---

## Exit condition

If you cannot honestly tick a row, the task is not done. Either fix it, or record it in the handoff's known-limitations section with the reason and what a human needs to decide. An empty self-critique-results section in the handoff means this pass did not happen.

Then apply the one-line test: **would the reviewer approve this with zero edits?** If you are not confident the answer is yes, come back to the top.
