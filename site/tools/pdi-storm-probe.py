#!/usr/bin/env python3
"""PDI 风暴探针 —— 冷长 prefill 是否冻住正在解码的流。

背景：`--prefill-decode-interval` (PDI) 默认 0。PDI=0 时调度器
（`sglang/srt/managers/scheduler.py: _should_defer_prefill`）只要有待 prefill
就每个 step 返回 prefill 批；而本栈实测 `enable_mixed_chunk=False`（上游默认，
且 `--enable-encoder-swa-bounded-replay` 与 mixed prefill/decode 互斥），
prefill 步**不携带**解码请求 —— 于是冷长文档的每个 chunk 都是一次独占 step。
本探针量这个冻结的幅度，以及解冻要付的代价。

方法（同一脚本跑两臂，臂间只差 PDI）：
  [预热] 长 prompt P（盐 s）发一条 max_tokens=1 请求，把 radix 缓存喂上
  [起流] N 条流式请求用同一 P（⇒ 命中缓存，TTFT 便宜），ignore_eos 长输出
  [基线] T_base 秒采样各流内容增量 → 基线速率
  [注入] 1 条冷请求 C（不同盐 ⇒ 不命中），t_inject 为窗起点
  [采样] 每秒记录各流累计增量，直到 C 完成（或超时）= 窗终点
输出：冻结比 = 窗内聚合速率 ÷ 基线聚合速率，以及 C 的 TTFT / 完成时间。

判据：冻结比 ≈ 1 ⇒ 无此问题；≪ 1 ⇒ 有，且数字就是受害流被冻掉的比例。

用法：
  python3 pdi-storm-probe.py --label pdi0
  # 在 EXTRA_SGLANG_ARGS 追加 --prefill-decode-interval N 并重启后：
  python3 pdi-storm-probe.py --label pdi16

口径说明：速率按**内容增量数**计（SSE delta），不是引擎侧 token 计数 —— 两臂
同一口径故可比；引擎报的 usage 另存于 JSON 供交叉核对。
"""
import argparse
import json
import os
import random
import threading
import time
import urllib.request

MODEL = "deepseek-v4.1-flash"

WORDS = ["harbour", "lantern", "meadow", "copper", "violin", "orchard", "compass",
         "thistle", "ember", "granite", "willow", "saffron", "anchor", "quartz",
         "ledger", "falcon"]


def post(url, key, body, timeout=3000, stream=False):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    if not stream:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    return urllib.request.urlopen(req, timeout=timeout)


def count_tokens(url, key, prompt):
    body = dict(model=MODEL, temperature=0, max_tokens=1, stream=False,
                chat_template_kwargs={"thinking": False},
                messages=[{"role": "user", "content": prompt}])
    return post(url, key, body)["usage"]["prompt_tokens"]


def build_prompt(target, seed, count_fn):
    rnd = random.Random(seed)

    def para(i):
        return (f"Entry {seed}-{i}: the {rnd.choice(WORDS)} keeper noted "
                f"{rnd.randint(1, 999)} {rnd.choice(WORDS)} crates by the "
                f"{rnd.choice(WORDS)} gate before the {rnd.choice(WORDS)} bell "
                f"rang at dusk. ")

    probe = "".join(para(i) for i in range(50))
    per = (count_fn(probe) - 24) / 50.0
    reps = max(10, int((target - 300) / per))
    return "".join(para(i) for i in range(reps)) + "\nSummarize in one short sentence.\n"


class State:
    def __init__(self, n):
        self.lock = threading.Lock()
        self.counts = [0] * n
        self.ttft = [None] * n
        self.errors = [None] * n
        self.usage = [None] * n
        self.stop = threading.Event()


