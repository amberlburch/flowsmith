# Section pattern library — whtml skeletons

Seven core section types, whtml_builder-ready. Every skeleton follows the fixed page skeleton (`section_[id]` > `padding-global` > `container-[size]` > `padding-section-[size]`) and the pinned grammar in `webflow-design-system/references/naming.md` — every custom class is `[component]_[element]`, hyphenated multiword, no abbreviations. No motion is inlined here; motion hooks name recipes from `webflow-motion/references/recipes.md` only — inject via `data_scripts_tool`, never IX2.

★ = reflects a production pattern shipped live on corient.com.au. Match it, don't reinvent it.

## 1. Hero ★

**Intent:** first-screen conversion moment — media background, headline, one CTA, optional booking-card corner slot. Use on homepage and top-of-funnel landing pages only; interior pages use a lighter header.

```html
<section class="section_hero">
  <div class="padding-global">
    <div class="container-large">
      <div class="padding-section-large">
        <div class="hero_media-wrap">
          <!-- asset: hero-media -->
          <img class="hero_media" src="" alt="Placeholder hero background" />
          <div class="hero_scrim"></div>
        </div>
        <div class="hero_content">
          <!-- copy: h1 -->
          <h1 class="hero_heading" data-hero-title>Placeholder headline for the hero</h1>
          <!-- copy: sub -->
          <p class="hero_subheading" data-hero-sub>Placeholder one-line supporting copy.</p>
          <a href="#" class="hero_cta button">Placeholder CTA</a>
        </div>
        <!-- slot: booking-card (optional) -->
        <div class="hero_booking-card">
          <p class="hero_booking-card-label">Placeholder booking prompt</p>
          <a href="#" class="hero_booking-card-link button">Book now</a>
        </div>
      </div>
    </div>
  </div>
</section>
```

**Variants:** split (media left/right of content, two-column) vs centred (media full-bleed background, content stacked centre) — ★ corient production default is centred + booking-card pinned bottom-right corner.

**Motion hooks:** hero split-text choreography · ★ cinematic scrim · parallax gallery (media-heavy variant).

**Assertable contract:**
- exactly one `h1` on the page, inside `.hero_heading`
- `.hero_cta` has a resolved `href` (not `#`) at content-fill time
- `.hero_media` has non-empty `alt`
- `.hero_booking-card` present only when the slot comment is filled, absent otherwise (no empty shell)

## 2. Features / services grid ★

**Intent:** the "what we do" proof section — card grid, each card reveals detail on hover. Use directly after hero or as a standalone interior-page section; never nest inside another grid.

```html
<section class="section_services">
  <div class="padding-global">
    <div class="container-large">
      <div class="padding-section-medium">
        <!-- copy: h2 -->
        <h2 class="services_heading">Placeholder section heading</h2>
        <div class="services_grid">
          <!-- repeat .services_card N× (content-driven count) -->
          <div class="services_card" data-reveal-card>
            <!-- asset: card-icon -->
            <img class="services_card-icon" src="" alt="Placeholder service icon" />
            <!-- copy: card-title -->
            <h3 class="services_card-title">Placeholder service name</h3>
            <p class="services_card-body">Placeholder one-line service description.</p>
            <div class="services_card-reveal" data-reveal>
              <p class="services_card-reveal-text">Placeholder reveal detail copy.</p>
              <a href="#" class="services_card-link">Learn more</a>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>
```

**Variants:** 2-col stagger (★ corient production default — cards offset vertically, alternating) vs 3/4-col even grid (denser catalogue use). Card count is content-driven, not fixed by the skeleton.

**Motion hooks:** ★ hover-reveal panels (Jore-style) · card stagger-in on scroll (batched ScrollTrigger, not one trigger per card).

**Assertable contract:**
- exactly one `h2` per section, inside `.services_heading`
- every `.services_card` has a `.services_card-title` and a non-empty `.services_card-icon` alt
- `.services_card-reveal` content hidden by default and reachable via keyboard focus (not hover-only)
- card count matches CMS/content source count when bound (no orphan placeholder cards left live)

## 3. Testimonials

