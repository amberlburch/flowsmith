# Figma → Webflow translation

The method behind "fidelity is the contract" (Path A). Read the frame, map it mechanically, verify against its screenshot.

## Intake sequence
1. **Emit the DESIGN INVENTORY as `<pack>/design-inventory.json`** (project pack; its path goes in
   the manifest's `design_inventory` field). It is the denominator for webflow-verify §2c, and the
   runner reads it directly (`webcheck.mjs --inventory`), so write exactly this shape (full
   format: `skills/webflow-verify/scripts/README.md`):
   ```json
   {
     "base": "https://<site>.webflow.io",
     "figma": "<file key>",
     "viewports": { "desktop": 1440, "mobile": 390 },
     "pages": {
       "/": {
         "desktop": [
           { "section": "hero", "node": "12:34", "name": "Hero", "photos": 1, "elements": [".hero_badge", ".hero_cta"] }
         ],
         "mobile": [ { "section": "hero", "node": "40:2", "name": "Hero", "photos": 1 } ]
       }
     },
     "waivers": []
   }
   ```
   Rules:
   - `viewports` are the design frames' own widths. Rows are in design (y) order: one row per
     top-level section of each page frame, enumerated with `get_metadata` (never as a content source,
     L-79). Never read sections off a screenshot: an inventory built from what you noticed misses
     what you did not.
   - `section` is the `section_[id]` slug the build must use (naming.md), assigned here, so the
     runner's default selector `.section_<section>` finds it. Only set `selector` for a section that
     cannot carry that class.
   - `photos` and `elements` come from that section's `get_design_context`, never from metadata,
     which truncates cards and panels into childless frames (L-79). Photos count image FILLS, not
     layer names. `elements` lists the grammar classes planned for the element checklist (chips,
     markers, hairlines, numerals, badges, embed slots: L-59); a builder may rename a selector but
     never drops one without a waiver.
   - Desktop and mobile frames are PAIRED. A page with no mobile frame gets no `mobile` key, and
     the runner warns that the twin was not checked; content differences between the pair are
     rows, not assumptions.
   - Developer-instruction frames (embed specs, code blocks) are not rows. Their functional intent
     (an embed slot) goes in the owning section's `elements`.
   - A section deliberately dropped is a `waivers` entry with `page`, `viewport`, `section`,
     `reason`, `approver` and `date`, never a deleted row.
   Validate it before the IA approval: `node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs
   <base>/ --inventory <pack>/design-inventory.json --html-only --job <job_id>-inv`. Exit 2 with an
   `inventory` message means the file is malformed; exit 0 or 1 only reports the served pages, which
   may not exist yet.
2. `get_variable_defs`: Figma variables → Webflow variable collections (table below).
3. `get_design_context` per section: layout tree, styles, text, assets. **HARD RULE: every section
   build starts from its section node's `get_design_context`, never from a screenshot alone.** A
   screenshot-referenced build produces a plausible hand-design carrying the right copy (L-59).
   The context payload is the ground truth for panel tints, hairlines, ghost
   numerals, markers, opacities, blend modes and offsets that a screenshot read misses; a section
   with no context read on record is a PROC defect. When capturing frame screenshots, set
   `maxDimension` to the frame's HEIGHT: the parameter caps the longer edge, and page frames are
   taller than wide, so the default crushes a 1440px design below native width, too coarse to show
   the very elements being verified.
4. `get_screenshot` per frame at 1x, saved as the pixel reference `/webflow-verify` compares
   against. Capture BOTH the desktop and mobile frame per page; each breakpoint verifies against
   its own frame, never the desktop frame at both widths.

## Mapping tables

**Auto-layout → CSS**
| Figma | Webflow style |
|---|---|
| Auto-layout vertical/horizontal | `display:flex; flex-direction:column/row` |
| Gap | `grid-column-gap`/`grid-row-gap` (works on flex) |
| Padding | padding longhands (API is longhand-only) |
| Hug contents | no explicit size |
| Fill container | `flex:1` or `width:100%` |
| Fixed size | width/height in rem (px ÷ 16) |
| Wrap | `flex-wrap:wrap` |
| Grid layouts | CSS grid; remember `#w-node` child placement beats class CSS |

**Variables**
| Figma | Webflow |
|---|---|
| Color variables | `Color/...` variable collection (semantic names survive, raw names get mapped into the grammar) |
| Number (spacing) | `Space/...`: convert to rem; if the file has no fluid scale, wrap the desktop value in clamp() per the design-system defaults |
| Typography styles | `Type/...` + a text class per style, fluid clamp() between the file's desktop and mobile sizes |
| Modes (light/dark) | variable modes via `set_style_variable_mode` |

**Structure**
| Figma | Webflow |
|---|---|
| Component + instances | `data_component_tool` component + `data_component_builder` instances; Figma component props → Webflow props |
| Text layers | whtml text (baked in: copy phase output, not lorem from the file) |
| Image fills/exports | export → host → `asset_tool.upload_image_by_url` (batches 2-4) → `set_image_asset` |
| Vectors/icons | inline SVG in HtmlEmbed (crisp, colourable via currentColor) |
| Effects (blur/shadow) | backdrop-filter / box-shadow, checked against the perf budget |
| Prototype interactions | NOT translatable → map intent to a webflow-motion recipe |

## Fidelity verification (the pixel-diff procedure)
Per section, after publish: headless-Chrome screenshot at the frame's width → compare against the Figma screenshot, asserting structurally (element geometry within 8px of the frame's boxes via getBoundingClientRect vs the design-context coordinates; font family/size/weight computed styles match the mapped tokens; colours match variable values). Pixel-perfect diffing across renderers is noise: geometry + token equality is the FLOOR, not the whole contract. Fidelity is gated by `webflow-verify` §2b: geometry+token equality PLUS the perceptual layer (per-region ΔE < 3, VLM judge vs the Figma screenshot ≥ 85). Deviations either get fixed or listed (never silently shipped).

## Traps
- Figma px → rem always (÷16); never copy px literals into styles.
- Figma line-height % → unitless; letter-spacing px → em.
- Absolute-positioned Figma layers usually mean the DESIGN wants layering: reach for grid/relative+absolute inside the section, not global absolutes.
- Text in the file is placeholder: the copy phase's approved copy wins, and length differences must be layout-tested (the design must survive real copy).
