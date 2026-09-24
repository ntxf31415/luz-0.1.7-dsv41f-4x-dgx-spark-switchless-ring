#!/bin/bash
set -uo pipefail
cd "$HOME/luz017"
TAG="$1"
LOG="logs-tp4/arm-$TAG.log"
exec > "$LOG" 2>&1
echo "=== $TAG start $(date -Is) ==="
docker cp state-tp4/sdbench/pr_matrix_v3.py dsv41-head:/state/sdbench/pr_matrix_v3.py >/dev/null
CH=$(grep -oP '(?<=^CHUNKED_PREFILL_SIZE=).*' .env.tp4)
for spec in "a|32768|1,2,4,8,16" "b|131072|1,2,4" "c|524288|1"; do
  IFS="|" read -r bn sz cc <<< "$spec"
  docker exec -e OUT_DIR="/state/bench-results/pr-$TAG-$bn" -e RUN_TAG="$TAG" -e SIZES="$sz" -e CONCS="$cc" \
    -e WAVES=1 -e MAXNEW=1 -e REQUEST_TIMEOUT=7200 -e CHUNKED_PREFILL_SIZE="$CH" \
    dsv41-head python3 /state/sdbench/pr_matrix_v3.py
  echo "PR $bn exit=$?"
done
python3 scripts/merge_pr_v3_batches.py --out "state-tp4/bench-results/pr-$TAG" --expect 9 \
  "state-tp4/bench-results/pr-$TAG-a" "state-tp4/bench-results/pr-$TAG-b" "state-tp4/bench-results/pr-$TAG-c"
echo "merge exit=$?"
echo "--- perf-gate (boot state marker) ---"
bash scripts/perf-gate.sh >/dev/null 2>&1
python3 -c "import json;d=json.load(open('state-tp4/perf-gate.json'));print({k:d[k] for k in ['ts','verdict','probe_D_8K','probe_D_100K','probe_PR_131072_C1']})"
echo "=== $TAG done $(date -Is) ==="
