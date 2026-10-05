# FLOWSMITH repo

This repo is the distributable package for the FLOWSMITH Webflow agent. The files under `agents/`, `skills/`, `hooks/`, `lib/` and `reference/` mirror the paths they install to under `~/.claude`. Do not restructure them: the prompts and hooks reference each other by those paths.

- Package files change only through the operator's private sync: `python3 ~/.claude/scripts/flowsmith_public_sync.py --dry-run`, then `--apply`, which sanitises them into this working tree and never commits. Never hand-copy them. `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `install.sh` and `agents/shared/budget-caps.json` are edited here.
- `install.sh` is the only entry point. Keep it dependency-free (bash, python3, cp). It only adds hook entries to `settings.json`, backs the file up first and never replaces an entry.
- Never mention a client: no names, site IDs, staging URLs or domains. The package uses `Project <letter>` (the sync gives each client a letter that never moves), `<site-id>`, `<site>.webflow.io` and `<client-domain>`. The local pre-push hook blocks a push that carries any of them. Corient itself is the operator's own company (co-founded) and may be named, as may corient.com.au.
- `learned-rules.md` is mutable at install sites. Ledger entries added here must pass `skills/flowsmith-loop/scripts/ledger_lint.py --all`.
- Australian English. No emojis, em dashes or en dashes.
