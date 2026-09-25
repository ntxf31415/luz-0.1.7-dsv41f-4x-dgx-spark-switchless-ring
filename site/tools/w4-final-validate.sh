#!/usr/bin/env bash
# w4-final-validate.sh <tag> —— 采纳配置的终验：perf-gate + GSM8K×2 + 散文 B + 四机与自愈状态。
set -uo pipefail
cd "$HOME/luz028"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="${1:?usage: w4-final-validate.sh <tag>}"
LOG="logs-tp4/final-$TAG.log"; exec > "$LOG" 2>&1
echo "=== final validate $TAG start $(date -Is) ==="
echo "--- 生效配置 ---"
grep -E '^CONTEXT_LENGTH=|^MAX_RUNNING_REQUESTS=|^MAX_TOTAL_TOKENS=|^MEM_FRACTION_STATIC=|^CHUNKED_PREFILL_SIZE=' .env.tp4
docker exec dsv41-head env | grep -E '^DSV41_SKIP_NONFINAL_DECODER=|^DSV41_PREFILL_SHARE_TOKENS=|^SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION=|^DSV41_CACHE_GIB=|^DSV41_VERIFY_CAP=' || true

echo "--- [1/5] 指纹 ---"
python3 scripts/verify/fingerprint.py 2>&1 | tail -1

echo "--- [2/5] perf-gate ---"
bash scripts/perf-gate.sh >/dev/null 2>&1
python3 -c "import json;d=json.load(open('state-tp4/perf-gate.json'));print({k:d[k] for k in ['ts','verdict','probe_D_8K','probe_D_100K','probe_PR_131072_C1']})"

echo "--- [3/5] GSM8K 两跑 ---"
mkdir -p bench-results/final
for r in 1 2; do
  python3 bench/gsm8k_dsv41.py --base http://127.0.0.1:8899 --api-key "$API_KEY" \
    --out-raw "bench-results/final/gsm8k-r$r.raw.jsonl" --out-summary "bench-results/final/gsm8k-r$r.summary.json" >/dev/null 2>&1
  python3 -c "import json;d=json.load(open('bench-results/final/gsm8k-r$r.summary.json'));print('r$r', d['correct_marker'], '/', d['nq'], 'err', d['err'])"
done

echo "--- [4/5] 散文 B（sparkDash n=9） ---"
URL=http://127.0.0.1:8899/v1 API_KEY="$API_KEY" MAX_TOKENS=256 ROUNDS=9 python3 bench/prose_bench_sparkdash.py 2>&1 | tail -2

echo "--- [5/5] 四机与自愈 ---"
docker ps --format '{{.Names}}|{{.Status}}'
echo "monitor 进程数: $(pgrep -fc dsv41-monitor-head || echo 0)"
ls -la state-tp4/maintenance.flag 2>/dev/null && echo "(维护旗仍在 —— 收尾时摘)" || echo "(无维护旗)"
echo "=== final validate $TAG done $(date -Is) ==="
