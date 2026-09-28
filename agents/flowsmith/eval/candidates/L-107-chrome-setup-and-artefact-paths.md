# L-107 eval candidate: Chrome setup and artefact paths before the first browser call

**Reproduction prompt:** Dispatch FLOWSMITH on a read-only verification task against any public page (for example `https://example.com`) with Chrome not running on port 9222: "Screenshot the page at 1440 and 390 and report the H1 text." Do not mention Chrome setup or file paths in the dispatch.

**Pass criterion:** before the first chrome-devtools call the agent runs `bash ~/.claude/lib/debug_chrome.sh` and gets a `ready` line; every screenshot `filePath` sits under `~/.claude/_scratch/`; the dispatch's telemetry row shows `chrome_connect_errors: 0` and `artefact_path_denied: 0`. Fails on any "Could not connect to Chrome" or "Access denied" result.

**Status:** candidate, not yet promoted.
