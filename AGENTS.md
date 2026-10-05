# AGENTS.md: FLOWSMITH

Read `CLAUDE.md` first; it is the detailed guide. This is a PUBLIC repository.

- Package files under `agents/`, `skills/`, `hooks/`, `lib/` and `reference/` mirror their install paths under `~/.claude`. Do not restructure or hand-edit them; they change only through the operator's private sanitising sync.
- `install.sh` is the only entry point and must stay dependency-free (bash, python3, cp).
- Never name a client: no client or contact names, site IDs, staging URLs, client domains or emails. Corient, the operator's own company, may be named.
- To try it: `./install.sh` (see `README.md`).

Stack: Claude Code agent and skills (Markdown), Python and shell hook scripts.

## Working rules (all agents)

- GitHub is the source of truth. Work on a branch and open a pull request; never push to the default branch directly.
- One small task per pull request, with a clear description of what changed and how it was checked.
- No refactors or style churn unless the task asks for it. Do not merge; Amber reviews and merges.
- Never commit secrets: `.env*`, keys, tokens, credentials and client data stay out of git (see `.gitignore`).
