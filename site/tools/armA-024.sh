#!/bin/bash
# armA-024.sh -- arm A chain: 0.2.4 + site autotune patch + PDI=8, our standard grid.
set -uo pipefail
cd "$HOME/luz017"
export API_KEY="$(cat state-tp4/api-key)"
export MODEL=deepseek-v4.1-flash
TAG="luz024-A-$(date +%Y%m%dT%H%M%S)"
LOG="logs-tp4/armA-$TAG.log"
exec > "$LOG" 2>&1
echo "=== armA start $(date -Is) tag=$TAG ==="

echo "--- waiting for gate --full to finish ---"
for i in $(seq 1 120); do
  grep -q "GATE_EXIT" logs-tp4/armA-gate-full.log 2>/dev/null && break
  sleep 20
done
echo "--- gate result ---"
grep -E "GATE_EXIT|PASS|FAIL|\[-\]" logs-tp4/armA-gate-full.log 2>/dev/null | tail -8

mkdir -p "bench-results/arms/$TAG"

echo "--- [1] fingerprint #2 (stability) ---"
python3 scripts/verify/fingerprint.py | tail -3

echo "--- [2] gsm8k (200q, 8-shot CoT) ---"
python3 bench/gsm8k_dsv41.py --base http://127.0.0.1:8899 \
  --out-raw "bench-results/arms/$TAG/gsm8k.raw.jsonl" \
  --out-summary "bench-results/arms/$TAG/gsm8k.summary.json"
echo "gsm8k exit=$?"

echo "--- [3] DE 20 cells ---"
docker cp benchmarks/de_matrix_v3.py dsv41-head:/state/sdbench/de_matrix_v3.py
docker exec -e OUT_DIR="/state/bench-results/de-$TAG" -e RUN_TAG="$TAG" \
  -e TYPES=structured,prose,code,json -e CONCURRENCIES=1,2,4,8,16 \
  -e WAVES=3 -e MAXTOK=2048 \
  dsv41-head python3 /state/sdbench/de_matrix_v3.py
echo "DE exit=$?"

echo "--- [4] PR 24 cells (conical, 3 batches + merge) ---"
docker cp state-tp4/sdbench/pr_matrix_v3.py dsv41-head:/state/sdbench/pr_matrix_v3.py
B1="/state/bench-results/pr-$TAG-b1"; B2="/state/bench-results/pr-$TAG-b2"; B3="/state/bench-results/pr-$TAG-b3"
docker exec -e OUT_DIR="$B1" -e RUN_TAG="$TAG" -e SIZES=512,2048,8192,32768 -e CONCS=1,2,4,8,16 \
  -e WAVES=1 -e MAXNEW=1 -e REQUEST_TIMEOUT=7200 -e CHUNKED_PREFILL_SIZE=4096 \
  dsv41-head python3 /state/sdbench/pr_matrix_v3.py; echo "PR b1 exit=$?"
docker exec -e OUT_DIR="$B2" -e RUN_TAG="$TAG" -e SIZES=131072 -e CONCS=1,2,4 \
  -e WAVES=1 -e MAXNEW=1 -e REQUEST_TIMEOUT=7200 -e CHUNKED_PREFILL_SIZE=4096 \
  dsv41-head python3 /state/sdbench/pr_matrix_v3.py; echo "PR b2 exit=$?"
docker exec -e OUT_DIR="$B3" -e RUN_TAG="$TAG" -e SIZES=524288 -e CONCS=1 \
  -e WAVES=1 -e MAXNEW=1 -e REQUEST_TIMEOUT=7200 -e CHUNKED_PREFILL_SIZE=4096 \
  dsv41-head python3 /state/sdbench/pr_matrix_v3.py; echo "PR b3 exit=$?"
python3 scripts/merge_pr_v3_batches.py --out "state-tp4/bench-results/pr-$TAG" --expect 24 \
  "state-tp4/bench-results/pr-$TAG-b1" "state-tp4/bench-results/pr-$TAG-b2" "state-tp4/bench-results/pr-$TAG-b3"
echo "PR merge exit=$?"

echo "=== armA done $(date -Is) tag=$TAG ==="
