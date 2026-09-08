#!/bin/zsh
set -e

project_dir="${0:A:h}"
cd "$project_dir"

if [[ ! -x .venv/bin/python ]]; then
  echo "Не найдено .venv. Выполните: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

exec .venv/bin/python -m app.supervisor