**Intent:** social proof, slider-safe. Use mid-page or pre-CTA-band; never as the first section.

```html
<section class="section_testimonials">
  <div class="padding-global">
    <div class="container-medium">
      <div class="padding-section-medium">
        <!-- copy: h2 -->
        <h2 class="testimonials_heading">Placeholder heading</h2>
        <div class="testimonials_track">
          <div class="testimonials_card">
            <p class="testimonials_card-quote">Placeholder quote text goes here.</p>
            <div class="testimonials_card-attribution">
              <!-- asset: attribution-avatar -->
              <img class="testimonials_card-avatar" src="" alt="Placeholder headshot" />
              <div class="testimonials_card-attribution-text">
                <p class="testimonials_card-name">Placeholder Name</p>
                <p class="testimonials_card-role">Placeholder Role, Placeholder Company</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>
```

**Variants:** single-card carousel (`.testimonials_track` as slider) vs static 3-up grid (drop the slider, `.testimonials_track` becomes a plain grid container — same markup, different style only).

**Motion hooks:** scroll-scrub scene (slide transitions) · none required for static grid variant.

**Assertable contract:**
- every `.testimonials_card` has name, role, and company text present (not just a quote)
- `.testimonials_card-avatar` has non-empty alt or is explicitly decorative (`alt=""`) — never missing
- slider variant reachable via keyboard (prev/next in tab order), respects `prefers-reduced-motion`

## 4. Pricing

**Intent:** tiered offer comparison. Use once per page, directly before or after the CTA band it feeds.

```html
<section class="section_pricing">
  <div class="padding-global">
    <div class="container-large">
      <div class="padding-section-medium">
        <!-- copy: h2 -->
        <h2 class="pricing_heading">Placeholder pricing heading</h2>
        <div class="pricing_grid">
          <!-- repeat .pricing_tier N× (max one carries is-featured) -->
          <div class="pricing_tier is-featured">
            <p class="pricing_tier-name">Placeholder tier name</p>
            <p class="pricing_tier-price">$0</p>
            <ul class="pricing_tier-features">
              <li class="pricing_tier-feature">Placeholder feature one</li>
              <li class="pricing_tier-feature">Placeholder feature two</li>
            </ul>
            <a href="#" class="pricing_tier-cta button">Choose plan</a>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>
```

**Variants:** 3-tier comparison (one `.is-featured` combo marks the recommended tier) vs single-tier "contact for quote" (drop the grid, one `.pricing_tier` centred, price replaced with CTA copy).

