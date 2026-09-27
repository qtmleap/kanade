#!/usr/bin/env bash
#
# Single source of the tmux session name used by start-agents.sh and any shell
# that needs to locate the shared agent session.
#
# The default is the workspace directory name: no project name is baked into the
# scripts. devcontainer.json passes the host folder name through AGENTS_SESSION,
# so inside the container the session is still named after the repository rather
# than after the mount point (/home/vscode/app).
#
#   AGENT_SESSION  tmux session name (override with AGENTS_SESSION)

# tmux treats '.' and ':' as target separators, so collapse everything that is
# not alphanumeric, '_' or '-' into '-'.
AGENT_SESSION="$(
  printf '%s' "${AGENTS_SESSION:-$(basename "$PWD")}" \
    | tr '[:upper:]' '[:lower:]' \
    | tr -cs 'a-z0-9_-' '-'
)"
AGENT_SESSION="${AGENT_SESSION:-agents}"
