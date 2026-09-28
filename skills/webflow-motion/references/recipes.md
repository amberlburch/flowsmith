# webflow-motion recipes

Each: intent · code · timing · contract (what /webflow-verify asserts). ★ = production-proven on corient.com.au 2026-07-11/12. All code assumes the boot kit (SKILL.md) and sits inside a reduced-motion guard.

**Selector-hook contract (decouple motion from class names):** recipes bind to `data-*` hooks the section skeletons emit (nav → `data-nav`; reveal cards → `data-reveal-card` with the list as `data-reveal`; marquee source → `data-marquee-src`; hero title → `data-hero-title`; scenes → `data-scene`). Never hard-code grammar classes like `.services_card` — they drift between the naming grammar and legacy sites. The ★ snippets below show corient's original classes for provenance; ship the `data-*` version. (Class-selector examples marked "legacy".)

## ★ Seamless marquee (logos, text ribbons)
Intent: continuous auto-scroll, no gap at any phase, pause on hover. The trap: one duplicated set must be ≥ container width, and flex `gap` breaks the -50% wrap point — use per-item margin.
```html
<style>
.ct-marquee { overflow: hidden; width: 100%; }
.ct-marquee-track { display: flex; width: max-content; align-items: center; animation: ctScroll 40s linear infinite; }
.ct-marquee:hover .ct-marquee-track { animation-play-state: paused; }
.ct-marquee-track > * { flex: 0 0 auto; margin-right: 60px; }
@keyframes ctScroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@media (prefers-reduced-motion: reduce) { .ct-marquee-track { animation: none; } }
.ct-marquee-pause { position: absolute; right: 8px; bottom: 8px; width: 28px; height: 28px; border-radius: 50%;
  background: rgba(10,10,10,.6); color: #fff; border: 1px solid rgba(255,255,255,.2); font-size: 11px; cursor: pointer; }
</style>
<script>
(function(){ function init(){
  var src = document.querySelector('[data-marquee-src]');
  if(!src || src.dataset.ctDone) return; src.dataset.ctDone = '1';
  var items = Array.prototype.filter.call(src.children, function(el){
    var i = el.querySelector('img'); return (i && i.getAttribute('src')) || el.textContent.trim(); });
  if(!items.length) return;
  var wrap = document.createElement('div'); wrap.className = 'ct-marquee';
  var track = document.createElement('div'); track.className = 'ct-marquee-track';
  wrap.appendChild(track); src.parentNode.insertBefore(wrap, src); src.style.display = 'none';
  function addSet(){ items.forEach(function(l){ var c = l.cloneNode(true); c.removeAttribute('href'); c.style.pointerEvents = 'none'; track.appendChild(c); }); }
  addSet();
  var setW = track.scrollWidth, cw = wrap.clientWidth || innerWidth;
  var reps = Math.max(2, Math.ceil((cw + 1) / Math.max(setW, 1)) + 1);
  for(var i = 1; i < reps; i++) addSet();  // complete half 1
  for(var j = 0; j < reps; j++) addSet();  // half 2 = exact duplicate
  track.style.animationDuration = Math.max(20, Math.round(track.scrollWidth / 2 / 45)) + 's';
  var btn = document.createElement('button'); btn.className = 'ct-marquee-pause';
  btn.type = 'button'; btn.setAttribute('aria-label', 'Pause scrolling logos'); btn.setAttribute('aria-pressed', 'false'); btn.textContent = '||';
  btn.addEventListener('click', function(){ var p = track.style.animationPlayState !== 'paused';
    track.style.animationPlayState = p ? 'paused' : 'running'; btn.setAttribute('aria-pressed', String(p)); btn.textContent = p ? '▶' : '||'; });
  wrap.style.position = 'relative'; wrap.appendChild(btn);
} if(document.readyState === 'loading'){ document.addEventListener('DOMContentLoaded', init); } else { init(); }
if(window.Webflow && Webflow.push) Webflow.push(init); })();
</script>
```
WCAG pausability (dod §8 — hover is not a pause mechanism for touch/keyboard): append a `.ct-marquee-pause` button toggling `track.style.animationPlayState` between `paused`/`running`, `aria-label="Pause scrolling logos"`, `aria-pressed` synced. Reduced-motion note: the CSS media query stops the animation AND the JS init sits in the global guard — either way the original static grid must remain the fallback (keep it `display:none` only when the marquee is built).
Contract: track scrollWidth ≥ 2× container; transform advances while page idle; pauses on hover AND via the button (focusable); reduced-motion shows static content; covers container edge-to-edge at 3 sampled phases. If replacing an IX2 scroll-move: hide the original element, never override its inline transform.

