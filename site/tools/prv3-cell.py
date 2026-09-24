#!/usr/bin/env python3
"""Dump chosen PR-v3 cells (throughput + ttft_first/last) for cross-arm comparison."""
import json, sys, os
d = json.load(open(sys.argv[1]))
want = [(131072,1),(131072,2),(131072,4),(32768,1),(32768,2),(32768,4),(8192,1),(8192,2),(2048,1),(2048,2),(512,1),(512,2)]
idx = {(c["input_tokens"], c["concurrency"]): c for c in d["cells"]}
print("cell            tput t/s   ttft_1st s  ttft_last s   ratio  serialized")
for k in want:
    c = idx.get(k)
    if not c: continue
    t1, t2 = c.get("ttft_first_s"), c.get("ttft_last_s")
    r = (t2/t1) if (t1 and t2 and t1 > 0) else None
    print("%-14s %9.1f  %10.3f  %11.3f  %6s  %s" % (
        "%dxC%d" % k, c["total_throughput_tps"], t1 or 0, t2 or 0,
        ("%.2f" % r) if r else "-", c.get("serialized")))