def stream_worker(idx, url, key, prompt, maxtok, st, timeout):
    body = dict(model=MODEL, temperature=0, max_tokens=maxtok, ignore_eos=True,
                stream=True, stream_options={"include_usage": True},
                chat_template_kwargs={"thinking": False},
                messages=[{"role": "user", "content": prompt}])
    t0 = time.time()
    r = None
    try:
        r = post(url, key, body, timeout=timeout, stream=True)
        for raw in r:
            if st.stop.is_set():
                break
            line = raw.decode().strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            d = json.loads(payload)
            if d.get("usage"):
                st.usage[idx] = d["usage"]
            for ch in d.get("choices", []):
                if (ch.get("delta") or {}).get("content"):
                    with st.lock:
                        st.counts[idx] += 1
                        if st.ttft[idx] is None:
                            st.ttft[idx] = time.time() - t0
    except Exception as e:  # noqa: BLE001 - 探针要把异常如实带出来
        st.errors[idx] = repr(e)
    finally:
        if r is not None:
            r.close()


def cold_worker(url, key, prompt, maxtok, box, timeout):
    body = dict(model=MODEL, temperature=0, max_tokens=maxtok, stream=True,
                stream_options={"include_usage": True},
                chat_template_kwargs={"thinking": False},
                messages=[{"role": "user", "content": prompt}])
    box["t_inject"] = time.time()
    t0 = box["t_inject"]
    r = None
    try:
        r = post(url, key, body, timeout=timeout, stream=True)
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            d = json.loads(payload)
            if d.get("usage"):
                box["usage"] = d["usage"]
            for ch in d.get("choices", []):
                if (ch.get("delta") or {}).get("content"):
                    if box.get("ttft") is None:
                        box["ttft"] = time.time() - t0
        box["wall"] = time.time() - t0
    except Exception as e:  # noqa: BLE001
        box["error"] = repr(e)
    finally:
        box["t_done"] = time.time()
        if r is not None:
            r.close()


