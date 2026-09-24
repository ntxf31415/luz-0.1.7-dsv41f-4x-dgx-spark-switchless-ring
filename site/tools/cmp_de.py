import json, sys
def load(p):
    d = json.load(open(p))
    out = {}
    for k, v in d.items():
        if k.startswith("_"):
            continue
        w = v.get("waves_detail") or []
        ws = [x.get("median_decode_tps") for x in w]
        out[k] = (v.get("median_decode_tps"), ws,
                  (max(ws) - min(ws)) / v.get("median_decode_tps") * 100 if ws and v.get("median_decode_tps") else 0)
    return out
a = load(sys.argv[1]); b = load(sys.argv[2])
keys = sorted(set(a) | set(b))
print("{:<12} {:>16} {:>16} {:>10}".format("格", sys.argv[3], sys.argv[4], "差"))
print("-" * 60)
for k in keys:
    x = a.get(k); y = b.get(k)
    if not x or not y:
        continue
    d = (y[0] - x[0]) / x[0] * 100
    print("{:<12} {:>7.2f} ({:>4.1f}%) {:>7.2f} ({:>4.1f}%) {:>+9.1f}%".format(
        k.replace("DE-V3_", ""), x[0], x[2], y[0], y[2], d))
