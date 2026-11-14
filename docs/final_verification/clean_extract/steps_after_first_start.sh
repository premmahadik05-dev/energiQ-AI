#!/usr/bin/env bash
# The steps run against the extracted delivery ZIP after its first start (see FINAL_TEST_REPORT.md section 9).
#   usage: steps_after_first_start.sh <extracted EnergiQ-AI folder> <log folder> <folder with check_running.py>
# The first start itself was run as `bash run_project.sh --no-browser` (its output is first_start.log).
# Every password in the logs is replaced by <redacted>.
set -u
ROOT="$1"; LOGS="$2"; TOOLS="$3"
cd "$ROOT" || exit 2
PW="$(sed -n 's/^password=//p' .energiq-run/admin_login.txt)"
redact() { sed "s|$PW|<redacted>|g"; }
count_servers() { pgrep -f "uvicorn backend.app.main:create_app" | wc -l; }

{
  echo '$ python check_running.py <extract>   (health through the proxy, API, forecasts, 13 pages in Chromium, no password in the logs)'
  python "$TOOLS/check_running.py" "$ROOT" 2>&1 | redact; echo "exit=${PIPESTATUS[0]}"
} > "$LOGS/check_running.log"

{
  echo '$ bash run_project.sh --status'
  bash run_project.sh --status 2>&1 | redact; echo "exit=${PIPESTATUS[0]}"
  echo; echo "backend (uvicorn) processes before the second start: $(count_servers)"
  echo '$ bash run_project.sh --no-browser      (a second start while the first is running)'
  bash run_project.sh --no-browser 2>&1 | redact; echo "exit=${PIPESTATUS[0]}"
  echo "backend (uvicorn) processes after the second start:  $(count_servers)"
} > "$LOGS/second_start_refused.log"

{
  echo '--- a recorded process that is NOT EnergiQ (a reused process number) must be left alone ---'
  sleep 600 & UNRELATED=$!
  cp .energiq-run/state.json /tmp/state.real.json
  echo '$ bash stop_project.sh   (real instance running)'
  bash stop_project.sh 2>&1 | redact; echo "exit=${PIPESTATUS[0]}"
  echo "servers left after stop: $(count_servers)"
  echo "launcher window ended cleanly (see first_start.log for its last lines)"
  echo
  python - "$UNRELATED" <<'PY'
import json, sys, time
json.dump({"launcher_pid": 999999, "backend_pid": int(sys.argv[1]), "frontend_pid": 0, "backend_port": 1, "frontend_port": 2,
           "phase": "running", "started_at": time.time()}, open(".energiq-run/state.json", "w"))
PY
  echo "stale record written: backend_pid=$UNRELATED (an unrelated 'sleep'), ports where nothing answers"
  echo '$ bash stop_project.sh'
  bash stop_project.sh 2>&1; echo "exit=${PIPESTATUS[0]}"
  if kill -0 "$UNRELATED" 2>/dev/null; then echo "RESULT: the unrelated process $UNRELATED is still running -> PASS"; else echo "RESULT: the unrelated process was killed -> FAIL"; fi
  kill "$UNRELATED" 2>/dev/null
  echo "state.json after stop: $( [ -e .energiq-run/state.json ] && echo present || echo removed )"
  echo '$ bash stop_project.sh   (nothing recorded)'
  bash stop_project.sh 2>&1; echo "exit=${PIPESTATUS[0]}"
  echo '$ bash run_project.sh --status'
  bash run_project.sh --status 2>&1; echo "exit=${PIPESTATUS[0]}"
} > "$LOGS/stop_and_ownership.log"

{
  echo '$ bash run_project.sh --no-browser      (warm start: packages installed, database exists)'
  S=$(date +%s)
  ( bash run_project.sh --no-browser > "$LOGS/warm_start.raw" 2>&1 & )
  for _ in $(seq 1 120); do grep -q "EnergiQ AI is running" "$LOGS/warm_start.raw" 2>/dev/null && break; sleep 1; done
  echo "warm start to 'running': $(( $(date +%s) - S )) s"
  redact < "$LOGS/warm_start.raw"
  echo "same password as before: $( [ "$(sed -n 's/^password=//p' .energiq-run/admin_login.txt)" = "$PW" ] && echo yes || echo NO )"
  rm -f "$LOGS/warm_start.raw"
} > "$LOGS/warm_start.log"
bash stop_project.sh > /dev/null 2>&1

{
  echo '--- a database that cannot be prepared must stop the start with a plain message and start nothing ---'
  mv data/energiq.db /tmp/energiq.db.keep; mkdir data/energiq.db
  echo '$ bash run_project.sh --no-browser'
  bash run_project.sh --no-browser 2>&1 | redact; echo "exit=${PIPESTATUS[0]}"
  echo "servers running afterwards: $(count_servers)"
  echo "state.json afterwards: $( [ -e .energiq-run/state.json ] && echo present || echo removed )"
  echo '--- last lines of .energiq-run/launcher.log ---'
  tail -n 6 .energiq-run/launcher.log | redact
  rmdir data/energiq.db; mv /tmp/energiq.db.keep data/energiq.db
} > "$LOGS/database_failure.log"

{
  echo '--- after the failure, with the database back, the next start works ---'
  ( bash run_project.sh --no-browser > "$LOGS/after_failure.raw" 2>&1 & )
  for _ in $(seq 1 120); do grep -q "EnergiQ AI is running" "$LOGS/after_failure.raw" 2>/dev/null && break; sleep 1; done
  redact < "$LOGS/after_failure.raw" | grep -E "Database:|Backend:|Web app:|is running"
  rm -f "$LOGS/after_failure.raw"
  bash stop_project.sh 2>&1 | tail -n 2
} > "$LOGS/recovery_after_failure.log"
echo done
