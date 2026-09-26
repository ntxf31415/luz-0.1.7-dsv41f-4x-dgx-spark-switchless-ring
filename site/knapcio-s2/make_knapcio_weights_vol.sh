#!/usr/bin/env bash
# 为 knapcio launcher 准备本地权重卷 dsv41-weights（NFS_SHARE=0 路径）。
# 它要求该卷在每台机上是"本地"的；我们用 bind driver 指到本机权重目录。
# 幂等；已存在即跳过。回滚：docker volume rm dsv41-weights
set -uo pipefail
W=${1:-/home/spark/models/DeepSeek-V4.1-Flash}
if ! [ -d "$W" ]; then echo "!! 权重目录不存在: $W"; exit 1; fi
n=$(ls "$W" 2>/dev/null | wc -l)
if docker volume inspect dsv41-weights >/dev/null 2>&1; then
  echo "已存在 dsv41-weights（跳过）"
else
  docker volume create --driver local \
    --opt type=none --opt device="$W" --opt o=bind dsv41-weights >/dev/null \
    && echo "已创建 dsv41-weights -> $W"
fi
echo "  本机 $(hostname): 权重分片 $n 个"
