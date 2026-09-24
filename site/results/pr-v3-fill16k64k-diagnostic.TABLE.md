# PR-v3 — pure-prefill total-throughput matrix

One request = `max_new_tokens=1` (pure prefill; no decode tail). Fresh nonce
per request; `/flush_cache` between cells. **total t/s = Σ(prompt tokens) /
wall-clock from arm start to last stream end** — one clock per arm, no
windows, no decode term.

`serialized=⚠` rows: the engine's running gauge never exceeded 1 AND the
streams' TTFT spans do not overlap — the cell ran one-request-at-a-time
(chunked-prefill admission above 4096 tokens). The total t/s is still the
honest wall-clock throughput of that admission policy, but it is not
parallel prefill. `overlap` is the peak number of streams whose prefills
were in flight simultaneously (computed from per-stream t_first/t_end).

| Input tokens | C | Streams OK | Total prompt tokens | Wall s | **Total t/s** | TTFT first s | TTFT last s | Prefill overlap peak | serialized |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 16384 | 1 | 1/1 | 16384 | 4.68 | **3500.6** | 4.677 | 4.677 | 1 | ok |
| 16384 | 2 | 2/2 | 32768 | 9.224 | **3552.6** | 5.608 | 9.222 | 1 | ⚠ |
| 16384 | 4 | 4/4 | 65536 | 18.445 | **3553.1** | 5.683 | 18.442 | 1 | ok |
| 65536 | 1 | 1/1 | 65536 | 19.363 | **3384.7** | 19.358 | 19.358 | 1 | ok |
| 65536 | 2 | 2/2 | 131072 | 38.336 | **3419.0** | 20.179 | 38.324 | 1 | ⚠ |
| 65536 | 4 | 4/4 | 262144 | 76.6 | **3422.2** | 20.354 | 76.595 | 1 | ok |
