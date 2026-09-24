#!/usr/bin/env python3
"""移植上游 sgl-project/sglang#40208：把融合 hc_combine_norm 的适用行数从 ≤8 扩到 9–96。

背景：本栈的融合路径只在 `m ≤ 8`（c1 的 verify 行数）启用，**9–96 行**（c2–c16）回落
到 unfused 的 combine + RMSNorm 两次核。上游 #40208 把 guard 扩到 96 行，并给核加了
`PARTS` 参数（行少时多切列、行多时少切列）以免 CTAs 过度细分。

⚠️ 与上游的差异（本脚本按**我们的**树写，不是照抄 patch）：
- 我们的 `hc_combine_norm.py` 比上游 PR 的 base **旧一步**：没有 4096–65536 那档，
  故只把上界扩到 96，不引入 prefill 档。
- 我们的 `deepseek_v4.py` 是 **LuZ overlay 版**：判据写成了 `tiny` 变量，且 `tiny`
  同时被 stats_stream 的先后顺序复用（2741/2768）。**只改融合判据那一处**，不动
  `tiny` 本身，避免顺带改掉 stream 重叠语义。

用法（在 head 上跑）：
  patch_hc_combine_96.py <src/hc_combine_norm.py> <src/deepseek_v4.py> <out_dir>
"""
import argparse
import os
import re
import sys

KERNEL_EDITS = [
    (
        r"^def _hc_combine_norm\(X, P, W, Y, SX: tl\.constexpr, SP: tl\.constexpr, "
        r"EPS: tl\.constexpr\):$",
        "def _hc_combine_norm(\n"
        "    X,\n"
        "    P,\n"
        "    W,\n"
        "    Y,\n"
        "    SX: tl.constexpr,\n"
        "    SP: tl.constexpr,\n"
        "    EPS: tl.constexpr,\n"
        "    PARTS: tl.constexpr,\n"
        "):",
        "核函数签名加 PARTS",
    ),
    (
        r"^(\s*)mask = \(h >= part \* 1280\) & \(h < \(part \+ 1\) \* 1280\)$",
        r"\1mask = (h >= part * (5120 // PARTS)) & (h < (part + 1) * (5120 // PARTS))",
        "列切分随 PARTS 变",
    ),
    (
        r"^(\s*)assert 0 < m <= 8 and x\.shape == \(m, 20480\)$",
        r"\1assert 0 < m <= 96 and x.shape == (m, 20480)",
        "断言上界 8 → 96",
    ),
    (
        r"^(\s*)_hc_combine_norm\[\(m, 4\)\]\(\n"
        r"\s*x, pre, weight, y, x\.stride\(0\), pre\.stride\(0\), eps, num_warps=8\n"
        r"\s*\)$",
        "\\1parts = 4 if m <= 8 else (2 if m <= 48 else 1)\n"
        "\\1_hc_combine_norm[(m, parts)](\n"
        "\\1    x, pre, weight, y, x.stride(0), pre.stride(0), eps, parts, num_warps=8\n"
        "\\1)",
        "按行数选 PARTS",
    ),
    (
        r'"""Fuse four-stream combine and RMSNorm for small BF16 batches of width 5120\."""',
        '"""Fuse four-stream combine and RMSNorm for BF16 batches of up to 96 rows, '
        'width 5120."""',
        "文档串跟上",
    ),
]

MODEL_EDITS = [
    (
        r"^(\s*)and tiny$",
        r"\1and (tiny or 9 <= x.shape[0] <= 96)",
        "融合判据扩到 96 行（不动 tiny 本身）",
    ),
]


def apply_edits(src, edits, tag):
    out = src
    for pattern, repl, label in edits:
        rx = re.compile(pattern, re.M)
        hits = rx.findall(out)
        if len(hits) != 1:
            print(f"[{tag}] 锚点「{label}」命中 {len(hits)} 次（应为 1）—— 树已变，拒绝生成",
                  file=sys.stderr)
            return None
        out = rx.sub(repl, out, count=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src_kernel")
    ap.add_argument("src_model")
    ap.add_argument("out_dir")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    results = []
    for src_path, edits, tag, out_name in (
        (args.src_kernel, KERNEL_EDITS, "kernel", "hc_combine_norm.py"),
        (args.src_model, MODEL_EDITS, "model", "deepseek_v4.py"),
    ):
        src = open(src_path).read()
        already = "PARTS" in src if tag == "kernel" else "9 <= x.shape[0] <= 96" in src
        if already:
            print(f"[{tag}] 已是补丁版，跳过")
            continue
        out = apply_edits(src, edits, tag)
        if out is None:
            return 2
        dst = os.path.join(args.out_dir, out_name)
        open(dst, "w").write(out)
        results.append((dst, len(src), len(out)))
        print(f"[{tag}] 已生成 {dst}（{len(src)} → {len(out)} 字节）")

    if not results:
        return 0

    import py_compile
    for dst, _, _ in results:
        py_compile.compile(dst, doraise=True)
    print("语法自检通过")
    print("\n挂载（head + 三 worker 都要）：")
    print('  -v "$HOME/luz017/site-patches/hc_combine_norm.py:'
          '/sgl-workspace/sglang/python/sglang/kernels/ops/layernorm/hc_combine_norm.py:ro"')
    print('  -v "$HOME/luz017/site-patches/deepseek_v4.py:'
          '/sgl-workspace/sglang/python/sglang/srt/models/deepseek_v4.py:ro"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
