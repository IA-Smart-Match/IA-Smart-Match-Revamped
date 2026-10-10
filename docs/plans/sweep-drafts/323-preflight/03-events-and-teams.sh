#!/usr/bin/env bash
# DRAFT — needs Danny decision. Reads scope, event lock state and Teams 1-6 state
# (runbook steps 3.2, 3.4, 3.5). GET routes on main:
#   /v1/exercise                               exercise_public.py:118
#   /v1/exercise/instructor/events             exercise_instructor.py:366
#   /v1/exercise/instructor/workspaces         exercise_instructor.py:518
#   /v1/exercise/instructor/workspaces/{n}     exercise_instructor_detail.py:100
# Optional extra arg: output directory for before-*.json (default: print only).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"
parse_args "$@"
need_cookie
OUTDIR="${EXTRA[0]:-}"
snap() { # snap NAME PATH [auth]
  if [ "$EXECUTE" = 1 ] && [ -n "$OUTDIR" ]; then
    mkdir -p "$OUTDIR"; ( umask 077; get "$2" "${3:-}" | tee "$OUTDIR/$1.json" )
  else
    get "$2" "${3:-}"
  fi
}
snap scope /v1/exercise
snap events /v1/exercise/instructor/events auth
snap teams /v1/exercise/instructor/workspaces auth
for n in 1 2 3 4 5 6; do
  # A team that never entered is refused; that answer is its "before" (runbook 3.5).
  snap "team-$n" "/v1/exercise/instructor/workspaces/$n" auth || echo "team $n: refused or absent (record it)"
done
