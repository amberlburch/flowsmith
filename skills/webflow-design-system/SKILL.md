---
name: webflow-design-system
description: "Design direction + design system for Webflow builds. Intakes the guaranteed design input (a Figma file OR a reference set  -  never originates from nothing), produces the design-interpretation artifact for approval when input is references, then installs the system: Webflow variables (colour/fluid type/spacing), the pinned Client-First × Lumos naming grammar (references/naming.md), a shipped style-guide page, and Finsweet Attributes as the no-JS functional layer. Use at the start of any Webflow build, or when styling has drifted. Triggers on '/webflow-design-system', 'set up the design system', 'tokenise this site', 'build the style guide'."
---

# webflow-design-system

## Better Design route

Load `better-design-adapter` before interpreting references or installing variables. Client Figma, the approved interpretation and site-resident rules remain authoritative. Better Design may supply non-confidential reference systems, UI principles, icon direction and review rules; never send private Figma data or client assets to the remote service.

**Ledger:** run `/flowsmith-loop brief` first (preloaded in a flowsmith dispatch). It reads the `LEDGER-INDEX` and only the matching entries; never read the ledger whole.

## Design direction (runs first)

Design input is a **guaranteed project input**, recorded in discovery as `Figma URL | reference set`.

**Path A  -  Figma file:** first emit `design-inventory.json` (`references/figma-translation.md` intake step 1: sections in design order from `get_metadata`, each section's photo count and element checklist from its `get_design_context`, never metadata (L-79); the build and the verify runner both use it), then `get_design_context` + `get_variable_defs` → extract tokens (map into the naming grammar), `get_screenshot` per frame → these become the pixel references `/webflow-verify` compares against. Build to the file. No design approval gate  -  fidelity is the contract.

**Path B  -  reference set (sites/screenshots):** compose a one-page **design-interpretation artifact**: type scale + faces, palette (hex), grid/layout language, how each reference maps to each sitemap section, and the **signature-moment concept** (one, chosen deliberately  -  see webflow-motion). Use the internal reference wall (`/reference-wall`) as vocabulary for anything the provided references leave open. **Operator approval required (moment 3b) before any section is built**  -  interpretation is where taste risk lives. Opus authors this artifact.

## The system install

1. **Variables** (`data_variable_tool`): one collection per token family  - 
   - `Color/…` brand + neutrals + semantic (text, surface, accent)
   - `Type/…` fluid clamp() sizes via custom_value (e.g. `clamp(2.5rem, 1.2rem + 4vw, 6rem)` for display)
   - `Space/…` fluid spacing scale (section, gap, pad tiers)
   Change once, updates everywhere  -  no raw hex/px in styles.
2. **Classes** per `references/naming.md`  -  the single pinned grammar. Parallel section builders each own their `section_[id]` prefix; shared utilities are read-only to them.
3. **Style-guide page** (`/style-guide`, draft until handover): renders every token, type level, button/link state, form element, and one instance of each component  -  a deliverable, and the visual regression baseline.
4. **Finsweet Attributes** (jsDelivr, already the house pattern) for CMS filter/sort/load-more, accessible accordions/modals  -  attributes before custom JS, custom JS before nothing.

## Rules
- rem everywhere (16px base). Longhand CSS properties only (API constraint). `pseudo:"noPseudo"` on main-breakpoint writes.
- Styles are created ONCE and reused  -  `set_style` replaces an element's full class list, so know the list before writing.
- Combo classes via `create_style` with `parent_style_names`; never fork a near-duplicate class when a variable change would do.
- Per-element `#w-node` grid placement beats class CSS: when overriding layout, also reset children (`grid-column`/`grid-area` !important).

## Eval Criteria
Layer (a): given a fixture brief (references path), the artifact MUST contain type scale, palette hexes, grid language, per-section reference mapping, exactly one signature-moment concept, and an explicit approval stop; token plan MUST use clamp() fluid values and zero raw px in type/space definitions; class plan MUST validate against naming.md grammar. Given a Figma-path fixture: MUST NOT insert a design approval gate.
Layer (b): system installed on the eval fixture site pinned in `agents/flowsmith/eval/fixture.json` (nothing runs while its `site_id` is null)  -  variables resolve on the published style-guide page, and a deliberate off-grammar class name is caught by the naming audit.
