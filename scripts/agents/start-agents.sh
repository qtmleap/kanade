#!/usr/bin/env bash
#
# Bring up orchestrator / implementer / reviewer side by side in one tmux session.
#
#   ┌──────────────┬──────────────┐
#   │              │ implementer  │  Claude Code, writes and verifies the code
#   │ orchestrator ├──────────────┤
#   │              │ reviewer     │  Claude Code, design and change review
#   └──────────────┴──────────────┘
#     Claude Code, receives every user request and runs the work
#
# The role names are also Claude Code cross-session addresses. All three seats
# can call Codex through their own project MCP process; there is no interactive
# Codex pane and no tmux-based messaging.
#
# The container is the sandbox, so every Claude approval check is off by default.
# Set CLAUDE_ARGS explicitly before running this anywhere that is not isolated.
#
# .vscode/tasks.json runs this on folderOpen, so a broken agent setup must still
# leave a usable terminal behind: every failure path falls back to a login shell.
#
# Environment:
#   AGENTS_TMUX         set to 0 to skip tmux and get a plain shell
#   AGENTS_SESSION      tmux session name                          (default: workspace directory name)
#   CLAUDE_ARGS         claude args for all three panes             (default: --dangerously-skip-permissions)
#   ORCHESTRATOR_ARGS   extra args for orchestrator only            (default: none)
#   ORCHESTRATOR_MODEL  --model for orchestrator                    (default: claude-sonnet-5)
#   IMPLEMENTER_ARGS    extra args for implementer only             (default: none)
#   IMPLEMENTER_MODEL   --model for implementer                     (default: claude-opus-5)
#   REVIEWER_ARGS       extra args for reviewer only                (default: none)
#   REVIEWER_MODEL      --model for reviewer                        (default: claude-sonnet-5)
#
# CLAUDE_ARGS is read as ${VAR-default}, so exporting an empty string drops the
# default; only an unset variable gets it.
#
# Arguments:
#   --no-attach   build the session but do not attach (used by postAttachCommand)
#   --restart     restart the agents in a session that already exists
#
# --restart replaces what runs inside each pane and leaves the session itself
# alone, so a terminal already attached to it keeps its place and simply shows
# the fresh agents. Killing the session instead would take that terminal down
# with it, which matters because the one VS Code opens on folderOpen is usually
# the only one. Needed whenever a model or a role prompt changes: both are read
# when claude starts, so a running seat keeps the old ones.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
. "$SCRIPT_DIR/agent-session.sh"
SESSION="$AGENT_SESSION"

CLAUDE_ARGS="${CLAUDE_ARGS---dangerously-skip-permissions}"
ORCHESTRATOR_ARGS="${ORCHESTRATOR_ARGS:-}"
ORCHESTRATOR_MODEL="${ORCHESTRATOR_MODEL:-claude-sonnet-5}"
IMPLEMENTER_ARGS="${IMPLEMENTER_ARGS:-}"
IMPLEMENTER_MODEL="${IMPLEMENTER_MODEL:-claude-opus-5}"
REVIEWER_ARGS="${REVIEWER_ARGS:-}"
REVIEWER_MODEL="${REVIEWER_MODEL:-claude-sonnet-5}"
ATTACH=1
RESTART=0
for arg in "$@"; do
  case "$arg" in
    --no-attach) ATTACH=0 ;;
    --restart) RESTART=1 ;;
  esac
done

# Drop to a plain shell. This is launched from a task and from terminal
# profiles, so exiting here would close the VS Code terminal outright.
fallback_shell() {
  [ "$ATTACH" -eq 0 ] && exit 0
  exec "${SHELL:-/bin/zsh}" -l
}

[ "${AGENTS_TMUX:-1}" = "0" ] && fallback_shell

for cmd in tmux claude; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    printf '\033[33mwarning:\033[0m %s not found, starting a plain shell instead.\n' "$cmd" >&2
    fallback_shell
  fi
done

# Never nest tmux: if this is called from inside a session, leave it alone.
[ -n "${TMUX:-}" ] && fallback_shell

