#!/usr/bin/env bash
# Restart the audit backend with a FRESH database and import the bundled societies. Frontend dev server is left running.
cd /home/claude/pro/EnergiQ-AI || exit 1
pkill -f "uvicorn backend.app.main:create_app" 2>/dev/null; sleep 1
rm -rf /home/claude/pro/run/energiq.db /home/claude/pro/run/uploads /home/claude/pro/run/models /home/claude/pro/run/reports
export ENERGIQ_DATABASE_URL=sqlite:////home/claude/pro/run/energiq.db ENERGIQ_UPLOAD_DIR=/home/claude/pro/run/uploads ENERGIQ_MODELS_DIR=/home/claude/pro/run/models ENERGIQ_REPORTS_DIR=/home/claude/pro/run/reports
export ENERGIQ_ADMIN_EMAIL=admin@example.com ENERGIQ_ADMIN_PASSWORD=AdminPass-12345 ENERGIQ_ENV=dev ENERGIQ_LOGIN_PER_MINUTE=${LOGIN_RATE:-10}
setsid nohup /tmp/venv311/bin/python -m uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8000 > /home/claude/pro/run/backend.log 2>&1 &
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/health/ready >/dev/null && break; sleep 1; done
TOK=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@example.com","password":"AdminPass-12345"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
JOB=$(curl -s -X POST http://127.0.0.1:8000/api/v1/admin/societies/import-bundled -H "Authorization: Bearer $TOK" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
for i in $(seq 1 120); do S=$(curl -s http://127.0.0.1:8000/api/v1/jobs/$JOB -H "Authorization: Bearer $TOK" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])"); [ "$S" = succeeded -o "$S" = failed ] && break; sleep 2; done
echo "import: $S"
curl -s http://127.0.0.1:8000/api/v1/societies -H "Authorization: Bearer $TOK" | python3 -c "import sys,json;[print(x['key'],'forecast_ready=',x['forecast_ready']) for x in json.load(sys.stdin)]"
