#!/usr/bin/env bash
# install-cache.sh <rank> — 把 /tmp/autotune-canon/*.json 装成本机该 rank 的缓存文件。
# 由 canon_autotune_cache.sh 分发到四台后各自执行（避免在 ssh 里嵌多层引号）。
set -uo pipefail
RANK="${1:?usage: install-cache.sh <rank>}"
IMG=dsv41-sglang-optimized:v7
CACHE=/home/spark/.cache/sglang/flashinfer/autotune
VER=0.6.18; ARCH=sm121
docker run --rm -v "$CACHE:/hc" -v /tmp/atc:/stage:ro --entrypoint sh "$IMG" -c "
  n=0
  for f in /stage/*.json; do
    [ -f \"\$f\" ] || continue
    k=\$(basename \"\$f\" .json)
    d=/hc/$VER/$ARCH/\$k
    mkdir -p \"\$d\"
    cp \"\$f\" \"\$d/rank_tp${RANK}_pp0_dp0.json\" && n=\$((n+1))
  done
  echo \"rank${RANK}: 装入 \$n 个 key\""
