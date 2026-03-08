#!/bin/sh

sudo chown -R "$(whoami)":"$(whoami)" /home/"$(whoami)"/app/.venv
sudo mkdir -p /usr/local/bin/Logs
sudo chmod 777 /usr/local/bin/Logs
uv sync
