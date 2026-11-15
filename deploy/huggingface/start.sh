#!/usr/bin/env bash
# API (serving the built frontend) and the background job worker in one container.
set -e
cd /app/backend
python -m app.jobs.worker &
exec uvicorn app.main:app --host 0.0.0.0 --port 7860 --proxy-headers --forwarded-allow-ips='*'
