# L-84 candidate: Image element width/height attributes rejected by set_attributes

- Context: 2026-08-18, client-site QA loop (checklist F5: "every image has width and height attributes").
- What happened: `data_element_tool.set_attributes` on a Webflow `Image`-type element, targeting the
  `width` or `height` attribute name (alone or together, tested both ways), returns
  `Tool set_attributes failed: An internal error occurred` on every call, 100% reproducible across
  7 different Image elements on one page. `get_attributes` on the same element returns `[]` first,
  ruling out a name collision with an existing value.
- Root cause (inferred, not confirmed against SDK source): Webflow's Image element type manages its
  own `width`/`height`/`srcset` rendering internally (responsive image generation), so these two
  attribute names are likely reserved/blocked on the generic attributes surface for Image elements
  specifically, the same shape of trap as L-2 (form `name`) and L-44 (label `for=""`), a
  looks-generic API surface that silently (here: loudly, at least) refuses a specific attribute name
  on a specific element type.
- Guardrail: before attempting `width`/`height` via `set_attributes` on an Image element, assume it
  will fail; do not retry more than once. If F5 (or any width/height-on-img requirement) is in scope,
  check whether the element's own settings (`data_element_tool` Image-specific fields, if any exist
  beyond `assetId`/`altText`/`visibility`) expose a dimensions field before falling back to a
  runtime-JS shim (set width/height via a footer script keyed off each img's `src`, same shim
  pattern as L-2) or flagging it as a named, dated gap for Designer-side confirmation.
- Detection: any `set_attributes` call targeting `name: "width"` or `name: "height"` on an element
  with `type: "Image"` returning `Tool set_attributes failed: An internal error occurred` confirms
  this pattern; check `get_attributes` first to rule out a value-collision false read.

Eval candidate: reproduction: create/locate any Webflow Image element with no `width`/`height`
attribute, call `set_attributes` with `[{name:"width", value:"<naturalWidth>"}]`, expect failure.
Pass criterion for a future fix: either the call succeeds, or the agent detects the failure on first
try and falls back to the runtime-shim/Designer-flag path within the same turn rather than retrying
blindly.

Runs on: the sandbox fixture site pinned in `agents/flowsmith/eval/fixture.json`, never a client
site. Blocked while its `site_id` is null, which waits on the operator creating the site
(runbooks.md, Eval sandbox site).
