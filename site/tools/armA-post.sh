#!/bin/bash
# armA-post.sh -- after the arm A chain: re-run gsm8k with the real key, then the PDI N=8 probe.
set -uo pipefail
cd "$HOME/luz017"
export MODEL=deepseek-v4.1-flash
KEY="$(cat state-tp4/api-key)"
LOG="logs-tp4/armA-post.log"
exec > "$LOG" 2>&1
echo "=== armA-post start $(date -Is) ==="
echo "--- waiting for armA-024.sh chain ---"
for i in $(seq 1 900); do
  pgrep -f "armA-024.sh" >/dev/null 2>&1 || break
  sleep 20
done
echo "--- chain finished; tail of chain log ---"
CH=$(ls -t logs-tp4/armA-luz024-A-*.log | head -1)
TA=$(echo "$CH" | sed "s/.*armA-//; s/\.log//")
grep -E "DE exit|PR b1 exit|PR b2 exit|PR b3 exit|PR merge exit|armA done" "$CH" | tail -6

echo "--- [A1] gsm8k RERUN with real key ---"
mkdir -p "bench-results/arms/$TA"
python3 bench/gsm8k_dsv41.py --base http://127.0.0.1:8899 --api-key "$KEY" \
  --out-raw "bench-results/arms/$TA/gsm8k.raw.jsonl" \
  --out-summary "bench-results/arms/$TA/gsm8k.summary.json"
echo "gsm8k rerun exit=$?"

echo "--- [A2] PDI storm probe, N=8 arm ---"
python3 scripts/verify/pdi-storm-probe.py --label pdi8-024
echo "=== armA-post done $(date -Is) tag=$TA ==="
