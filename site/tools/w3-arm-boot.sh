#!/usr/bin/env bash
# w3-arm-boot.sh <gate|off> <tag> —— 窗口3 单臂：装 gate → 四机停栈 → 起栈 → 验挂载/开关 → 打印判据行。
# 量具由调用方随后跑（site/tools/w34-de-subset.sh 与 gate --full）。
set -uo pipefail
cd "$HOME/luz028"
GATE="${1:?usage: w3-arm-boot.sh <gate|off> <tag>}"
TAG="${2:?usage: w3-arm-boot.sh <gate|off> <tag>}"
LOG="logs-tp4/w3-boot-$TAG.log"; exec > "$LOG" 2>&1
echo "=== w3-arm-boot gate=$GATE tag=$TAG start $(date -Is) ==="

echo "--- [1/5] 装 gate ---"
if [ "$GATE" = "off" ]; then
  python3 site/tools/set_extra_env.py --remove DSV41_VERIFY_CAP
  python3 site/tools/set_extra_env.py --remove DSV41_ROUTER_LIVE
else
  python3 site/tools/set_extra_env.py "DSV41_VERIFY_CAP=$GATE"
  case "$GATE" in
    conf:*) python3 site/tools/set_extra_env.py DSV41_ROUTER_LIVE=1 ;;
    *)      python3 site/tools/set_extra_env.py --remove DSV41_ROUTER_LIVE ;;
  esac
fi

echo "--- [2/5] 停栈（维护旗 + 四机 rm -f） ---"
touch state-tp4/maintenance.flag
docker rm -f dsv41-head
ssh -o BatchMode=yes spark@192.168.50.56 'docker rm -f dsv41-worker'
ssh -o BatchMode=yes spark@192.168.50.58 'docker rm -f dsv41-worker'
ssh -o BatchMode=yes spark@192.168.50.57 'docker rm -f dsv41-worker'
echo "剩余容器: $(docker ps -q | wc -l)"

echo "--- [3/5] 起栈（READY 判据 ~380s） ---"
S=$(date +%s)
ENV_FILE=.env.tp4 WARMUP=0 ./start-tp4.sh serve
echo "serve rc=$? 耗时 $(( $(date +%s) - S ))s"

echo "--- [4/5] 就绪与四机 ---"
for i in $(seq 1 30); do
  c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8899/health 2>/dev/null || true)
  [ "$c" = "200" ] && break
  sleep 10
done
echo "health=$c（轮询 $i 次）"
docker ps --format '{{.Names}}|{{.Status}}'

echo "--- [5/5] 判据：开关 / 挂载 / 补丁自述 ---"
docker exec dsv41-head env | grep -E '^DSV41_VERIFY_CAP=|^DSV41_ROUTER_LIVE=' || echo "(gate 未设 = off)"
echo "sp-adapters 挂载数: $(docker exec dsv41-head mount 2>/dev/null | grep -c /sp-adapters)"
docker exec dsv41-head ls /opt/sglang/lib/python3.12/site-packages/zz_sp_loader.pth 2>/dev/null || echo "(!! .pth 未挂)"
docker logs dsv41-head 2>&1 | grep -E '\[sp-loader\]|\[verify_cap\]' | head -10
echo "=== w3-arm-boot done $(date -Is) ==="
