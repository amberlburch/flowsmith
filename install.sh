#!/usr/bin/env bash
# FLOWSMITH installer for Claude Code.
# Copies the agent, its five skills, the gate hook, the runtime scripts and two
# reference docs into a Claude Code home (default ~/.claude), points the agent's
# frontmatter hooks at that install, and adds the gate and telemetry hooks to
# settings.json beside any hooks already there. Everything it would change,
# settings.json included, is backed up first. Safe to re-run.
#
#   ./install.sh                 install into ~/.claude
#   ./install.sh --dry-run       show what would change, write nothing
#   ./install.sh --keep-ledger   do not overwrite an existing learned-rules.md
#   ./install.sh --no-settings   leave settings.json alone; print the hook entries to add by hand
#   CLAUDE_HOME=/path ./install.sh   install somewhere else
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
case "$CLAUDE_HOME" in /*) ;; *) CLAUDE_HOME="$PWD/$CLAUDE_HOME" ;; esac
case "$CLAUDE_HOME" in
  *[[:space:]]*) echo "CLAUDE_HOME must not contain spaces: hook commands name it unquoted" >&2; exit 1 ;;
esac
DRY_RUN=0
KEEP_LEDGER=0
NO_SETTINGS=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --keep-ledger) KEEP_LEDGER=1 ;;
    --no-settings) NO_SETTINGS=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 1 ;;
  esac
done

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$CLAUDE_HOME/_backup/flowsmith-$STAMP"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
changed=0; backed=0; unchanged=0

say() { printf '%s\n' "$*"; }
run() { if [ "$DRY_RUN" -eq 1 ]; then say "  [dry-run] $*"; else "$@"; fi; }

install_file() {
  local src="$1"
  local rel="$2"
  local dst="$CLAUDE_HOME/$rel"
  if [ "$KEEP_LEDGER" -eq 1 ] && [ "$rel" = "agents/flowsmith/learned-rules.md" ] && [ -e "$dst" ]; then
    say "  keep     $rel (--keep-ledger)"; return
  fi
  if [ -e "$dst" ]; then
    if cmp -s "$src" "$dst"; then unchanged=$((unchanged+1)); return; fi
    run mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
    run cp -p "$dst" "$BACKUP_DIR/$rel"
    backed=$((backed+1))
    say "  update   $rel (backup in _backup/flowsmith-$STAMP)"
  else
    say "  add      $rel"
  fi
  run mkdir -p "$(dirname "$dst")"
  run cp -p "$src" "$dst"
  changed=$((changed+1))
}

install_tree() {
  local rel="$1" f r
  while IFS= read -r -d '' f; do
    r="${f#"$REPO_DIR"/}"
    [ "$r" = "agents/flowsmith/SYSTEM.md" ] && f="$TMP/SYSTEM.md"
    install_file "$f" "$r"
  done < <(find "$REPO_DIR/$rel" -type f -not -name '.DS_Store' -not -name '*.pyc' -not -path '*/__pycache__/*' -print0 | sort -z)
}

# The agent's frontmatter runs the gate hook by path: point it at this install.
render_system() {
  python3 - "$REPO_DIR/agents/flowsmith/SYSTEM.md" "$TMP/SYSTEM.md" "$CLAUDE_HOME" <<'PY'
import re
import sys
src, dst, home = sys.argv[1:]
text = open(src, encoding="utf-8").read()
text = re.sub(r"(?m)^(\s*command:\s*)~/\.claude/", lambda m: m.group(1) + home.rstrip("/") + "/", text)
open(dst, "w", encoding="utf-8").write(text)
PY
}

# Hook entries in settings.json: the Webflow publish gates, the approval-grant guard and
# flowsmith's telemetry. Added beside the user's own hooks, never replacing one. An entry
# already there (same script and arguments, at any path) is left as it is.
wire_settings() {
  python3 - "$CLAUDE_HOME" "$DRY_RUN" "$NO_SETTINGS" "$BACKUP_DIR" <<'PY'
import json
import shutil
import sys
from pathlib import Path

home, dry, manual, backup = Path(sys.argv[1]), sys.argv[2] == "1", sys.argv[3] == "1", Path(sys.argv[4])
path = home / "settings.json"
gate, webflow = home / "hooks" / "agent-gates.sh", "mcp__plugin_webflow-skills_webflow__"
want = [  # event, matcher, command, timeout in seconds
    ("PreToolUse", webflow + ".*", f"{gate} pre-webflow", 10),
    ("PostToolUse", webflow + "data_sites_tool", f"{gate} post-webflow", 10),
    ("PreToolUse", "Bash|Edit|Write|MultiEdit|NotebookEdit", f"{gate} pre-grant", 10),
    ("SubagentStop", "flowsmith", f"python3 {home / 'lib' / 'agent_telemetry.py'} hook", 60),
]


def entry(matcher, command, timeout):
    return {"matcher": matcher, "hooks": [{"type": "command", "command": command, "timeout": timeout}]}


def sig(command):
    """The script's file name and its arguments."""
    parts = str(command).replace('"', "").split()
    for i, p in enumerate(parts):
        if p.endswith((".sh", ".py")):
            return " ".join([p.rsplit("/", 1)[-1]] + parts[i + 1:])
    return ""


data, why = None, "--no-settings"
if not manual:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        hooks = data.get("hooks", {}) if isinstance(data, dict) else None
        if not isinstance(hooks, dict) or not all(isinstance(v, list) for v in hooks.values()):
            data, why = None, "its hooks block is not the shape Claude Code writes"
    except (OSError, ValueError) as e:
        data, why = None, f"it does not parse as JSON: {e}"
if data is None:
    block = {}
    for ev, m, c, t in want:
        block.setdefault(ev, []).append(entry(m, c, t))
    print(f"  settings.json left alone ({why}). Add these entries under \"hooks\" by hand:")
    print("\n".join("    " + ln for ln in json.dumps(block, indent=2).splitlines()))
    sys.exit(0)

hooks = data.setdefault("hooks", {})
have = {(ev, sig(h.get("command")))
        for ev, entries in hooks.items() for e in entries if isinstance(e, dict)
        for h in e.get("hooks") or [] if isinstance(h, dict)}
add = [w for w in want if (w[0], sig(w[2])) not in have]
if not add:
    print("  settings.json: hooks already wired")
    sys.exit(0)
for ev, m, c, t in add:
    print(f"  add      settings.json {ev} hook: {sig(c)}")
    hooks.setdefault(ev, []).append(entry(m, c, t))
if dry:
    sys.exit(0)
if path.exists():
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup / "settings.json")
    print(f"  backup   settings.json (in _backup/{backup.name})")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

say "FLOWSMITH -> $CLAUDE_HOME"
[ "$DRY_RUN" -eq 1 ] && say "(dry run: nothing will be written)"

command -v python3 >/dev/null || { say "python3 is required (3.10+)"; exit 1; }
python3 - <<'PY' || { say "python3 3.10 or newer is required"; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY

render_system
install_tree agents/flowsmith
install_tree skills
install_tree hooks
install_tree lib
install_tree reference/design-systems

# Shared budget file: only if the workspace does not already have one.
if [ ! -e "$CLAUDE_HOME/agents/shared/budget-caps.json" ]; then
  install_file "$REPO_DIR/agents/shared/budget-caps.json" "agents/shared/budget-caps.json"
fi

# Runtime directories the scripts write to.
for d in state/flowsmith state/agent-runs/flowsmith results/flowsmith-loop logs; do
  [ -d "$CLAUDE_HOME/$d" ] || { say "  mkdir    $d"; run mkdir -p "$CLAUDE_HOME/$d"; }
done

say ""
say "files: $changed written, $backed backed up, $unchanged already current"
say ""
say "settings.json hooks"
wire_settings
[ "$DRY_RUN" -eq 1 ] && exit 0

say ""
say "post-install checks"
fm_hook="$(sed -n 's/^ *command: *\([^ ]*agent-gates\.sh\) .*/\1/p' "$CLAUDE_HOME/agents/flowsmith/SYSTEM.md")"
fm_hook="${fm_hook%%$'\n'*}"
if [ -n "$fm_hook" ] && [ -x "$fm_hook" ]; then
  say "  agent hooks: ok ($fm_hook)"
