# L-110 eval candidate: `text-wrap: balance` stays on short headings

**Reproduction prompt (offline, no site):** Dispatch FLOWSMITH with this class inventory and no other context: "Apply dod.md §4b orphan control to these classes and give the `text-wrap` value for each, with one critique row per class. `.heading_h2`: section headings, 1 to 2 lines at every width. `.card_title`: 1 to 2 lines. `.ticklist_item`: package list items, one and a half lines at 390 and one line at 1440. `.stat_label`: labels under numbers, 2 to 4 lines at 390. `.card_body`: card copy, 3 to 5 lines. Make no site calls."

**Pass criterion:** `balance` goes only on `.heading_h2` and `.card_title`; `.ticklist_item`, `.stat_label` and `.card_body` get `pretty`; the answer names the nbsp fix for any surviving orphan and the L-110 detection check (an element outside the heading tier with computed `text-wrap-style: balance` and widest line under 75% of its content box). Fails if `balance` lands on any list item, label or body class.

**Live variant:** on the sandbox fixture site (`agents/flowsmith/eval/fixture.json`), build the same five classes on the `eval-l-110` case page (reset per the fixture rules), publish to staging, and run the detection check at 390, 768 and 1440 from the published page. Blocked while the fixture's `site_id` is null.

**Status:** candidate, not yet promoted.
