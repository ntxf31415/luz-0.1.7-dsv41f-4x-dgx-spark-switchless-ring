#!/usr/bin/env bash
# w2-matrix.sh <tag> — 窗口2：把 0.2.8 现役配置的全矩阵一次跑齐（总表 §一 0.2.8 行前置）。
# 顺序即纪律：指纹 → 散文B → DE20 → PR24 → 长档D（冷+needle）→ 快档门禁。
set -uo pipefail
cd "$HOME/luz028"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="${1:?usage: w2-matrix.sh <tag>}"
OUT="bench-results/matrix/$TAG"; mkdir -p "$OUT"
LOG="logs-tp4/w2-$TAG.log"; exec > "$LOG" 2>&1

idle() {
  local r q
  r=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics | grep -m1 '^sglang:num_running_reqs' | sed 's/.*} //')
  q=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics | grep -m1 '^sglang:num_queue_reqs' | sed 's/.*} //')
  echo "    [idle] running=$r queue=$q"
}

echo "=== w2-matrix $TAG start $(date -Is) ==="
echo "--- env in force ---"
grep -E "^CHUNKED_PREFILL_SIZE=|^MAX_RUNNING_REQUESTS=|^CONTEXT_LENGTH=|^MAX_TOTAL_TOKENS=|^MEM_FRACTION_STATIC=" .env.tp4
echo "--- image: $(docker image inspect dsv41-sglang-optimized:0.2.8 --format '{{.Id}}' 2>/dev/null)"

echo "--- [1/6] 贪心指纹 x2 ---"
idle
python3 scripts/verify/fingerprint.py 2>&1 | tail -1
python3 scripts/verify/fingerprint.py 2>&1 | tail -1

echo "--- [2/6] 散文 B（sparkDash, n=9, 256 tok） ---"
idle
URL=http://127.0.0.1:8899/v1 API_KEY="$API_KEY" MAX_TOKENS=256 ROUNDS=9 \
  python3 bench/prose_bench_sparkdash.py 2>&1 | tail -6

echo "--- [3/6] DE 20 格（SD-1） ---"
idle
docker cp benchmarks/de_matrix_v3.py dsv41-head:/state/sdbench/de_matrix_v3.py
docker exec -e OUT_DIR="/state/bench-results/de-$TAG" -e RUN_TAG="$TAG" \
  -e TYPES=structured,prose,code,json -e CONCURRENCIES=1,2,4,8,16 \
  -e WAVES=3 -e MAXTOK=2048 \
  dsv41-head python3 /state/sdbench/de_matrix_v3.py
echo "DE exit=$?"

echo "--- [4/6] PR 24 格（PR-v3 锥形 3 批 + merge） ---"
idle
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
echo "PR merge exit=$?"

echo "--- [5/6] 口径 D 长档（593K 冷 + 200K 冷，含 needle 判据） ---"
idle
docker cp scripts/verify/prefill_distinct.py dsv41-head:/tmp/prefill_distinct.py
docker exec dsv41-head python3 /tmp/prefill_distinct.py 593000 919 2>&1 | tail -6
docker exec dsv41-head python3 /tmp/prefill_distinct.py 200000 923 2>&1 | tail -5

echo "--- [6/6] 快档门禁 perf-gate ---"
idle
bash scripts/perf-gate.sh >/dev/null 2>&1
python3 -c "import json;d=json.load(open('state-tp4/perf-gate.json'));print({k:d[k] for k in ['ts','verdict','probe_D_8K','probe_D_100K','probe_PR_131072_C1']})"

echo "=== w2-matrix $TAG done $(date -Is) ==="