**Motion hooks:** card stagger-in on scroll · magnetic button (featured tier CTA only — restraint rule caps this to the one signature moment per site, don't apply site-wide).

**Assertable contract:**
- every `.pricing_tier` has a name, a price, at least one feature, and a working CTA link
- exactly one `.is-featured` tier maximum (never zero-is-fine, never two)
- feature list is a real `<ul>/<li>` (screen-reader list semantics, not divs)

## 5. CTA band

**Intent:** the single-purpose conversion interrupt — one message, one action, full-bleed contrast background. Use once per page, typically pre-footer.

```html
<section class="section_cta-band">
  <div class="padding-global">
    <div class="container-medium">
      <div class="padding-section-medium">
        <!-- copy: h2 -->
        <h2 class="cta-band_heading">Placeholder conversion prompt</h2>
        <p class="cta-band_body">Placeholder one-line supporting copy.</p>
        <a href="#" class="cta-band_cta button">Placeholder CTA</a>
      </div>
    </div>
  </div>
</section>
```

**Variants:** text-only (above) vs media-flanked (adds a `.cta-band_media` image beside the content, two-column at desktop, stacked at mobile — same class root, no new component name).

**Motion hooks:** magnetic button · draw-SVG (decorative accent only, never load-bearing).

**Assertable contract:**
- exactly one CTA link per band, `href` resolved (not `#`)
- heading is `h2` (never a second `h1`)
- band renders and reads correctly with animations off (`prefers-reduced-motion`)

## 6. Footer

**Intent:** the site-wide close — nav columns, socials, copyright row LAST. One instance per site, lives outside per-page section builds, owned by the main thread (not a section subagent).

```html
<footer class="footer_wrapper">
  <div class="padding-global">
    <div class="container-large">
      <div class="padding-section-medium">
        <div class="footer_top">
          <!-- asset: footer-logo -->
          <img class="footer_logo" src="" alt="Placeholder company name logo" />
          <div class="footer_nav-columns">
            <!-- repeat .footer_nav-column N× (content-driven count) -->
            <div class="footer_nav-column">
              <p class="footer_nav-column-title">Placeholder column title</p>
              <a href="#" class="footer_nav-link">Placeholder link</a>
              <a href="#" class="footer_nav-link">Placeholder link</a>
            </div>
          </div>
          <div class="footer_socials">
            <a href="#" class="footer_social-icon" aria-label="Placeholder social network">
              <!-- asset: social-icon -->
            </a>
          </div>
        </div>
        <div class="footer_bottom">
          <p class="footer_copyright">© Placeholder Year Placeholder Company. All rights reserved.</p>
        </div>
      </div>
    </div>
  </div>
</footer>
```

**Variants:** none structural — nav column count is content-driven; copyright row order is fixed and never negotiable (it is always last, per the section-type spec).

**Motion hooks:** none by default (footer rests — restraint rule reserves motion for hero/featured/conversion points).

**Assertable contract:**
- `.footer_bottom` (copyright) is the last child in DOM order, no element follows it
- every `.footer_social-icon` has an `aria-label` (icon-only links)
- every `.footer_nav-link` has a resolved `href`

## 7. Nav

**Intent:** persistent wayfinding — logo, links, mobile menu button, scroll-state ready. One instance per site, lives outside per-page section builds, owned by the main thread.

```html
<nav class="nav_wrapper" data-nav>
  <div class="padding-global">
    <div class="container-large">
      <div class="nav_inner">
        <a href="/" class="nav_logo-link">
          <!-- asset: nav-logo -->
          <img class="nav_logo" src="" alt="Placeholder company name" />
        </a>
        <div class="nav_menu">
          <a href="#" class="nav_menu-link">Placeholder link</a>
          <a href="#" class="nav_menu-link">Placeholder link</a>
          <a href="#" class="nav_cta button">Placeholder CTA</a>
        </div>
        <button class="nav_menu-button" aria-label="Open menu" aria-expanded="false">
          <span class="nav_menu-button-icon"></span>
        </button>
      </div>
    </div>
  </div>
</nav>
```

Scroll-state classes are toggled by the scroll-state nav recipe's script, never authored as Webflow styles directly: base `.nav_wrapper`, custom-code toggle target `ct-scrolled` (per the `ct-` prefix rule — origin must read as script-driven, not a designer style).

**Variants:** transparent-over-hero (nav starts transparent, `ct-scrolled` swaps to solid background) vs always-solid (interior pages, no scroll-state script needed).

**Motion hooks:** ★ scroll-state nav · mega-nav reveal (multi-column dropdown variant only).

**Assertable contract:**
- `.nav_menu-button` has `aria-label` and `aria-expanded` that flips on open/close
- exactly one `.nav_logo-link` pointing at `/`
- `ct-scrolled` toggle only ever applied via script (grep published output — never appears in a Designer-authored style block)
- mobile menu is fully keyboard-operable (focus trap in, `Escape` closes)

## Motion hooks (the recipe contract)
Every skeleton emits the `data-*` hooks the motion recipes bind to — never rely on class names for motion wiring. Nav → `data-nav`; reveal cards → `data-reveal-card` with the list child `data-reveal`; marquee track → `data-marquee-src`; hero title → `data-hero-title`, hero subtitle → `data-hero-sub`; scroll scenes → `data-scene`. (recipes.md "Selector-hook contract".)

## Growing the library
Hand-curated for now. When a section pattern proves out on a real build (passes section-verify + end-gate in ≤2 rounds), hand-add its grammar-clean skeleton here under its type. Revisit auto-induction/retrieval-indexing only once several projects of history exist — one project isn't a corpus.
