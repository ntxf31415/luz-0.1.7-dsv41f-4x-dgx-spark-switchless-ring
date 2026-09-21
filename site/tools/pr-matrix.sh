#!/usr/bin/env bash
# pr-matrix.sh — 用上游的 benchmarks/matrix.py 跑 PR（prompt-rate）矩阵。
# 口径：矩阵的「有效 prefill = size × N / max(first_token_s)」——**含排队**，
#       与口径 D（prefill_distinct 的 prompt_tokens/(t_first−t0)）**不是同一个量**，
#       跨口径不可比（见基准总表 §五）。本脚本产出的记为口径 **PR-matrix**。
# 用法： pr-matrix.sh <label> [sizes] [concurrencies]
set -uo pipefail

LABEL="${1:?usage: pr-matrix.sh <label> [sizes] [concurrencies]}"
SIZES="${2:-8192,32768,131072}"
CONCS="${3:-1,2,4,8}"
ROOT="$HOME/luz017"
OUT="$ROOT/bench-results/pr/$LABEL"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1

echo "=== pr-matrix $LABEL @ $(date '+%F %T %Z') ==="
echo "--- sizes=$SIZES concs=$CONCS"
echo "--- 引擎: $(docker exec dsv41-head sh -c 'echo "ctx=$CONTEXT_LENGTH pool=$MAX_TOTAL_TOKENS reqs=$MAX_RUNNING_REQUESTS"' 2>/dev/null)"
curl -s --max-time 5 http://127.0.0.1:8899/metrics | grep -E '^sglang:num_(running|queue)_reqs' | sed 's/{[^}]*}//' | sed 's/^/    [idle] /'

# matrix.py 必须跑在容器内：它用模型自带的 tokenizer.json 与 encoding 模块造 token 精确的输入
docker cp "$ROOT/benchmarks/matrix.py" dsv41-head:/tmp/matrix.py
PKG=$(docker exec -e PREFILL_SIZES="$SIZES" -e CONCURRENCIES="$CONCS" \
        -w /tmp dsv41-head python3 /tmp/matrix.py | head -1)
echo "--- 容器内产物目录: $PKG"
[ -n "$PKG" ] || { echo "!! matrix.py 未产出目录，失败即停"; exit 1; }

# /state 就是宿主上的 state-tp4，直接把整包搬进 bench-results
cp -r "$ROOT/state-tp4/$(basename "$PKG")" "$OUT/" && echo "--- 已归档到 $OUT/"
cat "$OUT/$(basename "$PKG")/TABLE.md" 2>/dev/null

echo "=== pr-matrix $LABEL done @ $(date '+%F %T %Z') ==="
