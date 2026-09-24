#!/usr/bin/env python3
"""把现役 .env.tp4 的 API_KEY 原样搬到新栈，避免新栈生成随机 key 导致下游 401。
只打印长度，不打印值。"""
import os
import re

OLD = os.path.expanduser('~/dsv41-4x-spark/.env.tp4')
NEW = os.path.expanduser('~/luz017/.env.tp4')

old = open(OLD, encoding='utf-8').read()
m = re.search(r'^API_KEY=(.*)$', old, re.M)
key = m.group(1).strip() if m else ''

s = open(NEW, encoding='utf-8').read()
if not re.search(r'^API_KEY=', s, re.M):
    raise SystemExit('新文件里没有 API_KEY= 行，中止')
open(NEW, 'w', encoding='utf-8').write(re.sub(r'^API_KEY=.*$', 'API_KEY=' + key, s, flags=re.M))
print(f'API_KEY 已从现役注入新栈，长度 {len(key)}')
