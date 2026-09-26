#!/usr/bin/env python3
"""修两处，让 knapcio 栈在我们的 ring-only NCCL 上起得来。

1) start.sh：把 head 的 per-rank PEER_HCA 注入从 `elif` 分支里 **挪到 if/elif 之外**
   —— 因为我们要走 `NCCL_SWITCHLESS_RING_ONLY=1` 分支（只有那条会调 nccl_mount_args、
   才会把我们的库 **覆盖到 pip 路径**，而 torch 走 RPATH 只认 pip 路径）。
2) .env.tp4：启 `NCCL_SWITCHLESS_RING_ONLY=1`；显式给 ring 必需项
   （它 files/nccl.sh 的 ring 检查要求：OVERLAY_PIP=1 · ALGO=Ring · NET=IB · IB_DISABLE=0 ·
   subnet-aware routing=1），并补 NCCL_P2P_LEVEL=SYS（它 ring 配方里的项）。
"""
import re
import shutil
import sys
import time

DEL_LINES = ['  # [站点补丁] ring-only NCCL 需要 per-rank 对端 HCA 映射（等价于 LuZ launcher 的做法）',
             '  [[ -n "${PEER_HCA_RANK0:-}" ]] && _a+=(-e "NCCL_IB_PEER_HCA=$PEER_HCA_RANK0")']
HEAD_FI = "  fi\n}\n\n# Every rank builds its own planner"
ADD = ('\n  # [站点补丁] per-rank 对端 HCA —— 放在 if/elif **之外**，两条 NCCL 分支都生效\n'
       '  [[ -n "${PEER_HCA_RANK0:-}" ]] && _a+=(-e "NCCL_IB_PEER_HCA=$PEER_HCA_RANK0")\n')

s = open("start.sh", encoding="utf-8").read()

# --- 1) 挪注入点 ---
for l in DEL_LINES:
    if l in s:
        s = s.replace(l + "\n", "", 1)
if HEAD_FI not in s:
    raise SystemExit("!! 锚点未命中（fi 之后的那段注释）—— 拒绝改写")
if s.count(HEAD_FI) != 1:
    raise SystemExit("!! 锚点不唯一")
shutil.copy2("start.sh", "start.sh.bak-%s-preRingFix" % time.strftime("%Y%m%d-%H%M%S"))
s = s.replace(HEAD_FI, "  fi\n}\n" + ADD + "\n# Every rank builds its own planner", 1)
open("start.sh", "w", encoding="utf-8").write(s)
print("[patch] head PEER_HCA 注入已挪到 if/elif 之外")

# --- 2) env ---
env = open(".env.tp4", encoding="utf-8").read().split("\n")


def setk(lines, k, v):
    for i, l in enumerate(lines):
        if l.startswith(k + "="):
            lines[i] = "%s=%s" % (k, v)
            return True
    lines.append("%s=%s" % (k, v))
    return False


for k, v in (("NCCL_SWITCHLESS_RING_ONLY", "1"),
             ("NCCL_ALGO", "Ring"),
             ("NCCL_P2P_LEVEL", "SYS"),
             ("NCCL_IB_SUBNET_AWARE_ROUTING", "1"),
             ("NCCL_NET", "IB"),
             ("NCCL_IB_DISABLE", "0")):
    setk(env, k, v)
open(".env.tp4", "w", encoding="utf-8").write("\n".join(env) + "\n")
print("[patch] .env.tp4：SWITCHLESS_RING_ONLY=1 + ring 必需项")