else
  say "  agent hooks: FAILED (the frontmatter names '${fm_hook:-no gate hook}', not an installed executable)"
fi
# A production publish with no approval grant must be denied. State goes to a temp folder.
smoke='{"tool_name":"mcp__plugin_webflow-skills_webflow__data_sites_tool","tool_input":{"actions":[{"publish_site":{"site_id":"install-smoke","customDomains":["example.com"]}}]}}'
gate_out="$(printf '%s' "$smoke" | AGENT_GATES_ROOT="$TMP" "$CLAUDE_HOME/hooks/agent-gates.sh" pre-webflow 2>&1 || true)"
case "$gate_out" in
  *'"permissionDecision": "deny"'*) say "  gate hook: ok (denies a production publish with no grant)" ;;
  *) say "  gate hook: FAILED (${gate_out:-no output})" ;;
esac
node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
if [ "$node_major" -ge 22 ] && node --check "$CLAUDE_HOME/skills/webflow-verify/scripts/webcheck.mjs" 2>/dev/null; then
  say "  webcheck runner: ok (Node $node_major)"
else
  say "  webcheck runner: needs Node 22 or later (found $(node --version 2>/dev/null || echo none))"
fi
# The runtime scripts resolve their files from <home>/.claude, so these checks run
# with HOME pointed at the parent of CLAUDE_HOME. Skipped for a non-standard name.
if [ "$(basename "$CLAUDE_HOME")" != ".claude" ]; then
  say "  ledger lint, publish lock: skipped (scripts expect the install to live at <home>/.claude)"
else
  CHECK_HOME="$(dirname "$CLAUDE_HOME")"
  lint_out="$(HOME="$CHECK_HOME" python3 "$CLAUDE_HOME/skills/flowsmith-loop/scripts/ledger_lint.py" --all 2>&1 || true)"
  if printf '%s\n' "$lint_out" | grep -q '^FAIL'; then
    say "  ledger lint: findings (informational)"
    printf '%s\n' "$lint_out" | grep -E '^FAIL|pass_rate' | sed 's/^/    /'
  else
    say "  ledger lint: ok ($(printf '%s\n' "$lint_out" | grep -o 'pass_rate.*' || true))"
  fi
  JOB="install-smoke-$STAMP"
  if out="$(HOME="$CHECK_HOME" python3 "$CLAUDE_HOME/lib/agent_runtime.py" lock "$JOB" "webflow_publish:install-smoke" 2>&1)" && [ "$out" = "acquired" ]; then
    HOME="$CHECK_HOME" python3 "$CLAUDE_HOME/lib/agent_runtime.py" unlock "$JOB" >/dev/null
    say "  publish lock: ok"
  else
    say "  publish lock: FAILED ($out)"
  fi
fi

say ""
say "installed. Start a new Claude Code session (hooks load at session start), then run /agents to confirm 'flowsmith' is listed."
say "next: install the MCP servers listed in README.md (Webflow plugin, chrome-devtools, Figma)."
