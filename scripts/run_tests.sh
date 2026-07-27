#!/usr/bin/env bash
# Run the full KerrOS test suite.
# Usage: ./scripts/run_tests.sh
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -p 'test_*.py' -t . "$@"
