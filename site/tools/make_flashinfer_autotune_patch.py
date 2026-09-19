#!/usr/bin/env python3
"""生成 flashinfer_autotune.py 的站点补丁：不再因 per-rank 缓存不一致而删除缓存。

背景（2026-09-19 实测定位）：
  `_drop_diverged_autotune_cache()` 把四个 rank 各自缓存文件的摘要 all_gather，
  只要不一致就 `cache_path.unlink()` 删掉、全部重调。但本栈是 **TP4 / EP2**，
  每个 rank 拥有不同的专家分片 ⇒ **各自的 MoE GEMM 形状集天然不相交**
  （实测四份形状集交集为 0：rank0 是 (192,2304,320)、rank1 是 (64,2304,320)…）。
  ⇒ 该条件在 EP 分片下**永远不满足** ⇒ 缓存每次 boot 被删 ⇒ 全量重调 ⇒
  fused-MoE 的 tactic 每次重新抽签（计时的），实测同配置跨 boot 长 prefill 差 1.5 倍。

本补丁只做一件事：**保留判定与日志，去掉 unlink**。于是每个 rank 自己那份完整的
缓存得以留存，下次 boot 命中它需要的形状 ⇒ 不再重调 ⇒ tactic 被钉住。

⚠️ 安全性前提：**四份缓存必须各自完整**（各自含本 rank 需要的全部形状），否则会出现
"部分 rank 命中、部分 rank 去调优"，而调优走 TP 计时归约这个集合操作 ⇒ 挂死。
故首次启用前必须先确保 per-rank 缓存完整（见 canon 流程），并留存 known-good 快照。

用法： python3 make_flashinfer_autotune_patch.py <输出路径>
"""
import re
import sys

SRC_IN_IMAGE = ("/sgl-workspace/sglang/python/sglang/srt/model_executor/runner/"
                "flashinfer_autotune.py")

OLD = "    cache_path.unlink(missing_ok=True)\n"
NEW = (
    "    # [site patch 2026-09-19] 不删缓存。EP2 下各 rank 的 MoE 形状集本就不同，\n"
    "    # 四份摘要永远不可能一致；原逻辑每 boot 删缓存 -> 全量重调 -> tactic 重新抽签。\n"
    "    # 保留各 rank 自己那份完整缓存，下次 boot 才能命中。判定与日志保留以便观测。\n"
    "    log_info_on_rank0(logger, \"[site patch] keeping per-rank autotune caches\")\n"
)

def main():
    out = sys.argv[1]
    src = open(SRC_IN_IMAGE, encoding="utf-8").read()
    n = src.count(OLD)
    if n != 1:
        sys.exit("!! 锚点命中 %d 次（应为 1），镜像内该文件可能已变，拒绝改写" % n)
    open(out, "w", encoding="utf-8").write(src.replace(OLD, NEW))
    # 语法自检：补丁后的文件必须能编译
    import py_compile
    py_compile.compile(out, doraise=True)
    print("已写出 %s（anchor 1 处，py_compile 通过）" % out)

if __name__ == "__main__":
    main()