## ★ Scroll-state nav
Intent: transparent bar over the hero, dark glass once scrolled — solves nav-over-light-sections without a permanent band (a translucent bar over bright video reads as flat grey; and mix-blend-mode dies inside wrapper stacking contexts — don't use it).
```html
<style>
[data-nav] { background: transparent; transition: background .35s ease, backdrop-filter .35s ease; }
[data-nav].ct-scrolled { background: rgba(10,10,10,.72); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); }
</style>
<script>
(function(){ var nav = null, t = false;
function u(){ t = false; nav = nav || document.querySelector('[data-nav]'); if(!nav) return;
  nav.classList.toggle('ct-scrolled', (scrollY || 0) > 60); }
addEventListener('scroll', function(){ if(!t){ t = true; requestAnimationFrame(u); } }, { passive: true }); u(); })();
</script>
```
Timing: 0.35s ease. Contract: class absent at y=0, present past 60px; nav text legible over the lightest section (screenshot) and the darkest.

## ★ Cinematic scrim (text over bright media)
Intent: hero text legible over video/photography without a grey band — multi-stop gradient reads as photographic vignette.
```html
<div class="ct-hero-scrims"><div class="ct-hero-scrim-top"></div><div class="ct-hero-scrim"></div></div>
<style>
.ct-hero-scrims { position: absolute; inset: 0; z-index: 1; pointer-events: none; }
.ct-hero-scrim { position: absolute; left: 0; right: 0; bottom: 0; height: 45%;
  background: linear-gradient(to top, rgba(10,10,10,.78) 0%, rgba(10,10,10,.62) 18%, rgba(10,10,10,.45) 40%, rgba(10,10,10,.22) 68%, rgba(10,10,10,0) 100%); }
.ct-hero-scrim-top { position: absolute; left: 0; right: 0; top: 0; height: 20%;
  background: linear-gradient(to bottom, rgba(10,10,10,.35), rgba(10,10,10,0)); }
</style>
```
Place between the media layer and the text layer in DOM order; give the text container an explicit higher z-index + a faint text-shadow (`0 1px 24px rgba(0,0,0,.45)`) as the second layer. Contract: text container contrast passes over the brightest media frame; scrims pointer-events none.

## ★ Hover-reveal panels (Jore-style service cards)
Intent: clean cards whose detail list reveals on hover; always-visible on touch (no hover there).
```css
@media (min-width: 768px) {
  [data-reveal-card] [data-reveal] { opacity: 0; max-height: 0; overflow: hidden; transition: opacity .3s ease, max-height .4s ease; pointer-events: none; }
  [data-reveal-card]:hover [data-reveal] { opacity: 1; max-height: 600px; pointer-events: auto; }
}
```
Timing: 0.3/0.4s. Contract: reveal on hover, collapse on out (desktop); list fully visible below 768px; content readable with animations off.

## Hero split-text choreography
Intent: the opening statement — chars/words rise in with stagger. Needs SplitText (native GSAP hosting).
```js
const split = new SplitText('[data-hero-title]', { type: 'chars,words' });
gsap.set('[data-hero-title]', { visibility: 'visible' });
gsap.from(split.chars, { yPercent: 110, opacity: 0, duration: 0.9, ease: 'power3.out', stagger: 0.02 });
gsap.from('[data-hero-sub]', { y: 24, opacity: 0, duration: 0.6, ease: 'power2.out', delay: 0.35 });
```
Guard FOUC: title `visibility:hidden` via CSS until the tween sets it (and visible-by-default inside the reduced-motion guard). Failsafe — GSAP can fail to load (toggle off, CDN block): `setTimeout(() => { if (!window.gsap) document.querySelectorAll('[data-hero-title]').forEach(el => el.style.visibility = 'visible'); }, 2000);` — an invisible h1 forever is worse than an unanimated one. Timing: 0.9s feature, 0.02s/char. Contract: no FOUC flash, chars end at identity transform, reduced-motion shows title instantly, title visible even with GSAP absent.

## Scroll-scrub scene
Intent: scroll position drives a scene (pin + progress) — the storytelling device.
```js
gsap.timeline({ scrollTrigger: { trigger: '[data-scene]', start: 'top top', end: '+=150%', scrub: 0.6, pin: true } })
  .fromTo('[data-scene-media]', { scale: 1.15 }, { scale: 1, ease: 'none' })
  .fromTo('[data-scene-caption]', { yPercent: 30, opacity: 0 }, { yPercent: 0, opacity: 1, ease: 'none' }, 0.2);
ScrollTrigger.matchMedia({ '(max-width: 767px)': () => { /* no pin on mobile — simple fade-up instead */ } });
```
Contract: pin releases cleanly (no layout jump, CLS holds), scrub tied to scroll (transform differs at two scroll positions), mobile variant unpinned.

## Parallax gallery
```js
gsap.utils.toArray('[data-parallax]').forEach(el => {
  const depth = parseFloat(el.dataset.parallax || 0.15);
  gsap.fromTo(el, { yPercent: depth * 100 }, { yPercent: -depth * 100, ease: 'none',
    scrollTrigger: { trigger: el.parentElement, start: 'top bottom', end: 'bottom top', scrub: true } });
});
```
Depth 0.08-0.2. Contract: transform-only, one batched setup (not per-item triggers beyond the array), disabled under 768px via matchMedia.

## Page transitions (Barba shutter)
Intent: cross-page wipe. Load Barba site-wide; container = `main` wrapper with `data-barba`.
```js
barba.init({ transitions: [{
  leave: ({ current }) => gsap.timeline()
    .set('.ct-shutter', { display: 'block', yPercent: 100 })
    .to('.ct-shutter', { yPercent: 0, duration: 0.5, ease: 'power3.inOut' })
    .to(current.container, { opacity: 0, duration: 0.2 }, '<'),
  enter: () => gsap.to('.ct-shutter', { yPercent: -100, duration: 0.5, ease: 'power3.inOut',
    onComplete: () => { gsap.set('.ct-shutter', { display: 'none' }); ScrollTrigger.refresh(); window.Webflow && Webflow.require('ix2') && Webflow.require('ix2').init(); } })
}]});
```
CAUTION: Barba swaps the DOM — Webflow forms, IX2 and Finsweet need re-init on enter; test every interactive element post-transition. If re-init proves flaky on a given site, ship without transitions rather than with broken forms (restraint beats breakage). Timing: 0.5s inOut. Contract: forms and nav work after two transitions; back-button works; scripts don't double-bind.

## Magnetic button
```js
gsap.utils.toArray('[data-magnetic]').forEach(btn => {
  const s = gsap.quickTo(btn, 'x', { duration: 0.3, ease: 'power3' }), t = gsap.quickTo(btn, 'y', { duration: 0.3, ease: 'power3' });
  btn.addEventListener('mousemove', e => { const r = btn.getBoundingClientRect();
    s((e.clientX - r.left - r.width / 2) * 0.3); t((e.clientY - r.top - r.height / 2) * 0.3); });
  btn.addEventListener('mouseleave', () => { s(0); t(0); });
});
```
Desktop only (guard `(hover:hover)`). Pull factor ≤ 0.35. Contract: returns to identity on leave; no effect on touch.

## Custom cursor
Dot + trailing ring via two fixed elements + quickTo (0.15/0.45 durations); scale up over `[data-cursor="link"]`. Hide via `cursor:none` ONLY on `(hover:hover) and (pointer:fine)`. Contract: native cursor intact on touch/keyboard; ring never blocks clicks (pointer-events none).

## Text scramble / number odometer
Scramble: swap chars through a glyph set over 0.6-0.9s on reveal (feature timing). Odometer: `gsap.to(obj, { val: target, duration: 1, snap: { val: 1 }, onUpdate })` triggered `once: true` at `top 85%`. Contract: final values exact; runs once.

## Draw-SVG
`gsap.from('[data-draw] path', { drawSVG: 0, duration: 1.2, ease: 'power2.inOut', stagger: 0.15, scrollTrigger: { trigger: '[data-draw]', start: 'top 80%', once: true } })`. Paths need stroke. Contract: strokes end fully drawn; once-only.

## Preloader
Only if asset weight justifies it: fixed brand-dark panel, logo micro-animation, min 0.4s / max 2.5s hard cap, slide away with `power3.inOut` 0.6s, then `ScrollTrigger.refresh()`. NEVER a colour that isn't in the brand tokens (the Corient red-flash lesson). Contract: removed from DOM/hidden after load; no scroll lock left behind; brand-token colours only.

## Mega-nav reveal
Full-screen overlay: clip-path `inset(0 0 100% 0)` → `inset(0)` 0.6s power3.inOut, links stagger 0.05s after 0.2s. Lock body scroll while open (`lenis.stop()`/`start()`). Contract: focus trapped while open, ESC closes, scroll restored.
