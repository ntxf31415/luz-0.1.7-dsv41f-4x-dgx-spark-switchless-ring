#!/usr/bin/env python3
"""把 pr_matrix_v3.py 的填充换成高熵词表，产出 pr_matrix_v3_entropy.py。

动机：上游 issue MiaAI-Lab/DeepSeek-v4.1-Flash-DGX-Sparks#21 指出，
基准填充若无熵（他们的例子是单 token `" the"` 重复），所有 token 会命中同一个
Engram 行，于是基准测的是 Engram row store 的命中路径，而不是 prefill。
本变体把填充改成 ~400 个词、从 32 词词表随机抽取 —— 除填充外与原件逐字节相同，
其余口径（max_new_tokens=1、唯一 nonce、格间 flush、总吞吐）一律不动。
"""
import sys

SRC = "/state/sdbench/pr_matrix_v3.py"
DST = "/state/sdbench/pr_matrix_v3_entropy.py"

OLD = '''FILLER = ("Reference notes: the cache stores recently accessed entries. "
          "An implementation should maintain ordering, handle replacement and "
          "validate its invariants.\\n")'''

NEW = '''import random as _r
_r.seed(20260919)
_W = ("harbour lantern meadow copper violin orchard compass thistle ember granite "
      "willow saffron anchor quartz ledger falcon glacier tundra basalt cedar mosaic "
      "prism cobalt ivy jasper kelp loam nimbus onyx petal quill reed slate").split()
FILLER = " ".join(_r.choice(_W) for _ in range(400)) + "\\n"'''

src = open(SRC, encoding="utf-8").read()
if OLD not in src:
    sys.exit("!! 在 %s 里找不到 FILLER 锚点，原件可能已变，拒绝改写" % SRC)
open(DST, "w", encoding="utf-8").write(src.replace(OLD, NEW))
print("已写出 %s（除 FILLER 外与原件逐字节相同）" % DST)
