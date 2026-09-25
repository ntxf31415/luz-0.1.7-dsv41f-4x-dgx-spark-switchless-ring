#!/usr/bin/env bash
# w34-de-subset.sh <tag> — 窗口3/4 的单臂快速量具：指纹 + DE 子集(code,prose × c1/c2/c4, 2 波) + 判决摘要。
set -uo pipefail
cd "$HOME/luz028"
export MODEL=deepseek-v4.1-flash
export API_KEY="$(cat state-tp4/api-key)"
TAG="${1:?usage: w34-de-subset.sh <tag>}"
OUT="bench-results/arms/$TAG"; mkdir -p "$OUT"
LOG="logs-tp4/w34-$TAG.log"; exec > "$LOG" 2>&1

idle() {
  local r q
  r=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics | grep -m1 '^sglang:num_running_reqs' | sed 's/.*} //')
  q=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics | grep -m1 '^sglang:num_queue_reqs' | sed 's/.*} //')
  echo "    [idle] running=$r queue=$q"
}

echo "=== w34 arm $TAG start $(date -Is) ==="
echo "--- 生效开关（窗口3/4 关注的） ---"
docker exec dsv41-head env | grep -E "^DSV41_VERIFY_CAP|^DSV41_ROUTER_LIVE|^DSV41_CACHE_GIB|^DSV41_CACHE_WAYS|^MAX_RUNNING_REQUESTS|^CONTEXT_LENGTH|^MAX_TOTAL_TOKENS|^DSV41_PREFILL_SP" | sort
echo "--- 站点挂载件（应为 6 条） ---"
grep -c "v \"\$HOME/luz028/site-patches" start.sh || true

echo "--- [1/2] 贪心指纹 ---"
idle
python3 scripts/verify/fingerprint.py 2>&1 | tail -1

echo "--- [2/2] DE 子集 code,prose × c1,c2,c4（2 波） ---"
idle
docker cp benchmarks/de_matrix_v3.py dsv41-head:/state/sdbench/de_matrix_v3.py
docker exec -e OUT_DIR="/state/bench-results/de-sub-$TAG" -e RUN_TAG="$TAG" \
  -e TYPES=code,prose -e CONCURRENCIES=1,2,4 -e WAVES=2 -e MAXTOK=2048 \
  dsv41-head python3 /state/sdbench/de_matrix_v3.py
echo "DE 子集 exit=$?"
echo "--- 结果摘要（格值=单流 t/s，聚合=×N） ---"
OUTDIR="state-tp4/bench-results/de-sub-$TAG" python3 - <<'PY'
import glob, json, os
d = os.environ["OUTDIR"]
rows = []
for f in sorted(glob.glob(os.path.join(d, "de_*.json"))):
    j = json.load(open(f))
    for k, v in j.items():
        if k.startswith("_"):
            continue
        w = [x.get("median_decode_tps") for x in (v.get("waves_detail") or [])]
        rows.append((os.path.basename(f)[3:-5], v.get("median_decode_tps") or 0,
                     v.get("agg_decode_tps") or 0, (v.get("median_ttft_s") or 0) * 1000,
                     v.get("median_prefill_tps") or 0, [round(x, 1) for x in w]))
for name, med, agg, ttft, pre, w in sorted(rows):
    print(f"  {name:16s} 单流 {med:7.2f}  聚合 {agg:7.2f}  TTFT {ttft:7.0f}ms  prefill {pre:6.0f}  波 {w}")
PY

echo "=== w34 arm $TAG done $(date -Is) ==="
