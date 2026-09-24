#!/bin/bash
set -uo pipefail
cd "$HOME/luz017"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="pr2"
LOG="logs-tp4/arm-$TAG.log"
exec > "$LOG" 2>&1
echo "=== arm $TAG start $(date -Is) ==="
echo "--- [1] gate --full ---"
./start-tp4.sh gate --full 2>&1 | tail -12
echo "--- [2] gsm8k ---"
mkdir -p "bench-results/arms/$TAG"
python3 bench/gsm8k_dsv41.py --base http://127.0.0.1:8899 --api-key "$API_KEY" \
  --out-raw "bench-results/arms/$TAG/gsm8k.raw.jsonl" --out-summary "bench-results/arms/$TAG/gsm8k.summary.json"
echo "gsm8k exit=$?"
echo "--- [3] PR-v3 24 cells ---"
docker cp state-tp4/sdbench/pr_matrix_v3.py dsv41-head:/state/sdbench/pr_matrix_v3.py >/dev/null
CH=$(grep -oP '(?<=^CHUNKED_PREFILL_SIZE=).*' .env.tp4)
for spec in "b1|512,2048,8192,32768|1,2,4,8,16" "b2|131072|1,2,4" "b3|524288|1"; do
  IFS="|" read -r bn sz cc <<< "$spec"
  docker exec -e OUT_DIR="/state/bench-results/pr-$TAG-$bn" -e RUN_TAG="$TAG" -e SIZES="$sz" -e CONCS="$cc" \
    -e WAVES=1 -e MAXNEW=1 -e REQUEST_TIMEOUT=7200 -e CHUNKED_PREFILL_SIZE="$CH" \
    dsv41-head python3 /state/sdbench/pr_matrix_v3.py
  echo "PR $bn exit=$?"
done
python3 scripts/merge_pr_v3_batches.py --out "state-tp4/bench-results/pr-$TAG" --expect 24 \
  "state-tp4/bench-results/pr-$TAG-b1" "state-tp4/bench-results/pr-$TAG-b2" "state-tp4/bench-results/pr-$TAG-b3"
echo "merge exit=$?"
echo "=== arm $TAG done $(date -Is) ==="
