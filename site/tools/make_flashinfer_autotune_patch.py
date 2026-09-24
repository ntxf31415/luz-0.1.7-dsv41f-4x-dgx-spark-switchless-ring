#!/usr/bin/env python3
"""生成 flashinfer_autotune.py 的站点补丁（v14 版，LuZ 0.2.8 起）。

背景（2026-09-19 定位，2026-09-24 随 0.2.8 迁移重写）：
  `_drop_diverged_autotune_cache()` 把四个 rank 各自缓存文件的摘要 all_gather。
  本栈是 **TP4 / EP2**，每个 rank 拥有不同的专家分片 ⇒ **各自的 MoE GEMM 形状集天然
  不相交**（实测四份形状集交集为 0：rank0 是 (192,2304,320)、rank1 是 (64,2304,320)…）
  ⇒ 四份摘要永远不一致。

  v14（0.2.8 起）把「不一致」分成两种处置：
    ① `counts[best] < len(digests)//2+1`（4 rank 需 3 票）⇒ 记日志后
       `cache_path.unlink()`（日志原文 "treating as cold start"）；
    ② 无人持缓存（文件缺失/损坏）⇒ 同样 unlink 后重调。
  EP2 下永远落进 ① ⇒ **每 boot 删缓存 ⇒ 全量重调 ⇒ fused-MoE 的 tactic 每次重新
  抽签（计时的），实测同配置跨 boot 长 prefill 差 1.5 倍。**

本补丁只改 ①：**保留判定与日志，去掉那一处 unlink**，于是每个 rank 自己那份完整
缓存得以留存，下次 boot 命中它需要的形状 ⇒ 不再重调 ⇒ tactic 被钉住。
② 处**有意不动** —— 那里本来就没有可用缓存，unlink 只是清掉损坏文件；删掉它反而
可能让下游加载器读到坏 JSON。

⚠️ 安全性前提：**四份缓存必须各自完整**（各自含本 rank 需要的全部形状），否则会出现
"部分 rank 命中、部分去调优"，而调优走 TP 计时归约这个集合操作 ⇒ 挂死。
故首次启用前必须先确保 per-rank 缓存完整（见 canon 流程），并留存 known-good 快照。

用法： python3 make_flashinfer_autotune_patch.py <输入文件> <输出路径>
"""
import py_compile
import sys

# v14 里两处 unlink 的缩进不同：12 空格那处在「真多数不足」分支（本补丁目标），
# 4 空格那处在「无人持缓存」分支（有意保留）。缩进即身份，故按缩进区分。
ANCHOR_DROP = "            cache_path.unlink(missing_ok=True)\n"      # 12 空格：本补丁改
ANCHOR_COLD = "    cache_path.unlink(missing_ok=True)\n"              # 4 空格：不动
NEEDLE = "counts[best] < _need"

REPLACEMENT = (
    "            # [site patch 2026-09-24] EP2 下四 rank 的 MoE 形状集天然不相交 ⇒\n"
    "            # 四份摘要永远凑不出真多数 ⇒ 原逻辑在此 unlink ⇒ 每 boot 全量重调 ⇒\n"
    "            # tactic 重新抽签（实测同配置跨 boot 长 prefill 差 1.5 倍）。\n"
    "            # 保留各 rank 自己那份完整缓存，下次 boot 才能命中。\n"
    "            # 真·无人持缓存/损坏的清理仍走本函数末尾那处（有意不对其动手）。\n"
    "            log_info_on_rank0(\n"
    "                logger,\n"
    "                \"[site patch] keeping per-rank autotune caches: a true \"\n"
    "                \"majority is impossible under EP2 (disjoint shape sets).\",\n"
    "            )\n"
)


def main():
    src_path, out_path = sys.argv[1], sys.argv[2]
    src = open(src_path, encoding="utf-8").read()
    lines = src.splitlines(keepends=True)

    # 按「整行相等」判定：12 空格行本身含 4 空格串，用子串计数会误判。
    n_drop = sum(1 for l in lines if l == ANCHOR_DROP)
    n_cold = sum(1 for l in lines if l == ANCHOR_COLD)
    if n_drop != 1:
        sys.exit("!! 12 空格锚点命中 %d 次（应为 1），镜像内该文件可能已变，拒绝改写" % n_drop)
    if n_cold != 1:
        sys.exit("!! 4 空格锚点命中 %d 次（应为 1）——文件形态与预期不符，拒绝改写" % n_cold)
    if src.count(NEEDLE) == 0:
        sys.exit("!! 未见到 %s（真多数门）——v14 语义已变，拒绝改写" % NEEDLE)

    # 只在「真多数不足」分支里替换：确认目标锚点之前最近的门控就是该判断。
    idx = src.index(ANCHOR_DROP)
    if NEEDLE not in src[:idx][-600:]:
        sys.exit("!! 目标锚点前 600 字符内没有 `%s`——错分支，拒绝改写" % NEEDLE)

    out = src.replace(ANCHOR_DROP, REPLACEMENT)
    open(out_path, "w", encoding="utf-8").write(out)
    py_compile.compile(out_path, doraise=True)   # 语法自检：补丁后必须能编译
    print("已写出 %s（12 空格锚点 1 处替换，4 空格锚点保留，py_compile 通过）" % out_path)


if __name__ == "__main__":
    main()
