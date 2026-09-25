#!/usr/bin/env python3
"""把站点挂载的 encoding_dsv41.py 的 reasoning 预算改到上游发布版值。

上游 issue #39909 / PR #39929（2026-09-24 合并）认定：该文件的
REASONING_EFFORT_MAPPINGS 带的是**发布前**预算（low 25 / high 50），
与 release reference / deepseek-recipe 的 50 / 75 不符。

本站自 0.2.8 起以站点挂载件承载 #40758，故本改动也必须落在站点件上。

判据：
  - 锚点必须逐字命中（`"low": 25,` / `"high": 50,`），否则拒绝改写（fail-closed）
  - 幂等：已是 50/75 则报告「已是目标值」并退出 0
  - 逐份备份 .bak-<ts>-preReasoning
用法： patch_encoding_reasoning_budget.py [--dry]
"""
import glob
import os
import shutil
import sys
import time

DRY = "--dry" in sys.argv
ANCHOR_OLD = '    "low": 25,\n    "high": 50,\n'
TARGET_NEW = '    "low": 50,\n    "high": 75,\n'
ANCHOR_NEW = TARGET_NEW

cands = []
for pat in (
    os.path.expanduser("~/luz028/site-patches/encoding_dsv41.py"),
    os.path.expanduser("~/luz028/site-patches/mount/encoding_dsv41.py"),
):
    cands.extend(glob.glob(pat))

if not cands:
    raise SystemExit("找不到 encoding_dsv41.py（站点件）")

ts = time.strftime("%Y%m%d-%H%M%S")
rc = 0
for path in cands:
    s = open(path, encoding="utf-8").read()
    if ANCHOR_NEW in s and ANCHOR_OLD not in s:
        print(f"[skip] {path} 已是目标值 50/75")
        continue
    if ANCHOR_OLD not in s:
        print(f"[FAIL] {path} 锚点未命中（既不是旧值也不是新值）—— 拒绝改写")
        rc = 1
        continue
    if DRY:
        print(f"[dry ] {path} 锚点命中，将改写 low 25→50 / high 50→75")
        continue
    bak = f"{path}.bak-{ts}-preReasoning"
    shutil.copy2(path, bak)
    s2 = s.replace(ANCHOR_OLD, TARGET_NEW, 1)
    open(path, "w", encoding="utf-8").write(s2)
    chk = open(path, encoding="utf-8").read()
    ok = ANCHOR_NEW in chk and ANCHOR_OLD not in chk
    print(f"[{'ok  ' if ok else 'FAIL'}] {path} 备份={os.path.basename(bak)} 改写{'成功' if ok else '失败'}")
    rc |= 0 if ok else 1

sys.exit(rc)
