# FLOWSMITH

An autonomous Webflow developer for Claude Code. It runs a full site build, from discovery to launch, against a written definition of done, and verifies every change on the published page rather than trusting the API response.

Built by [Amber Burch](https://amberburch.com) and operated at Corient. This repo is the portable package: the agent, its five skills, the gate hook that enforces its publish and process rules, the scripts they call, and the learned-rules ledger from production builds.

## What is in the box

| Path | What it is |
|---|---|
| `agents/flowsmith/SYSTEM.md` | The agent definition. Claude Code loads it as the `flowsmith` subagent |
| `agents/flowsmith/dod.md` | Definition of done. Every project is judged against every line |
| `agents/flowsmith/runbooks.md` | Click paths for the handful of steps the Webflow API cannot do |
| `agents/flowsmith/learned-rules.md` | The ledger: Webflow API traps and build lessons, indexed by category |
| `agents/flowsmith/eval/` | Eval cases and candidate ledger entries |
| `skills/flowsmith-loop` | Start-of-task brief, pre-handoff critique, feedback absorb, and the ledger linter |
| `skills/webflow-build` | The build orchestrator, phase by phase |
| `skills/webflow-design-system` | Tokens, naming grammar, Figma translation |
| `skills/webflow-motion` | GSAP and Lenis recipes with restraint rules |
| `skills/webflow-verify` | The mechanical gate. `scripts/webcheck.mjs` is its check runner: served HTML, layout across a 320 to 1920 sweep, text, images, accessibility, open states, console and design completeness, with a `report.json` as the evidence |
| `hooks/agent-gates.sh` | The gate hook. Runs `lib/agent_gates.py` from `settings.json` and from the agent's frontmatter |
| `lib/` | Ten scripts: the gates, run records and the publish lock, the project manifest, telemetry, KPIs, the scorecard, the naming audit, the ledger index, a skill output helper and the debug Chrome launcher |
| `reference/design-systems/` | Anti-patterns and the component-corpus note |
| `agents/shared/budget-caps.json` | Per-agent caps. Installed only if you have none |

## Requirements

- macOS or Linux, with a shell
- [Claude Code](https://docs.claude.com/en/docs/claude-code) 2.1.220 or later (tested on 2.1.220)
- Python 3.10 or later
- Node.js 22 or later. The webcheck runner uses Node 22's built-in WebSocket, and the MCP servers run through `npx`
- Google Chrome
- A Webflow account with Designer access to the site being built
- A Figma account for design-input projects

## Install

Clone the repo, preview, then run the installer.

```bash
git clone https://github.com/amberlburch/flowsmith.git
cd flowsmith
./install.sh --dry-run
./install.sh
```

The installer copies files into `~/.claude`, backs up anything it would overwrite to `~/.claude/_backup/flowsmith-<time>/`, and smoke-tests the agent hooks, the gate hook, the webcheck runner, the ledger lint and the publish lock. It also adds four hooks to `~/.claude/settings.json`, beside any hooks you already have:

| Event | Runs | For |
|---|---|---|
| `PreToolUse` on every Webflow MCP tool | `agent-gates.sh pre-webflow` | The publish, brief and snapshot gates |
| `PostToolUse` on `data_sites_tool` | `agent-gates.sh post-webflow` | Records each landed publish for the spacing and re-check rules |
| `PreToolUse` on Bash and file writes | `agent-gates.sh pre-grant` | Stops a subagent writing a production approval grant |
| `SubagentStop` for `flowsmith` | `agent_telemetry.py hook` | Records what each dispatch did, read from its transcript |

The agent's own frontmatter adds the brief, handoff and call-cap gates, and the installer points it at the installed hook. `settings.json` is backed up before it changes, and an entry that is already there is left alone. If the file does not parse, or you pass `--no-settings`, it is not touched and the installer prints the entries to add by hand. On a re-install, pass `--keep-ledger` if you have added your own entries to `learned-rules.md`.

Then start a new Claude Code session (hooks load at session start) and run `/agents`. `flowsmith` should be listed.

## What the hooks enforce

They apply in every session, not only to the agent, and each deny names its fix.

- **Production publish.** A `publish_site` with any `customDomains` is denied until a grant exists at `~/.claude/state/approvals/webflow-production-<site_id>.json` with `site_id`, `domains`, `approved_at` and `approval` (the approver's words). The main session writes it after a human says yes, and it lasts 30 minutes. A subagent can never write it.
- **Staging publish.** Needs `publishToWebflowSubdomain: true` and `customDomains: []` passed explicitly, and a live publish lock (`python3 ~/.claude/lib/agent_runtime.py lock <job_id> webflow_publish:<site_id>`). A second publish needs 60 seconds since the last one and, within two hours of it, a webcheck `report.json` written since.
- **Brief and handoff.** A flowsmith dispatch cannot make its first Webflow write before its `brief.md`. A dispatch that made Webflow writes is blocked once at stop until its `handoff.md` exists and passes the linter. A main session is asked once for a lite brief before its first Webflow write.
- **Snapshots.** `remove_element` and `remove_style` need a snapshot under `~/.claude/state/snapshots/<job_id>/` first.
- **Call cap.** 200 tool calls a dispatch, with a warning at 150. Past the cap only reads and state-saving calls run, for 40 more calls, so the next dispatch can resume. Add a `flowsmith` row to `agents/shared/budget-caps.json` to change it.

## Connect the tools

FLOWSMITH talks to Webflow, Chrome and Figma through MCP servers. Run these from any terminal, then authenticate inside Claude Code with `/mcp`.

**1. Webflow plugin (required).** Inside a Claude Code session:

```
/plugin marketplace add webflow/webflow-skills
/plugin install webflow-skills@webflow-skills
```

Restart the session, run `/mcp`, and complete the Webflow OAuth login. Grant access to the sites you will build on.

**2. Chrome DevTools (required).** Used for published-page verification at every breakpoint.

```bash
claude mcp add chrome-devtools -- npx -y chrome-devtools-mcp@latest --browserUrl=http://127.0.0.1:9222
```

The agent starts its own debug Chrome before its first browser check. To start it yourself:

```bash
bash ~/.claude/lib/debug_chrome.sh            # headless, for layout and console checks
bash ~/.claude/lib/debug_chrome.sh --headed   # a real window and GPU, for WebGL checks
```

The launcher uses macOS Chrome at its default path. On Linux, start Chrome yourself with `--remote-debugging-port=9222` and its own `--user-data-dir`, and the launcher will reuse it.

**3. Figma (required for Figma-input projects).**

```bash
claude mcp add --transport http figma-remote https://mcp.figma.com/mcp
```

Run `/mcp` in Claude Code to sign in.

**4. Optional.** These improve the critique pass but the agent never blocks on them.

```bash
claude mcp add --transport http 21st https://21st.dev/api/mcp
claude mcp add --transport http better-design https://better-design.com/api/mcp
```

The 30-day post-launch smoke in `webflow-build` uses the Claude desktop app's scheduled-tasks connector. Without it, schedule the weekly check by hand.

## Use it

In a Claude Code session, address the agent directly:

```
Use the flowsmith agent. Site ID <id>, Figma file <url>. Build the home page to the design at 1440 and 375, publish to staging, and hand off.
```

Or drive the skills yourself:

| Command | When |
|---|---|
| `/flowsmith-loop brief <task>` | Before the first write of any job. Pulls the relevant ledger entries and writes the build plan. `brief --lite` for a fix of three items or fewer |
| `/webflow-build` | Full site delivery, phase by phase |
| `/webflow-design-system` | Tokens, naming grammar, style-guide page |
| `/webflow-motion` | Motion recipes and the restraint rules |
| `/webflow-verify` | The gate after any change worth trusting |
| `/flowsmith-loop critique` | Before every handoff |
| `/flowsmith-loop absorb "<feedback>"` | When feedback comes back, so the ledger learns |

Check and measure from any terminal:

| Command | Shows |
|---|---|
| `node ~/.claude/skills/webflow-verify/scripts/webcheck.mjs <urls> --job <job_id>` | The check runner. Flags and the report format are in `scripts/README.md` beside it |
| `python3 ~/.claude/lib/agent_kpis.py --agent flowsmith` | First-pass approval rate and the other KPIs from run records |
| `python3 ~/.claude/lib/agent_telemetry.py summary --agent flowsmith` | Whether each dispatch wrote its brief and handoff, and its tokens and active minutes |

Three rules the agent will hold you to:

1. Done means live on the published URL and re-verified there. A staged change is reported as staged.
2. Production publishes, custom domains and any spend of $25 or more stop for human approval.
3. Motion is custom code (GSAP, Lenis, CSS). IX2 interactions cannot be authored by any API, and IX3 writes stay on a test site until a pilot proves them.

## What is not included

- **Creative-code runtime.** Tier 2 and 3 builds (WebGL surfaces, full immersive pages) load a private creative-code runtime that is not part of this repo. Tier 0 and 1 builds, which cover most marketing sites, do not need it.
- **Site corpus.** The whole-site reference cards used for from-scratch design direction stay with Corient. Supply a Figma file or a reference set at discovery instead.
- **Companion agents.** SYSTEM.md hands app, API and n8n work to a `wright` agent and standalone live-site repairs to `webflow-fix`. Neither ships here.
- **Test suites.** The pytest suites behind the ledger linter and the webcheck runner stay private. The runner's `fixtures/` ship, so it can be tried against local pages.
- **Project content.** Names, site IDs and staging URLs from past builds are replaced with placeholders throughout. The lessons are intact.

## Keeping the ledger healthy

After editing `learned-rules.md` by hand:

```bash
python3 ~/.claude/skills/flowsmith-loop/scripts/ledger_lint.py --reindex && python3 ~/.claude/skills/flowsmith-loop/scripts/ledger_lint.py --all
```

`/flowsmith-loop absorb` does this for you.

## Uninstall

1. Remove `~/.claude/agents/flowsmith`, the five skill folders (`flowsmith-loop`, `webflow-build`, `webflow-design-system`, `webflow-motion`, `webflow-verify`) and `~/.claude/hooks/agent-gates.sh`.
2. Remove the ten files in `~/.claude/lib`: `agent_gates.py`, `agent_kpis.py`, `agent_runtime.py`, `agent_scorecard.py`, `agent_telemetry.py`, `debug_chrome.sh`, `flowsmith_manifest.py`, `memory_index.py`, `skill_output.py` and `webflow_naming_audit.py`, plus the two docs in `~/.claude/reference/design-systems/`.
3. Remove the four `settings.json` hook entries that run `agent-gates.sh` or `agent_telemetry.py`. If you had a `settings.json` before the first install, its original is in that install's backup folder.

Backups from each install are under `~/.claude/_backup/`.
