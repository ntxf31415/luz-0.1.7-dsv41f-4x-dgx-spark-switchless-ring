#!/usr/bin/env python3
"""Mixed-queue probe: one long COLD prefill in flight, then a short request queued.
Measures the short request's TTFT (the knob's actual target case)."""
import json, os, random, threading, time, urllib.request
URL = "http://127.0.0.1:8899/v1/chat/completions"
KEY = open(os.path.expanduser("~/luz017/state-tp4/api-key")).read().strip()
MODEL = "deepseek-v4.1-flash"
LONG_TOK, SHORT_TOK, DELAY_S = 131072, 512, 1.0
rnd = random.Random(int(time.time()) % 100000)
words = ["harbour","lantern","meadow","copper","violin","orchard","compass","thistle","ember","granite","willow","saffron","anchor","quartz","ledger","falcon"]
def para(seed, i):
    r = random.Random(seed * 100000 + i)
    return f"Entry {seed}-{i}: the {r.choice(words)} keeper noted {r.randint(1,999)} {r.choice(words)} crates by the {r.choice(words)} gate before the {r.choice(words)} bell rang at dusk. "
def body(text, maxtok, stream):
    return json.dumps(dict(model=MODEL, temperature=0, max_tokens=maxtok, stream=stream,
        chat_template_kwargs={"thinking": False},
        messages=[{"role":"user","content":text}])).encode()
def post(payload):
    return urllib.request.urlopen(urllib.request.Request(URL, data=payload,
        headers={"Content-Type":"application/json","Authorization":"Bearer "+KEY}), timeout=3000)
seed = rnd.randint(1,9999)
long_text = "".join(para(seed, i) for i in range(1))  # placeholder, built below
# build ~LONG_TOK tokens by repeating paragraphs
unit = para(seed, 0)
long_text = (unit * ((LONG_TOK // max(1, len(unit.split()))) + 40))
res = {}
def fire_long():
    t0 = time.time()
    r = post(body(long_text, 4, False))
    d = json.loads(r.read())
    res["long_pt"] = d["usage"]["prompt_tokens"]; res["long_wall"] = time.time() - t0
t = threading.Thread(target=fire_long); t.start()
time.sleep(DELAY_S)
t1 = time.time()
r = post(body("Say OK. " + str(seed), 4, False))
d = json.loads(r.read())
res["short_ttft"] = time.time() - t1
res["short_ok"] = d["choices"][0]["message"]["content"][:20]
t.join()
print(json.dumps(res, indent=1))
