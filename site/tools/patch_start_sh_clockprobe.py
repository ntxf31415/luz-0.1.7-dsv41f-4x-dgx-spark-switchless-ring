#!/usr/bin/env python3
"""站点补丁：修 `gpu_clock_preflight()` head 分支的「采样过早 ⇒ 误报楔死」。

背景（2026-09-24 窗口实测）：
  该探针在**时钟刚过 1000MHz** 时立刻取读数，健康判据是 ≥1500MHz。head 分支没有 ssh
  开销（worker 分支经 ssh 反而天然多等了几百毫秒），于是 head 常读到**爬坡点**：
  实测 `burn=1495MHz/6W`（6W = 负载尚未建立）⇒ 被误判「PD 安全模式楔死」并 hard-fail，
  把人推向无谓的物理断电。同一时刻手动烧机 head 稳在 **2288MHz/59W**，GPU 完全健康。

  真·楔死的band是 513–728MHz（探针注释原文），与 1495 相距甚远 ⇒ 这是**采样时序**问题，
  不是判据问题。修法：head 分支在采样前**等功耗真上载**（≥30W，最多等 12s；楔死机等不到
  ⇒ 仍会超时取到低值 ⇒ 正确 FAIL），保留原有 ≥1500MHz 判据不变。

用法： SITE_ROOT=$HOME/luz028 python3 patch_start_sh_clockprobe.py
"""
import os
import shutil
import subprocess
import time

ROOT = os.environ.get("SITE_ROOT", os.path.expanduser("~/luz028"))
START = os.path.join(ROOT, "start.sh")

ANCHOR = (
    '        nvidia-smi --query-gpu=clocks.sm,power.draw --format=csv,noheader,nounits | tr -d \' \'\n'
    '        wait $p 2>/dev/null\n'
)

GUARD = (
    "        # [site patch 2026-09-24] 采样过早的假楔死：head 无 ssh 开销，时钟刚过 1000MHz\n"
    "        # 就被读到爬坡点（实测 1495MHz/6W）⇒ 误报。等功耗真上载（≥30W，最多 12s）再采；\n"
    "        # 真楔死机（513–728MHz band）等不到 ⇒ 超时后仍取低值 ⇒ 照旧 FAIL。判据不变。\n"
    "        _pw=0\n"
    "        while [ $_pw -lt 6 ]; do\n"
    "          _p=$(nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits 2>/dev/null | tr -d ' ' | grep -oE '^[0-9]+' || echo 0)\n"
    "          [ \"${_p:-0}\" -ge 30 ] && break\n"
    "          sleep 2; _pw=$((_pw+1))\n"
    "        done\n"
)

MARK = "[site patch 2026-09-24] 采样过早的假楔死"


def main():
    t = open(START, encoding="utf-8").read()
    if MARK in t:
        print("已打过该补丁（幂等），未改动：%s" % START)
        return
    n = t.count(ANCHOR)
    if n != 1:
        raise SystemExit("!! 锚点命中 %d 次（应为 1）——start.sh 形态已变，拒绝改写" % n)
    ts = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(START, "%s.bak-%s-preClockPatch" % (START, ts))
    open(START, "w", encoding="utf-8").write(t.replace(ANCHOR, GUARD + ANCHOR))
    if subprocess.run(["bash", "-n", START]).returncode != 0:
        shutil.copy2("%s.bak-%s-preClockPatch" % (START, ts), START)
        raise SystemExit("!! bash -n 失败，已回滚")
    print("已打补丁：%s（bash -n 通过）" % START)


if __name__ == "__main__":
    main()
