#!/usr/bin/env bash
# DRAFT — needs Danny decision. Compares the live data-file checksum with a local file
# (runbook step 3.3). Route: GET /v1/exercise/instructor/datasets
# (services/api/smartmatch_api/routers/exercise_instructor.py:167). Needs instructor cookie.
# Extra arg: path to Ann's workbook (the file you believe is live).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"
parse_args "$@"
FILE="${EXTRA[0]:-}"
[ -n "$FILE" ] || { echo "error: pass the workbook path as a final argument" >&2; exit 2; }
[ -r "$FILE" ] || { echo "error: cannot read $FILE" >&2; exit 2; }
need_cookie
LOCAL="$(sha256sum "$FILE" | cut -d' ' -f1)"
echo "local sha256: $LOCAL"
if [ "$EXECUTE" = 0 ]; then
  get /v1/exercise/instructor/datasets auth
  echo "DRY-RUN would then check that one row's checksum equals the local sha256 (row_count 300, event_count 12)"
  exit 0
fi
OUT="$(get /v1/exercise/instructor/datasets auth)"
echo "$OUT"
if printf '%s' "$OUT" | grep -q "$LOCAL"; then echo "PASS: a dataset row carries the local checksum"; else echo "FAIL: no row matches the local checksum" >&2; exit 1; fi
