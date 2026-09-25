#!/usr/bin/env bash
# w4-e2-measure.sh <tag> —— 1M ctx 臂量具：指纹 + 900K 冷 needle（含内存地板）+ gate --full + DE 子集。
set -uo pipefail
cd "$HOME/luz028"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="${1:?usage: w4-e2-measure.sh <tag>}"
LOG="logs-tp4/w4-e2-$TAG.log"; exec > "$LOG" 2>&1
echo "=== w4-e2 $TAG start $(date -Is) ==="
docker exec dsv41-head env | grep -E '^CONTEXT_LENGTH=|^MAX_RUNNING_REQUESTS=|^MAX_TOTAL_TOKENS='

echo "--- [1/4] 指纹 ---"
python3 scripts/verify/fingerprint.py 2>&1 | tail -1

echo "--- [2/4] 900K 冷 needle + MemAvailable 地板（1M ctx 的判据） ---"
docker cp scripts/verify/prefill_distinct.py dsv41-head:/tmp/prefill_distinct.py >/dev/null
( while true; do awk '/MemAvailable/{print $2}' /proc/meminfo; sleep 5; done > "/tmp/mem-$TAG.log" ) &
MP=$!
docker exec dsv41-head python3 /tmp/prefill_distinct.py 900000 771 2>&1 | tail -3
kill $MP 2>/dev/null
echo "MemAvailable 最低三点（kB）:"; sort -n "/tmp/mem-$TAG.log" | head -3

echo "--- [3/4] gate --full ---"
./start-tp4.sh gate --full 2>&1 | tail -12

echo "--- [4/4] DE 子集 ---"
"$HOME/luz028/site/tools/w34-de-subset.sh" "$TAG"
echo "=== w4-e2 $TAG done $(date -Is) ==="
