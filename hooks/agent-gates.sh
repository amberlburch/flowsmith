#!/bin/bash
# Webflow and dispatch gates: publish (production grant, staging parameters, lock, spacing),
# brief before the first write, handoff before stop, tool-call cap, snapshot before removal,
# no approval grant written by a subagent, and no GitHub MCP write to the public flowsmith repo.
# Registered in settings.json (pre-webflow, post-webflow, pre-grant, pre-github) and in the flowsmith and
# wright frontmatter (pre-agent, stop-agent). Logic and the fail-open contract: lib/agent_gates.py.
lib="${0%/*}/../lib/agent_gates.py"
if [ "$1" = pre-grant ]; then
  # Runs on every Bash call and file write: start Python only when a subagent names a grant.
  payload=$(cat)
  case $payload in *'"agent_id"'*) ;; *) exit 0 ;; esac
  case $payload in *approvals*|*webflow-production-*) ;; *) exit 0 ;; esac
  exec python3 "$lib" "$@" <<<"$payload"
fi
exec python3 "$lib" "$@"
