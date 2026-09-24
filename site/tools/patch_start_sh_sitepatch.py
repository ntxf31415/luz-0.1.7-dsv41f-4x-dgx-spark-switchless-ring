#!/usr/bin/env python3
"""把站点补丁文件 flashinfer_autotune.py 的生产挂载加进 start.sh（head + worker 两处）。

补丁内容见 make_flashinfer_autotune_patch.py：不再因 per-rank 缓存不一致而 unlink。
必须**四台都挂**：只挂 head 会让其余 rank 仍删自己的缓存 ⇒ 下次 boot 出现
「部分 rank 命中、部分去调优」⇒ 调优走 TP 计时归约集合 ⇒ 挂死（2026-09-19 已踩过）。
"""
import shutil
import sys

F = "/home/spark/luz017/start.sh"
BAK = F + ".bak-preSitePatchMount"

GUEST = ("/sgl-workspace/sglang/python/sglang/srt/model_executor/runner/"
         "flashinfer_autotune.py")

# head 侧（2 空格缩进、无转义）
A_OLD = ('    -v "$HOME/.cache/sglang/flashinfer/autotune:/root/.cache/sglang/flashinfer/autotune")\n')
A_NEW = ('    -v "$HOME/.cache/sglang/flashinfer/autotune:/root/.cache/sglang/flashinfer/autotune"\n'
         '    -v "$HOME/luz017/site-patches/flashinfer_autotune.py:' + GUEST + ':ro")\n')

# worker 侧（8 空格缩进、\" 与 \$ 带转义）
B_OLD = ('        CACHE_VOL=\\"-v \\$HOME/.cache/sglang/flashinfer/autotune:'
         '/root/.cache/sglang/flashinfer/autotune\\"\n')
B_NEW = ('        CACHE_VOL=\\"-v \\$HOME/.cache/sglang/flashinfer/autotune:'
         '/root/.cache/sglang/flashinfer/autotune'
         ' -v \\$HOME/luz017/site-patches/flashinfer_autotune.py:' + GUEST + ':ro\\"\n')

src = open(F, encoding="utf-8").read()
for name, old in (("head mount", A_OLD), ("worker CACHE_VOL", B_OLD)):
    n = src.count(old)
    if n != 1:
        sys.exit("!! 锚点 %s 命中 %d 次（应为 1），拒绝改写" % (name, n))

shutil.copy2(F, BAK)
open(F, "w", encoding="utf-8").write(src.replace(A_OLD, A_NEW).replace(B_OLD, B_NEW))

chk = open(F, encoding="utf-8").read()
cnt = chk.count("site-patches/flashinfer_autotune.py")
assert cnt == 2, "补丁挂载应两处，实际 %d" % cnt
print("已写入 %s\n备份   %s" % (F, BAK))
