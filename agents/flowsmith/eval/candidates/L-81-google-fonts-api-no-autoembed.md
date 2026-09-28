# Eval candidate: L-81: FontFamily variable does not auto-embed Google Fonts

## Reproduction prompt
Given a build decision naming a Google Font (not a system font) for headings or body text,
create the font as a `data_variable_tool` FontFamily variable and wire it into the typography
classes via `variable_as_value`. Publish the site.

## Pass criterion
Before reporting the font system done, the agent greps the PUBLISHED page's `<head>` for
`fonts.googleapis.com` (or an equivalent `@font-face` block in the published CSS). If absent, it
injects the Google Fonts `<link>` embed via `data_scripts_tool.set_site_freeform_code` (site head),
republishes, and re-checks the published head before closing the check. A pass that only confirms
the CSS custom property resolves to the right family name, without checking the published head for
an actual font request, fails this criterion.

## Runs on
The sandbox fixture site pinned in `agents/flowsmith/eval/fixture.json`, never a client
site. Blocked while its `site_id` is null, which waits on the operator creating the site
(runbooks.md, Eval sandbox site).
