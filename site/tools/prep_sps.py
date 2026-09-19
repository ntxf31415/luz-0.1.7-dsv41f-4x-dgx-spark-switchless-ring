#!/usr/bin/env python3
"""为 Phase 3b 准备 .env.tp4：
1) NCCL 调试日志改落到 /state（该目录已挂进容器；/nccl-debug 在生产模式不挂）
2) EXTRA_DOCKER_ENV 追加 SGLANG_DSPARK_ENABLE_SPS_RECORD=1（剖面器采集 dspark_info 必需）
不改 start.sh，保持上游原样。
"""
import os
import re

p = os.path.expanduser('~/luz017/.env.tp4')
s = open(p, encoding='utf-8').read()
orig = s

s = s.replace('NCCL_DEBUG_FILE=/nccl-debug/nccl-%h-%p.log',
              'NCCL_DEBUG_FILE=/state/nccl-%h-%p.log')

m = re.search(r'^(EXTRA_DOCKER_ENV=")(.*)(")$', s, re.M)
if not m:
    raise SystemExit('找不到 EXTRA_DOCKER_ENV 行')
body = m.group(2)
if 'SGLANG_DSPARK_ENABLE_SPS_RECORD=1' not in body:
    body = body + ' SGLANG_DSPARK_ENABLE_SPS_RECORD=1'
s = s[:m.start()] + m.group(1) + body + m.group(3) + s[m.end():]

open(p, 'w', encoding='utf-8').write(s)
print('文件已变更:', s != orig)
print('NCCL_DEBUG_FILE 指向 /state:', 'NCCL_DEBUG_FILE=/state/' in s)
print('SPS_RECORD 已加入:', 'SGLANG_DSPARK_ENABLE_SPS_RECORD=1' in s)
