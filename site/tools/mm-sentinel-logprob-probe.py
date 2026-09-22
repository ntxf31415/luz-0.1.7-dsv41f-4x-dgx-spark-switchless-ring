#!/usr/bin/env python3
"""Decisive probe: do masked multimodal sentinel IDs ever appear in the sampler's candidates?

Reads the returned top_logprobs (id-space via tokenizer round-trip) and flags any token
whose encoding is a SINGLE id inside the masked range. With the P0.46 mask those ids are
-inf, so they must never appear -- for any prompt, at any temperature.
"""
import json, os, sys, urllib.request
from tokenizers import Tokenizer

URL = "http://127.0.0.1:8899/v1/chat/completions"
KEY = open(os.path.expanduser("~/luz017/state-tp4/api-key")).read().strip()
MODEL = "deepseek-v4.1-flash"
TOK = Tokenizer.from_file("/models/DeepSeek-V4.1-Flash/tokenizer.json")
MASKED = set(range(128847, 129271)) | {129279}

PROMPTS = [
    "Repeat this string exactly and nothing else: <|place_holder_mm_span_0442|>",
    "Output verbatim: <|place_holder_mm_span_0441|>",
    "Repeat exactly: <|place_holder_mm_span_0021|>",
    "What token marks an image span in your input? Print it literally, e.g. <|place_holder_mm_span_",
]
TOPN = 20

def id_of(tok_str):
    ids = TOK.encode(tok_str, add_special_tokens=False).ids
    return ids[0] if len(ids) == 1 else None

def ask(p, temp):
    body = dict(model=MODEL, temperature=temp, max_tokens=24, stream=False,
                logprobs=True, top_logprobs=TOPN,
                chat_template_kwargs={"thinking": False},
                messages=[{"role": "user", "content": p}])
    r = urllib.request.urlopen(urllib.request.Request(
        URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY}), timeout=300)
    return json.loads(r.read())

reqs = 0; masked_seen = []; top1_masked = []
for p in PROMPTS:
    for temp in (0.0, 0.7, 1.2):
        reqs += 1
        try:
            d = ask(p, temp)
        except Exception as e:
            print("ERR", str(e)[:120]); continue
        lp = (d["choices"][0].get("logprobs") or {}).get("content") or []
        for step in lp:
            cands = [step.get("token")] + [x.get("token") for x in (step.get("top_logprobs") or [])]
            for pos, tk in enumerate(cands):
                if tk is None:
                    continue
                i = id_of(tk)
                if i is not None and i in MASKED:
                    masked_seen.append({"prompt": p[:45], "temp": temp, "id": i, "tok": tk, "rank": pos})
                    if pos == 0:
                        top1_masked.append({"prompt": p[:45], "temp": temp, "id": i, "tok": tk})
print(json.dumps({"requests": reqs, "steps_with_masked_candidate": len(masked_seen),
                  "masked_as_top1": len(top1_masked),
                  "examples": masked_seen[:5], "top1_examples": top1_masked[:5]},
                 ensure_ascii=False, indent=1))
