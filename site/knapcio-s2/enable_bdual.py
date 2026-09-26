#!/usr/bin/env python3
"""把 ~/knapcio/.env.tp4 切到 **B-dual**（本站目前最快配置，2026-09-26 实测）。

前提：`~/tr-abc/nccl-host-dual/` 已有自编的 dual-PCI-domain NCCL
（`nccl-2.30.7-dual-pci-domain.patch`，**已含** switchless-cycle）。构建见
`make_bdual_nccl.md` / KB《4DGX-环网最快配置-Bdual-20260926》§二。

相对 knapcio 原封配置，只动 6 处：
  1. NCCL_HOST_DIR      → 我们自编的 dual 库目录
  2. 取消注释           NCCL_SWITCHLESS_RING_ONLY / NCCL_ALGO=Ring / NCCL_P2P_LEVEL=SYS
  3. 取消注释           NCCL_IB_EXTENDED_IPV4_GIDS / PRESERVE_PCI_DOMAIN /
                        ROUTE_DIAGNOSTICS / QPS_PER_CONNECTION
  4. 站点块去覆盖       文件后半段有一处 `NCCL_SWITCHLESS_RING_ONLY=0`，**在 2 之后**，
                        不改就是静默关掉 switchless
  5. EXTRA 行大小写     `NCCL_ALGO=RING` → `Ring`（launcher 预检做精确串比较，大小写不对硬失败）
  6. （另需，非本脚本）`state-tp4/sdbench/{pr_matrix_v3.py,sd_protocol.py}` + `state-tp4/api-key`
                        —— 让 PR131K 门禁探针能在它的容器里跑

用法：python3 enable_bdual.py [--env PATH] [--lib DIR] [--dry-run]
幂等：重复运行不产生额外变化。
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

LIBS = "/home/spark/tr-abc/nccl-host-dual"
UNCOMMENT = [
    "NCCL_SWITCHLESS_RING_ONLY=1",
    "NCCL_ALGO=Ring",
    "NCCL_P2P_LEVEL=SYS",
    "NCCL_IB_EXTENDED_IPV4_GIDS=1",
    "NCCL_IB_PRESERVE_PCI_DOMAIN=1",
    "NCCL_IB_ROUTE_DIAGNOSTICS=1",
    "NCCL_IB_QPS_PER_CONNECTION=1",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(Path.home() / "knapcio/.env.tp4"))
    ap.add_argument("--lib", default=LIBS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    env = Path(a.env)
    if not env.is_file():
        print(f"[x] 找不到 {env}", file=sys.stderr)
        return 1
    if not (Path(a.lib) / "libnccl.so.2.30.7").is_file():
        print(f"[x] {a.lib}/libnccl.so.2.30.7 不存在 —— 先编 dual 库（见 docstring）", file=sys.stderr)
        return 1

    original = env.read_text()
    out, notes = [], []

    for ln in original.splitlines():
        s = ln.strip()

        # 1) 指向自编 dual 库
        if s.startswith("NCCL_HOST_DIR=") and "/nccl-host-dual" not in s:
            out.append(f"NCCL_HOST_DIR={a.lib}")
            notes.append(f"NCCL_HOST_DIR -> {a.lib}")
            continue

        # 4) 站点块的覆盖行（必须晚于 2，否则静默关闭）
        if s == "NCCL_SWITCHLESS_RING_ONLY=0":
            out.append("NCCL_SWITCHLESS_RING_ONLY=1")
            notes.append("站点块 NCCL_SWITCHLESS_RING_ONLY 0 -> 1")
            continue

        # 5) EXTRA 行的大小写（预检精确串比较）
        if ln.startswith("EXTRA_CONTAINER_ENV=") and "NCCL_ALGO=RING" in ln:
            out.append(ln.replace("NCCL_ALGO=RING", "NCCL_ALGO=Ring"))
            notes.append("EXTRA_CONTAINER_ENV: NCCL_ALGO RING -> Ring")
            continue

        # 2)+3) 取消注释（只动注释标记，不碰已生效的行）
        un = False
        for k in UNCOMMENT:
            if s == "#" + k or s == "# " + k:
                out.append(k)
                notes.append(f"取消注释 {k}")
                un = True
                break
        if un:
            continue

        out.append(ln)

    new = "\n".join(out) + "\n"
    changed = new != original

    print(f"env      : {env}")
    print(f"lib      : {a.lib}")
    print(f"改动     : {len(notes)} 处" + ("" if changed else "（已是 B-dual，幂等）"))
    for n in notes:
        print(f"  · {n}")

    # 自检：生效值必须只有一处定义且为期望值
    for key, want in [("NCCL_SWITCHLESS_RING_ONLY", "1"), ("NCCL_ALGO", "Ring")]:
        vals = re.findall(rf"^{key}=(\S+)", new, re.M)
        ok = vals and all(v == want for v in vals)
        print(f"  自检 {key}: {vals}  {'OK' if ok else '✗ 不一致'}")

    if a.dry_run:
        print("(--dry-run，未写回)")
        return 0
    if changed:
        bak = env.with_suffix(env.suffix + ".bak-enable-bdual")
        if not bak.exists():
            shutil.copy2(env, bak)
            print(f"备份     : {bak}")
        env.write_text(new)
        print("已写回")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
