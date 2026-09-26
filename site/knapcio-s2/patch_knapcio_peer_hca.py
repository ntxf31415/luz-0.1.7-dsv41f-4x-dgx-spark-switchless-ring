#!/usr/bin/env python3
"""给 knapcio launcher 注入 per-rank NCCL_IB_PEER_HCA（环网必需）。

为什么：我们复用的是宿主 LuZ ring-only NCCL，它依赖 per-rank 的 NCCL_IB_PEER_HCA
（`<对端rank>=<本机HCA对>`）。LuZ 的 launcher 从 `PEER_HCA_RANK<n>` 注入，**knapcio 的
launcher 没有这套**（它的模板里也没有 PEER_HCA 键）⇒ 我们补两处：

  * head（rank0）：容器参数 `_a` 里加 -e NCCL_IB_PEER_HCA=$PEER_HCA_RANK0
  * worker（rank≠0）：`worker_env_lines()` 里按传入的 $rank 加同项

锚点断言 + 幂等 + 备份；失败即拒绝改写（不改判据，只加一注入）。
"""
import re
import shutil
import sys
import time

P = "start.sh"
HEAD_ANCHOR = '    _a+=(-v "$NCCL_HOST_DIR:$NCCL_CONTAINER_DIR:ro" -e "LD_LIBRARY_PATH=$NCCL_CONTAINER_DIR")'
WORKER_ANCHOR = '  for _kv in ${EXTRA_CONTAINER_ENV:-}; do _extra_env+=" -e $(printf \'%q\' "$_kv")"; done'
HEAD_ADD = ('\n  # [站点补丁] ring-only NCCL 需要 per-rank 对端 HCA 映射（等价于 LuZ launcher 的做法）\n'
            '  [[ -n "${PEER_HCA_RANK0:-}" ]] && _a+=(-e "NCCL_IB_PEER_HCA=$PEER_HCA_RANK0")')
WORKER_ADD = ('\n  # [站点补丁] per-rank 对端 HCA（worker 侧；rank 由调用方传入）\n'
              '  local _phv="PEER_HCA_RANK${rank}"; [[ -n "${!_phv:-}" ]] && '
              '_extra_env+=" -e NCCL_IB_PEER_HCA=$(printf \'%q\' "${!_phv}")"')

s = open(P, encoding="utf-8").read()
if "NCCL_IB_PEER_HCA" in s:
    print("[skip] 已打过补丁")
    sys.exit(0)

n_head = s.count(HEAD_ANCHOR)
n_work = s.count(WORKER_ANCHOR)
if n_head != 1 or n_work != 1:
    raise SystemExit("锚点未命中（head=%d worker=%d）—— 拒绝改写" % (n_head, n_work))

shutil.copy2(P, P + ".bak-%s-prePeerHca" % time.strftime("%Y%m%d-%H%M%S"))
s = s.replace(HEAD_ANCHOR, HEAD_ANCHOR + HEAD_ADD, 1)
s = s.replace(WORKER_ANCHOR, WORKER_ANCHOR + WORKER_ADD, 1)
open(P, "w", encoding="utf-8").write(s)

chk = open(P, encoding="utf-8").read()
ok = chk.count("NCCL_IB_PEER_HCA") == 2
print("[%s] 已注入 per-rank NCCL_IB_PEER_HCA（2 处）" % ("ok  " if ok else "FAIL"))
sys.exit(0 if ok else 1)
