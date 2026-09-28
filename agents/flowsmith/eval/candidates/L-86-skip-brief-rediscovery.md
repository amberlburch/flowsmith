# L-86 eval candidate — skipping `/flowsmith-loop brief` causes re-discovery of ledgered defects

**Reproduction prompt:** Dispatch a FLOWSMITH task naming 3+ named fix items on an existing Webflow
site with a populated `learned-rules.md` ledger containing at least one `[MOTION]`-tagged and one
`[LIVE]`-tagged entry relevant to the task (e.g. a task touching a Lenis-scroll page and a
Turnstile-gated form). Do not mention `/flowsmith-loop brief` in the dispatch.

**Pass criterion:** The agent's first tool-call sequence includes reading the ledger index
(`learned-rules.md` LEDGER-INDEX block) and emits a BUILD PLAN block with a non-empty
`LEDGER LESSONS IN PLAY` field naming the relevant entries, before any Webflow MCP write or
browser-verification call. Fails if the agent proceeds directly to Webflow/browser tool calls
without first restating the matching ledger lessons.

**Status:** candidate, not yet promoted to `golden/baseline.json`.
