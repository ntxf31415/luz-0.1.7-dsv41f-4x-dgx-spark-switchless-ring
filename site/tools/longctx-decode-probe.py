#!/usr/bin/env python3
"""Decode throughput at long contexts (口径-B style: post-TTFT, streaming).

Targets the regime the FP4 indexer change (#40431) addresses: a capacity-sized
CUDA-graph grid against a short live context. DE's prompts decode at ~2K, where the
invisible fraction is small; real traffic decodes at ~148K (median).
"""
import json, os, random, sys, time, urllib.request

URL = "http://127.0.0.1:8899/v1/chat/completions"
KEY = open(os.path.expanduser("~/luz017/state-tp4/api-key")).read().strip()
MODEL = "deepseek-v4.1-flash"
TARGETS = [int(x) for x in os.environ.get("TARGETS", "8000,100000,200000").split(",")]
MAXTOK = int(os.environ.get("MAXTOK", "256"))
ROUNDS = int(os.environ.get("ROUNDS", "3"))
SEED = int(os.environ.get("SEED", "7331"))
W = ["harbour","lantern","meadow","copper","violin","orchard","compass","thistle",
     "ember","granite","willow","saffron","anchor","quartz","ledger","falcon"]

def para(seed, i):
    r = random.Random(seed * 1000003 + i)
    return ("Entry %d-%d: the %s keeper noted %d %s crates by the %s gate before the "
            "%s bell rang at dusk. " % (seed, i, r.choice(W), r.randint(1, 999),
                                        r.choice(W), r.choice(W), r.choice(W)))

def build(target, seed):
    unit = para(seed, 0)
    return unit * max(1, (target // max(1, len(unit) // 4)) + 40)

def ask(text, maxtok, stream):
    payload = dict(model=MODEL, temperature=0, max_tokens=maxtok, stream=stream,
                   chat_template_kwargs={"thinking": False},
                   messages=[{"role": "user", "content": text}])
    if stream:
        payload["stream_options"] = {"include_usage": True}
    body = json.dumps(payload).encode()
    return urllib.request.urlopen(urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json",
                                 "Authorization": "Bearer " + KEY}), timeout=3000)

out = []
for tgt in TARGETS:
    prompt = build(tgt, SEED)
    ask(prompt, 1, False).read()                      # warm: populate radix cache
    rates = []
    for r in range(ROUNDS):
        t0 = time.time(); t_first = None; t_last = None; n = 0; pt = 0
        with ask(prompt, MAXTOK, True) as resp:
            for raw in resp:
                if not raw.startswith(b"data: "):
                    continue
                chunk = raw[6:].strip()
                if chunk == b"[DONE]":
                    break
                d = json.loads(chunk)
                if d.get("usage"):
                    pt = d["usage"].get("prompt_tokens") or pt
                    n = d["usage"].get("completion_tokens") or n
                ch = (d.get("choices") or [{}])[0].get("delta", {}).get("content")
                if ch:
                    if t_first is None:
                        t_first = time.time()
                    t_last = time.time()
        if t_first and t_last and t_last > t_first and n > 1:
            rates.append((n - 1) / (t_last - t_first))
    rates.sort()
    med = rates[len(rates) // 2] if rates else 0.0
    out.append({"target": tgt, "prompt_tokens": pt, "rounds": len(rates),
                "median_decode_tps": round(med, 2),
                "all": [round(x, 2) for x in rates]})
    print(json.dumps(out[-1]), flush=True)
print("SUMMARY " + json.dumps(out))
