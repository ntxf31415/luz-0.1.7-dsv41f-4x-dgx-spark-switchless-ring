#!/usr/bin/env python3
"""把「新 boot 跑一次性能门禁」挂进 dsv41-monitor-head.sh。

为什么挂在 monitor：门禁要覆盖的失效模式是「某次重启落到慢档而无人知道」。
靠人记得手动跑就不算门禁。monitor 本来就在 60s 循环做健康检查 —— 但它查不出
慢档（容器 healthy、/health 200 都正常）。所以在健康分支里加一条：**容器 ID 变了
（= 新 boot）就跑一次 perf-gate**，后台起、不阻塞健康检查。

两处改动，改前备份，改后逐条断言。
"""
import shutil
import sys

F = "/home/spark/luz017/scripts/dsv41-monitor-head.sh"
BAK = F + ".bak-prePerfGate"

A_OLD = 'MAINT_FLAG="$ROOT/state-tp4/maintenance.flag"\n'
A_NEW = ('MAINT_FLAG="$ROOT/state-tp4/maintenance.flag"\n'
         '# 性能门禁状态：存上次已门禁的容器 ID；ID 变即新 boot，需重跑一次\n'
         'GATE_STATE="$ROOT/state-tp4/.perf-gate-container-id"\n')

B_OLD = '  if [ "$ok" = 1 ]; then FAILS=0; sleep 60; continue; fi\n'
B_NEW = ('  if [ "$ok" = 1 ]; then\n'
         '    FAILS=0\n'
         '    # 新 boot → 跑一次性能门禁。健康检查看不出「落慢档」，必须显式测。\n'
         '    # 后台起：门禁约 2.5 分钟，不能阻塞健康检查循环。\n'
         '    _cid=$(docker inspect -f \'{{.Id}}\' "$NAME" 2>/dev/null || echo none)\n'
         '    if [ -n "$_cid" ] && [ "$(cat "$GATE_STATE" 2>/dev/null)" != "$_cid" ]; then\n'
         '      echo "$_cid" > "$GATE_STATE" 2>/dev/null || true\n'
         '      setsid nohup bash "$ROOT/scripts/perf-gate.sh" \\\n'
         '        >> "$ROOT/logs-tp4/perf-gate.log" 2>&1 < /dev/null &\n'
         '    fi\n'
         '    sleep 60; continue\n'
         '  fi\n')

src = open(F, encoding="utf-8").read()
for name, old in (("MAINT_FLAG", A_OLD), ("健康分支", B_OLD)):
    n = src.count(old)
    if n != 1:
        sys.exit("!! 锚点 %s 命中 %d 次（应为 1），拒绝改写" % (name, n))

shutil.copy2(F, BAK)
open(F, "w", encoding="utf-8").write(src.replace(A_OLD, A_NEW).replace(B_OLD, B_NEW))

chk = open(F, encoding="utf-8").read()
assert chk.count("perf-gate.sh") == 1, "门禁调用未落地"
assert chk.count("GATE_STATE=") == 2, "GATE_STATE 定义/使用不成对"
print("已写入 %s\n备份   %s" % (F, BAK))
