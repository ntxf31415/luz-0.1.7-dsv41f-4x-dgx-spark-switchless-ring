#!/bin/bash
# arm-chunk-lite.sh <tag> -- fingerprint + PR-v3 24 + long-档 D with memory sample.
set -uo pipefail
cd "$HOME/luz017"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="$1"
LOG="logs-tp4/arm-$TAG.log"
exec > "$LOG" 2>&1
echo "=== arm $TAG start $(date -Is) ==="
grep -E "^CHUNKED_PREFILL_SIZE=|^EXTRA_DOCKER_ENV=" .env.tp4 | cut -c1-300
echo "--- [1] fingerprint ---"
python3 scripts/verify/fingerprint.py 2>&1 | tail -2
echo "--- [2] PR-v3 24 cells ---"
docker cp state-tp4/sdbench/pr_matrix_v3.py dsv41-head:/state/sdbench/pr_matrix_v3.py
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
echo "--- [3] long-档 D 563000 + memory sample ---"
( for i in $(seq 1 400); do awk -v t="$(date +%s)" '/MemAvailable/{printf "%s %s\n", t, $2}' /proc/meminfo; sleep 1.5; done > state-tp4/mem-$TAG.log ) & SAMP=$!
python3 scripts/verify/prefill_distinct.py 563000 919
echo "long exit=$?"
kill $SAMP 2>/dev/null
awk '{if($2<min||min==0)min=$2}END{printf "mem floor = %.2f GB\n", min/1048576}' state-tp4/mem-$TAG.log
echo "=== arm $TAG done $(date -Is) ==="