def engine_idle(url, key):
    try:
        req = urllib.request.Request(base_metrics(url),
                                     headers={"Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=10) as r:
            txt = r.read().decode()
        running = queue = None
        for line in txt.splitlines():
            if line.startswith("sglang:num_running_reqs"):
                running = float(line.rsplit(" ", 1)[1])
            elif line.startswith("sglang:num_queue_reqs"):
                queue = float(line.rsplit(" ", 1)[1])
        return running, queue
    except Exception:  # noqa: BLE001
        return None, None


def base_metrics(url):
    return url.split("/v1/")[0] + "/metrics"


def snap(st):
    with st.lock:
        return list(st.counts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="臂名，进输出文件名")
    ap.add_argument("--url", default="http://127.0.0.1:8899/v1/chat/completions")
    ap.add_argument("--key-file", default=os.path.expanduser("~/luz017/state-tp4/api-key"))
    ap.add_argument("--key", default=os.environ.get("API_KEY", ""))
    ap.add_argument("--streams", type=int, default=3)
    ap.add_argument("--ctx", type=int, default=100000, help="解码流的上下文长度")
    ap.add_argument("--cold", type=int, default=100000, help="注入的冷请求长度")
    ap.add_argument("--maxtok", type=int, default=20000, help="流式输出上限（要够撑满窗口）")
    ap.add_argument("--baseline-sec", type=float, default=15.0)
    ap.add_argument("--timeout", type=float, default=1800.0, help="冷请求等待上限（秒）")
    ap.add_argument("--out", default="pdi-storm-results")
    ap.add_argument("--allow-busy", action="store_true", help="引擎非空闲也照跑")
    args = ap.parse_args()

    key = args.key or open(args.key_file).read().strip()
    os.makedirs(args.out, exist_ok=True)
    count_fn = lambda p: count_tokens(args.url, key, p)  # noqa: E731

    running, queue = engine_idle(args.url, key)
    print(f"[idle] running={running} queue={queue}")
    if not args.allow_busy and (running or 0) > 0:
        raise SystemExit("引擎非空闲，拒绝开跑（--allow-busy 可覆盖）")

    seed = 4242
    print(f"[prompt] 构造 {args.ctx} tok 解码用 prompt …")
    prompt = build_prompt(args.ctx, seed, count_fn)
    n_tok = count_tokens(args.url, key, prompt)
    print(f"[prompt] prompt_tokens={n_tok}")

    print("[warmup] 冷灌一次（这一发本身也是冷 prefill 的墙钟参照）")
    t0 = time.time()
    post(args.url, key, dict(model=MODEL, temperature=0, max_tokens=1, stream=False,
                             chat_template_kwargs={"thinking": False},
                             messages=[{"role": "user", "content": prompt}]))
    warm_cold = time.time() - t0
    hit = post(args.url, key, dict(model=MODEL, temperature=0, max_tokens=1, stream=False,
                                   chat_template_kwargs={"thinking": False},
                                   messages=[{"role": "user", "content": prompt}]))
    cached = (hit["usage"].get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    print(f"[warmup] 冷灌 {warm_cold:.1f}s · 复灌 cached={cached}/{hit['usage']['prompt_tokens']}")

    print(f"[streams] 起 {args.streams} 条解码流（应命中缓存，max_tokens={args.maxtok}）")
    st = State(args.streams)
    ths = [threading.Thread(target=stream_worker,
                            args=(i, args.url, key, prompt, args.maxtok, st, args.timeout),
                            daemon=True)
           for i in range(args.streams)]
    for t in ths:
        t.start()

    t_streams = time.time()
    while any(x is None for x in st.ttft) and time.time() - t_streams < 120:
        time.sleep(0.5)
    print(f"[streams] 首包用时 ttft={[None if x is None else round(x, 2) for x in st.ttft]}")

    print(f"[baseline] 采样 {args.baseline_sec:.0f}s")
    b0, tb0 = snap(st), time.time()
    time.sleep(args.baseline_sec)
    b1, tb1 = snap(st), time.time()
    base_rate = (sum(b1) - sum(b0)) / max(tb1 - tb0, 1e-9)
    print(f"[baseline] 聚合 {base_rate:.2f} delta/s · 各流 "
          f"{[b1[i] - b0[i] for i in range(args.streams)]}")

    cold_prompt = build_prompt(args.cold, seed + 7, count_fn)
    box = {}
    th = threading.Thread(target=cold_worker,
                          args=(args.url, key, cold_prompt, 128, box, 3000.0), daemon=True)
    th.start()
    while "t_inject" not in box:
        time.sleep(0.01)
    t_inj = box["t_inject"]
    c0 = snap(st)
    print(f"[inject] 冷请求已发出（{args.cold} tok），开始按秒采样")

    samples = []
    while th.is_alive() and time.time() - t_inj < args.timeout:
        time.sleep(1.0)
        samples.append((time.time() - t_inj, snap(st)))
    th.join(timeout=30)
    t_end = box.get("t_done", time.time())
    c1 = snap(st)
    win = max(t_end - t_inj, 1e-9)
    win_rate = (sum(c1) - sum(c0)) / win
    ratio = win_rate / base_rate if base_rate > 0 else float("nan")

    print("\n===== 结果 =====")
    print(f"臂                {args.label}")
    print(f"风暴窗时长        {win:.1f} s")
    print(f"窗内聚合速率      {win_rate:.2f} delta/s（基线 {base_rate:.2f}）")
    print(f"冻结比            {ratio:.3f}   ← 越接近 0 冻得越死")
    print(f"窗内各流增量      {[c1[i] - c0[i] for i in range(args.streams)]}")
    print(f"冷请求 TTFT       {box.get('ttft')}")
    print(f"冷请求完成        {box.get('wall')}")
    print(f"冷请求 usage       {box.get('usage')}")

    out = dict(label=args.label, ts=time.strftime("%F %T"), streams=args.streams,
               ctx=args.ctx, cold=args.cold, prompt_tokens=n_tok, cached=cached,
               warm_cold_s=warm_cold, baseline_rate=base_rate, window_s=win,
               window_rate=win_rate, freeze_ratio=ratio, base_counts=b1, end_counts=c1,
               cold_req=box, samples=[[round(t, 2), c] for t, c in samples],
               stream_usage=st.usage, errors=st.errors)
    path = os.path.join(args.out, f"{args.label}.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n[out] {path}")

    st.stop.set()
    for t in ths:
        t.join(timeout=5)


if __name__ == "__main__":
    main()
