---
name: webflow-motion
description: "The award-tier motion engine for Webflow. ALL motion is custom code: IX2 interactions cannot be authored by any API, and IX3 is banned except its pilot on the eval fixture site. Four experience tiers: native CSS scroll-driven animation (T0), GSAP + Lenis choreography (T1), WebGL shader surfaces (T2), full immersive experiences (T3). T0/T1 inject via data_scripts_tool; T2/T3 ship from the corient-web-runtime bundle. Use for hero choreography, scroll scenes, page transitions, marquees, split-text reveals, custom cursors, hover systems, preloaders, fluted glass, dither/halftone/ASCII treatments, image displacement, flow fields. Triggers on \"/webflow-motion\", \"animate this section\", \"add the motion pass\", \"make it feel like an award site\", \"add a shader\", \"immersive hero\"."
---

# webflow-motion: the craft layer

**Ledger:** run `/flowsmith-loop brief` first (preloaded in a flowsmith dispatch); it reads the `LEDGER-INDEX` and only the matching entries, never the whole ledger. Shim discipline from rule 19: never set textContent on a non-leaf element; walk to leaf text nodes only.

## The one architectural fact
No API can create, edit, or delete Webflow IX2 interactions. Every animation this skill ships is **custom code**. Never fight an existing IX2 interaction's inline transforms: build a fresh element the interaction doesn't touch and hide the original.

**IX3 is banned except its pilot.** `data_interactions_tool` can now create, update and delete IX3 interactions headlessly, but no recipe, contract or verify check covers IX3 playback or reduced motion yet. Create, update or delete one only on the eval fixture site (`agents/flowsmith/eval/fixture.json`), for the pilot. Everywhere else, `list_interactions` (read-only) to inventory what a site already has, and record them with `python3 ~/.claude/lib/flowsmith_manifest.py add <project> --kind interactions --items '[{"id": "...", "name": "..."}]'`. With no manifest, or if `add` rejects the kind, list them in the handoff's Known limitations instead. Never remove an existing one. The pilot (one fixture section, a simple reveal with `conditionalPlayback` `prefers-reduced-motion`, a webflow-verify contract) lands as a ledger entry before this ban lifts.

## The second architectural fact
No Webflow custom-code surface can carry creative code (learned-rule 101). Page freeform 406s on any `<script>` tag or `url(` token, registered inline scripts cap at 2000 characters, and the registry 404s on sites that never used it. So the ceiling on what this skill can inject inline is roughly a snippet, and everything above that ships from **`~/Code/corient/corient-web-runtime`**: TypeScript source, esbuild bundle, unit tests, an 18KB core budget enforced by the build, published to a pinned jsDelivr tag.

## Choose the tier before choosing the recipe
| Tier | Vocabulary | Where the code lives | Budget |
|---|---|---|---|
| **T0 Refined** | `animation-timeline: view()` / `scroll()`, view transitions, CSS states | runtime `reveal`/`scroll-nav`, or plain page CSS | performance >= 95 |
| **T1 Choreographed** | GSAP + Lenis, the recipe library below | freeform head/footer, or the runtime | performance >= 90 |
| **T2 Surfaced** | 1-3 WebGL shader surfaces on named elements | runtime only | >= 90 desktop / >= 85 mobile, <= 1.5MB added, 60fps at 1440 |
| **T3 Immersive** | full WebGL page, or a Webflow Cloud app | runtime or a Cloud app | frame-time budget + hard mobile fallback + client sign-off |

**T0 first.** Native scroll-driven animations run on the compositor with zero main-thread JavaScript and now have roughly 84% global support (Chrome/Edge 115+, Firefox 132+, Safari 18+). Most reveals, progress indicators and simple parallax should be a `view-timeline` with a `@supports` fallback, not a ScrollTrigger. Main-thread budget you don't spend on a fade is budget the one signature moment can have.

Tier is named at design direction and recorded in the manifest. It never creeps upward mid-build. `reference/design-systems/anti-patterns.md` decides whether an effect is authored or decorative: a shader used as a default surface treatment is banned at every tier.

