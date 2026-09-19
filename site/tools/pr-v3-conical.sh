#!/usr/bin/env bash
# pr-v3-conical.sh — PR-v3 口径 + 本站 §1.3 锥形网格（24 格）一键跑 + 合并 + 渲染。
#
# 口径（SD-1 PR-v3，上游 70a1d02 现行版；v2 表已作废不得引用）：
#   max_new_tokens = 1     → 纯 prefill，无 decode 尾巴
#   每请求唯一 nonce        → radix 永不命中
#   每格之间 POST /flush_cache（失败即中止，不静默继续）
#   总吞吐 = Σ(成功流 prompt token) ÷ 墙钟(放行第一流 → 最后一流结束)
#
# 网格（锥形，不是笛卡尔积 ⇒ 分 3 批，跑完用 merge_pr_v3_batches.py 合并）：
#   b1  512 / 2048 / 8192 / 32768  × C1,2,4,8,16     20 格
#   b2  131072                     × C1,2,4           3 格
#   b3  524288                     × C1              1 格
#
# 用法： pr-v3-conical.sh <label>
# 前置： harness 已在 ~/luz017/state-tp4/sdbench/，且引擎 chunked-prefill-size = 4096。
set -uo pipefail

LABEL="${1:?usage: pr-v3-conical.sh <label>}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HOME/luz017"
SB="$ROOT/state-tp4/sdbench"
ARCH="$ROOT/state-tp4/bench-results/luz017-sd1/pr-v3-$LABEL"
mkdir -p "$ARCH/batches" "$ARCH/raw"
exec > >(tee -a "$ARCH/run.log") 2>&1

echo "=== PR-v3 锥形 24 格 · $LABEL @ $(date '+%F %T %Z') ==="

# --- 前置①：引擎必须真空闲。白天有真实流量，非空闲就拒绝开跑（纪律 §6.1）
idle=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics \
        | grep -E '^sglang:num_(running|queue)_reqs' | awk '{s+=$2} END{print s+0}')
echo "--- 空闲检查 running+queue = $idle"
[ "$idle" = "0" ] || { echo "!! 引擎非空闲，拒绝开跑"; exit 1; }

# --- 前置②：CHUNKED_PREFILL_SIZE 必须等于 v3 的 CHUNK=4096，否则渲染器的准入律预测是错的
echo "--- 引擎实际 launch 参数"
docker exec dsv41-head sh -c \
  'ps aux | grep -oE "\-\-chunked-prefill-size [0-9]+|\-\-context-length [0-9]+|\-\-max-running-requests [0-9]+|\-\-mem-fraction-static [0-9.]+"' \
  | sort -u | sed 's/^/    /'
chunk=$(docker exec dsv41-head sh -c \
  'ps aux | grep -oE "\-\-chunked-prefill-size [0-9]+"' | grep -oE '[0-9]+' | head -1)
[ "$chunk" = "4096" ] || { echo "!! chunked-prefill-size=$chunk ≠ 4096，与 v3 harness 不一致，停"; exit 1; }

run_batch() {  # $1=批次名 $2=SIZES $3=CONCS
  local name="$1" sizes="$2" concs="$3"
  echo "--- 批 $name : SIZES=$sizes CONCS=$concs @ $(date '+%T')"
  docker exec -e SIZES="$sizes" -e CONCS="$concs" -e WAVES=1 \
    -e OUT_DIR="/state/bench-results/luz017-sd1/pr-v3-$LABEL/batches/$name" \
    -w /state/sdbench dsv41-head python3 /state/sdbench/pr_matrix_v3.py 2>&1 | tail -2
  local n
  n=$(ls "$ARCH/batches/$name"/*-c*-w0.json 2>/dev/null | wc -l | tr -d ' ')
  echo "    批 $name 完成：$n 个逐流文件 @ $(date '+%T')"
  [ "$n" -gt 0 ] || { echo "!! 批 $name 无产物，停"; exit 1; }
}

run_batch b1 "512,2048,8192,32768" "1,2,4,8,16"
run_batch b2 "131072"              "1,2,4"
run_batch b3 "524288"              "1"

# --- 合并（锥形网格分批发跑，summary.json 是每批重写的，必须合并）
echo "--- 合并批次 @ $(date '+%T')"
python3 "$SELF_DIR/merge_pr_v3_batches.py" --out "$ARCH" --expect 24 \
  "$ARCH/batches/b1" "$ARCH/batches/b2" "$ARCH/batches/b3" || exit 1

# --- 并发真伪：逐流首包时刻聚类（ttft_overlap_peak 在 MAXNEW=1 下退化，不可用）
echo "--- 并发真伪复核（聚类，非计数器）"
python3 "$SB/pr_v3_concurrency.py" "$ARCH/raw" > "$ARCH/CONCURRENCY.md" 2>&1
tail -6 "$ARCH/CONCURRENCY.md"

# --- 渲染两张表
echo "--- 渲染表"
python3 "$SB/render_pr_v3_tables.py" "$ARCH" > "$ARCH/TABLE.md" 2>/dev/null
head -12 "$ARCH/TABLE.md"

echo "=== 完成 @ $(date '+%F %T %Z') ==="
echo "产物： $ARCH (summary.json / TABLE.md / CONCURRENCY.md / raw/)"
