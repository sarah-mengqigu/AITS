#!/usr/bin/env bash
# AITS v2 one-command verification.
# Usage: ./scripts/verify.sh [--skip-frontend]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
PY="$BACKEND/.venv/bin/python"
SKIP_FRONTEND=0
[[ "${1:-}" == "--skip-frontend" ]] && SKIP_FRONTEND=1

FAILED=0
step() { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✔ %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m✘ %s\033[0m\n' "$*"; FAILED=1; }

step "Backend: system check"
( cd "$BACKEND" && AITS_ENV=test "$PY" manage.py check ) && ok "django check" || fail "django check"

step "Backend: migrations complete?"
( cd "$BACKEND" && AITS_ENV=test "$PY" manage.py makemigrations --check --dry-run ) \
  && ok "no missing migrations" || fail "missing migrations (run makemigrations)"

step "Backend: full test suite"
( cd "$BACKEND" && AITS_ENV=test "$PY" manage.py test apps tests -v 1 ) \
  && ok "backend tests" || fail "backend tests"

if [[ $SKIP_FRONTEND -eq 0 && -d "$ROOT/frontend" ]]; then
  step "Frontend: unit tests"
  ( cd "$ROOT/frontend" && pnpm test -- --run ) && ok "frontend tests" || fail "frontend tests"

  step "Frontend: production build"
  ( cd "$ROOT/frontend" && pnpm build ) && ok "frontend build" || fail "frontend build"
else
  printf '\033[1;33m↷ frontend skipped\033[0m\n'
fi

step "Live API smoke (skipped when no server is running)"
( cd "$ROOT" && "$PY" "$ROOT/scripts/smoke_live.py" ) \
  && ok "live smoke" || fail "live smoke"

printf '\n'
if [[ $FAILED -eq 0 ]]; then
  printf '\033[1;32m════ ALL CHECKS PASSED ════\033[0m\n'
  exit 0
else
  printf '\033[1;31m════ CHECKS FAILED ════\033[0m\n'
  exit 1
fi
