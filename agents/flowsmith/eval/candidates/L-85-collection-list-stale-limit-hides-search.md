# L-85 candidate: Client-side filter over a Collection List with a stale `limit` silently searches a subset

- Context: 2026-08-18, a client site's Resources page, uplift U9 (real search filter) plus content growth
  (5 new articles landed, 3 retired, net +2) inside the same session.
- What happened: the Resources Collection List's `limit` was set to 8 (from the original design,
  which showed exactly 8 cards) and never revisited when the collection grew to 10 published items.
  The grid silently rendered only 8, "Page 1 of 1" showed with no next-page control, and 2 published
  articles were unreachable from any index. The client-side search filter (built the same session for
  U9) only ever queries `.w-dyn-item` elements present in the DOM, so it inherited the same blind
  spot: searching a term unique to one of the 2 missing articles returned zero results even though
  the filter's match logic (case-insensitive substring, escape-to-clear) was entirely correct.
- Root cause: three separately-correct pieces of work (the original 8-item build, the U9 filter, the
  same-session article swap) each assumed the layer below it was complete, and none re-checked the
  Collection List's item cap against the live CMS count after the count changed. The symptom
  (search returns nothing for a real term) pointed at the filter, when the actual defect was the
  `limit` two layers upstream.
- Guardrail: any time a CMS collection's published-item count changes, re-check every Collection
  List rendering it for `limit` vs `list_collection_items` total on that collection_id, not just the
  page that was directly edited. Building a client-side filter over a Collection List is a commitment
  to keep `limit` >= collection size for as long as the filter exists, or to have the filter query
  the CMS API directly once real pagination exists; decide and record which, don't leave it
  implicit. `get_settings` (`all_raw_settings`) on the `DynamoWrapper` reports `limit`/`offset`/
  `pagination`; per L-65 these are writable via `static_number`, so this is always a direct fix.
- Detection: count rendered card-title instances on the published page against `list_collection_items`
  for the same collection_id. A mismatch with `pagination: null` and no visible next-page control
  means items are silently capped. Confirm any fix by searching a term unique to a previously-missing
  item and checking a result renders, not just by re-running the raw item count.

Eval candidate: reproduction: build (or locate) a Collection List with `limit` less than the live
collection's published-item count, and any client-side filter querying the rendered `.w-dyn-item`
set. Search for a term unique to an item beyond the limit; expect zero results despite correct filter
logic. Pass criterion for a future check: the agent diagnoses the `limit` mismatch (not the filter)
as root cause, fixes `limit` directly via `set_settings`, and verifies via item-count-vs-CMS-total
plus a term-unique-to-a-previously-missing-item search, not by re-testing only the already-visible
items.

Runs on: the sandbox fixture site pinned in `agents/flowsmith/eval/fixture.json`, never a client
site. Blocked while its `site_id` is null, which waits on the operator creating the site
(runbooks.md, Eval sandbox site).
