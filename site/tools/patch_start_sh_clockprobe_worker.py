#!/usr/bin/env python3
"""worker 分支的 gpu-clock 预检假阳修补（P0.48 那次的 head 版只覆盖了 head）。

背景（2026-09-26 窗口3 实测）：
  worker 分支跑 burn 后，等待判据是「时钟 ≥1000MHz 即采样」。.56 因此在**爬坡点**
  被读到 `burn=1495MHz/7W`（7W = 负载尚未建立）⇒ 被误判「PD 安全模式楔死」，
  serve 直接 `rc=1` 停在那里（head/.58/.57 同刻分别 2158/2275/2047MHz 全过）。
  真·楔死 band 是 513–728MHz ⇒ 这是采样时序问题，不是判据问题。

修法：worker 分支的等待循环改成**等功耗 ≥30W**（与 head 版一致，最多 6×2=12s，
与 burn 时长一致）；真楔死机等不到 ⇒ 超时取低值 ⇒ 判据仍会 FAIL。**判据本身不动。**

用法： SITE_ROOT=$HOME/luz028 python3 patch_start_sh_clockprobe_worker.py
"""
import os
import shutil
import subprocess
import sys
import time

ROOT = os.environ.get("SITE_ROOT", os.path.expanduser("~/luz028"))
START = os.path.join(ROOT, "start.sh")

# 仅在 worker（ssh 内联脚本）分支里出现的等待循环
ANCHOR = (
    '_w=0\n'
    'while [ \\$_w -lt 14 ]; do\n'
    '  _cl=\\$(nvidia-smi --query-gpu=clocks.sm --format=csv,noheader,nounits 2>/dev/null | tr -d \' \' | grep -oE \'^[0-9]+\' || echo 0)\n'
    '  [ "\\${_cl:-0}" -ge 1000 ] && break\n'
    '  sleep 2; _w=\\$((_w+1))\n'
    'done\n'
)

REPL = (
    '_w=0\n'
    '# [site patch 2026-09-26] 等功耗真上载再采样（head 版同法）：时钟刚过 1000MHz 时\n'
    '# 读到的是爬坡点（实测 .56 得 1495MHz/7W）⇒ 误报楔死。判据（≥1500MHz）不变。\n'
    'while [ \\$_w -lt 6 ]; do\n'
    '  _pww=\\$(nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits 2>/dev/null | tr -d \' \' | grep -oE \'^[0-9]+\' || echo 0)\n'
    '  [ "\\${_pww:-0}" -ge 30 ] && break\n'
    '  sleep 2; _w=\\$((_w+1))\n'
    'done\n'
)

MARK = "[site patch 2026-09-26]"


def main():
    t = open(START, encoding="utf-8").read()
    if MARK in t:
        print("已打过该补丁（幂等），未改动")
        return
    n = t.count(ANCHOR)
    if n != 1:
        print("!! 锚点命中 %d 次（应为 1）—— 形态已变，拒绝改写" % n)
        sys.exit(2)
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak-%s-preClockPatchWorker" % (START, ts)
    shutil.copy2(START, bak)
    open(START, "w", encoding="utf-8").write(t.replace(ANCHOR, REPL))
    if subprocess.run(["bash", "-n", START]).returncode != 0:
        shutil.copy2(bak, START)
        sys.exit("!! bash -n 失败，已回滚")
    print("已打补丁（worker 分支，bash -n 通过）：%s" % START)


if __name__ == "__main__":
    main()
