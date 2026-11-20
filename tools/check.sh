#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .tmp .runtime
export TMPDIR="$PWD/.tmp"
python_path="${WZL_TEST_PYTHON:-.venv/bin/python}"
PYTHONPATH="$PWD" "$python_path" -m pytest -q --basetemp="$PWD/.runtime/pytest" tests
node --check web/app.js
