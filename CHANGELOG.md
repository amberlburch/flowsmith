# Changelog

## 2026-09-28

- Package brought up to date: ledger entries to L-110, and the current definition of done, runbooks and five skills.
- Gate hook: `hooks/agent-gates.sh` running `lib/agent_gates.py`. A production publish needs an approval grant; a staging publish needs the publish lock, both staging parameters and a webcheck report since the last publish; a dispatch needs its brief before the first Webflow write, and one that wrote is blocked once at stop until its handoff passes the linter; removals need a snapshot; each dispatch is capped at 200 tool calls.
- Check runner: `skills/webflow-verify/scripts/webcheck.mjs` with its fixtures. Needs Node.js 22.
- New scripts: `lib/agent_telemetry.py` (what each dispatch did, read from its transcript), `lib/agent_kpis.py`, `lib/agent_scorecard.py` and `lib/debug_chrome.sh`, which replaces the manual Chrome launch in the README.
- `install.sh` installs `hooks/`, points the agent's frontmatter hooks at the installed path, adds four hook entries to `settings.json` (backed up first, add-only, `--no-settings` to wire by hand) and smoke-tests the gate hook and the runner.

## 2026-09-14

- First public package. Agent, five skills, runtime scripts and the ledger as at 2026-09-09 (entries L-0 to L-105), with client identifiers replaced by placeholders.
- `install.sh` with dry-run, backups and post-install smoke checks.
