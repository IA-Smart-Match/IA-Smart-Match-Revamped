# Shared by the 323 pre-flight scripts. Sourced, not run. READ-ONLY: GET only.
# DRAFT — needs Danny decision. Nothing here is decided.
# Usage of every script:  NN-name.sh --base-url URL [--execute] [...]
# Without --execute: prints the requests it WOULD make, sends nothing.

EXECUTE=0
BASE_URL=""
EXTRA=()

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --execute) EXECUTE=1 ;;
      --base-url) shift; BASE_URL="${1:-}" ;;
      *) EXTRA+=("$1") ;;
    esac
    shift || true
  done
  # No default host on purpose: the caller must name the target.
  [ -n "$BASE_URL" ] || { echo "error: --base-url URL is required (no default)" >&2; exit 2; }
  BASE_URL="${BASE_URL%/}"
  case "$BASE_URL" in http://*|https://*) ;; *) echo "error: --base-url must start with http:// or https://" >&2; exit 2 ;; esac
}

# need_cookie: instructor GET routes need the session cookie. Value comes from
# the environment as the full "name=value" pair; never printed, never in code.
need_cookie() {
  if [ "$EXECUTE" = 1 ] && [ -z "${EXERCISE_INSTRUCTOR_COOKIE:-}" ]; then
    echo "error: --execute needs EXERCISE_INSTRUCTOR_COOKIE (name=value) in the environment" >&2
    exit 2
  fi
}

# get PATH [auth]: GET only. Dry-run prints the request; execute sends it.
get() {
  local path="$1" auth="${2:-}"
  if [ "$EXECUTE" = 0 ]; then
    echo "DRY-RUN GET $BASE_URL$path${auth:+  (with instructor cookie)}"
    return 0
  fi
  if [ -n "$auth" ]; then
    curl -sS --fail-with-body -X GET -H "Cookie: $EXERCISE_INSTRUCTOR_COOKIE" "$BASE_URL$path"
  else
    curl -sS --fail-with-body -X GET "$BASE_URL$path"
  fi
  echo
}
