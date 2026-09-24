#!/usr/bin/env bash
# pr-v3-ab-arm.sh <label> — b12x A/B 的「单臂」测量：指纹门 + PR-v3 长档八格。
#
# 为什么这么窄：这轮只回答一个问题 —— **把 DSV41_MOE_B12X 打开，本栈在 8192 之上
# 会不会冒出上游那处 −42% 悬崖**。所以只测 16384/65536/32768/131072 × C1/C4 八格，
# 不重复整张 24 格网格（那部分两个臂都已在别处有数）。
#
# 顺序即纪律（同 ab-arm.sh）：**先指纹**。b12x 已知会让贪心输出不可复现，
# 这里跑两次是为了在本臂上再证一次；两次不一致 ⇒ 本臂按「改输出」论处，
# 吞吐数字只作参考、不作采纳依据。
set -uo pipefail

LABEL="${1:?usage: pr-v3-ab-arm.sh <label>}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HOME/luz017"
SB="$ROOT/state-tp4/sdbench"
ARCH="$ROOT/state-tp4/bench-results/luz017-sd1/pr-v3-ab-$LABEL"
mkdir -p "$ARCH"
exec > >(tee -a "$ARCH/run.log") 2>&1

echo "=== b12x A/B 臂 $LABEL @ $(date '+%F %T %Z') ==="

echo "--- 本臂的关键开关（必须是本臂独有的差异）"
for v in DSV41_MOE_B12X DSV41_MOE_B12X_CAPS DSV41_MOE_B12X_QUANT DSV41_MXFP8_BACKEND; do
  printf '    %-28s = %s\n' "$v" "$(docker exec dsv41-head printenv "$v" 2>/dev/null | head -1 || echo '(未设)')"
done
echo "    manifest_sha256 = $(docker exec dsv41-head sha256sum /state/launch.json 2>/dev/null | cut -c1-16)"

echo "--- 前置空闲"
curl -s --max-time 5 http://127.0.0.1:8899/metrics \
  | grep -E '^sglang:num_(running|queue)_reqs' | sed 's/{[^}]*}//' | sed 's/^/    /'

echo "--- [1/2] 贪心指纹 ×2（必须一致，否则本臂按「改输出」论处）"
KEY="$(cat "$ROOT/state-tp4/api-key")"
for i in 1 2; do
  URL=http://127.0.0.1:8899/v1/chat/completions API_KEY="$KEY" \
    python3 "$ROOT/scripts/verify/fingerprint.py" 2>&1 | tail -1 | tee "$ARCH/fingerprint-$i.txt"
done
a=$(tail -1 "$ARCH/fingerprint-1.txt"); b=$(tail -1 "$ARCH/fingerprint-2.txt")
if [ "$a" = "$b" ]; then echo "    ✓ 确定性 OK（$a）"; else echo "    ✗ 两次不一致：$a vs $b —— 改输出，本臂吞吐只作参考"; fi

echo "--- [2/2] PR-v3 长档八格：16384/65536/32768/131072 × C1/C4 @ $(date '+%T')"
docker exec -e SIZES=16384,65536,32768,131072 -e CONCS=1,4 -e WAVES=1 \
  -e OUT_DIR="/state/bench-results/luz017-sd1/pr-v3-ab-$LABEL" \
  -w /state/sdbench dsv41-head python3 /state/sdbench/pr_matrix_v3.py 2>&1 | tail -2

# 注意：容器（root）已经在本目录写过一份 TABLE.md，宿主再写同名文件会 Permission denied，
# 所以渲染结果另存 TABLES.md（容器那份是 harness 自己的单批视图，不含并发列）。
python3 "$SB/render_pr_v3_tables.py" "$ARCH" > "$ARCH/TABLES.md" 2>/dev/null
echo "--- 本臂总吞吐（t/s）"
grep -E "^\| (16384|65536|32768|131072) " "$ARCH/TABLES.md" | awk -F'|' '{printf "    %8s x C%-3s %s\n", $2, $3, $7}' 2>/dev/null || echo "    (渲染失败，见 $ARCH/TABLES.md)"

echo "=== 本臂完成 @ $(date '+%F %T %Z') ==="
echo "产物： $ARCH"
