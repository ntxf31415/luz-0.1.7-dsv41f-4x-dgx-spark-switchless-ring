#!/usr/bin/env bash
# canonicalize_autotune_cache.sh — 让四个 rank 的 autotune 缓存内容逐字节一致。
#
# 为什么必须一致（2026-09-19 从源码定位）：
#   sglang/srt/model_executor/runner/flashinfer_autotune.py 里的
#   `_drop_diverged_autotune_cache()` 会把四个 rank 各自缓存文件的摘要
#   （sha256{文件内容, 环境}）all_gather，**只要不一致就 unlink 掉缓存、全部重调**。
#   而调优是计时的 ⇒ tactic 每次 boot 重新抽签，且永不收敛。
#
#   镜像自带的那份缓存只含 sparse_mla、**不含 fused-MoE 的 80 个形状** ⇒ 缺形状就必须调
#   ⇒ 每个 rank 各写各的 ⇒ 下个 boot 摘要不一致 ⇒ 全删重调。这是一个自我维持的循环。
#
# 本脚本的做法：以 head（rank0）的内容为规范，按字节一致地写到四台各自同名 rank 文件。
# 四份一致 + 形状齐全 ⇒ 缓存真正命中 ⇒ 不再重调 ⇒ tactic 被钉住。
#
# 前置：start.sh 的生产模式已挂载 ~/.cache/sglang/flashinfer/autotune（否则写不进容器）。
# 用法： canon_autotune_cache.sh            # 采集 + 分发 + 逐机校验
set -uo pipefail

IMG=dsv41-sglang-optimized:v7
CACHE=/home/spark/.cache/sglang/flashinfer/autotune
VER=0.6.18
ARCH=sm121
KEYS="3791e5b7aa102b24 85711ef344e18516 a4bba847bf039e87 f72f37b0801895b7"
# rank 0..3 对应的主机（与 .env.tp4 的 WORKER_IPS 顺序一致）
NODES=(192.168.50.55 192.168.50.56 192.168.50.58 192.168.50.57)
STAGE=/tmp/autotune-canon

echo "=== ① 采集 head(rank0) 的规范内容 ==="
rm -rf "$STAGE"; mkdir -p "$STAGE"
docker run --rm -v "$CACHE:/hc:ro" -v "$STAGE:/stage" --entrypoint sh "$IMG" -c "
  for k in $KEYS; do
    f=/hc/$VER/$ARCH/\$k/rank_tp0_pp0_dp0.json
    if [ -f \"\$f\" ]; then cp \"\$f\" /stage/\$k.json; printf '  staged %-20s %s bytes\n' \"\$k\" \"\$(wc -c < /stage/\$k.json)\"; else echo \"  (rank0 无 \$k，跳过)\"; fi
  done"
staged=$(ls "$STAGE"/*.json 2>/dev/null | wc -l)
[ "$staged" -gt 0 ] || { echo "!! 没采到任何规范文件，停"; exit 1; }
echo "  共 $staged 个 key"

echo "=== ② 分发到四台（各写自己的 rank 文件名）==="
idx=0
for ip in "${NODES[@]}"; do
  rank=$idx
  printf "  rank%d @ %-16s " "$rank" "$ip"
  if [ "$ip" = "192.168.50.55" ]; then
    # 本机：直接从 STAGE 装
    docker run --rm -v "$CACHE:/hc" -v "$STAGE:/stage:ro" --entrypoint sh "$IMG" -c "
      n=0; for f in /stage/*.json; do k=\$(basename \$f .json)
        d=/hc/$VER/$ARCH/\$k; mkdir -p \$d
        cp \$f \$d/rank_tp${rank}_pp0_dp0.json && n=\$((n+1)); done; echo \"装 \$n 个\""
  else
    scp -q -o BatchMode=yes "$STAGE"/*.json "spark@$ip:/tmp/" 2>/dev/null || { echo "scp 失败"; idx=$((idx+1)); continue; }
    ssh -o BatchMode=yes -o ConnectTimeout=8 "spark@$ip" "docker run --rm -v $CACHE:/hc -v /tmp:/stage:ro --entrypoint sh $IMG -c \"
      n=0; for f in /stage/*.json; do k=\\\$(basename \\\$f .json)
        d=/hc/$VER/$ARCH/\\\$k; mkdir -p \\\$d
        cp \\\$f \\\$d/rank_tp${rank}_pp0_dp0.json && n=\\\$((n+1)); done; echo \\\"装 \\\$n 个\\\"\"" 2>&1 | tail -1
  fi
  idx=$((idx+1))
done

echo "=== ③ 逐机校验：同一 key 的四份内容哈希应完全相同 ==="
for k in $KEYS; do
  echo "  --- key $k"
  idx=0
  for ip in "${NODES[@]}"; do
    printf "      rank%d @ %-16s " "$idx" "$ip"
    if [ "$ip" = "192.168.50.55" ]; then
      docker run --rm -v "$CACHE:/hc:ro" --entrypoint sh "$IMG" -c "sha256sum /hc/$VER/$ARCH/$k/rank_tp${idx}_pp0_dp0.json 2>/dev/null | cut -c1-32" 2>/dev/null || echo "(缺)"
    else
      ssh -o BatchMode=yes -o ConnectTimeout=8 "spark@$ip" "docker run --rm -v $CACHE:/hc:ro --entrypoint sh $IMG -c \"sha256sum /hc/$VER/$ARCH/$k/rank_tp${idx}_pp0_dp0.json 2>/dev/null | cut -c1-32\"" 2>&1 | tail -1
    fi
    idx=$((idx+1))
  done
done
echo "=== 完成 ==="
