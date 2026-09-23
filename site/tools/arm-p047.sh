#!/bin/bash
# arm-p047.sh <tag> [fprint] -- DE 20 cells + long-context decode probe + PR-v3 subset + perf-gate.
set -uo pipefail
cd "$HOME/luz017"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="$1"; DOFP="${2:-}"
LOG="logs-tp4/arm-$TAG.log"
exec > "$LOG" 2>&1
echo "=== arm $TAG start $(date -Is) ==="
echo "--- active mounts ---"; grep -o 'site-patches/[^:"]*' start.sh | sort -u

if [ "$DOFP" = "fprint" ]; then
  echo "--- [0] fingerprint ---"
  python3 scripts/verify/fingerprint.py 2>&1 | tail -2
fi

echo "--- [1] DE 20 cells ---"
docker cp state-tp4/sdbench/de_matrix_v3.py dsv41-head:/state/sdbench/de_matrix_v3.py >/dev/null 2>&1
docker exec -e OUT_DIR="/state/bench-results/de-$TAG" -e RUN_TAG="$TAG" \
  -e TYPES=structured,prose,code,json -e CONCURRENCIES=1,2,4,8,16 -e WAVES=3 -e MAXTOK=2048 \
  dsv41-head python3 /state/sdbench/de_matrix_v3.py
echo "DE exit=$?"

echo "--- [2] long-context decode probe ---"
TARGETS=8000,100000,200000 ROUNDS=3 timeout 1800 python3 scripts/verify/longctx-decode-probe.py 2>&1 | tail -5

echo "--- [3] PR-v3 subset ---"
docker cp state-tp4/sdbench/pr_matrix_v3.py dsv41-head:/state/sdbench/pr_matrix_v3.py >/dev/null 2>&1
CH=$(grep -oP '(?<=^CHUNKED_PREFILL_SIZE=).*' .env.tp4)
for spec in "a|32768|1" "b|131072|1"; do
  IFS="|" read -r bn sz cc <<< "$spec"
  docker exec -e OUT_DIR="/state/bench-results/pr-$TAG-$bn" -e RUN_TAG="$TAG" -e SIZES="$sz" -e CONCS="$cc" \
    -e WAVES=1 -e MAXNEW=1 -e REQUEST_TIMEOUT=7200 -e CHUNKED_PREFILL_SIZE="$CH" \
    dsv41-head python3 /state/sdbench/pr_matrix_v3.py
  echo "PR $bn exit=$?"
done
python3 scripts/merge_pr_v3_batches.py --out "state-tp4/bench-results/pr-$TAG" --expect 2 \
  "state-tp4/bench-results/pr-$TAG-a" "state-tp4/bench-results/pr-$TAG-b"
echo "merge exit=$?"

echo "--- [4] perf-gate (boot-state marker) ---"
bash scripts/perf-gate.sh >/dev/null 2>&1
python3 -c "import json;d=json.load(open('state-tp4/perf-gate.json'));print({k:d[k] for k in ['ts','verdict','probe_D_8K','probe_D_100K','probe_PR_131072_C1']})"
echo "=== arm $TAG done $(date -Is) ==="
