#!/usr/bin/env python3
"""A 路：不启 SWITCHLESS（我们的 LuZ 库没有 sparkring 的标记），但仍把库覆盖到 pip 路径。

它原代码：
  elif [[ -f "$NCCL_HOST_DIR/libnccl.so.2.30.7" || ... ]]; then
    _a+=(-v "$NCCL_HOST_DIR:$NCCL_CONTAINER_DIR:ro" -e "LD_LIBRARY_PATH=$NCCL_CONTAINER_DIR")
  fi
问题：torch 走自己的 RPATH，**LD_LIBRARY_PATH 不生效** ⇒ 环补丁没进到 torch。
改法：这一支也调 `nccl_mount_args`（它在 NCCL_OVERLAY_PIP=1 时会把库挂到 `$NCCL_PIP_SO`），
失败再退回原来的 LD_LIBRARY_PATH 写法。
"""
import re
import shutil
import sys
import time

OLD = '''  elif [[ -f "$NCCL_HOST_DIR/libnccl.so.2.30.7" || -f "$NCCL_HOST_DIR/libnccl.so.2" ]]; then
    _a+=(-v "$NCCL_HOST_DIR:$NCCL_CONTAINER_DIR:ro" -e "LD_LIBRARY_PATH=$NCCL_CONTAINER_DIR")
  fi'''
NEW = '''  elif [[ -f "$NCCL_HOST_DIR/libnccl.so.2.30.7" || -f "$NCCL_HOST_DIR/libnccl.so.2" ]]; then
    # [站点补丁] 也走 nccl_mount_args：NCCL_OVERLAY_PIP=1 时把库覆盖到 pip 路径（torch 只认它）
    nccl_mount_args _a || _a+=(-v "$NCCL_HOST_DIR:$NCCL_CONTAINER_DIR:ro" -e "LD_LIBRARY_PATH=$NCCL_CONTAINER_DIR")
  fi'''

s = open("start.sh", encoding="utf-8").read()
if "[站点补丁] 也走 nccl_mount_args" in s:
    print("[skip] 已打过")
else:
    if s.count(OLD) != 1:
        raise SystemExit("!! 锚点命中 %d 次（应为 1）" % s.count(OLD))
    shutil.copy2("start.sh", "start.sh.bak-%s-preOverlayPip" % time.strftime("%Y%m%d-%H%M%S"))
    s = s.replace(OLD, NEW, 1)
    open("start.sh", "w", encoding="utf-8").write(s)
    print("[patch] elif 分支改为 nccl_mount_args（含回退）")

# env：关掉 SWITCHLESS，显式开 OVERLAY_PIP，并补我们生产用的 NIC 参数套件
env = open(".env.tp4", encoding="utf-8").read().split("\n")


def setk(lines, k, v):
    for i, l in enumerate(lines):
        if l.startswith(k + "="):
            lines[i] = "%s=%s" % (k, v)
            return
    lines.append("%s=%s" % (k, v))


for k, v in (("NCCL_SWITCHLESS_RING_ONLY", "0"),
             ("NCCL_OVERLAY_PIP", "1"),
             ("NCCL_ALGO", "Ring"),
             ("NCCL_IB_SUBNET_AWARE_ROUTING", "1"),
             ("NCCL_IB_MERGE_NICS", "0"),
             ("NCCL_CROSS_NIC", "1"),
             ("NCCL_MIN_NCHANNELS", "4"),
             ("NCCL_MAX_NCHANNELS", "4"),
             ("NCCL_NET_PLUGIN", "none"),
             ("NCCL_CUMEM_HOST_ENABLE", "0"),
             ("NCCL_SHM_DISABLE", "1")):
    setk(env, k, v)
# EXTRA 里也要有 GID=-1（它白名单不含 FORCE 后缀的键，只能经 EXTRA 透传）
for i, l in enumerate(env):
    if l.startswith("EXTRA_CONTAINER_ENV=") and "DSV41_MOE_B12X_NEXT_DETERMINISTIC=1" in l:
        body = l[len('EXTRA_CONTAINER_ENV="'):].rstrip('"')
        toks = body.split()
        if not any(t.startswith("NCCL_IB_GID_INDEX_FORCE") for t in toks):
            toks.append("NCCL_IB_GID_INDEX_FORCE=-1")
        env[i] = 'EXTRA_CONTAINER_ENV="' + " ".join(toks) + '"'
        break
open(".env.tp4", "w", encoding="utf-8").write("\n".join(env) + "\n")
print("[env] SWITCHLESS=0 / OVERLAY_PIP=1 / NIC 套件已补")
