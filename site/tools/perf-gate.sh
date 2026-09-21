#!/usr/bin/env bash
# perf-gate.sh — 重启后的性能门禁（2026-09-19 立）
#
# 为什么需要它：**同配置跨 boot 长 prefill 可差 1.5 倍**（基准总表 §五 修正 5/6，
# 机制＝fused-MoE GEMM 的 tactic 每次 boot 现场抽签，目前无已知手段钉住）。
# 引擎的 health 检查**看不出**这个差异 —— 抽到差签时生产静默变慢，无人知晓。
# 每次新 boot 跑一次本门禁，把"是否落在慢档"变成一个显式判据。
#
# 判据三点，覆盖不同 M 与上下文长度：
#   口径 D 8000 / 100000（单流 needle，异质加盐）· PR-v3 131072×C1（总吞吐）
# 门限取自实测两档之间的安全带（2026-09-19 实测）：
#   慢档  8K 1251 · 100K 2105 · PR131K 2237
#   快档  8K 2980–3237 · 100K 2939–3278 · PR131K 3045–3290
# 主判据用 100K 与 PR131K（分离最干净）；8K 只作 WARN —— 它自身离散最大。
#
# 产物：
#   state-tp4/perf-gate.json   本次判定（机器可读，供外部巡检/通知读取）
#   state-tp4/perf-gate.FAIL   仅 FAIL 时创建（存在即"需要人看"）
#   logs-tp4/perf-gate.log     追加日志
#
# 用法（在 head 上）： scripts/perf-gate.sh          # 正常，退出码 0/1
#                      scripts/perf-gate.sh --verbose
set -uo pipefail

ROOT="${ROOT:-$HOME/luz017}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$ROOT/state-tp4/perf-gate.json"
FAILMARK="$ROOT/state-tp4/perf-gate.FAIL"
LOG="$ROOT/logs-tp4/perf-gate.log"
SBD="$ROOT/state-tp4/sdbench"
CTN=dsv41-head
mkdir -p "$(dirname "$LOG")"

exec >> "$LOG" 2>&1
echo "=== perf-gate @ $(date '+%F %T %Z') ==="

# --- 前置：引擎必须空闲，否则测的是别人的负载
idle=$(curl -s --max-time 5 http://127.0.0.1:8899/metrics \
        | grep -E '^sglang:num_(running|queue)_reqs' | awk '{s+=$2} END{print s+0}')
echo "  前置空闲 running+queue=$idle"
if [ "$idle" != "0" ]; then
  echo "  !! 引擎非空闲，本次不作判定"; exit 2
fi

# --- 探针 1/2：口径 D（单流 needle，异质加盐）
# seed 每次随日期变化：探针内容若固定，连续跑会命中 radix 前缀缓存而**虚高**
# （2026-09-19 实测同一 seed 连测 8K 拿到 24669 t/s）。
SEED=$(( $(date +%s) % 90000 + 1000 ))
docker cp "$SCRIPT_DIR/verify/prefill_distinct.py" "$CTN:/tmp/prefill_distinct.py" >/dev/null 2>&1
# 8K 单次离散大（实测同机不同 seed 2661–3154）⇒ 取三次中位；100K 稳，单测即可。
d8=$(for i in 1 2 3; do
       docker exec "$CTN" python3 /tmp/prefill_distinct.py 8000 $((SEED + i)) 2>/dev/null \
         | grep -oE '\([0-9]+ tok/s\)' | grep -oE '[0-9]+'
     done | sort -n | sed -n 2p)
d100=$(docker exec "$CTN" python3 /tmp/prefill_distinct.py 100000 "$SEED" 2>/dev/null \
       | grep -oE '\([0-9]+ tok/s\)' | grep -oE '[0-9]+')
echo "  口径 D: 8K=${d8:-?} tok/s(3 次中位) · 100K=${d100:-?} tok/s · seed=$SEED"

