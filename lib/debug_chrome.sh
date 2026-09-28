#!/bin/bash
# Ensure a debug Chrome is listening on 127.0.0.1:9222 for the chrome-devtools MCP.
#
# The MCP is configured with --browserUrl=http://127.0.0.1:9222 and never launches
# Chrome itself, so every agent verification pass depends on this (flowsmith L-107:
# 52 "Could not connect to Chrome" failures before this existed). Uses its own
# profile, never the operator's: Chrome refuses remote debugging on the default profile.
#
# Usage: debug_chrome.sh [--headed] [--restart]
#   default   headless (no window). Right for layout, console, curl-grade checks.
#   --headed  real window and GPU. Needed for WebGL frame-counter liveness (L-100/L-102).
#   --restart kill the managed instance first (closes every session's pages).
# Prints "ready: <browser> (<mode>)" and exits 0, or "error: <reason>" and exits 1.
set -u

PORT=9222
PROFILE="$HOME/.cache/claude-debug-chrome"
LOG="$HOME/.cache/claude-debug-chrome.log"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
want="headless"
restart=0
for a in "$@"; do
  case "$a" in
    --headed) want="headed" ;;
    --restart) restart=1 ;;
    *) echo "error: unknown flag $a"; exit 1 ;;
  esac
done

version() { curl -s -m 2 "http://127.0.0.1:$PORT/json/version"; }
managed_pids() { pgrep -f -- "--user-data-dir=$PROFILE" ; }
mode_of() { case "$1" in *HeadlessChrome*) echo headless ;; *) echo headed ;; esac; }

v=$(version)
if [ -n "$v" ] && [ "$restart" -eq 0 ]; then
  have=$(mode_of "$v")
  if [ "$have" = "$want" ] || [ -z "$(managed_pids)" ]; then
    # Right mode, or an unmanaged Chrome someone else started: use it, never kill it.
    browser=$(printf '%s' "$v" | sed -n 's/.*"Browser"[^"]*"\([^"]*\)".*/\1/p')
    echo "ready: $browser ($have$([ -z "$(managed_pids)" ] && echo ', unmanaged'))"
    exit 0
  fi
  # Wrong mode. Another session may be mid-verification in this browser, so refuse
  # rather than kill; the caller decides whether --restart is safe.
  echo "error: debug Chrome is running $have and $want was asked for; rerun with --restart to replace it (closes every session's pages)"
  exit 1
fi

if [ "$restart" -eq 1 ] && [ -n "$(managed_pids)" ]; then
  pkill -f -- "--user-data-dir=$PROFILE"
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -z "$(managed_pids)" ] && break; sleep 0.5; done
fi

[ -x "$CHROME" ] || { echo "error: Chrome not found at $CHROME"; exit 1; }
mkdir -p "$PROFILE"

flags=(
  "--remote-debugging-port=$PORT"
  "--user-data-dir=$PROFILE"
  --no-first-run --no-default-browser-check
  # Keep timers and rAF running in background tabs so timing checks do not read as
  # failures (L-100), while the frame-counter assertion itself still needs a
  # foreground page (L-102).
  --disable-background-timer-throttling
  --disable-renderer-backgrounding
  --disable-backgrounding-occluded-windows
)
[ "$want" = "headless" ] && flags+=(--headless=new --window-size=1440,900)

nohup "$CHROME" "${flags[@]}" about:blank >"$LOG" 2>&1 &

for _ in $(seq 1 40); do
  v=$(version)
  if [ -n "$v" ]; then
    browser=$(printf '%s' "$v" | sed -n 's/.*"Browser"[^"]*"\([^"]*\)".*/\1/p')
    echo "ready: $browser ($want)"
    exit 0
  fi
  sleep 0.5
done
echo "error: Chrome did not open port $PORT within 20s (log: $LOG)"
exit 1
