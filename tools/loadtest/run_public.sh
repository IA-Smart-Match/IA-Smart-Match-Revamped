#!/bin/bash
# run_public.sh <students> <label>  -- public-link load test (Plan C) with VM logs captured.
# Owner-run (the classifier blocks agents). Never prints the passcode or team codes.
#   REF=origin/feat/loadtest-connection-reuse tools/loadtest/run_public.sh 50 public-50b
# REF picks the tool version (default origin/main). WEB_CONTAINER overrides the web
# container name. A log capture that cannot start stops the run before any load is sent.
set -uo pipefail
N=$1; L=$2; OUT=/home/danny/sweep-recovery/oct23/vm-deploy-2026-10-22/$L; mkdir -p "$OUT"
REF=${REF:-origin/main}; WEB=${WEB_CONTAINER:-smartmatch-web-exercise-1}
T=/home/danny/worktrees/oct23-i-main; PY=/mnt/c/Users/DangT/Documents/GitHub/IA-Smart-Match-Revamped/.venv/bin/python
git -C "$T" fetch -q origin && git -C "$T" checkout -q --detach "$REF" || { echo "cannot check out $REF"; exit 1; }
git -C "$T" log -1 --format="tool %h %s" | tee "$OUT/meta.txt"
curl -s https://exercise.smartmatch.cloud/api/health | tee "$OUT/health.json"; echo
SSH="gcloud compute ssh smartmatch --zone us-west2-c --tunnel-through-iap --command"
# Printed into every log before following, so an empty capture shows what was there.
INV='echo "== docker ps"; sudo docker ps --format "{{.Names}}"; echo "== cloudflared units"; systemctl list-units "*cloudflared*" --no-legend; echo "=="'
$SSH 'for i in $(seq 500); do date -u +%T; vmstat 1 2 | tail -1; sudo docker stats --no-stream --format "{{.Name}} {{.CPUPerc}} {{.MemUsage}}" | grep -E "exercise|db"; ps -o pid,pcpu,rss,comm -C cloudflared --no-headers; sleep 3; done' > "$OUT/vm-sample.log" 2>&1 & SP=$!
$SSH 'sudo docker logs -f --since 1s smartmatch-api-exercise-1 2>&1 | grep -v -i passcode' > "$OUT/vm-api.log" 2>&1 & AP=$!
$SSH "$INV"'
if sudo docker ps --format "{{.Names}}" | grep -qx '"$WEB"'; then
  echo "capture: docker logs '"$WEB"'"; exec sudo docker logs -f --since 1s '"$WEB"' 2>&1
fi
echo "CAPTURE FAILED: no running container named '"$WEB"' (set WEB_CONTAINER from the list above)"; exit 3' > "$OUT/vm-web.log" 2>&1 & WP=$!
$SSH "$INV"'
U=$(systemctl list-units "*cloudflared*" --no-legend --plain | awk "{print \$1}" | head -1)
if [ -n "$U" ]; then echo "capture: journalctl -u $U"; exec sudo journalctl -u "$U" -f -n 0 --no-pager; fi
C=$(sudo docker ps --format "{{.Names}}" | grep cloudflared | head -1)
if [ -n "$C" ]; then echo "capture: docker logs $C"; exec sudo docker logs -f --since 1s "$C" 2>&1; fi
echo "CAPTURE FAILED: no cloudflared systemd unit and no cloudflared container"; exit 3' > "$OUT/vm-cloudflared.log" 2>&1 & CP=$!
sleep 25  # IAP ssh needs ~10-20 s; a capture that died by now never started
for f in api web cloudflared; do
  P=$AP; [ $f = web ] && P=$WP; [ $f = cloudflared ] && P=$CP
  if ! kill -0 "$P" 2>/dev/null || grep -q "CAPTURE FAILED" "$OUT/vm-$f.log"; then
    echo "!!!!! CAPTURE FAILED: vm-$f.log -- no load sent. Last lines:"; tail -20 "$OUT/vm-$f.log"
    kill $SP $AP $WP $CP 2>/dev/null; exit 2
  fi
  echo "capture ok: vm-$f.log ($(grep -m1 '^capture:' "$OUT/vm-$f.log" || echo following))"
done
export LOADTEST_INSTRUCTOR_PASSCODE="$(cat /home/danny/.oct23-instructor-passcode)"
[ -n "$LOADTEST_INSTRUCTOR_PASSCODE" ] && echo "passcode: present" || { echo "passcode: MISSING (run owner command 2)"; kill $SP $AP $WP $CP; exit 1; }
cd /tmp && "$PY" -u "$T/tools/loadtest/classroom_load.py" --base https://exercise.smartmatch.cloud \
  --i-own-this-public-host exercise.smartmatch.cloud --allow-any-release \
  --students "$N" --out "$OUT/run" --label "$L" > "$OUT/stdout.log" 2>&1; echo "load exit $?" | tee -a "$OUT/meta.txt"
unset LOADTEST_INSTRUCTOR_PASSCODE
kill $SP $AP $WP $CP 2>/dev/null; wait 2>/dev/null
grep -E "Correctness|FAIL|\| (API|page|unex|no 5|0 unex)" "$OUT/run/report.md" | head -30
sed -n '/^## Transport errors/,/^## Correctness/p' "$OUT/run/report.md" | head -14
