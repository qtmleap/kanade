#!/bin/zsh
set -e

sudo chown -R $(whoami):$(whoami) .venv 2>/dev/null || true

# gamdl などの外部ツールが書き出すログの置き場
sudo mkdir -p /usr/local/bin/Logs
sudo chmod 777 /usr/local/bin/Logs

# Silence direnv output.
# In direnv 2.36+, DIRENV_LOG_FORMAT env var is ignored unless direnv.toml exists.
# See: https://github.com/direnv/direnv/issues/1418
mkdir -p ~/.config/direnv
cat > ~/.config/direnv/direnv.toml <<'EOF'
[global]
log_format = ""
hide_env_diff = true
EOF

# Install Python declared in .python-version / pyproject.toml, then sync deps.
# `uv sync` creates .venv if it does not exist yet.
if [ -f pyproject.toml ]; then
  if [ -f uv.lock ]; then
    uv sync --frozen
  else
    uv sync
  fi
fi
