# FLOWSMITH operator runbooks: versioned once, pasted per project

Exact click paths for the API-less human steps. Paste the relevant block (with project values filled) when the moment fires; each should take under 2 minutes. Webflow UI changes → update here, not per project.

## Moment 1: create the site
Webflow dashboard → your workspace → **New site** → Blank site → name it `[project]` → Create. Then open **Site settings → General** and send me the **Site ID** (or just the site name; I can list it).

## Eval sandbox site (once, for flowsmith evals)
Same path as Moment 1, named `flowsmith-sandbox`, in a **paid Workspace plan** the Webflow MCP can reach: a free Starter site there gets custom code and up to 300 static pages at no extra cost. A free Starter site in a free workspace does not work: it allows 2 static pages and no custom code, and the evals need one page per case plus custom code for L-81, L-83 and L-88. If no paid workspace is available, the site needs a paid CMS site plan (Basic has no CMS, and L-85 needs a collection), which is a spend. Attach no custom domain, then send me the Site ID. I pin it in `agents/flowsmith/eval/fixture.json`, and evals then write only to that site.

## Moment 2: Phase 0 settings pass
Site settings →
1. **GSAP** (under Site settings → GSAP / Custom code area): toggle **GSAP core ON** + enable plugins (ScrollTrigger, SplitText, Flip).
2. **SEO tab → Indexing**: **Disable Webflow subdomain indexing = ON** (staging must not index).
3. **General → Icons**: upload favicon (32px) + webclip (256px), files staged at `[path]`.
4. Publishing tab: confirm the `[project].webflow.io` staging domain is enabled.

## Moment 5a: form field rename (the name-attribute trap)
Designer → select the input → Settings panel (D) → **Text Field settings → Name**: change to `[FieldName]` → Publish. (API renames don't reach the published `name=` attribute; my runtime shim keeps submissions correct until this is done, and I'll remove the shim after.)

