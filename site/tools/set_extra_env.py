#!/usr/bin/env python3
"""向 ~/luz017/.env.tp4 的 EXTRA_DOCKER_ENV 行追加/移除一个 env 项。
用法: set_extra_env.py KEY=VALUE        # 追加（幂等）
      set_extra_env.py --remove KEY     # 移除
"""
import os
import re
import sys

p = os.path.expanduser('~/luz017/.env.tp4')
s = open(p, encoding='utf-8').read()

m = re.search(r'^(EXTRA_DOCKER_ENV=")(.*)(")$', s, re.M)
if not m:
    raise SystemExit('找不到 EXTRA_DOCKER_ENV 行')
items = m.group(2).split()

if sys.argv[1] == '--remove':
    key = sys.argv[2]
    items = [i for i in items if not i.startswith(key + '=')]
    action = f'移除 {key}'
else:
    kv = sys.argv[1]
    key = kv.split('=')[0]
    items = [i for i in items if not i.startswith(key + '=')]
    items.append(kv)
    action = f'设置 {kv}'

s = s[:m.start()] + m.group(1) + ' '.join(items) + m.group(3) + s[m.end():]
open(p, 'w', encoding='utf-8').write(s)
print(action, '-> 完成；EXTRA_DOCKER_ENV 现有', len(items), '项')
print('校验:', [i for i in items if i.startswith(('SGLANG_SIMULATE', 'SGLANG_DSPARK_ENABLE', 'EP_SUPPRESS'))])
