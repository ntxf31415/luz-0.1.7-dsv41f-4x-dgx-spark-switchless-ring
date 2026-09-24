#!/usr/bin/env python3
"""把 start.sh 的「生产不持久化 autotune 选择」改成持久化（外科式，只挂 autotune 子目录）。

背景：SGLANG_CODE_MOUNTS=1（开发）挂宿主 ~/.cache；生产（=0）不挂，于是
flashinfer/TRT-LLM 的 autotune 结果只写在容器层，每次重建容器就丢 —— TRT-LLM
AutoTuner 于是在每次启动重新调优 fused-MoE GEMM 内核。调优是计时的 ⇒ 选型每次
重新抽签。2026-09-19 实测：同配置跨 boot 长 prefill 差 1.5 倍；b12x ON 那次因换掉
fused func 不走该路径，所以不抽签。

只挂 autotune 子目录而非整个 ~/.cache/sglang：镜像里那份含 387M 的 nv 缓存，
宿主那份只有 4K 且多出 35M triton —— 整体覆盖会丢 nv。

两处都要改（head 的 cache_mounts、worker 远程 heredoc 里的 CACHE_VOL），
且两处缩进与转义规则不同，故用精确锚点替换并逐条断言。
"""
import shutil
import sys

F = "/home/spark/luz017/start.sh"
BAK = F + ".bak-preAutotunePersist"

# ---------- ① head 侧：2 空格缩进，无转义 ----------
A_OLD = '  [[ "$SGLANG_CODE_MOUNTS" = 1 ]] && cache_mounts=(-v "$HOME/.cache:/root/.cache")'
A_NEW = ('  [[ "$SGLANG_CODE_MOUNTS" = 1 ]] && cache_mounts=(-v "$HOME/.cache:/root/.cache")\n'
         '  # 生产：只把 autotune 的选择结果持久化（外科式）。不挂 ⇒ 每次重建容器都重调优，\n'
         '  # 而 TRT-LLM AutoTuner 是计时的 ⇒ fused-MoE GEMM 选型每次重新抽签（2026-09-19 实测\n'
         '  # 同配置跨 boot 长 prefill 差 1.5 倍）。挂整个 ~/.cache/sglang 则丢镜像里 387M 的 nv 缓存。\n'
         '  [[ "$SGLANG_CODE_MOUNTS" != 1 ]] && cache_mounts=(\n'
         '    -v "$HOME/.cache/sglang/flashinfer/autotune:/root/.cache/sglang/flashinfer/autotune")')

# ---------- ② worker 侧：6/8 空格缩进，\" 与 \$ 带转义 ----------
B_OLD = '        CACHE_VOL=\\"-v \\$HOME/.cache:/root/.cache\\"'
B_NEW = (B_OLD + '\n'
         '      else\n'
         '        CACHE_VOL=\\"-v \\$HOME/.cache/sglang/flashinfer/autotune:/root/.cache/sglang/flashinfer/autotune\\"')

src = open(F, encoding="utf-8").read()
for name, old in (("head cache_mounts", A_OLD), ("worker CACHE_VOL", B_OLD)):
    n = src.count(old)
    if n != 1:
        sys.exit("!! 锚点 %s 命中 %d 次（应为 1），拒绝改写" % (name, n))

shutil.copy2(F, BAK)
open(F, "w", encoding="utf-8").write(src.replace(A_OLD, A_NEW).replace(B_OLD, B_NEW))

chk = open(F, encoding="utf-8").read()
assert chk.count("autotune:/root/.cache/sglang/flashinfer/autotune") == 2, "补丁未两处落地"
assert chk.count("  [[ \"$SGLANG_CODE_MOUNTS\" != 1 ]] && cache_mounts=(") == 1, "head 分支出错"
print("已写入 %s\n备份   %s" % (F, BAK))
