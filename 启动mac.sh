#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PATH="$PWD/.tools/node/bin:$HOME/bin:$PATH"
if [ ! -x .venv/bin/python ]; then
  echo "请先运行：/opt/homebrew/bin/python3.12 scripts/setup.py"
  exit 1
fi
exec .venv/bin/python app.py "$@"
