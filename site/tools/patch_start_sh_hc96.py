#!/usr/bin/env python3
"""把 #40208 移植件的两个文件挂进容器（head + worker 两处都要）。

`start.sh` 的站点补丁挂载是**硬编码的单文件**（autotune 那条），没有通用 map。本脚本
沿用同一形式再加两条。定位方式：按唯一子串找到目标行，再改行尾 —— **不整行做正则**
（整行正则会被不可见差异咬）。改动前自动备份，锚点不唯一即拒绝。

用法（在 head 上跑）：
  patch_start_sh_hc96.py <path/to/start.sh>
"""
import argparse
import shutil
import sys
import time

KERNEL_SRC, KERNEL_DST = ("hc_combine_norm.py",
                          "/sgl-workspace/sglang/python/sglang/kernels/ops/layernorm/hc_combine_norm.py")
MODEL_SRC, MODEL_DST = ("deepseek_v4.py",
                        "/sgl-workspace/sglang/python/sglang/srt/models/deepseek_v4.py")

HEAD_NEEDLE = '    -v "$HOME/luz017/site-patches/flashinfer_autotune.py:'   # head 侧挂载行
WORKER_NEEDLE = 'CACHE_VOL='                                              # worker 侧那一行
WORKER_SUB = '/sgl-workspace/sglang/python/sglang/srt/model_executor/runner/flashinfer_autotune.py:ro'


def find_unique(lines, pred, tag):
    hits = [i for i, l in enumerate(lines) if pred(l)]
    if len(hits) != 1:
        print(f"[{tag}] 候选行 {len(hits)} 条（应为 1）—— 拒绝改", file=sys.stderr)
        return None
    return hits[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    args = ap.parse_args()

    src = open(args.path).read()
    if "hc_combine_norm.py:" in src:
        print("已挂载过，跳过")
        return 0

    lines = src.splitlines(keepends=True)
    head_i = find_unique(lines, lambda l: l.startswith(HEAD_NEEDLE), "head")
    work_i = find_unique(lines, lambda l: "CACHE_VOL=" in l and WORKER_SUB in l, "worker")
    if head_i is None or work_i is None:
        return 2

    hl = lines[head_i].rstrip("\n")
    if not hl.endswith('")'):
        print(f"[head] 目标行结尾不是 '\")'：{hl[-12:]!r} —— 拒绝改", file=sys.stderr)
        return 2
    lines[head_i] = (hl[:-1] + "\n"
                     f'    -v "$HOME/luz017/site-patches/{KERNEL_SRC}:{KERNEL_DST}:ro"\n'
                     f'    -v "$HOME/luz017/site-patches/{MODEL_SRC}:{MODEL_DST}:ro")\n')

    wl = lines[work_i].rstrip("\n")
    tail = '\\"'                        # worker 那行**末尾的闭合引号**（`:ro` 属于上一条挂载，不能一起吃）
    if not wl.endswith(tail):
        print(f"[worker] 目标行结尾不是 {tail!r}：{wl[-14:]!r} —— 拒绝改", file=sys.stderr)
        return 2
    # 新挂载必须插在闭合引号**之前**，否则字符串提前闭合 ⇒ 生成到 worker 的
    # bash -c 出现引号不配对（2026-09-19 首次尝试即踩：行 40 unmatched "）
    lines[work_i] = (wl[:-len(tail)]
                     + f' -v \\$HOME/luz017/site-patches/{KERNEL_SRC}:{KERNEL_DST}:ro'
                     + f' -v \\$HOME/luz017/site-patches/{MODEL_SRC}:{MODEL_DST}:ro'
                     + tail + "\n")
    if lines[work_i].count('\\"') != 2:
        print(f"[worker] 自检不过（转义引号 {lines[work_i].count(chr(92) + chr(34))} 个，应为 2）"
              "—— 拒绝落盘", file=sys.stderr)
        return 2

    out = "".join(lines)
    bak = f"{args.path}.bak-{time.strftime('%Y%m%d-%H%M%S')}-preHc96"
    shutil.copy2(args.path, bak)
    open(args.path, "w").write(out)
    print(f"已在 head 行 {head_i + 1}、worker 行 {work_i + 1} 各挂两条补丁；备份 {bak}")
    print("生效需重建容器（下次 start.sh serve）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
