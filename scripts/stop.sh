#!/usr/bin/env bash
# Linux/macOS: stop the processes started by scripts/dev.sh (Windows users: use stop.ps1).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

kill_tree() {  # terminate a process and all of its descendants (npx -> vite, etc.)
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null); do kill_tree "$child"; done
  kill -TERM "$pid" 2>/dev/null || true
}

for name in frontend worker backend; do
  f="$ROOT/logs/$name.pid"
  [ -f "$f" ] || continue
  pid="$(cat "$f")"
  if kill -0 "$pid" 2>/dev/null; then
    kill_tree "$pid"
    echo "stopped $name ($pid)"
  fi
  rm -f "$f"
done
