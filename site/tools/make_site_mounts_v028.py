#!/usr/bin/env python3
"""把站点补丁的逐文件挂载烘进 **LuZ 0.2.8 版** start.sh（清单驱动，运行期行为不变）。

与 0.1.7 版生成器的差别（0.2.8 的启动器被上游重构过，锚点全变了）：
  * head 侧：0.2.8 用 `local -a cache_mounts=()` + 条件填充，最后 `"${cache_mounts[@]}"`
    汇入 `_a+=()`。本生成器在 CODE_MOUNTS 那行之后追加一个生成块，把站点挂载
    `cache_mounts+=( ... )` 进去 ⇒ 生产模式（SGLANG_CODE_MOUNTS=0）也能生效。
  * worker 侧：0.2.8 的 `CACHE_VOL=''` 后跟一个 dev-only 的 if。生成块插在该 if
    **之后**，并用 `\\$CACHE_VOL` 追加 ⇒ 生产模式得到我们的挂载、dev 模式在其基础上追加。
  * 生产模式不挂宿主缓存是**上游的有意设计**（靠 golden 树）；本站在 route A（不用
    golden）下必须自己挂 `~/.cache/sglang/flashinfer/autotune`，否则 per-rank 缓存
    不落盘，站点补丁就无从「保住缓存」。

Manifest：每行 `<相对 $SITE_ROOT/site-patches 的路径>|<容器内路径>`，空行与 `#` 忽略。
幂等：生成块由 >>>/<<< 标记包裹，重复运行只重写块内内容。

用法： SITE_ROOT=$HOME/luz028 python3 make_site_mounts_v028.py
"""
import os
import shutil
import subprocess
import time

ROOT = os.environ.get("SITE_ROOT", os.path.expanduser("~/luz028"))
SP = os.path.join(ROOT, "site-patches")
MANIFEST = os.path.join(SP, "mount.manifest")
START = os.path.join(ROOT, "start.sh")

CACHE_SRC = "-v \\$HOME/.cache/sglang/flashinfer/autotune:/root/.cache/sglang/flashinfer/autotune"

HEAD_ANCHOR = '  [[ "$SGLANG_CODE_MOUNTS" = 1 ]] && cache_mounts=(-v "$HOME/.cache:/root/.cache")\n'
WORKER_ANCHOR = (
    "      CACHE_VOL=''\n"
    "      if [ '${SGLANG_CODE_MOUNTS}' = 1 ]; then\n"
    '        CACHE_VOL=\\"-v \\$HOME/.cache:/root/.cache\\"\n'
    "      fi\n"
)

# 标记必须两侧**不同名**：6 空格缩进的 worker 块里，2 空格缩进的 head 标记是它的
# 子串，同名会让 strip 误切 worker 块（第一版就踩了，表现为 worker 块后多出缩进）。
MK_A, MK_B = "  # >>> site-mounts-head (generated) >>>", "  # <<< site-mounts-head <<<"
MK_A_W, MK_B_W = (
    "      # >>> site-mounts-worker (generated) >>>",
    "      # <<< site-mounts-worker <<<",
)


def read_manifest():
    out = []
    for ln in open(MANIFEST):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        src, dst = ln.split("|")
        src, dst = src.strip(), dst.strip()
        p = os.path.join(SP, src)
        assert os.path.exists(p), "manifest src missing: %s" % p
        _ok_dst = ("/sgl-workspace/sglang/", "/opt/sglang/", "/sp-adapters/", "/b12x-adapters/")
        assert dst.startswith(_ok_dst), "unexpected dst: %s" % dst
        out.append((src, dst))
    assert out, "manifest is empty"
    return out


def strip_block(t, a, b):
    """幂等：把上一次生成块（含标记与行尾换行）整段去掉。

    必须连 `b` 所在行的行尾换行一起吃掉 —— 否则第二次生成会在块后留下一行空行，
    每次重跑多一行（P0.43 那类"看不出来的漂移"）。
    """
    while a in t:
        i = t.index(a)
        j = t.index(b, i) + len(b)
        if t[j:j + 1] == "\n":
            j += 1
        t = t[:i] + t[j:]
    return t


def main():
    entries = read_manifest()
    t = open(START).read()
    ts = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(START, "%s.bak-%s-preMounts" % (START, ts))

    t = strip_block(t, MK_A, MK_B)
    t = strip_block(t, MK_A_W, MK_B_W)

    # ---- head：在 CODE_MOUNTS 行之后追加站点挂载 ----
    assert t.count(HEAD_ANCHOR) == 1, "head 锚点命中 %d 次（应为 1）" % t.count(HEAD_ANCHOR)
    head = [MK_A, "  cache_mounts+=(", '    -v "$HOME/.cache/sglang/flashinfer/autotune:/root/.cache/sglang/flashinfer/autotune"']
    for src, dst in entries:
        head.append('    -v "$HOME/%s/site-patches/%s:%s:ro"' % (os.path.basename(ROOT), src, dst))
    head += ["  )", MK_B]
    t = t.replace(HEAD_ANCHOR, HEAD_ANCHOR + "\n".join(head) + "\n")

    # ---- worker：在 dev-only if 之后追加（用 \$CACHE_VOL 前缀保留 dev 侧内容）----
    assert t.count(WORKER_ANCHOR) == 1, "worker 锚点命中 %d 次（应为 1）" % t.count(WORKER_ANCHOR)
    wparts = ["\\$CACHE_VOL", CACHE_SRC]
    for src, dst in entries:
        wparts.append('-v \\$HOME/%s/site-patches/%s:%s:ro' % (os.path.basename(ROOT), src, dst))
    wline = '      CACHE_VOL=\\"' + " ".join(wparts) + '\\"'
    t = t.replace(WORKER_ANCHOR, WORKER_ANCHOR + MK_A_W + "\n" + wline + "\n" + MK_B_W + "\n")

    open(START, "w").write(t)
    rc = subprocess.run(["bash", "-n", START]).returncode
    assert rc == 0, "bash -n 失败：生成后的 start.sh 语法错误"
    print("已生成 %d 个文件挂载；start.sh 语法 OK（备份 .bak-%s-preMounts）" % (len(entries), ts))
    for s, d in entries:
        print("  %s -> %s" % (s, d))


if __name__ == "__main__":
    main()
