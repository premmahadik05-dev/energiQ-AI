#!/usr/bin/env bash
# macOS / Linux: stop the EnergiQ AI started by run_project.sh (same as STOP_PROJECT.bat)
cd "$(dirname "$0")" || exit 1
for v in python3.11 python3.12 python3.13 python3; do
  if command -v "$v" >/dev/null 2>&1; then exec "$v" run_energiq.py --stop; fi
done
echo "Python was not found." >&2
exit 1
