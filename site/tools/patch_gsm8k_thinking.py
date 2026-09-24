#!/usr/bin/env python3
"""把 GSM8K harness 的 thinking 开关钉死，不再隐式依赖引擎默认值。

背景：`bench/gates_suite.py`（`ask()` 默认 `thinking=False`）、`scripts/gate.sh`
（三处 payload 写死）与 SD-1 性能口径（`benchmarks/sd_protocol.py`）都**显式**声明了
思考开关，唯独 `bench/gsm8k_dsv41.py` 没有 —— 它的 payload 里没有
`chat_template_kwargs`，思考与否由引擎默认值（`SGLANG_DEFAULT_THINKING`）兜底，
而脚本默认 `BASE` 指向网关、中间层可以改写该默认值 ⇒ 一旦默认翻转，GSM8K 基线
会**静默漂移**且不报错。

上游同款修复见 luxingcom/LuZ-0.1.7 PR #1（我的措辞与它一致）。本脚本是本站的
落地手段：上游树零改动，改动只发生在**运行时副本**上，可重复、幂等。

用法：
  patch_gsm8k_thinking.py <path/to/gsm8k_dsv41.py> [--dry-run]
"""
import argparse
import re
import shutil
import sys
import time

ANCHOR = re.compile(r'^(\s*)"temperature":\s*TEMPERATURE,\s*$', re.M)
# \g<0> = 整行原样保留，只在其前插入新键
INJECT = '\\1"chat_template_kwargs": {"thinking": False},\n\\g<0>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = open(args.path).read()
    if '"chat_template_kwargs"' in src:
        print("已钉死，无需改动")
        return 0
    m = ANCHOR.search(src)
    if not m:
        print("找不到锚点（\"temperature\": TEMPERATURE,）—— 上游可能已改版，人工确认后再改",
              file=sys.stderr)
        return 2

    out = ANCHOR.sub(INJECT, src, count=1)
    if out == src:
        print("替换无效果，中止", file=sys.stderr)
        return 2
    if args.dry_run:
        print("dry-run：将插入 chat_template_kwargs（未落盘）")
        return 0

    bak = f"{args.path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(args.path, bak)
    open(args.path, "w").write(out)
    print(f"已钉死 thinking=off；备份 {bak}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
