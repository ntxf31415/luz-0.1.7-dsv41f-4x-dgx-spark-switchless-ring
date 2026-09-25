#!/usr/bin/env bash
# w4-e1-measure.sh <tag> —— Engram 缓存臂量具：DE 子集 + 570K 冷 prefill 期间的内存地板采样。
set -uo pipefail
cd "$HOME/luz028"
TAG="${1:?usage: w4-e1-measure.sh <tag>}"
LOG="logs-tp4/w4-e1-$TAG.log"; exec > "$LOG" 2>&1
echo "=== w4-e1 $TAG start $(date -Is) ==="
docker exec dsv41-head env | grep -E '^DSV41_CACHE_GIB=|^DSV41_CACHE_WAYS='

echo "--- [1/2] DE 子集 ---"
"$HOME/luz028/site/tools/w34-de-subset.sh" "$TAG"

echo "--- [2/2] 570K 冷 prefill + MemAvailable 地板 ---"
docker cp scripts/verify/prefill_distinct.py dsv41-head:/tmp/prefill_distinct.py >/dev/null
( while true; do
    a=$(awk '/MemAvailable/{print $2}' /proc/meminfo); echo "$(date +%H:%M:%S) $a"; sleep 5
  done > "/tmp/mem-$TAG.log" ) &
MP=$!
docker exec dsv41-head python3 /tmp/prefill_distinct.py 570000 919 2>&1 | tail -3
kill $MP 2>/dev/null
echo "--- MemAvailable 采样（kB，含最低点） ---"
sort -k2 -n "/tmp/mem-$TAG.log" | head -3
echo "总采样数: $(wc -l < /tmp/mem-$TAG.log)"
echo "=== w4-e1 $TAG done $(date -Is) ==="
