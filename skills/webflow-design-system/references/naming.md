# The pinned naming grammar — Client-First structure × Lumos tokens

One grammar. Every FLOWSMITH build, every parallel subagent, this file wins conflicts.

## Page skeleton (fixed, every page)
```
page-wrapper
└─ main-wrapper                (tag: main)
   └─ section_[id]             (tag: section — [id] = kebab slug: section_hero, section_services)
      └─ padding-global        (horizontal gutters only)
         └─ container-[size]   (large | medium | small — max-width + centre)
            └─ padding-section-[size]  (vertical rhythm: small | medium | large)
```

## Class types
- **Custom classes** — `[component]_[element]`: underscore splits component folder from element. `services_card`, `services_card-title`, `nav_menu-link`, `footer_social-icon`. Hyphenate multiword segments. A custom class never leaves its component.
- **Utility classes** — `[property]-[value]`, combo-safe, global: `text-color-primary`, `background-dark`, `hide-mobile`, `text-align-center`. Utilities never carry layout that belongs to a component.
- **Section ownership**: a section subagent may create/edit only `section_[its-id]` and `[its-component]_*` classes + read-only use of utilities and tokens. Shared/base classes change only in the main thread. This is the collision guard.

## Variables (Lumos-style tokens — the only source of visual values)
```
Color/Brand/…       brand hues
Color/Neutral/…     50-900 ramp
Color/Semantic/…    text-primary, text-muted, surface, surface-raised, accent, border
Type/Display|H1|H2|H3|Body|Small|Micro   fluid: clamp(min, base + vw, max)
Space/Section|Block|Gap|Pad × S|M|L      fluid clamp() spacing
Radius/…  Shadow/…  (sparingly — Swiss restraint)
```
No raw hex, px, or font-size literals inside classes. rem everywhere; 16px root. Fluid clamp() means breakpoints carry layout changes only, not size babysitting.

## Naming bans
- No abbreviations a client couldn't read (`svc-` ✗, `services_` ✓)
- No `Div Block 47`, no `Heading 3` defaults left behind
- No style forked from another with a numeric suffix (`Card 2` ✗ — use a combo or a variable)
- Custom-code classes (injected via scripts, not Webflow styles) take the `ct-` prefix so their origin is legible: `ct-marquee`, `ct-hero-scrim`

## Audit assertion (used by evals + verify)
**Single pinned source: `~/.claude/lib/webflow_naming_audit.py` (GRAMMAR).** The regex below is illustrative and must stay in sync with the lib — the lib wins any discrepancy. Global components `button`, `nav`, `footer` are legal bare classes. The lib also EXEMPTS any class sharing an element with a `w-*` class (Webflow native components — navbar/dropdown/slider/tabs/lightbox — pair their default class with a `w-*` internal), so native components never false-flag.

Every class on the published page matches: `^(page-wrapper|main-wrapper|section_[a-z0-9-]+|padding-(global|section-(small|medium|large))|container-(large|medium|small)|button|nav|footer|[a-z0-9]+(-[a-z0-9]+)*_[a-z0-9]+(-[a-z0-9]+)*|(text|background|display|hide|align|margin|padding|is)-[a-z0-9-]+|ct-[a-z0-9-]+|w-[a-z0-9-]+|w--[a-z0-9-]+)$` (Webflow's own `w-*` classes exempt).