## Boot kit (once per site)
1. **GSAP**: Webflow-native hosting (Site Settings → GSAP toggle, includes ScrollTrigger/SplitText/Flip/MorphSVG/DrawSVG: a staged human step in Phase 0). Fallback: jsDelivr `gsap@3` + plugins, `defer`.
2. **Lenis** via jsDelivr, wired exactly so:
```js
const lenis = new Lenis({ duration: 1.1, smoothWheel: true, smoothTouch: false });
lenis.on('scroll', ScrollTrigger.update);
gsap.ticker.add((t) => lenis.raf(t * 1000));
gsap.ticker.lagSmoothing(0);
```
3. Reduced-motion guard wraps EVERYTHING: `if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;`, and the page must be complete without any of it.
4. **Editor guard** (mandatory): motion must NOT run inside the Webflow Designer/editor: it fights the canvas and misleads QA. Gate every init: `if (window.Webflow && Webflow.env && Webflow.env('editor')) return;` (or check `html.w-editor`).
5. **Lifecycle + teardown discipline** (Webflow behaves SPA-like on internal nav / Barba; ScrollTriggers, RAF loops and listeners LEAK and double-fire across page changes if never cleaned up, and the two-surface audit can't see this by inspection). Register each scene through a lifecycle so it tears down on page-out:
```js
// one loader, per-page teardown. Scenes push their cleanup; page-out runs them all.
window.__ct = window.__ct || { cleanups: [] };
function ctScene(fn){ var c = fn(); if (typeof c === 'function') window.__ct.cleanups.push(c); }
function ctTeardown(){ window.__ct.cleanups.splice(0).forEach(function(c){ try { c(); } catch(e){} });
  if (window.ScrollTrigger) ScrollTrigger.getAll().forEach(function(t){ t.kill(); }); }
// example scene returning its cleanup:
ctScene(function(){ var st = ScrollTrigger.create({ /* ... */ });
  var onResize = function(){ ScrollTrigger.refresh(); }; addEventListener('resize', onResize);
  return function(){ st.kill(); removeEventListener('resize', onResize); }; });
// Barba/SPA nav: call ctTeardown() on leave, re-run scene init on enter (see page-transitions recipe).
```
Single-loader indirection (one externally-hosted/site-footer entry that dispatches per-page scenes) means motion updates without re-publishing every page. Priority RAF/resize/scroll subscriptions (one shared loop, scenes subscribe/unsubscribe) beat N independent loops.

## Restraint rules (hard constraints, not suggestions)
- **3-5 animated moments per section.** Heroes, featured content, conversion points move; supporting content rests.
- **One signature moment per site**: a single interaction worth stopping for. Choose it deliberately at design direction.
- Timing hierarchy: micro 0.2-0.3s · standard 0.4-0.6s · feature 0.8-1.2s · storytelling 1.5s+. Ease-out for deceleration; elastic only for snap-back; SplitText stagger ~0.02s/char, card staggers 0.1s.
- **transform/opacity only** (GPU). `will-change` on ≤10 elements, removed after animation.
- Mobile simplification via `ScrollTrigger.matchMedia()`: elaborate desktop, calm mobile.
- Batch ScrollTriggers with staggers; never one trigger per list item.

## Injection discipline (where code lives)
| Code | Where | Via |
|---|---|---|
| **The runtime (all T2/T3, plus T0/T1 scenes it covers)** | **site head, once, pinned `@vX.Y.Z`** | **`set_site_freeform_code`: one `<script type="module">` tag, never a branch** |
| Libraries (Lenis, Barba) | site head | `data_scripts_tool.set_site_freeform_code` |
| Site-wide boot + shared scenes | site footer | same |
| Page-specific scenes + `@keyframes` | page footer `<style>`/`<script>` | `set_page_freeform_code` |
| Component-scoped markup/SVG | HtmlEmbed element | `data_element_tool.set_settings` code |

whtml_builder css CANNOT carry @keyframes or non-Webflow media queries: keyframes always go in freeform `<style>`. Inline scripts registered via the scripts registry cap at 2000 chars, so freeform blocks or hosted (jsDelivr/GitHub) for anything bigger.

## Recipe library
`references/recipes.md`: each recipe = intent · code · timing spec · perf notes · **assertable contract** (what webflow-verify checks). Production-proven recipes are marked ★ (shipped live on corient.com.au). Compose recipes; don't invent choreography from nothing: the Osmo-tier patterns are the vocabulary.

Index (T0/T1): hero split-text choreography · scroll-scrub scene · parallax gallery · seamless marquee ★ · scroll-state nav ★ · cinematic scrims ★ · hover-reveal panels ★ · page transitions (Barba shutter/wipe) · magnetic buttons · custom cursor · text scramble · number odometer · draw-SVG · preloader.

Index (T2, runtime scenes, configured with `data-ct-scene` + `data-ct-*`, never hand-written): `fluted-glass` (vertical ribs refracting the element's image) · `dither` (ordered dither / halftone / ASCII, `data-ct-mode`) · `displace` (image displacement on hover and scroll with chromatic split) · `flow-field` (domain-warped gradient field in brand tokens) · `text-fx` (WebGL display type: ripple / dissolve / scatter / refract, DOM heading stays for a11y and SEO) · `cursor-trail` (fluid ink trail, fine pointers only) · `model` (GLTF hero object, OGL-lit, pointer / idle / scrub rotation, its own lazy chunk). Full option lists in the runtime's README and at the top of each `src/effects/` file.

Index (T0, runtime scenes): `scrub` (sticky-runway scroll progress as `--ct-progress` + `uProgress`, replaces most pin/scrub ScrollTrigger uses) · `page-transitions` (cross-document View Transitions: fade / wipe / slide + shared-element morphs via `data-ct-vt`, **the replacement for Barba**: no DOM swap, so Webflow forms, IX2 and Finsweet never need re-init, and unsupported browsers simply navigate). The Barba recipe stays in the library for legacy maintenance only; never introduce it on a new build.

**Adaptive quality is on for every runtime GL page**: the governor degrades DPR then cheap-shader then poster under sustained frame-time pressure, degrade-only. Nothing to author, but budget your scene for the fact that `uQuality` can drop to 0: expensive branches must be behind it.

## Ambient audio (the sound layer)
Scene `audio`, its own lazy chunk. Two modes: `generative` (WebAudio drone in the brand's pitch material, zero assets, scroll opens the filter) and `file` (an authored seamless loop via `data-ct-src`: the Åtrå path, and the differentiator). Non-negotiables baked into the runtime: OFF by default, a real 44px `aria-pressed` toggle (author-supplied via `data-ct-audio-toggle` or runtime-injected bottom-left), the AudioContext constructed only inside the click, choice persisted but a remembered "on" only ARMS the button, context suspended when the tab hides. Never propose autoplaying audio to a client; the runtime cannot do it and would not.

**Every T2 scene is poster-first**: the `<img>` stays in the DOM carrying its alt text and `width`/`height`, it is the LCP element, and the canvas fades in over it. The capability gate denies software rasterisers (which is what Lighthouse's mobile run emulates), sub-4GB devices, sub-4-core devices and save-data, and on a denial the 66KB WebGL chunk is never fetched at all.

## Definition of done for a motion pass
Every recipe's contract green in `/webflow-verify` (console zero, reduced-motion complete, budgets held, contract assertions), restraint rules audited (count the moments per section: literally count), signature moment demonstrably present, and the scripted-interaction trace under 200ms.

**T2/T3 adds `/webflow-verify` §2d**, and it is behavioural, not static (learned-rule 102): a growing `data-ct-frames` on every in-viewport surface read from a foreground tab, off-screen surfaces holding a static count, one shared RAF loop and one shared pointer listener per page, `?ct-gl=off` producing zero canvases with the poster intact and the WebGL chunk never fetched, reduced motion holding one static frame rather than disappearing, and GL context count flat across internal navigation. A surface marked `data-ct-gl="live"` whose frame counter never moves is a defect, not a pass.

## Eval Criteria
Layer (a), gate-runnable: given a fixture section brief, the emitted plan/code MUST contain the Lenis→ScrollTrigger wiring lines, a reduced-motion guard, only transform/opacity tweens, timings within the hierarchy bounds, and keyframes placed in freeform style (never whtml css); MUST NOT reference IX2 or IX3 authoring or exceed 5 moments for one section.
Layer (b), live fixture: the recipe runs on the eval fixture site pinned in `agents/flowsmith/eval/fixture.json` (nothing runs while its `site_id` is null) and passes its assertable contract via /webflow-verify, including the reduced-motion render.
