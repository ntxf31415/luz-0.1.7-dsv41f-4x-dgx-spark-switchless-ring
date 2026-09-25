#!/usr/bin/env bash
# w4-arm-boot.sh <tag> <KEY=VAL> [KEY=VAL ...] —— 窗口4 单臂：设顶层/EXTRA_DOCKER_ENV → 重建 → 验 → 打印判据。
# 顶层键（CONTEXT_LENGTH / MAX_RUNNING_REQUESTS / MAX_TOTAL_TOKENS）用 sed 直改；其余进 EXTRA_DOCKER_ENV。
set -uo pipefail
cd "$HOME/luz028"
TAG="${1:?usage: w4-arm-boot.sh <tag> K=V [K=V ...]}"; shift
[ $# -gt 0 ] || { echo "!! 没给 env"; exit 64; }
LOG="logs-tp4/w4-boot-$TAG.log"; exec > "$LOG" 2>&1
echo "=== w4-arm-boot tag=$TAG $(date -Is) args=$* ==="

cp .env.tp4 ".env.tp4.bak-$(date +%H%M)-pre-$TAG"
for kv in "$@"; do
  k="${kv%%=*}"; v="${kv#*=}"
  case "$k" in
    CONTEXT_LENGTH|MAX_RUNNING_REQUESTS|MAX_TOTAL_TOKENS|MEM_FRACTION_STATIC|CHUNKED_PREFILL_SIZE)
      python3 - "$k" "$v" <<'PY'
import re, sys
k, v = sys.argv[1], sys.argv[2]
p = ".env.tp4"
s = open(p).read()
s2, n = re.subn(rf"^{k}=.*$", f"{k}={v}", s, count=1, flags=re.M)
assert n == 1, f"顶层键 {k} 未命中"
open(p, "w").write(s2)
print(f"顶层 {k}={v}")
PY
      ;;
    *)
      python3 site/tools/set_extra_env.py "$kv"
      ;;
  esac
done
echo "--- 生效行 ---"
grep -E "^CONTEXT_LENGTH=|^MAX_RUNNING_REQUESTS=|^MAX_TOTAL_TOKENS=|^CHUNKED_PREFILL_SIZE=" .env.tp4

echo "--- 停栈 ---"
touch state-tp4/maintenance.flag
docker rm -f dsv41-head
ssh -o BatchMode=yes spark@192.168.50.56 'docker rm -f dsv41-worker'
ssh -o BatchMode=yes spark@192.168.50.58 'docker rm -f dsv41-worker'
ssh -o BatchMode=yes spark@192.168.50.57 'docker rm -f dsv41-worker'

echo "--- 起栈 ---"
S=$(date +%s)
ENV_FILE=.env.tp4 WARMUP=0 ./start-tp4.sh serve
echo "serve rc=$? 耗时 $(( $(date +%s) - S ))s"

for i in $(seq 1 30); do
  c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8899/health 2>/dev/null || true)
  [ "$c" = "200" ] && break
  sleep 10
done
echo "health=$c"
docker ps --format '{{.Names}}|{{.Status}}'

echo "--- 判据：容器内关键值 ---"
docker exec dsv41-head env | grep -E '^DSV41_CACHE_GIB=|^DSV41_CACHE_WAYS=|^CONTEXT_LENGTH=|^MAX_RUNNING_REQUESTS=|^MAX_TOTAL_TOKENS=' || true
echo "--- 内存（MemAvailable 采样） ---"
grep -E 'MemAvailable' /proc/meminfo
echo "=== w4-arm-boot done $(date -Is) ==="
