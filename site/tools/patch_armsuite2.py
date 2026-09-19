#!/usr/bin/env python3
"""armsuite.sh 站点化补丁 2：第 3 阶段改用宿主侧 prefill_distinct.py。
镜像内那份的 Authorization 是占位符 "Bearer YOUR_API_KEY"，开了鉴权后必 401；
我们站点那份带真 key。每次重启容器后 /tmp 会清空，故在阶段开始时 docker cp 一次。
"""
import os
import re

p = os.path.expanduser('~/luz017/scripts/verify/armsuite.sh')
s = open(p, encoding='utf-8').read()

old = '''for T in 8000 32000 100000; do
  docker exec dsv41-head python3 /opt/dsv41/scripts/verify/prefill_distinct.py "$T" 1 2>&1 \\
    | tee -a "$OUT/prefill.txt"
done'''
new = '''# 镜像内那份的 key 是占位符，用宿主侧带真 key 的副本（容器重建后 /tmp 会清空，故每次拷）
docker cp "$ROOT/scripts/verify/prefill_distinct.py" dsv41-head:/tmp/prefill_distinct.py
for T in 8000 32000 100000; do
  docker exec dsv41-head python3 /tmp/prefill_distinct.py "$T" 1 2>&1 \\
    | tee -a "$OUT/prefill.txt"
done'''

if old not in s:
    raise SystemExit('未找到阶段 3 的原文，未改动')
s = s.replace(old, new)
open(p, 'w', encoding='utf-8').write(s)
print('armsuite.sh 阶段 3 已改为使用宿主侧 prefill_distinct.py')
