#!/usr/bin/env bash
# Bengal Download Manager - Full Test Suite Runner
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT_DIR"

# Default: verbose per-test lines, short tracebacks, failure summary.
# pyproject's addopts starts with -q which would cancel -v, so override it here.
#
# Usage:
#   scripts/run_tests.sh                       # all 548 tests, verbose
#   scripts/run_tests.sh tests/e2e/            # one directory
#   scripts/run_tests.sh tests/e2e/test_options_flow.py
#   scripts/run_tests.sh tests/unit/ -k config
#   scripts/run_tests.sh -x --tb=long          # stop at first failure
#   scripts/run_tests.sh -q                    # back to quiet dots
if [ "$#" -eq 0 ]; then
    set -- tests/
fi

exec env PYTHONPATH=src uv run pytest \
    -o addopts="--disable-warnings --tb=short" \
    -v "$@"
