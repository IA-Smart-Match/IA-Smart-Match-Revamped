#!/usr/bin/env bash
# DRAFT — needs Danny decision. Records the /api/health release (runbook step 2.1 / 7).
# Route: services/api/smartmatch_api/main.py:760 (GET /api/health). Public, no cookie.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"
parse_args "$@"
echo "# release check at $(date -u +%Y-%m-%dT%H:%M:%SZ) — compare with the SHA in the written go-ahead"
get /api/health
