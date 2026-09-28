# webcheck

One self-tested check runner for published pages. It replaces hand-written `evaluate_script`
checks with one call whose JSON report is the evidence for the verify gate. Node 22 only: no
npm install, no Playwright. It drives the debug Chrome on `127.0.0.1:9222` over the Chrome
DevTools Protocol, and has a served-HTML mode that needs no browser.

Read-only against the site: it never publishes, never writes to Webflow, and never submits a form.
The state step skips submit buttons and blocks every submit event and `form.submit()` while it runs.

## Run

```
node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs <url>... [flags]
```

| Flag | Default | Meaning |
|---|---|---|
| `--widths 320,375,...` | `320,375,390,480,768,991,1024,1280,1440,1920` | The canonical sweep. Each width is a fresh, cache-busted load. |
| `--checks a,b` | all except `completeness` (added when `--inventory` is given) | Any of `served,layout,text,images,a11y,state,console,completeness`. |
| `--inventory <file>` | none | JSON design inventory (format below). Turns on `completeness`. |
| `--copy <file>` | none | Approved copy: a `.json` file (every string value counts) or a `.md`/`.txt` copy map (every line and table cell counts; inline code such as a node id in backticks, and a bare leading node id, is dropped). Turns on the copy diff and makes Sentence case strict. |
| `--out <dir>` | `~/.claude/_scratch/YYYY-MM-webcheck-<job>` | Must be under `~/.claude/_scratch`. |
| `--job <id>` | `wc-<timestamp>` | Names the output folder. Pass the dispatch job id. |
| `--html-only` | off | Served-HTML checks only (`served` must be among `--checks`). Use when Chrome is down. |
| `--expect <text>` | none | Repeatable. The served bytes of every URL must contain it (confirms a write landed). |
| `--absent <text>` | none | Repeatable. The served bytes must not contain it (retired script or marker). |
| `--ignore <css>` | none | Repeatable. Elements inside it are skipped by the browser checks. Name the reason in the handoff. |
| `--waive "<check>\|<text>\|<reason>"` | none | Repeatable, served checks only. A problem in that `served.*` row containing `<text>` stops counting; the reason is kept in the row's `evidence.waived`. All three parts are required. |
| `--lang <code>` | `en-AU` | Expected `<html lang>`. `any` only requires a value. |
| `--noindex expect\|forbid` | `expect` on `*.webflow.io`, unchecked elsewhere | `forbid` for launch mode on the production domain. |
| `--sitemap` | off | Also check every same-origin URL in `/sitemap.xml` (served checks, up to 200). |
| `--axe <path>` | off | Inject a local `axe.min.js` (for example from any project's `node_modules/axe-core/`). Nothing is downloaded. |
| `--port <n>` | `9222` | Debug Chrome port. On 9222 the runner starts Chrome itself through `~/.claude/lib/debug_chrome.sh` when nothing listens. |

Exit code: `0` everything passed (warnings allowed), `1` any check failed, `2` usage error or the
browser could not be used (the report says which). A run in which no check produced a pass or a
fail is `ERROR`, never `PASS`. Stdout is the short summary and names the check families that ran;
the full evidence is `report.json` beside `summary.txt` in the output folder, plus a viewport
screenshot for every width that failed (taken after the state step, on a fresh load) and one at
the first colliding width of a failing band sweep.

Typical calls:

```
# phase gate on staging, every page in the inventory, copy diffed against the copy map
node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs https://<site>.webflow.io/ https://<site>.webflow.io/about \
  --inventory <pack>/design-inventory.json --copy <pack>/copy-map.md --job <job_id>

# confirm a write landed, without a browser
node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs https://<site>.webflow.io/pricing --html-only --expect "New headline"

# launch mode on the production domain
node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs https://<domain>/ --noindex forbid --sitemap
```

## Report

`report.json`: `{ verdict, job, started, finished, chrome, urls, widths, checks, checksRun, waivers, summary, results }`.
Each result is `{ check, status, message, page, width, evidence }`, with status `pass`, `fail`,
`warn`, `error`, `skip` or `info` (screenshot paths). Passing results are kept, so the report
shows what was measured at every width, not only what broke. Cite the report path as the
evidence source in the critique and handoff.

## What each check proves

**served** (cache-busted `?wcb=` plus no-cache headers, no browser)
- `served.status`, `served.type`: the page returns 200 HTML. Records `age` and `x-cache` so a stale edge is visible.
- `served.noindex`: staging carries noindex; with `--noindex forbid`, production does not.
- `served.residue`: no template residue in the bytes, hidden elements and attributes included: lorem ipsum, John or Jane Doe, Example Text, "This is some text inside of a div block", Webflow's default form success and failure copy, template stock names, and bare default labels (`Heading`, `Text Link`, `Button Text`, `Block Quote`, `List Item`, `Field Label`).
- `served.lang`: `<html lang>` matches `--lang`.
- `served.headings`: exactly one h1 in the bytes and no skipped heading level.
- `served.meta`: title, description, canonical, og:title, og:description, og:image and twitter:card present; every JSON-LD block parses.
- `served.labels`: every `label for=` points at a real id (catches Webflow's `for=""`).
- `served.alt`: every img carries an alt attribute.
- `served.sri`: scripts from static CDNs (jsdelivr, unpkg, cdnjs, Google, jQuery) carry `integrity` and `crossorigin`. Webflow's own Google Fonts loader (`webfont.js` on ajax.googleapis.com) only warns, because the fix is to self-host the fonts, not to edit the tag.
- `served.lazy-hero` (warn): the first content image is not `loading=lazy`.
- `served.links`: no `href="#"`, empty, `javascript:`, malformed or dangling `#id` links, and no raw 24-hex item ids in paths. `href="#"` is allowed on a scripted toggle (`role="button"` or `aria-controls`) and on a Webflow lightbox (`w-lightbox`), and `#top` is valid by spec.
- `served.link-status`: every internal link target returns 200 cache-busted.
- `served.assets`: every stylesheet and same-origin script returns 200 cache-busted.
- `served.unique`: title, description and og:image differ across the checked pages.
- `served.404`: a bogus URL returns a real 404, not a soft one.
- `served.expect`, `served.absent`, `served.sitemap`: the flags above.
- A page that breaks the parser gives an `error` row for that page; the other pages and the site-wide rows still run.

**layout** (every width; `layout.viewport` first asserts `innerWidth` and a visible tab, or the width is marked invalid)
- `layout.overflow`: the page does not scroll sideways; names the outermost offenders.
- `layout.escape`: nothing is partly cut off at the viewport edge. Catches content that `html` or `body` `overflow-x:hidden` hides from `scrollWidth`.
- `layout.containment`: every in-flow element fits inside its parent, and no text overflows its own box (the per-element check the L-90 amendment requires). Negative margins, absolute and fixed boxes, and overflow that an ancestor visibly clips (masks, marquees, scrollers) are deliberate and skipped.
- `layout.clipped`: no box with `overflow:hidden` or `clip` cuts a line of text on the axis it clips. Ellipsis, line clamp, running animations and slider classes are skipped.
- `layout.overlap`: absolutely positioned text blocks sharing a container never intersect.
- `layout.overlap-band`: when a pair overlaps or sits within 40px at a width, the bands either side are swept in 20px steps (L-106), so a collision that exists only between two clean breakpoints still fails.

**text**
- `text.orphans` (every width): no heading, paragraph, quote, caption, kicker, label or title block of three or more words ends on a one-word line. Words go to the line of their last rect (L-43), and a synthetic forced orphan must be caught first or the result is a fail, never a trusted zero.
- `text.hyphen-wrap` (warn): hyphenated words split across lines.
- `text.case` (once, at the width nearest 1440): headings, kickers, titles, nav links and buttons in Sentence case. Flags a line when more than half its non-initial words of four or more letters are capitalised, ignoring acronyms, words after `. ? ! :` and proper nouns (capitalised mid-sentence somewhere in the copy map and never written there in lower case). An exact copy-map match passes. CSS `text-transform: capitalize` always fails. Without `--copy` this is a warning, because proper nouns are unknown.
- `text.full-stop`: no heading, kicker, title or label ends in a full stop (`?`, `!` and ellipses are fine).
- `text.residue`: the residue list above in the rendered text, including copy injected by script.
- `text.copy` (with `--copy`): every visible run of four or more words matches the copy map (at least 90% of its words in order in one entry). An invented CTA or testimonial is listed as unmatched.

**images** (every width, DPR 2 emulated so `srcset` picks its retina file)
- `images.floor`: ratio = the `currentSrc` file's own pixel width / rendered CSS width (dod.md section 6). Under 1.0 fails as upscaled, under 1.8 warns as soft. Background images with `cover` or `contain` are included.
- `images.ceiling`: over 3x (4x when `srcset` exists, since the browser already chose) with a file of 60KB or more fails as oversupplied, as does anything over 300KB and 2.2x. Smaller cases warn.
- `images.broken`, `images.dimensions`: no image fails to load; every img has width and height attributes.
- `images.lazy-lcp`: the actual Largest Contentful Paint element (from the browser) is not `loading=lazy`. `images.lazy-fold` warns for other lazy images above the fold.

**a11y** (at the widths nearest 1440 and 375)
- `a11y.headings`, `a11y.landmarks`: one visible h1, no skipped levels, exactly one main, and nav, banner and contentinfo present (missing ones warn).
- `a11y.alt`, `a11y.labels`: every img has alt (file-name alts warn); every field has a real label, and placeholder-only fields and dangling `label for` fail.
- `a11y.names`: every link, button, field and image has an accessible name, read from the browser's own accessibility tree, not from `textContent` (M7).
- `a11y.focus-visible`, `a11y.focus-hidden`, `a11y.focus-trap`: real Tab key presses walk the page. Every stop must change its focus style (outline, shadow, border, colour, background or a pseudo-element), never land on something invisible or off screen, and never loop. `a11y.focus-order` warns for unreachable focusables and positive tabindex.
- `a11y.contrast`: text colour from computed style against background pixels sampled from a screenshot with all text hidden, 15 points per line, 10th percentile. AA thresholds (3:1 for large text). Only text that is actually on top is sampled, so stacked tab panels and clipped text do not count. `a11y.contrast-coverage` warns for text never sampled.
- `a11y.axe` (with `--axe`): serious and critical violations fail, others warn.

**state** (F10; nav toggles at every width they show, other disclosures and forms at the width nearest 1440 and 375)
- `state.negative`: on a fresh load no empty, no-results, error, validation, alert or Webflow form done/fail state is visible (id and class selectors both, M3).
- `state.toggle`, `state.aria`, `state.menu-links`, `state.open-layout`, `state.close`: each `.w-nav-button`, `[aria-expanded]`, `details>summary`, `.w-dropdown-toggle` and accordion or FAQ trigger is clicked with a real mouse event (a submit button inside a form never is). It must reveal something, `aria-expanded` must match what is shown, every revealed link must sit inside the viewport (or in a scrollable panel), the layout checks are re-run with it open, and it must close on a second click and, for nav and dropdowns, on Escape.
  - Visible means visible after every clipping ancestor, so a `max-height:0; overflow:hidden` panel counts as closed. A control with an `aria-controls` target is judged on that target (new text inside it, or its visible height growing). Others are judged on text that newly appeared anywhere, minus content that moves on its own: sliders, marquees, looping CSS animations, and anything that changed while nobody clicked.
  - A blank first click gets a second, because a hover dropdown can close on the click. If still nothing is revealed, it fails when the control declares `aria-expanded` or `aria-controls`, and warns otherwise.
  - Each wait lasts until the page is stable and no finite CSS transition or animation is still running, so a slow close is not read as stuck.
  - `state.submit-blocked` (warn): a tested control fired a form submission, which was blocked.
- `state.form-names`, `state.form-validation`, `state.form-layout`: field names at submit time are present and unique; the form's validation state is entered with `reportValidity()` (never a submit), errors should be associated with their fields (warn), and the layout is re-measured in that state. A form with no required fields warns, because an empty submit would send.

**console**: no console error, uncaught exception or failed resource across every load of the page.

**completeness** (F12): each designed section exists, renders with a non-zero box, sits in design order, meets its photo count and renders every element on its checklist, at each viewport the inventory names. A dropped section passes only with a named waiver that has a reason and an approver. A viewport the inventory leaves out warns, so a missing mobile twin is named, never assumed.

## Design inventory format

```json
{
  "base": "https://<site>.webflow.io",
  "viewports": { "desktop": 1440, "mobile": 390 },
  "pages": {
    "/": {
      "desktop": [
        { "section": "hero", "node": "12:34", "photos": 1, "elements": [".hero_badge", ".hero_cta"] },
        { "section": "logos", "node": "12:80", "selector": ".section_logos" }
      ],
      "mobile": [
        { "section": "hero", "node": "40:2", "photos": 1 }
      ]
    }
  },
  "waivers": [
    { "page": "/", "viewport": "mobile", "section": "logos", "reason": "Dropped in client review", "approver": "The operator", "date": "2026-09-28" }
  ]
}
```

- `pages` keys are paths (or full URLs). Every page in the inventory is checked, whether or not it was passed on the command line; `base` (or the first URL's origin) resolves the paths.
- Rows are in design order. `section` is required. `selector` defaults to `.section_<section>`, the naming grammar's section class. `photos` counts raster images and CSS background images inside the section. `elements` are selectors that must render inside it. `node` is carried through for traceability.
- `viewports` maps names to widths (defaults `desktop: 1440`, `mobile: 390`) and those widths are loaded even when they are not in `--widths`.
- A waiver matches on `section`, and on `page` and `viewport` when given. Without `reason` and `approver` it does not suppress the row.

## Browser notes

- Each run opens its own browser context in the shared debug Chrome, so parallel jobs never share tabs, cookies or storage, and closes it at the end.
- HTTP cache is disabled and every load carries a `wcb` cache-bust parameter.
- Escape is sent as an in-page keydown: a CDP Escape key event hangs the browser process of headless Chrome 154 on macOS. Tab uses real key events.
- Screenshots are taken at 1x of the scrolled viewport: a full DPR 2 frame of a photo-heavy page is larger than one WebSocket message and closes the connection.
- If another session restarts the shared Chrome mid-run, the run stops with an `error` result and exit 2 within seconds. Rerun it.
- A Chrome that answers `/json/version` but never replies over the socket gives an `error` result, a `report.json` and exit 2 after about 15 seconds.

## Self-test

```
python3 -m pytest ~/.claude/tests/test_webcheck.py -q
```

It serves `fixtures/` with `python3 -m http.server` on a free port. `pass.html` must come back
clean on every check, and each `fail-*.html` must fail the checks it was built to break (overflow,
the L-90 clipped CTA, the L-106 band collision, orphans, case, full stops, invented copy, residue,
upscaled, oversupplied, broken and lazy LCP images, headings, landmarks, names, labels, focus
ring, hidden focus, focus trap, contrast, open-menu geometry, aria mismatch, a stuck
`aria-expanded` on a max-height accordion, Escape, a declared toggle that reveals nothing,
negative states, duplicate form names, console errors, and every completeness failure including an
invalid waiver). `pass.html` also carries a looping marquee beside a read-more toggle, which must
not read as a reveal. The state test reads the fixture server's request log to prove no form was
submitted. Other tests cover a stalled Chrome (exit 2 with a report), the house `copy-map.md`
format, served toggles, lightboxes, `#top`, a malformed fragment, the Webflow font loader and
`--waive`. Browser tests skip when the debug Chrome cannot start; the axe test runs only when a
local `axe-core` copy exists under `~/Code/*/*/node_modules/`.

## Not covered here

Visual fidelity against the design (VLM judge and colour difference), WebGL liveness and the
creative-code layer, throttled performance, reduced motion, focus moving into an opened menu,
search filtering, hover styles, and closing a menu by choosing a link. Those stay with the other
webflow-verify layers and chrome-devtools.
