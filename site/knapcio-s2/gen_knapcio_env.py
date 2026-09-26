#!/usr/bin/env python3
"""为 knapcio 栈生成 ~/knapcio/.env.tp4：模板 + 我们站点值 + 环网适配。

环网适配要点（2026-09-26）：
  * 不启它 launcher 的 NCCL_SWITCHLESS_RING_ONLY（那条要 sparkring patched NCCL），
    走默认分支：NCCL_HOST_DIR 指向我们宿主已有的 LuZ ring-only 库。
  * 我们那份库依赖 **per-rank** NCCL_IB_PEER_HCA（由 PEER_HCA_RANK<n> 注入）；
    它 launcher 不注入 ⇒ 另用 patch_launcher_peer_hca.py 打在它的 start.sh 上。
  * 生产 EXTRA 行去掉 RoCE 系（它 docs：环网上要 SGLANG_ROCE_ALLREDUCE=0），补 NCCL_ALGO=RING / GID=-1。
"""
import re

SRC = ".env.tp4.example"
DST = ".env.tp4"

SITE = {
    "HEAD_IP": "192.168.50.55",
    "WORKER_IPS": '"192.168.50.56 192.168.50.58 192.168.50.57"',
    "WORKER_HOSTS": '"192.168.50.56 192.168.50.58 192.168.50.57"',
    "WORKER_USER": "spark",
    "SSH_IDENTITY": "$HOME/.ssh/id_ed25519",
    "IB_HCA": "rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1",
    "NCCL_HOST_DIR": "/opt/nccl-ringonly",
    "MODEL_DIR": "/home/spark/models/DeepSeek-V4.1-Flash",
    "IMAGE": "dsv41-4x-spark:knapcio",
    "NFS_SHARE": "0",
    "EP_SIZE": "1",
    "ENGRAM_DIR": "$HOME/dsv41-engram",
    "WORKER_ENGRAM_DIR": "/home/spark/dsv41-engram",
    "WORKER_DIR": "/home/spark/knapcio",
    "PORT": "8888",
    "BUILD_DOCKERFILE": "Dockerfile.canary-roce",
}

DROP_PREFIX = ("SGLANG_ROCE_ALLREDUCE", "SGLANG_ROCE_MAX_SIZE",
               "B12X_ROCE_HCA", "B12X_ROCE_CACHE_DIR", "DSV41_ROCE_GATHER")
ADD = ["NCCL_ALGO=RING", "NCCL_IB_GID_INDEX_FORCE=-1"]


def setk(lines, k, v):
    for i, l in enumerate(lines):
        if l.startswith(k + "="):
            lines[i] = "%s=%s" % (k, v)
            return
    lines.append("%s=%s" % (k, v))


def main():
    lines = open(SRC, encoding="utf-8").read().split("\n")
    for k, v in SITE.items():
        setk(lines, k, v)

    hit = False
    for i, l in enumerate(lines):
        if l.startswith("#EXTRA_CONTAINER_ENV=") and "SGLANG_ROCE_ALLREDUCE=1" in l \
                and "DSV41_MOE_B12X_NEXT_DETERMINISTIC=1" in l:
            body = l[len('#EXTRA_CONTAINER_ENV="'):].rstrip('"')
            keep = [t for t in body.split() if not t.startswith(DROP_PREFIX)]
            keep += ADD
            lines[i] = 'EXTRA_CONTAINER_ENV="' + " ".join(keep) + '"'
            hit = True
            print("生产 EXTRA 行启用：去 RoCE、加 ring 参数，共 %d 项" % len(keep))
            break
    if not hit:
        raise SystemExit("!! 没找到生产 EXTRA 行（模板变了？）")

    open(DST, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("已写", DST)
    for k in ("HEAD_IP", "IMAGE", "EP_SIZE", "NCCL_HOST_DIR", "NFS_SHARE", "WORKER_DIR"):
        for l in lines:
            if l.startswith(k + "="):
                print("  %s" % l[:110])
                break


if __name__ == "__main__":
    main()
