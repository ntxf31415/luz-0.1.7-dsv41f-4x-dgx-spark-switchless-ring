#!/usr/bin/env python3
"""站点补丁：让 0.2.8 的 fabric GID 洞预检跳过「本站约定 -1」的情形。

背景（2026-09-24 窗口实测）：
  本站 `.env.tp4` 明写 `NCCL_IB_GID_INDEX_FORCE=-1`（注释原文：「kernel-1031 GID 表重排：
  禁止自动探测，恒 -1」）。它是 **start.sh 自用的宿主侧键** —— 起栈时被消费成
  `-e NCCL_IB_GID_INDEX=-1` 注入 head 与三 worker（0.1.7 与 0.2.8 行为一致）。

  0.2.8 新增的 `fabric_gid_preflight()` 取 `_idx="${NCCL_IB_GID_INDEX_FORCE:-${NCCL_IB_GID_INDEX:-3}}"`
  后去读 `/sys/class/infiniband/<hca>/ports/1/gid_attrs/types/$_idx`，**没有考虑负值**：
  `types/-1` 必然不存在 ⇒ 四口全被判成「洞」⇒ 直接 hard-fail（实测四机 16 口在
  idx 1/3 上都是 RoCE v2，**没有真洞**）。

  该检查的本意是拦「钉住某个索引但它没 GID」的情形（上游注释：`NCCL_IB_GID_INDEX_FORCE=3`
  时 NCCL 在洞口 modify_qp RTR 必挂）。**本站不钉索引**，前提不成立 ⇒ 负值时跳过、只告警。

用法： SITE_ROOT=$HOME/luz028 python3 patch_start_sh_gidpreflight.py
"""
import os
import shutil
import subprocess
import time

ROOT = os.environ.get("SITE_ROOT", os.path.expanduser("~/luz028"))
START = os.path.join(ROOT, "start.sh")

ANCHOR = (
    '  local _idx="${NCCL_IB_GID_INDEX_FORCE:-${NCCL_IB_GID_INDEX:-3}}"\n'
    '  local holes="$(_gid_holes_local)"\n'
)

GUARD = (
    '  # [site patch 2026-09-24] 本站约定 GID_INDEX_FORCE=-1（kernel-1031 GID 表重排后不钉索引、\n'
    '  # 交 NCCL 自适应）⇒「被钉的索引缺 GID」这个前提不成立。原逻辑会去读 types/-1（必不存在）\n'
    '  # 而把四个口全判成洞并 hard-fail。负值即跳过本检查，只留告警。\n'
    '  if [[ "$_idx" -lt 0 ]]; then\n'
    '    warn "NCCL_IB_GID_INDEX_FORCE=${_idx}（本站约定：不钉索引）⇒ 跳过 fabric GID 洞预检"\n'
    '    return 0\n'
    '  fi\n'
)

MARK = "[site patch 2026-09-24] 本站约定 GID_INDEX_FORCE=-1"


def main():
    t = open(START, encoding="utf-8").read()
    if MARK in t:
        print("已打过该补丁（幂等），未改动：%s" % START)
        return
    n = t.count(ANCHOR)
    if n != 1:
        raise SystemExit("!! 锚点命中 %d 次（应为 1）——start.sh 形态已变，拒绝改写" % n)
    t = t.replace(ANCHOR, ANCHOR + GUARD)
    ts = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(START, "%s.bak-%s-preGidPatch" % (START, ts))
    open(START, "w", encoding="utf-8").write(t)
    rc = subprocess.run(["bash", "-n", START]).returncode
    if rc != 0:
        shutil.copy2("%s.bak-%s-preGidPatch" % (START, ts), START)
        raise SystemExit("!! bash -n 失败，已回滚")
    print("已打补丁并回滚锚点就位：%s（bash -n 通过，备份 .bak-%s-preGidPatch）" % (START, ts))


if __name__ == "__main__":
    main()
