#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "请先运行：python3 scripts/setup.py"
  exit 1
fi
exec .venv/bin/python app.py "$@"
