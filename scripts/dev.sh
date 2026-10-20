#!/usr/bin/env bash
# Start the full AITS dev stack (backend + frontend).
# Redis is optional: without it the backend falls back to in-memory cache and
# eager Celery, which is enough for UI development.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
PY="$BACKEND/.venv/bin/python"

if [[ -z "${REDIS_URL:-}" ]] && command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
  export REDIS_URL="redis://127.0.0.1:6379/0"
fi

echo "▶ migrate"
( cd "$BACKEND" && "$PY" manage.py migrate --noinput )

echo "▶ backend  http://127.0.0.1:8000"
( cd "$BACKEND" && "$PY" manage.py runserver 0.0.0.0:8000 ) &
BACK_PID=$!

if [[ -d "$ROOT/frontend" ]]; then
  echo "▶ frontend http://127.0.0.1:5173"
  ( cd "$ROOT/frontend" && pnpm dev --host 127.0.0.1 ) &
  FRONT_PID=$!
else
  FRONT_PID=""
fi

trap 'kill $BACK_PID $FRONT_PID 2>/dev/null' INT TERM
wait