# --- 探针 3：PR-v3 131072×C1（总吞吐）
pr=$(docker exec -e SIZES=131072 -e CONCS=1 -e WAVES=1 \
      -e OUT_DIR=/state/bench-results/gate \
      -w /state/sdbench "$CTN" python3 /state/sdbench/pr_matrix_v3.py 2>/dev/null \
      | python3 -c "
import sys,json
for l in sys.stdin:
    l=l.strip()
    if l.startswith('{'):
        try: print(json.loads(l)['total_throughput_tps'])
        except Exception: pass
" | tail -1)
echo "  PR-v3 131072×C1 = ${pr:-?} t/s"
# 吞吐是浮点（如 3296.4），而 shell 的 [ -lt ] 只接受整数 —— 不取整会让判据
# **静默失效**（[: 3296.4: 需要整数表达式），安全装置变成永远 PASS。故先截断。
pr=${pr%%.*}

# --- 本 boot 的旁证（Codex 建议：调优次数 + 缓存指纹）
tuners=$(grep -ac "Tuning trtllm::fused_moe" "$ROOT/logs-tp4/dsv41.log" 2>/dev/null || echo 0)
# 缓存文件是容器 root 写的，宿主 spark 读不了 ⇒ 在容器里算
cache_sha=$(docker exec "$CTN" sh -c "find /root/.cache/sglang/flashinfer/autotune -name '*.json' 2>/dev/null | sort | xargs cat 2>/dev/null | sha256sum | cut -c1-16" 2>/dev/null || echo n/a)
echo "  旁证: 本 boot 调优次数=$tuners · autotune 缓存指纹=${cache_sha:-n/a}"

# --- 判定
verdict=PASS; reasons=""
note() { reasons="$reasons $1"; }

# ① 取不到数一律 FAIL —— 门禁宁可误报，不可漏报（曾经因浮点比较静默失效）
for p in "$d8" "$d100" "$pr"; do
  case "$p" in ''|*[!0-9]*) verdict=FAIL; note "有探针缺测或非整数"; break;; esac
done

# ② 硬门限（取自实测慢档与快档之间的安全带）
if [ "$verdict" != FAIL ]; then
  [ "$d100" -lt 2500 ] && { verdict=FAIL; note "D100K=$d100<2500"; }
  [ "$pr"   -lt 2700 ] && { verdict=FAIL; note "PR131K=$pr<2700"; }
fi

# ③ 软门限（仅在未 FAIL 时降级为 WARN）
if [ "$verdict" != FAIL ]; then
  [ "$d100" -lt 2900 ] && { verdict=WARN; note "D100K=$d100偏低"; }
  [ "$pr"   -lt 3000 ] && { verdict=WARN; note "PR131K=$pr偏低"; }
  [ "$d8"   -lt 2600 ] && { verdict=WARN; note "D8K=$d8偏低"; }
fi
[ "$verdict" = PASS ] && reasons=" 三点均在快档带内"

python3 - "$OUT" "$verdict" "${d8:-}" "${d100:-}" "${pr:-}" "$tuners" "${cache_sha:-}" <<'PY'
import json,sys,time
out,verdict,d8,d100,pr,tuners,sha = sys.argv[1:8]
def n(x): return int(x) if x.strip().isdigit() else None
json.dump({"_comment":"perf-gate：重启后性能门禁，判据与门限见 scripts/perf-gate.sh 头部",
           "ts": time.strftime("%F %T"), "verdict": verdict,
           "probe_D_8K": n(d8), "probe_D_100K": n(d100), "probe_PR_131072_C1": n(pr),
           "b12x_off": True, "tuner_runs_this_boot": int(tuners) if tuners.isdigit() else None,
           "autotune_cache_sha16": sha,
           "bands": {"slow":[1251,2105,2237],"fast":[2980,2939,3045]}},
          open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
PY

if [ "$verdict" = FAIL ]; then
  date '+FAIL @ %F %T' > "$FAILMARK"
  echo "  ✗ FAIL:$reasons  （标记 $FAILMARK）"
else
  rm -f "$FAILMARK"
  echo "  ✓ $verdict:$reasons"
fi
echo "=== perf-gate done ==="
[ "$verdict" = FAIL ] && exit 1 || exit 0
