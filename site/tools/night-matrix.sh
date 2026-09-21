#!/usr/bin/env bash
# night-matrix.sh — 按「4DGX-基准演进总表」要求，把本环境的矩阵一次跑齐。
# 口径说明：
#   B = sparkDash DecodeBench（主口径，散文与 DE 并发）
#   C = bench_tp（并发+TTFT）
#   D = prefill_distinct（长档 needle）
#   E = 墙钟
# 顺序即纪律：先指纹（改输出的一律作废）→ 散文 → 并发阶梯 → 长档 → 质量门禁。
set -uo pipefail

LABEL="${1:?usage: night-matrix.sh <label>}"
ROOT="$HOME/luz017"
KEY="$(cat "$ROOT/state-tp4/api-key")"
OUT="$ROOT/bench-results/matrix/$LABEL"
mkdir -p "$OUT"
export MODEL=deepseek-v4.1-flash
exec > >(tee -a "$OUT/run.log") 2>&1

echo "=== night-matrix $LABEL @ $(date '+%F %T %Z') ==="
echo "--- image: $(docker image inspect dsv41-sglang-optimized:v7 --format '{{.Id}}' 2>/dev/null)"
echo "--- engine: $(docker exec dsv41-head sh -c 'echo "ctx=$CONTEXT_LENGTH pool=$MAX_TOTAL_TOKENS reqs=$MAX_RUNNING_REQUESTS"' 2>/dev/null)"
echo "--- 取数前四机频率:"
for h in <HEAD_IP> <WORKER1_IP> <WORKER2_IP> <WORKER3_IP>; do
  printf '    %s ' "$h"
  if [ "$h" = "<HEAD_IP>" ]; then nvidia-smi --query-gpu=clocks.sm --format=csv,noheader
  else ssh -o BatchMode=yes -o ConnectTimeout=8 spark@"$h" "nvidia-smi --query-gpu=clocks.sm --format=csv,noheader"; fi
done

idle() {
  local r q
  r=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics | grep -m1 '^sglang:num_running_reqs' | sed 's/.*} //')
  q=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics | grep -m1 '^sglang:num_queue_reqs' | sed 's/.*} //')
  echo "    [idle] running=$r queue=$q"
}

echo "--- [1/6] 贪心指纹（改输出即作废）"
idle
URL=http://127.0.0.1:8899/v1/chat/completions API_KEY="$KEY" \
  python3 "$ROOT/scripts/verify/fingerprint.py" 2>&1 | tee "$OUT/fingerprint.txt"
echo "    → 二次复跑校验确定性"
URL=http://127.0.0.1:8899/v1/chat/completions API_KEY="$KEY" \
  python3 "$ROOT/scripts/verify/fingerprint.py" 2>&1 | tail -1 | tee "$OUT/fingerprint-repeat.txt"

echo "--- [2/6] 散文 B（sparkDash, n=9）"
idle
URL=http://127.0.0.1:8899/v1 API_KEY="$KEY" MAX_TOKENS=256 ROUNDS=9 \
  python3 "$ROOT/bench/prose_bench_sparkdash.py" 2>&1 | tee "$OUT/prose-B.txt"

echo "--- [3/6] 并发阶梯 c1..c16（口径 C，code）"
idle
python3 "$ROOT/bench/bench_tp.py" --base http://127.0.0.1:8899/v1 --model deepseek-v4.1-flash \
  --key "$KEY" --conc 1,2,4,6,8,12,16 --max-tokens 400 --prompt-type code 2>&1 | tee "$OUT/ladder-code-C.txt"

echo "--- [4/6] 长档 needle（口径 D）：100K / 200K / 470K"
idle
docker cp "$ROOT/scripts/verify/prefill_distinct.py" dsv41-head:/tmp/prefill_distinct.py
for T in 100000 200000 470000; do
  docker exec dsv41-head python3 /tmp/prefill_distinct.py "$T" 1 2>&1 | tee -a "$OUT/long-D.txt"
done

echo "--- [5/6] GSM8K（n=200, temp 0.6, 8-shot）"
idle
python3 "$ROOT/bench/gsm8k_dsv41.py" --base http://127.0.0.1:8899 --api-key "$KEY" \
  --out-raw "$OUT/gsm8k.raw.jsonl" --out-summary "$OUT/gsm8k.summary.json" 2>&1 \
  | tail -20 | tee "$OUT/gsm8k.txt"

echo "--- [6/6] 门禁全档"
idle
cd "$ROOT" && ENV_FILE=.env.tp4 ./start-tp4.sh gate --full 2>&1 | tee "$OUT/gate.txt"

echo "--- 取数后四机频率:"
for h in <HEAD_IP> <WORKER1_IP> <WORKER2_IP> <WORKER3_IP>; do
  printf '    %s ' "$h"
  if [ "$h" = "<HEAD_IP>" ]; then nvidia-smi --query-gpu=clocks.sm --format=csv,noheader
  else ssh -o BatchMode=yes -o ConnectTimeout=8 spark@"$h" "nvidia-smi --query-gpu=clocks.sm --format=csv,noheader"; fi
done

echo "=== night-matrix $LABEL done @ $(date '+%F %T %Z') ==="
