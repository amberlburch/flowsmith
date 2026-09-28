# Eval candidate: L-80: data_variable_tool custom_value non-functional

## Reproduction prompt
Given a design token requiring an alpha-channel colour (e.g. `rgba(20,20,20,0.72)`), a fluid
clamp() type size (e.g. `clamp(2rem, 4vw, 3.5rem)`), or a font-family fallback stack, attempt to
create the corresponding Webflow variable (`create_color_variable` / `create_size_variable` /
`create_font_family_variable`) using the `custom_value` field.

## Pass criterion
The agent does not retry the same `custom_value` payload more than once on identical failure.
After the first "internal error occurred" response, it switches to `static_value` with the
correct workaround for the token type (8-digit hex for alpha colour, bare family name for font,
literal property value on the style class rather than a variable for clamp()/fluid size), and
verifies the resulting variable or style resolves correctly via `query_styles` or the published
CSS before continuing.

## Runs on
The sandbox fixture site pinned in `agents/flowsmith/eval/fixture.json`, never a client
site. Blocked while its `site_id` is null, which waits on the operator creating the site
(runbooks.md, Eval sandbox site).
