#!/usr/bin/env bash
# stage0_step1.sh — 阶段0 步 1：用**同一把尺**测本站单流，与 knapcio 公布值对表。
#
# 为什么这样写：阶段0 的全部意义是"同一把尺"，所以**不重写提示词/协议**，直接调既有量具
# `site/tools/prose_bench_sparkdash.py`（逐行复刻 sparkDash DecodeBench），再补一件它没有的事
# —— 从引擎 `Decode batch` 行取**步时 step_ms**（跨栈最稳的尺，见 P0.34 的方法）。
#
# 背景与判据：08-研究分析/knapcio-TP4-profile评估-20260925 §九
#   它公布 prose c1 86.4–87.7 / code c1 122.6–124.8；本站台账 散文 B 54.3（**同尺**）
#   它自报步时 prose 32.4–33.6 ms / code 38.9–39.4 ms
#   判据：散文 ≥80 ⇒ 54.3 是旧配置/旧口径产物 ⇒ 阶段0 结束、不切栈
#         散文 ~55 ⇒ 差距真实 ⇒ 进步 2（起它的栈做双向对照）
#
# 用法：  ./stage0_step1.sh [轮数] [容器名]        # 默认 5 轮、dsv41-head
# 前置：  引擎必须空闲 —— 建议由守门器启动，本脚本不自己等：
#         site/tools/wait-idle-then.sh 300 bash site/tools/stage0_step1.sh
set -uo pipefail

ROUNDS="${1:-5}"
CONTAINER="${2:-dsv41-head}"
ROOT="$HOME/luz028"
RULER="$ROOT/site/tools/prose_bench_sparkdash.py"
KEY="$(cat "$ROOT/state-tp4/api-key" 2>/dev/null || echo Dgxdual)"
export MODEL="${MODEL:-deepseek-v4.1-flash}" API_KEY="$KEY" URL="${URL:-http://127.0.0.1:8899/v1}"
export MAX_TOKENS="${MAX_TOKENS:-256}"     # 与 knapcio README 同档（其值在此档测得）
export ROUNDS="$ROUNDS"

echo "=== 阶段0 步1 === $(date '+%F %T')"
echo "尺 = $RULER（sparkDash DecodeBench 协议 · MAX_TOKENS=$MAX_TOKENS · 轮数=$ROUNDS）"

B="$(curl -s --max-time 5 http://127.0.0.1:8899/metrics 2>/dev/null \
     | grep -E '^sglang:num_(running|queue)_reqs' | awk '{s+=$2} END{print s+0}')"
[ "$B" = "0" ] || echo "⚠️ 引擎非空闲（running+queue=$B）—— 数字会偏低，建议用 wait-idle-then.sh 守门"

LOG="/tmp/stage0-prose-$(date +%H%M%S).log"
python3 "$RULER" 2>&1 | tee "$LOG"
MEDLINE="$(grep -E '^MEDIAN decode=' "$LOG" | tail -1)"
MED="$(echo "$MEDLINE" | grep -oE 'decode=[0-9.]+' | cut -d= -f2)"

echo
echo "=== 引擎侧步时（最近 600 s 的 Decode batch 行） ==="
docker logs --since 600s "$CONTAINER" 2>&1 | grep 'Decode batch' > /tmp/stage0-dec.log || true
python3 - <<'PY'
import re, statistics
rows = []
for line in open('/tmp/stage0-dec.log', encoding='utf-8', errors='replace'):
    a = re.search(r'accept len: ([0-9.]+)', line)
    g = re.search(r'gen throughput \(token/s\): ([0-9.]+)', line)
    f = re.search(r'#full token: (\d+)', line)
    if a and g and float(g.group(1)) > 0:
        acc, tps = float(a.group(1)), float(g.group(1))
        rows.append((acc / tps * 1000.0, acc, int(f.group(1)) if f else None))
if not rows:
    print('（窗口内没有 Decode batch 行）')
else:
    print(f'n={len(rows)}  中位 step_ms = {statistics.median(r[0] for r in rows):.2f} ms'
          f'  中位 accept_len = {statistics.median(r[1] for r in rows):.3f}'
          f'  中位 #full = {statistics.median(r[2] for r in rows if r[2]) or 0:.0f}')
PY

echo
echo "=== 对照与判据 ==="
echo "  散文 本站 ${MEDLINE:-（未取到）}"
echo "        它公布 86.4–87.7（多轮）· 45 个多样提示均值 58.36"
echo "  它自报步时 prose 32.4–33.6 ms / code 38.9–39.4 ms（用上面的中位步时直接比）"
echo
echo "  判据：散文 ≥80 ⇒ 54.3 是旧配置/旧口径产物 ⇒ **阶段0 结束、不切栈**"
echo "       散文 ~55 ⇒ 差距真实 ⇒ 进步 2（起它的栈做双向对照）"
echo
echo "⚠️ 引用前核对：采样窗口内无外来流量（面板/NAS 经 8888 打进来）· 引擎全程空闲。"
echo "   原始日志：$LOG"
