#!/usr/bin/env bash
# Linux/macOS development launcher (Windows users: use start.ps1).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/logs"
cd "$ROOT/backend"
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$ROOT/logs/backend.log" 2>&1 &
echo $! > "$ROOT/logs/backend.pid"
python -m app.jobs.worker > "$ROOT/logs/worker.log" 2>&1 &
echo $! > "$ROOT/logs/worker.pid"
cd "$ROOT/frontend"
npx vite --port 5173 --strictPort > "$ROOT/logs/frontend.log" 2>&1 &
echo $! > "$ROOT/logs/frontend.pid"
echo "Sylva: http://localhost:5173  API: http://localhost:8000/docs  (stop: kill \$(cat logs/*.pid))"
