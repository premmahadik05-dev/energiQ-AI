#!/usr/bin/env bash
# macOS / Linux launcher (same steps and options as RUN_PROJECT.bat):   ./run_project.sh [--no-browser] [--reinstall]
cd "$(dirname "$0")" || exit 1
for v in python3.11 python3.12 python3.13 python3; do
  if command -v "$v" >/dev/null 2>&1 && "$v" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)'; then
    exec "$v" run_energiq.py "$@"
  fi
done
echo "Python 3.11 to 3.13 was not found. Install Python 3.11 from https://www.python.org/downloads/" >&2
exit 1
