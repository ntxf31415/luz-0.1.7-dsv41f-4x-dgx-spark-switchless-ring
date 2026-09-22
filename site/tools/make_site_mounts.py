#!/usr/bin/env python3
"""Bake site-patch file mounts into start.sh from site-patches/mount.manifest.

Runtime behaviour is unchanged: the mounts stay static lines in start.sh. This is a
build-time generator so that adding/removing an experiment's files is data, not a
hand edit of a production script (P0.43 lost a window to that quoting trap).

Manifest: one entry per line, `<src relative to $HOME/luz017/site-patches>|<container path>`.
Blank lines and `#` comments ignored. Regenerating with a different manifest is the
supported way to change the set; regenerating with only the production entry restores
the exact production block.
"""
import os, re, shutil, subprocess, sys, time

SP = os.path.expanduser("~/luz017/site-patches")
MANIFEST = os.path.join(SP, "mount.manifest")
START = os.path.expanduser("~/luz017/start.sh")

HEAD_OPEN = '  [[ "$SGLANG_CODE_MOUNTS" != 1 ]] && cache_mounts=('
HEAD_CLOSE = ':ro")'
WORKER_NEEDLE = 'CACHE_VOL=\\"-v \\$HOME/.cache/sglang/flashinfer/autotune'
MK_A, MK_B = "    # >>> site-mounts (generated) >>>", "    # <<< site-mounts <<<"


def read_manifest():
    out = []
    for ln in open(MANIFEST):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        src, dst = ln.split("|")
        src = src.strip(); dst = dst.strip()
        p = os.path.join(SP, src)
        assert os.path.isfile(p), f"manifest src missing: {p}"
        assert dst.startswith("/sgl-workspace/sglang/"), f"unexpected dst: {dst}"
        out.append((src, dst))
    assert out, "manifest is empty"
    return out


def main():
    entries = read_manifest()
    t = open(START).read()
    ts = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(START, f"{START}.bak-{ts}-preMounts")

    # ---- head: regenerate the cache_mounts array body (line-based => idempotent) ----
    lines = t.splitlines()
    i = [k for k, l in enumerate(lines) if l == HEAD_OPEN]
    assert len(i) == 1, f"head block open marker count={len(i)} (want 1)"
    i = i[0]
    # end of the array: a line that is exactly "  )" (our generated form) or ends with ':ro")'
    j = None
    for k in range(i + 1, len(lines)):
        ls = lines[k].strip()
        if ls == ")" or ls.endswith(':ro")') or ls.endswith('\")'):
            j = k
            break
    assert j is not None, "head block close not found"
    head_lines = ['    -v "$HOME/.cache/sglang/flashinfer/autotune:/root/.cache/sglang/flashinfer/autotune"',
                  MK_A]
    for src, dst in entries:
        head_lines.append(f'    -v "$HOME/luz017/site-patches/{src}:{dst}:ro"')
    head_lines += [MK_B, "  )"]
    lines[i + 1:j + 1] = head_lines
    t = "\n".join(lines) + "\n"

    # ---- worker: one escaped-quote string, every -v before the closing \" ----
    parts = ['-v \\$HOME/.cache/sglang/flashinfer/autotune:/root/.cache/sglang/flashinfer/autotune']
    for src, dst in entries:
        parts.append(f'-v \\$HOME/luz017/site-patches/{src}:{dst}:ro')
    worker_line = '        CACHE_VOL=\\"' + " ".join(parts) + '\\"'

    lines = t.splitlines()
    wl = [k for k, l in enumerate(lines)
          if l.lstrip().startswith('CACHE_VOL=\\') and 'site-patches/' in l]
    assert len(wl) == 1, f"worker CACHE_VOL line count={len(wl)} (want 1)"
    lines[wl[0]] = worker_line
    t = "\n".join(lines) + "\n"

    open(START, "w").write(t)
    rc = subprocess.run(["bash", "-n", START]).returncode
    assert rc == 0, "bash -n failed after generating mounts"
    print(f"generated {len(entries)} file mount(s); start.sh syntax OK (backup .bak-{ts}-preMounts)")
    for s, d in entries:
        print(f"  {s} -> {d}")


if __name__ == "__main__":
    main()
