# Eval candidate: L-83: set_page_freeform_code replaces the whole block; concurrent writers silently clobber each other

## Reproduction prompt
Given a Webflow page that already carries freeform footer/head code (e.g. an FAQ accordion script
written by an earlier build step), write a second, unrelated runtime shim (e.g. a form-name
rewrite) to the same page and same location (`footer` or `head`) via `data_scripts_tool.
set_page_freeform_code`, without first reading the existing content and merging.

## Pass criterion
Before reporting the second script live, the agent calls `get_page_freeform_code` on that exact
page and location BEFORE writing, detects the pre-existing content, and writes back the union of
both scripts rather than a bare replacement. After publish, the agent greps the PUBLISHED page's
inline `<script>` output for a distinguishing string from BOTH scripts (the pre-existing one and
the newly added one) and confirms both are present. A pass that greps only for the string it just
wrote, or that trusts the tool's "success" response without a published-page re-check, fails this
criterion: that is exactly the failure mode that shipped silently in the source incident (the form
kept submitting under Webflow's default field names with no error surfaced anywhere).

## Runs on
The sandbox fixture site pinned in `agents/flowsmith/eval/fixture.json`, never a client
site. Blocked while its `site_id` is null, which waits on the operator creating the site
(runbooks.md, Eval sandbox site).
