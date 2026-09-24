#!/usr/bin/env python3
"""merge_pr_v3_batches.py — 把分批跑出的 pr_matrix_v3.py 产物合并成一个归档目录。

为什么要合并
------------
`pr_matrix_v3.py` 每次调用都会**重写** summary.json，里面只含本次 invocation 跑过的格
（`summaries = []` 在 main() 开头）。而本站锥形网格不是笛卡尔积——同一个尺寸只跑部分并发档
——所以必须分批发 SIZES/CONCS，跑完再合并。直接三批写同一个 OUT_DIR 会只剩最后一批。

合并出的目录布局对齐 `render_pr_v3_tables.py` 的期望：
    <out>/summary.json           合并后的 _meta + cells
    <out>/raw/*-c*-w0.json       各格逐流记录（渲染器的并发列从这里重算）

用法：
    merge_pr_v3_batches.py --out <归档目录> <批次目录> [<批次目录> ...]
"""
import argparse
import glob
import json
import os
import shutil
import sys

# 本站 §1.3 锥形网格的尺寸顺序（渲染器按这个顺序出行；与 CFG 里的分批一致）
SIZES = [512, 2048, 8192, 32768, 131072, 524288]
CONCS = [1, 2, 4, 8, 16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="合并后的归档目录")
    ap.add_argument("batches", nargs="+", help="各批次的 OUT_DIR")
    ap.add_argument("--expect", type=int, default=None,
                    help="期望格数；实际不符则非零退出（缺格要 explicitness，不能静默）")
    args = ap.parse_args()

    raw_dir = os.path.join(args.out, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    cells, meta, absent = {}, None, []
    for b in args.batches:
        sp = os.path.join(b, "summary.json")
        if not os.path.exists(sp):
            absent.append(b)
            continue
        with open(sp, encoding="utf-8") as fh:
            doc = json.load(fh)
        if meta is None:
            meta = dict(doc.get("_meta", {}))
        for c in doc.get("cells", []):
            key = (c["input_tokens"], c["concurrency"])
            if key in cells:
                print("  警告：格 %s 重复出现，后一批覆盖前一批" % (key,), file=sys.stderr)
            cells[key] = c
        for f in glob.glob(os.path.join(b, "*-c*-w0.json")):
            shutil.copy2(f, os.path.join(raw_dir, os.path.basename(f)))

    if absent:
        print("!! 以下批次目录没有 summary.json（跑挂了？）：%s" % absent, file=sys.stderr)
        return 2

    meta = meta or {}
    meta.update({
        "protocol_id": "PR-V3",
        "sizes": SIZES,
        "concurrencies": CONCS,
        "grid": "conical (site §1.3): 512/2048/8192/32768 x C1-16 + 131072 x C1/2/4 + 524288 x C1",
        "merged_batches": [os.path.basename(b.rstrip("/")) for b in args.batches],
        "cell_count": len(cells),
    })

    # 网格外的尺寸排在末尾并告警，而不是崩在 SIZES.index 上——批次跑错尺寸时
    # 要看到明确的提示，不是一条 ValueError 栈。
    off = sorted({c["input_tokens"] for c in cells.values()} - set(SIZES))
    if off:
        print("  警告：以下尺寸不在本站 §1.3 网格内，排在表尾：%s" % off, file=sys.stderr)

    def sort_key(c):
        s = c["input_tokens"]
        return (SIZES.index(s) if s in SIZES else len(SIZES), s, c["concurrency"])

    ordered = sorted(cells.values(), key=sort_key)
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"_meta": meta, "cells": ordered}, fh, ensure_ascii=False, indent=2)

    n_raw = len(glob.glob(os.path.join(raw_dir, "*-c*-w0.json")))
    print("合并 %d 格（逐流文件 %d 个）→ %s" % (len(cells), n_raw, args.out))
    if n_raw != len(cells):
        print("!! 格数与逐流文件数不一致 —— 渲染器会在 width 上 KeyError", file=sys.stderr)
        return 3
    if args.expect is not None and len(cells) != args.expect:
        print("!! 期望 %d 格，实际 %d 格" % (args.expect, len(cells)), file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
