#!/usr/bin/env bash
# ab-arm.sh — 轻量臂：用于配置 A/B。每臂约 10 分钟。
# 顺序即纪律：先指纹（改输出的一律作废，且必须两次一致）→ 散文 B → 并发阶梯。
set -uo pipefail

LABEL="${1:?usage: ab-arm.sh <label>}"
ROOT="$HOME/luz017"
KEY="$(cat "$ROOT/state-tp4/api-key")"
OUT="$ROOT/bench-results/arms/$LABEL"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1

echo "=== ab-arm $LABEL @ $(date '+%F %T %Z') ==="
echo "--- 形态: $(docker exec dsv41-head sh -c 'echo "ctx=$CONTEXT_LENGTH pool=$MAX_TOTAL_TOKENS reqs=$MAX_RUNNING_REQUESTS"' 2>/dev/null)"
echo "--- 关键开关:"
for v in SGLANG_DSV4_KV_LAYOUT DSV41_MOE_B12X DSV41_MXFP8_BACKEND DSV41_SHARED_PAD_K SGLANG_QW3_DSPARK_LAUNCH_PARAMS DSV41_SKIP_NONFINAL_DECODER; do
  printf '    %-40s ' "$v"
  docker exec dsv41-head printenv "$v" 2>/dev/null | head -1 || printf '(未设)\n'
done

idle() {
  local r q
  r=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics | grep -m1 '^sglang:num_running_reqs' | sed 's/.*} //')
  q=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics | grep -m1 '^sglang:num_queue_reqs' | sed 's/.*} //')
  echo "    [idle] running=$r queue=$q"
}

echo "--- [1/3] 指纹 ×2（必须一致，否则本臂作废）"
idle
URL=http://127.0.0.1:8899/v1/chat/completions API_KEY="$KEY" \
  python3 "$ROOT/scripts/verify/fingerprint.py" 2>&1 | tee "$OUT/fingerprint.txt"
URL=http://127.0.0.1:8899/v1/chat/completions API_KEY="$KEY" \
  python3 "$ROOT/scripts/verify/fingerprint.py" 2>&1 | tail -1 | tee "$OUT/fingerprint-repeat.txt"
a=$(tail -1 "$OUT/fingerprint.txt"); b=$(tail -1 "$OUT/fingerprint-repeat.txt")
[ "$a" = "$b" ] && echo "    ✓ 确定性 OK（$a）" || echo "    ✗ 两次不一致：$a vs $b —— 本臂作废"

echo "--- [2/3] 散文 B（sparkDash, n=9）"
idle
URL=http://127.0.0.1:8899/v1 API_KEY="$KEY" MAX_TOKENS=256 ROUNDS=9 \
  python3 "$ROOT/bench/prose_bench_sparkdash.py" 2>&1 | tee "$OUT/prose-B.txt"

echo "--- [3/3] 并发阶梯 c1/c4/c8/c16（口径 C, code）"
idle
python3 "$ROOT/bench/bench_tp.py" --base http://127.0.0.1:8899/v1 --model deepseek-v4.1-flash \
  --key "$KEY" --conc 1,4,8,16 --max-tokens 400 --prompt-type code 2>&1 | tee "$OUT/ladder-C.txt"

echo "=== ab-arm $LABEL done @ $(date '+%F %T %Z') ==="
