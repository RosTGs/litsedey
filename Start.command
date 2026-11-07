#!/bin/zsh
set -eu
studio_root="${0:A:h}"
if [[ -x "$studio_root/.venv/bin/python" ]]; then
  studio_python="$studio_root/.venv/bin/python"
else
  studio_python="$studio_root/../.venv/bin/python"
fi
cd "$studio_root"
exec "$studio_python" launch.py