# ─── Commands for each pane ────────────────────────────────────────────
model_flag() { [ -n "${1:-}" ] && printf -- '--model %q ' "$1"; return 0; }
# Append <role>.md to the system prompt when it exists; warn and fall back to
# a bare claude when it does not.
prompt_flag() {
  local f="$SCRIPT_DIR/$1.md"
  if [ -r "$f" ]; then
    printf -- '--append-system-prompt "$(cat %q)" ' "$f"
  else
    printf '\033[33mwarning:\033[0m %s missing, starting %s as a bare claude.\n' "$f" "$1" >&2
  fi
  return 0
}

ORCH_CMD="claude --name orchestrator $(model_flag "${ORCHESTRATOR_MODEL:-}")$(prompt_flag orchestrator)${CLAUDE_ARGS} ${ORCHESTRATOR_ARGS}"
IMPL_CMD="claude --name implementer $(model_flag "${IMPLEMENTER_MODEL:-}")$(prompt_flag implementer)${CLAUDE_ARGS} ${IMPLEMENTER_ARGS}"
REVIEW_CMD="claude --name reviewer $(model_flag "${REVIEWER_MODEL:-}")$(prompt_flag reviewer)${CLAUDE_ARGS} ${REVIEWER_ARGS}"

pane_cmd() {
  case "$1" in
    orchestrator) printf '%s' "$ORCH_CMD" ;;
    implementer) printf '%s' "$IMPL_CMD" ;;
    reviewer) printf '%s' "$REVIEW_CMD" ;;
  esac
  return 0
}

# Keep the role in a pane option: Claude Code rewrites pane_title, so the title
# is not a reliable way to identify a seat. --restart pairs each pane with its
# command through this option, and cross-session messages use the same name.
pane_label() {
  printf '%s' "$1"
}

if tmux has-session -t "=$SESSION" 2>/dev/null; then
  if [ "$RESTART" -eq 1 ]; then
    # ─── Restart in place ────────────────────────────────────────────────
    # respawn-pane -k replaces the process and keeps the pane, so the layout,
    # the pane options and any attached client all survive. A pane carrying no
    # @role is someone's own shell — leave it running.
    while read -r pane role; do
      # Sessions created before the Codex MCP migration have an interactive
      # `codex` seat in the third pane. Convert that pane in place so the VS Code
      # Restart command applies the new topology without killing the tmux client.
      if [ "$role" = "codex" ]; then
        role=reviewer
        tmux set-option -p -t "$pane" @role "$role"
      fi
      # Normalize labels from older sessions too: the implementer used to be
      # displayed as `claude code`, before all three panes became Claude seats.
      label="$(pane_label "$role")"
      tmux set-option -p -t "$pane" @label "$label"
      tmux select-pane -t "$pane" -T "$label"
      cmd="$(pane_cmd "$role")"
      [ -z "$cmd" ] && continue
      tmux respawn-pane -k -t "$pane" -c "$PWD"
      tmux send-keys -t "$pane" "$cmd" C-m
    done < <(tmux list-panes -t "=$SESSION" -F '#{pane_id} #{@role}')
  fi
else
  # ─── Build the session ─────────────────────────────────────────────────
  tmux new-session -d -s "$SESSION" -c "$PWD" -n dev
  tmux split-window -h -t "$SESSION:dev" -c "$PWD"        # right column
  tmux split-window -v -t "$SESSION:dev.1" -c "$PWD"      # split the right column
  ROLES=(orchestrator implementer reviewer)

  i=0
  for role in "${ROLES[@]}"; do
    label="$(pane_label "$role")"
    tmux set-option -p -t "$SESSION:dev.$i" @role "$role"
    tmux set-option -p -t "$SESSION:dev.$i" @label "$label"
    tmux select-pane -t "$SESSION:dev.$i" -T "$label"
    i=$((i + 1))
  done

  tmux set-option -t "$SESSION" -g pane-border-status top
  tmux set-option -t "$SESSION" -g pane-border-format ' #{@label} '
  tmux set-option -t "$SESSION" -g history-limit 50000
  tmux set-option -t "$SESSION" -g mouse on

  tmux send-keys -t "$SESSION:dev.0" "$ORCH_CMD" C-m
  tmux send-keys -t "$SESSION:dev.1" "$IMPL_CMD" C-m
  tmux send-keys -t "$SESSION:dev.2" "$REVIEW_CMD" C-m

  tmux select-pane -t "$SESSION:dev.0"
fi

[ "$ATTACH" -eq 0 ] && exit 0

exec tmux attach-session -t "=$SESSION"
