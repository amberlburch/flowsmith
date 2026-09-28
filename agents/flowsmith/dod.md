# FLOWSMITH definition of done: the $50k bar

Every project is judged against every line. Items are green, waived (listed with a one-line reason, operator-approved), or the project is not done. Sources: top-1% craft research 2026-07-12 (Awwwards standards, elite-agency anatomy) + plan v2.3.

**This file is the standard; `/webflow-verify` is the proof.** Where a line names a webcheck check id (`layout.containment`, `text.orphans` and so on), the evidence is that check's result in the runner's `report.json`, run across the canonical sweep (the runner's default widths, 320 to 1920). No other width list applies. Lines without a check id name their own evidence in `skills/flowsmith-loop/references/critique.md`.

## 1. Discovery & strategy
- [ ] discovery.md complete: business goals, audience/ICP, competitor set, content inventory, page-purpose map, integration list
- [ ] Design input recorded: Figma URL or reference set (guaranteed input)
- [ ] Keyword + search-intent map per page, with target-inlink column
- [ ] Migrations only: full crawl of the old site → URL inventory → evidence-based redirect map
- [ ] Locale stance recorded (default: single-locale; hreflang = scope change)
- [ ] IA/sitemap approved (operator moment #3)

## 2. Design system & design fidelity
- [ ] Tokens live as Webflow variables (colour, fluid type scale, spacing) per `references/naming.md` grammar
- [ ] Class discipline: Client-First × Lumos hybrid, `section_[id]` skeleton, rem-based
- [ ] Style-guide page shipped in the project
- [ ] **Class hygiene:** no auto-generated names left in place (`Div Block 27`, `Heading 12`); no duplicate class where one already existed (search the style guide before creating: a duplicate is a defect, not a shortcut); max one combo class per element and only for a genuine variant (a second means refactor to a utility or component class); every wrapper justified by layout, alignment or reuse, with gratuitous nesting flattened
- [ ] **Full interactive state matrix on every interactive element:** default, hover, focus, active, disabled, plus loading and empty wherever the component can be slow or empty (a collection with no items, a form mid-submit, a failed submit). A missing hover or empty state is a defect, not a nice-to-have. Focus specifically is `:focus-visible` per item 8; the empty and loading cases are verified by triggering them, not by reading the code, and no negative state shows on a fresh load (`state.negative`)
- [ ] Figma-input: build matches the file in **content** (the completeness gate below) AND **fidelity** (the visual gate below), against **both** the desktop and mobile frames. References-input: interpretation artifact approved (moment #3b) and build matches it
- [ ] **Design completeness gate green (runs BEFORE the visual gate):** every row in `design-inventory.json` has a built counterpart at every viewport it names, in design order, with its photo count and element checklist met: the runner's `completeness.inventory`, never inspection. A designed section not built is a defect; one deliberately dropped is a waiver with `reason` and `approver` in the inventory, also listed in §11. (A fidelity score cannot fail for content that is not there, so completeness needs its own gate with a design-side denominator.)
- [ ] **Visual fidelity gate green:** per-viewport ΔE colour (each key region <3) + VLM judge vs the reference for THAT viewport (each render at its frame's own width, against its own frame) ≥85, named discrepancies resolved. Geometry and token equality alone are not sufficient

## 3. Pages & CMS
- [ ] All sitemap pages built; none left draft at launch except intentionally
- [ ] CMS collections editor-safe: reference-linked, sensible field names, no orphan fields, template pages resolve every bound field
- [ ] Custom 404 page shipped (serves real HTTP 404: `served.404`)
- [ ] **CMS behaviour ships as Finsweet Attributes v2, not custom JS**: filtering, search, sort, load-more/pagination, nested collections, lightbox, and conditional visibility use `fs-list` / `fs-*` data attributes. One script tag in site footer freeform, pinned to an exact version (never `@2` or `@latest`), declaring each solution explicitly (`fs-list`, `fs-modal` ...) rather than `fs-attributes-auto`. Verified on the published page, not the API response: the attribute functions across the canonical sweep and no duplicate custom-JS implementation of the same behaviour remains. Motion stays GSAP/Lenis; the runtime stays creative code only
- [ ] Forms: every field uniquely named in the SUBMITTED payload (`state.form-names` reads names at submit time), submit path smoke-tested in handover mode

## 4. Copy & content
- [ ] Copy written against the keyword/intent map, through brand-profile → page-copy → humanise
- [ ] Operator-approved before publish (moment #4)
- [ ] Every visible run of copy matches the approved copy map: `text.copy` with `--copy`. An invented CTA or testimonial is a defect (L-91, L-93)
- [ ] Australian English, no em-dashes, no emojis
- [ ] Alt text on every meaningful image (asset-audit clean); decorative images marked as such

## 4b. Typography (orphan control + case discipline)
- [ ] Zero orphan lines (a single word alone on the last line) on any heading, paragraph, quote, caption, kicker, label or title block at any width in the canonical sweep: `text.orphans`. Fix in this order. `text-wrap: balance` only on heading-tier classes whose text runs to 3 lines or fewer (H1-H3, kickers, short card titles). `text-wrap: pretty` on everything else: body copy, list items, labels, stat labels, card bodies, quotes and captions. Balance on a list item or label breaks short lines early and reads as a defect (seven client-logged defects on one build came from a class-level balance on list items). Where neither resolves it, bind the last two words of that instance with `&nbsp;` and re-check. A repeated section is an independent element per page in the Webflow API, not a synced symbol, so each page instance gets its own fix
- [ ] All visible on-page headings (H1-H3, kickers, card titles, nav links, footer column labels, button labels) in Sentence case unless the brand's approved copy is deliberately otherwise; proper nouns preserved: `text.case`, strict with `--copy`. SEO `<title>` and meta stay in their existing case convention: this is a visible-heading rule only. Any JSON-LD `name`/`headline` field that mirrors a visible heading (e.g. BreadcrumbList item name, Service name) gets the same case update so schema matches what's on screen; page-title-mirroring `WebPage.name` fields are out of scope.
- [ ] No overflow, escape, containment or clipping failure at any width in the canonical sweep: `layout.overflow`, `layout.escape`, `layout.containment`, `layout.clipped`. Each element is measured against its own parent (L-90); `scrollWidth` alone never proves it, because `overflow-x:hidden` on `body` hides an escape from it.
- [ ] Heading punctuation is consistent site-wide: no visible heading (H1-H3, kickers, card titles, stat labels, list-row labels) ends with a trailing full stop (`text.full-stop`). Terminal `?` and `!` are kept (not full stops). Internal sentence-separating periods are kept; only the TRAILING period is dropped (e.g. "Ten seats. Real commitment." → "Ten seats. Real commitment"). Body copy, paragraphs, card/list descriptions, and testimonial quotes are NOT headings and keep normal sentence punctuation. Any JSON-LD `name`/`headline` mirroring a visible heading gets the same trailing-period drop. Before editing, grep any site-wide freeform/registered custom code for the exact before-text of every heading being changed: hardcoded phrase-matches (e.g. a JS `indexOf`/`textContent ===` lookup used to inject an `<em>` wrap or similar treatment) can silently stop matching once a trailing period is removed, breaking a reveal/emphasis effect without any error. Fix the code's literal alongside the heading text in the same pass, and re-verify the dependent effect (not just the text) against the published output.

## 5. Motion and creative code (the craft layer)

**Experience tier is chosen at design direction, recorded in the manifest, and named in the handoff.** It is a decision with an owner, never something that creeps upward during a build. Each tier carries its own budget; the rows below apply from the tier named. Performance scores are the Lighthouse CLI performance score from §6: mobile, and desktop where the tier names it.

| Tier | What it is | Budget |
|---|---|---|
| **T0 Refined** | CSS only: scroll-driven animations (`animation-timeline: view()`), view transitions, considered type and spacing. No animation library on the critical path | Performance >= 95. **The default for most client marketing pages** |
| **T1 Choreographed** | GSAP + Lenis choreography, the recipe library | Performance >= 90 |
| **T2 Surfaced** | One to three WebGL shader surfaces on specific elements (hero panel, image grid, CTA) | Performance >= 90 desktop, >= 85 mobile with poster fallback; <= 1.5MB added weight; 60fps at 1440 |
| **T3 Immersive** | A full WebGL narrative page, or a standalone experience in a Webflow Cloud app | Exempt from the standard performance gate. Held to a frame-time budget, a hard mobile fallback, and explicit client sign-off that performance was traded for experience |

- [ ] Experience tier named, recorded, and its budget met. An unnamed tier is T1 by default and any WebGL on the page is a defect
- [ ] GSAP + Lenis boot verified on the published site (T1+)
- [ ] One signature moment; 3-5 animated moments per section max
- [ ] Timing within standards (micro 0.2-0.3s / standard 0.4-0.6s / feature 0.8-1.2s); transform/opacity only; will-change ≤ 10 elements
- [ ] No IX3 interaction created, updated or deleted except on the eval fixture site (`eval/fixture.json`), for the pilot that lands as a ledger entry: nothing verifies IX3 playback or reduced motion yet (webflow-motion). Any existing one is listed in the manifest's `interactions`, or in the handoff where there is no manifest, and never removed
- [ ] `prefers-reduced-motion` honoured: page fully usable with animation off
- [ ] **Reduced-motion disables MOTION only, not static layers.** Static texture/depth/colour/focus effects (film grain, ambient gradients, colour states, focus rings) must still render for reduced-motion users: verify by asserting these layers are present when `prefers-reduced-motion: reduce` is emulated, not just that the motion is absent. (A grain overlay initialised behind the reduced-motion early return silently disappeared for those users on one build: check every static layer's init is reachable in the reduced-motion path.)
- [ ] **Text-reveal masks never clip glyphs at rest.** Any line-mask / clip-based heading or text reveal must reserve descender room (e.g. `padding-bottom` on the mask with a cancelling negative margin so leading is unchanged) AND release the clip (`overflow:visible`) once each line settles. Verify descenders (g/y/p/j/q) and low punctuation (`?` `!` `,`) render fully at rest at every width, and for reduced-motion users, who skip the wrap entirely (their resting state must also be un-clipped).
- [ ] Mobile simplification via `ScrollTrigger.matchMedia()`
- [ ] Zero console errors from motion code at every width (`console`)
- [ ] Motion runs through a lifecycle: tears down on internal nav (no leaked ScrollTriggers/RAF/listeners across page changes), and is inert inside the Webflow editor (`w-editor` guard)

### 5b. Creative code (T2 and T3 only)
- [ ] **All creative code ships from `corient-web-runtime`** (learned-rule 101), referenced by ONE pinned `@vX.Y.Z` script tag in site head freeform. No shader, canvas or module source in any Webflow custom-code surface. The runtime version used is recorded in the handoff
- [ ] **Poster-first:** every shader surface has a real `<img>` in the DOM carrying the alt text, with `width`/`height` attributes, and that image is the LCP element. `loading="lazy"` on it is a defect (`images.lazy-lcp`). The canvas fades in over it and the img is hidden only once the shader is provably live
- [ ] **Capability gate honoured:** verified that a denied device (software rasteriser, low memory, low core count, save-data) produces zero `<canvas>` elements, an untouched poster, and **no fetch of the WebGL chunk at all**. Assert it with `?ct-gl=off` on the published URL
- [ ] **Liveness proven, not inferred (learned-rule 102):** every in-viewport shader surface publishes a growing `data-ct-frames` across a one-second gap, read on a foreground tab (`document.visibilityState === "visible"`, learned-rule 100). A surface marked `data-ct-gl="live"` with a frozen counter is a defect
- [ ] **Off-screen surfaces are culled:** a shader surface scrolled out of view sits at a static frame count and leaves the render loop. Assert one shared RAF loop and one shared pointer listener per page, not one per instance
- [ ] **Context hygiene:** GL context count does not grow across internal navigation; `webglcontextlost` is handled; DPR capped (2 desktop, 1.5 touch)
- [ ] **Reduced motion freezes motion, not layers** (the rule above, applied to shaders): each surface renders one static frame and holds, so texture, depth and colour survive with animation off
- [ ] **Authored, not decorative:** every effect traces to a stated design purpose in the design direction. A shader applied as a default surface treatment is the `anti-patterns.md` violation it looks like, whatever tier the project is
- [ ] **Adaptive quality live:** `<html data-ct-quality>` published; verified the ladder fires (induced-jank test on the fixture or staging, not assumed) and that a degraded surface restores its poster img via the fallback path
- [ ] **Audio (if present) never autoplays:** AudioContext count is 0 before the first user gesture, the toggle is accessible (44px, `aria-pressed`, keyboard), the persisted choice arms but does not start, and the context suspends when the tab hides. An autoplaying page is a defect regardless of how good the sound is
- [ ] **View Transitions (if present):** shared-element `data-ct-vt` names exist on BOTH pages of each morph pair and are unique per page; reduced-motion navigates plain

## 6. Performance (mobile, throttled, per page: instruments in webflow-verify §3)
- [ ] LCP < 1.5s and CLS < 0.05 from a throttled mobile trace (Slow 4G, 4x CPU), saved as a trace file under the job's scratch folder
- [ ] Performance score ≥ 90 (or the tier's budget in §5), TBT < 300ms and page weight < 3MB, from the Lighthouse CLI JSON saved under the job's scratch folder. `lighthouse_audit` has no performance category: its scores never satisfy this line. Not measured is reported as not measured, never estimated
- [ ] Scripted-interaction trace: signature-moment interaction latency < 200ms (INP is field-only: noted, not faked)
- [ ] Images webp/avif via `data_assets_tool.compress_assets`, run only after each original file is downloaded to `~/.claude/state/snapshots/<job_id>/assets/` and recorded in the manifest asset map as `{id, hostedUrl, local}` (`flowsmith_manifest.py add <project> --kind assets`): compression replaces the hosted file with no undo, and changes its URL (L-99). Descriptive hyphenated filenames; width/height attributes present (`images.dimensions`)
- [ ] **Image resolution in band, both ways, on one ratio:** the `currentSrc` file's pixel width over its rendered CSS width, measured at DPR 2. `images.floor`: under 1.8 is soft, under 1.0 upscaled. `images.ceiling`: over 3 (over 4 with `srcset`) on a file of 60KB or more is oversupplied, and so is any file over 300KB above 2.2. No lazy-loaded LCP image: `images.lazy-lcp` reads the browser's own largest-contentful-paint entry, not the first image in the source. Fix a floor failure with a genuine high-res re-export (e.g. `mcp__figma-remote__download_assets`), never by enlarging, and NEVER AI-upscale real people or faces if the brand bans AI imagery (flag those for the client to supply). Fix a ceiling failure by exporting at 2x the largest rendered width, or adding `srcset`. Inspect any sourced or exported asset for baked watermarks or artifacts before shipping (Figma image fills can carry a stock-source watermark).

- [ ] **No `!important` and no specificity hacks** to make a style land. Reaching for one is a signal the structure is wrong: fix the structure. The one sanctioned exception is the documented `#w-node` grid-placement override (learned-rule 6), where per-element Webflow output genuinely beats class CSS.
- [ ] **Left cleaner than found:** every style, element, interaction and asset that YOUR change orphaned is removed. Pre-existing dead code is flagged in the handover, never silently deleted ("looks unused" is not a reason, and is not yours to decide).

## 7. SEO / AEO
- [ ] Meta contract: unique titles + descriptions to pattern and length on every page (`served.meta`, `served.unique`); SERP previews emitted
- [ ] Per-page OG images; og:/twitter: tags present, image URLs return 200
- [ ] Schema map implemented per page type (runtime-injected where the templated-{{wf}} trap applies); JSON-LD parses (`served.meta`) with required fields
- [ ] Exactly one h1 per page, monotonic heading levels (`served.headings`)
- [ ] Paginated collection lists self-canonicalise; no soft-404s (`served.404`)
- [ ] Internal linking: money pages meet their inbound-link minimums from the map; no broken internal links (`served.link-status`)
- [ ] Sitemap flags correct; no orphan pages
- [ ] Staging carried noindex throughout the build (`served.noindex`)
- [ ] **Launch-day production re-run passed:** custom-domain pages 200 with no noindex (`--noindex forbid --sitemap`), robots.txt fetched and sane, sitemap reachable, canonicals on the custom host, favicon 200, top-N redirects verified
- [ ] Search Console verified (head meta) + sitemap submitted; site-settings SEO pass done (moment #6b)

## 8. Accessibility
- [ ] **A11y essentials are BUILT IN during section builds, not deferred to the QA pass:** the QA pass verifies them, it should not be discovering them. Every section ships with: a visible `:focus-visible` state on every interactive element (button + link; not `:focus`, so mouse clicks don't ring); ≥44×44px tap targets for buttons and, on touch/mobile, nav/footer/text links; exactly one `<h1>` per page with monotonic heading levels; page-level landmarks incl. a `<main>` wrapping the primary content; alt text on every meaningful image (decorative marked as such); a `title` on every `<iframe>`; matched `for`/`id` + `autocomplete` on form fields; NO opacity-muted interactive text (no `rgba(...,<1)` / `opacity` used to dim links/buttons below AA); and AA contrast (≥4.5:1) on all text, pixel-sampled from the published render (not computed from tokens, learned-rules 32/33), in idle AND hover states and across any gradient/photo background the text sits on.
- [ ] The runner's `a11y.*` checks green: landmarks, names, labels, focus visible with no hidden stops and no trap, sampled contrast (add `--axe` with a local axe-core copy when one exists). Hover-state contrast and tap targets are checked by hand
- [ ] Marquees/auto-motion pausable; ARIA on Finsweet components; menus and disclosures open, close and report `aria-expanded` honestly (`state.*`)
- [ ] accessibility-audit (WCAG 2.1) pass at both themes

## 9. QA & revisions
- [ ] Full verify loop green across the canonical sweep (visual + console + interaction), **including mobile-frame fidelity: the mobile render is checked against the MOBILE design frame, not just for responsive hygiene**: mobile-only sections, reorders and copy differences are design content, not reflow
- [ ] **Full-range responsive, not just breakpoint endpoints.** There must be no width where a mobile control and its desktop equivalent are BOTH visible (a hamburger showing from 991 while the inline CTAs hid only below 479 left both on screen from 480 to 991 on one build). Proven by the runner's ten widths, `layout.overlap-band` (20px sweeps wherever a pair comes within 40px) and `state.open-layout` (layout re-measured with every menu open)
- [ ] Two structured revision rounds completed via comments intake; scope changes flagged, not absorbed
- [ ] Zero P1/P2 defects on two consecutive QA sweep rounds

## 10. Launch & handover
- [ ] Tier 3 production publish approved and executed through a grant: after the operator's yes the main session writes `~/.claude/state/approvals/webflow-production-<site_id>.json` (site_id, domains, approved_at, approval; valid 30 minutes), and the gate hook denies any non-empty `customDomains` without it. The publish itself runs under the `webflow_publish:<site_id>` lock taken under the job's id, like a staging one, with the same spacing and report rules (§11). Post-publish verification (item 7 launch re-run) green
- [ ] Handover doc: build structure (naming grammar note), where motion code lives, CMS editing guide, the operator runbook for settings-panel items
- [ ] **Custom-code inventory**: every registered script AND freeform block (site + page level) listed with purpose, injection point, and retirement instructions (emitted by webflow-verify handover mode: the two-surface paper trail)
- [ ] 30-day post-launch smoke scheduled (weekly: webcheck + Lighthouse CLI + form-submission check)

## 11. Honesty ledger
- [ ] Every waived item listed with reason and approval
- [ ] Every design-inventory row waived (a designed section deliberately not built) is listed with who approved dropping it
- [ ] Every operator moment that fired is logged with time consumed
- [ ] Silent API failures caught during the build are recorded as learned rules
- [ ] Every change reported as done was confirmed LIVE on the published URL (not staged); any change left staged is reported "STAGED: NOT LIVE" with the owed publish, never as complete
- [ ] The `webflow_publish:<site_id>` lock was held under the job's id around each publish and released after (no concurrent-publish clobber), every staging publish passed `publishToWebflowSubdomain: true` and `customDomains: []` (L-109), and a webcheck `report.json` for the job was written between consecutive publishes. The gate hook (`hooks/agent-gates.sh`) denies a publish without the lock, without both staging parameters, or (within two hours of the last publish) without a report since it; the unlock is yours
