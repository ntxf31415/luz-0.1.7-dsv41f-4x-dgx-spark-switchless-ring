#!/usr/bin/env python3
"""#40758 A/B: does a literal <|deepseek_image|> in USER text get rejected (400) or escaped (200)?

Before the patch the server raises -> HTTP 400, and a client that keeps the failed turn
wedges the conversation. After, the text is rewritten to the ASCII-pipe spelling.
Run on both the unpatched and patched boot; compare the per-case HTTP codes.
"""
import json, os, urllib.request, urllib.error

URL = "http://127.0.0.1:8899/v1/chat/completions"
KEY = open(os.path.expanduser("~/luz017/state-tp4/api-key")).read().strip()
MODEL = "deepseek-v4.1-flash"
PH = "<｜deepseek_image｜>"

CASES = [
    ("string_content", [{"role": "user", "content": "What does the token %s mean?" % PH}]),
    ("text_block", [{"role": "user", "content": [{"type": "text", "text": "explain %s" % PH}]}]),
    ("tool_result_string", [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "calling", "tool_calls": [
            {"id": "a", "type": "function", "function": {"name": "lookup", "arguments": {"q": "x"}}}]},
        {"role": "tool", "tool_call_id": "a", "content": "result mentions %s literally" % PH},
    ]),
    ("reasoning_content", [
        {"role": "user", "content": "q"},
        {"role": "assistant", "reasoning_content": "thinking about %s" % PH, "content": "a"},
    ]),
    ("control_no_placeholder", [{"role": "user", "content": "What is 2+2?"}]),
]

rows = []
for name, messages in CASES:
    body = json.dumps(dict(model=MODEL, temperature=0, max_tokens=16, stream=False,
                           chat_template_kwargs={"thinking": False},
                           messages=messages)).encode()
    req = urllib.request.Request(URL, data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + KEY})
    try:
        r = urllib.request.urlopen(req, timeout=300)
        text = json.loads(r.read())["choices"][0]["message"]["content"] or ""
        rows.append({"case": name, "http": r.status, "ok": True, "reply": text[:60]})
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read()).get("message", "")[:160]
        except Exception:
            pass
        rows.append({"case": name, "http": e.code, "ok": False, "error": detail})
for r in rows:
    print(json.dumps(r, ensure_ascii=False))
n400 = sum(1 for r in rows[:4] if r["http"] == 400)
print("SUMMARY " + json.dumps({"cases": len(rows), "http_400": n400,
                               "control_ok": rows[-1]["ok"]}))
