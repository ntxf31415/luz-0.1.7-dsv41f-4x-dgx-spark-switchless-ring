#!/usr/bin/env bash
# wait-idle-then.sh — 等引擎**连续**空闲 N 秒后，执行给定命令。
#
# 为什么不只是「看一眼空闲就开跑」：本站产线白天有真实流量（面板/NAS 经 8888），
# 单次采样撞上瞬时低谷会误判。基准纪律 §6.1 要的是真空闲 —— 连续保持才算。
# 负载一出现，空闲计时**归零重来**。
#
# 用法： wait-idle-then.sh <连续空闲秒数> <命令> [参数...]
# 例：   wait-idle-then.sh 600 ~/luz017/scripts/pr-v3-conical.sh luz017-20260919
set -uo pipefail

NEED="${1:?usage: wait-idle-then.sh <sustained_seconds> <cmd...>}"; shift
[ $# -gt 0 ] || { echo "!! 没给要执行的命令"; exit 64; }
POLL="${POLL_S:-30}"
METRICS="http://127.0.0.1:8899/metrics"

# 正在跑的请求数：running + queue 求和
busy() {
  curl -s --max-time 5 "$METRICS" 2>/dev/null \
    | grep -E '^sglang:num_(running|queue)_reqs' \
    | awk '{s+=$2} END{print s+0}'
}

idle_since=""
echo "=== 等待连续空闲 ${NEED}s（轮询 ${POLL}s）@ $(date '+%F %T %Z') ==="
while true; do
  n=$(busy)
  now=$(date +%s)
  if [ "$n" = "0" ]; then
    [ -n "$idle_since" ] || idle_since=$now
    held=$(( now - idle_since ))
  else
    [ -n "$idle_since" ] && echo "  $(date '+%T') ★ 负载出现 (running+queue=$n)，空闲计时归零"
    idle_since=""; held=0
  fi
  printf '  %s running+queue=%s 连续空闲 %ss/%ss\n' "$(date '+%T')" "$((n))" "$held" "$NEED"
  [ "$held" -ge "$NEED" ] && break
  sleep "$POLL"
done

echo "=== 连续空闲 ${NEED}s 达成，开跑 @ $(date '+%F %T %Z') ==="
echo "=== 命令： $* ==="
"$@"
rc=$?
echo "=== 被守门器启动的命令退出 rc=$rc @ $(date '+%F %T %Z') ==="
exit $rc
