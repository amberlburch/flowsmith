# CMS population patterns

Schema design lives in `cms-best-practices`; this is about getting CONTENT in safely at scale.

## Item publish semantics (distinct from site publish)
CMS items stage and publish SEPARATELY: `update_collection_items` writes drafts; `publish_collection_items` makes items live; a site publish does not implicitly publish staged item edits in all cases, and item publishes don't need a site publish. Treat item state as its own verify surface: after publishing items, curl a live item URL and confirm the change. (Confirm-per-site at fixture stage; encode observed behaviour in learned-rules once verified live.)

## Bulk creation under rate limits
- `create_collection_items` accepts arrays — batch 20-50 items per call rather than item-per-call (60 req/min shared with everything else).
- Slugs are permanent-ish: changing one breaks inbound links — set them right at creation (kebab, keyword-bearing).
- Always write `name` + `slug` + every required field; missing required fields fail the whole batch.

## Rich-text surgery (the proven href-rewrite pattern ★)
For editing rich-text HTML fields (post bodies) without collateral damage:
1. Fetch the item; operate on the `post-body` (or equivalent) HTML string only.
2. String-surgery hrefs ONLY — never regenerate the HTML: map old→new URLs; unwrap dead links by replacing the whole `<a …>text</a>` with its inner text.
3. **Byte-identical text check**: strip tags before and after; the visible text must be identical unless text change was the task.
4. Archive originals (`{itemId}.orig.html`) before writing; update item; `publish_collection_items`; re-fetch and grep to confirm (0 occurrences of the old domain, external links untouched).

## Template-page bindings
- Collection template pages resolve `{{wf}}` bindings at publish — every bound field must be populated on every item or the template renders holes; the DoD asserts "template pages resolve every bound field".
- Template-page SEO: meta-title/meta-description as CMS fields, populated per item (unresolved `{{wf}}` tokens in published meta = defect).
- Templated JSON-LD cannot be written via the API (trap 1) — runtime-injected schema on template pages.

## Editor safety
Populating is not owning: after handover the CLIENT edits these items. Field help-text on non-obvious fields, option fields over free text where values are finite, and no fields that only make sense to the agent.

## Partial-success ledger + item-granular resume (rate-limit resilient)
Bulk CMS writes hit the ~60/min cap and fail mid-batch — do NOT treat a collection as all-or-nothing.
- Chunk at ≤50 items per `create_collection_items`/`update_collection_items` call.
- After each chunk record three DISTINCT sets in the manifest: `succeeded` (item ids), `failed` (id + error), `skipped` (id + reason). Not just a count.
  - Persist via `flowsmith_manifest.py add --kind cms_ledger --items '[{"collection":"...","chunk":N,"succeeded":[...],"failed":[...],"skipped":[...]}]'` so a cold resume sees exactly where the batch stopped.
- On a mid-batch 429/error: back off 60s, then resume from the first item NOT in `succeeded` — never re-create succeeded items (duplicate slugs) or restart the collection.
- Publish (`publish_collection_items`) only the succeeded set; re-drive `failed` in the next round; surface `skipped` for a human call.
- Verify surface: after publish, curl one live item per chunk to confirm — item publish is its own surface (staged vs live), distinct from site publish.