## Moment 5b: templated page schema
Pages panel → gear on `[template page]` → Custom code / SEO → paste the schema block I stage (the API can't write `{{wf}}`-templated schema).

## Moment 5c: CMS-template SEO title/description binding
Pages panel → gear on the CMS collection template page (e.g. Resources article Template) → **SEO Settings → Title / Description**: click into the field, use the CMS-field-token picker to insert `{{Name}}` (or the equivalent field) into the title, e.g. `{{Name}} | [Brand]` → Publish. (The Data API's `seo.title`/`seo.description` write literal text only; a per-item token binding on a collection template is Designer-only. Until this is done every item under this template shares one static title/description, flagged as a named waiver, not a silent gap.)

## Moment 6b: site-settings SEO pass (pre-launch)
Site settings →
1. **Publishing → 301 redirects**: paste each pair from the staged redirect map: `[old path] → [new path]`.
2. **SEO → robots.txt**: paste the staged block exactly (I verify it post-publish: a stray `Disallow: /` is the catastrophic case, which is why I re-check).
3. **SEO → Global canonical tag**: set to `https://[domain]/`.
4. Search Console: I inject the verification meta tag; you just click **Verify** at `search.google.com/search-console` after launch.

## Moment 5d: Resources/article "Read more" link binding (the collection-item-link trap, L-41)

The Data API cannot bind a Collection List link to "current CMS item" -- only the Designer attaches
that context. A client-side shim rewrites the href from the correctly server-bound slug (already in
each anchor's `id` attribute) on every page load, which is correct and robust, but a crawler or a
visitor with JavaScript blocked still sees the raw served href. Two-minute fix, once, fixes it at the
true source for both the Resources grid and every article's "More from resources" block (same
component):

1. Open the Designer, go to `/resources` (or any page using the Resources Collection List).
2. Select the "Read more" link element inside the Collection List item.
3. Settings panel → Link → change from whatever it currently resolves to → **Current [Article] Page** (the
   Designer's own current-item binding option, listed under the Collection's item type).
4. Repeat on the Resources article template's "More from resources" related-items block (same link
   element type, same fix).
5. Publish. Verify with `curl` on a few slugs: the href in the raw served HTML should now read
   `/resources-articles/<slug>` directly, no JavaScript required.
6. Once confirmed, the client-side shim can be safely removed from the site-wide freeform footer code
   (the script tagged "P1 fix, 2026-08-19: consolidated site-wide readmore/related-article href
   repair") -- leaving it in place afterward is harmless (it will no-op on already-correct hrefs) but
   redundant.

## Moment 5e: Contact form method (GET to POST, the fault-path PII risk)

The Contact form element's Data API record and its served HTML both read `method="get"`. `set_attributes`
rejects a direct write to `method` on a FormForm element (same "internally managed" pattern as the
`method`/`action` fields elsewhere), and there is no form-settings write action in the Data API surface
(`data_forms_tool` only reads schema and manages submissions). Webflow's own AJAX handler normally
intercepts the submit and posts to its own endpoint, so this is a fault-path risk, not an active leak:
if that script fails to load or errors, the browser falls back to a native GET, and the borrower's name,
email, phone, company and free-text situation land in the URL, browser history, and the referrer header
on the next navigation. Two-minute fix:

1. Open the Designer, go to `/contact`.
2. Select the Contact form element.
3. Settings panel → Form settings → change **Method** from GET to POST.
4. Publish. Verify with `document.querySelector('form').method` returning `"post"` on the published page,
   or a curl of the served HTML showing `method="post"` on the `<form>` tag.

## Moment 5f: article date format (US to Australian, at source)

Checked before staging, not assumed: the `published-date` field on the Resources Articles collection
is a plain `DateTime` field (`validations.format: "date-time"`) with no locale or display-format
setting anywhere in its schema, and the site's own settings carry no date-format field either
(`locales.primary.tag` is generic `"en"`, not `"en-AU"`, the same gap D25/P2 already named for
`<html lang>`). Webflow renders a DateTime field's date format from a per-element binding option set
in the Designer (the "Date Format" dropdown on the specific text element bound to that field), which
has no Data API surface at all, which is why the served HTML shows `August 17, 2026` while a runtime
shim rewrites it to `17 August 2026` after load. Two-minute fix, needed twice (once per template):

1. Open the Designer, go to `/resources`.
2. Select the date-chip text element bound to `published-date` inside the Collection List item.
3. In the field-binding panel, change **Date Format** from `MMMM D, YYYY` (or whatever it currently
   reads) to `D MMMM YYYY`.
4. Repeat on the Resources article template's own date-chip element (a separate binding instance).
5. Publish. Verify with `curl` on `/resources` and one article slug: dates should read e.g.
   `17 August 2026` directly in the served HTML, no JavaScript required.
6. Once confirmed, the `G7` reformat shim in the site-wide freeform script becomes redundant and can
   be safely left in place (it will no-op on an already-correct string) or removed.

## Moment 5g: Finsweet Attributes install (CMS filter / search / load-more / sort / lightbox)

One script tag, site-wide, in **Site settings → Custom code → Footer code** (footer, not head: the DOM
must exist before Attributes initialises). Pin the exact version; check the current one with
`curl -s https://registry.npmjs.org/@finsweet/attributes/latest` (2.7.1 as at 2026-09-09). Declare
every solution the site uses as an attribute on the tag; do not use `fs-attributes-auto`, which
scans the whole DOM and can load solutions from hidden elements.

```html
<script type="module"
  src="https://cdn.jsdelivr.net/npm/@finsweet/attributes@2.7.1/attributes.js"
  fs-list></script>
```

Add `fs-modal`, `fs-accordion`, `fs-copyclip` etc. to the same tag as they are used; never a second
tag. Elements then carry the solution's `fs-list-*` data attributes. Copy the exact attribute names
and values from the solution's page at finsweet.com/attributes for the version pinned, never from
memory: names changed between v1 and v2 and a wrong value fails silently.

Verify on the published page in a real browser, not curl: the behaviour works across the canonical sweep (webcheck default widths, 320 to 1920),
`window.FinsweetAttributes.modules` lists the declared solutions, the console is clean, and any
earlier custom-JS version of the same behaviour has been removed from every custom-code surface
(site head/footer, page head/footer, embeds). Record the pinned version in the custom-code inventory
at handover (dod.md §10).

## Moment 7: production publish (Tier 3 approval)
Nothing manual beyond your approval. After your yes to the exact publish, the main session records it in `~/.claude/state/approvals/webflow-production-<site_id>.json` (site, the exact domain ids from `get_site` that the publish sends as `customDomains` and never hostnames, time and your words; valid 30 minutes): the gate hook denies a live publish without it, and I cannot write it myself. Then I publish and run the launch-day production SEO re-run as the exit condition. If custom domains aren't connected yet: Site settings → Publishing → Custom domains → add `[domain]` + `www.[domain]`, set DNS per the panel, wait for the tick.

## Backup restore (break-glass, human-only)
Site settings → **Backups** → pick the timestamped snapshot → Preview → Restore. The API cannot do this; if I request it I'll name the exact timestamp to restore to and what will be lost.

## Designer bridge (optional, enables snapshots/uploads)
Open the Designer via the `?app=` bridge link I provide and KEEP THE TAB FOREGROUNDED: the bridge drops silently when backgrounded.

## Chrome for chrome-devtools (L-107)

The MCP connects to `127.0.0.1:9222` and never launches Chrome, which is why five client-site dispatches in a
row lost their verification pass. Before the first chrome-devtools call:

```bash
bash ~/.claude/lib/debug_chrome.sh            # headless; prints "ready: Chrome/<version> (headless)"
bash ~/.claude/lib/debug_chrome.sh --headed   # real window and GPU, for WebGL frame-counter checks
bash ~/.claude/lib/debug_chrome.sh --restart  # replace a wedged or wrong-mode instance; closes every session's pages
```

It runs its own profile at `~/.cache/claude-debug-chrome`, never the operator's browser, and reuses an instance
that is already listening. Concurrent sessions share that one Chrome: isolate with
`new_page(isolatedContext: "<job_id>")` and pass `pageId` on every call (L-36). Every `filePath` goes
under `~/.claude/_scratch/YYYY-MM-<job_id>/`; the MCP denies the session scratchpad and `/tmp`.
