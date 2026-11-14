#!/usr/bin/env bash
# macOS / Linux: check Python, Node.js, ports and disk space without starting anything (same as CHECK_ENVIRONMENT.bat)
cd "$(dirname "$0")" || exit 1
for v in python3.11 python3.12 python3.13 python3; do
  if command -v "$v" >/dev/null 2>&1; then exec "$v" run_energiq.py --doctor; fi
done
echo "Python was not found. Install Python 3.11 from https://www.python.org/downloads/" >&2
exit 1
