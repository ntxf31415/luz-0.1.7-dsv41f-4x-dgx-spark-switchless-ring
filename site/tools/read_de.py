import json, sys
d = json.load(open(sys.argv[1]))
print("meta:", {k: v for k, v in (d.get("_meta") or {}).items() if k in
      ("run_tag", "types", "concurrencies", "waves", "max_tokens", "convention")})
print()
for k in sorted(d):
    if k.startswith("_"):
        continue
    c = d[k]
    w = c.get("waves_detail") or []
    ws = [x.get("median_decode_tps") for x in w]
    med = c.get("median_decode_tps") or 0
    sp = (max(ws) - min(ws)) / med * 100 if ws and med else 0
    print("  {:<22} 格值 {:>6.2f}  聚合 {:>6.2f}  TTFT {:>5.0f}ms  prefill {:>6.0f}  波 {}  离散 {:.1f}%".format(
        k, med, c.get("agg_decode_tps") or 0, (c.get("median_ttft_s") or 0) * 1000,
        c.get("median_prefill_tps") or 0, [round(x, 1) for x in ws], sp))
