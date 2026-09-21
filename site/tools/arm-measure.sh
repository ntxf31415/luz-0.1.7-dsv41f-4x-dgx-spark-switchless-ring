#!/bin/bash
# arm-measure.sh <tag> -- fingerprint + PR-v3 24 cells (conical, 3 batches + merge).
set -uo pipefail
cd "$HOME/luz017"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="$1"
LOG="logs-tp4/arm-$TAG.log"
exec > "$LOG" 2>&1
echo "=== arm $TAG start $(date -Is) ==="
echo "--- env in force ---"
grep -E "^CHUNKED_PREFILL_SIZE=|^EXTRA_DOCKER_ENV=" .env.tp4 | cut -c1-400
echo "--- fingerprint ---"
python3 scripts/verify/fingerprint.py 2>&1 | tail -2
mkdir -p "bench-results/arms/$TAG"
docker cp state-tp4/sdbench/pr_matrix_v3.py dsv41-head:/state/sdbench/pr_matrix_v3.py
B1="/state/bench-results/pr-$TAG-b1"; B2="/state/bench-results/pr-$TAG-b2"; B3="/state/bench-results/pr-$TAG-b3"
for spec in "b1|512,2048,8192,32768|1,2,4,8,16" "b2|131072|1,2,4" "b3|524288|1"; do
  IFS="|" read -r bn sz cc <<< "$spec"
  docker exec -e OUT_DIR="/state/bench-results/pr-$TAG-$bn" -e RUN_TAG="$TAG" -e SIZES="$sz" -e CONCS="$cc" \
    -e WAVES=1 -e MAXNEW=1 -e REQUEST_TIMEOUT=7200 -e CHUNKED_PREFILL_SIZE="$(grep -oP '(?<=^CHUNKED_PREFILL_SIZE=).*' .env.tp4)" \
    dsv41-head python3 /state/sdbench/pr_matrix_v3.py
  echo "PR $bn exit=$?"
done
python3 scripts/merge_pr_v3_batches.py --out "state-tp4/bench-results/pr-$TAG" --expect 24 \
  "state-tp4/bench-results/pr-$TAG-b1" "state-tp4/bench-results/pr-$TAG-b2" "state-tp4/bench-results/pr-$TAG-b3"
echo "merge exit=$?"
echo "=== arm $TAG done $(date -Is) ==="
