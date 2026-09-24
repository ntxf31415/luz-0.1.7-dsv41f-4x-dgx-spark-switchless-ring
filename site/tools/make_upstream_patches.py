#!/usr/bin/env python3
"""Apply two upstream fixes to our tree's files, with anchor assertions.

  pr2     -- LuZ PR #2 (mm sentinel masking)  -> deepseek_v4.py, dspark_draft.py
  40111   -- sglang #40111 (drop host sync in DSpark prefill slot expansion) -> dspark_worker_v2.py

Anchors must be UNIQUE; every edit is asserted and py_compile'd. Outputs to
site-patches/mount/<name>.  Nothing is mounted unless listed in mount.manifest.
"""
import os, py_compile, shutil, sys, time

W = os.path.expanduser("~/luz017/site-patches/work")
OUT = os.path.expanduser("~/luz017/site-patches/mount")
os.makedirs(OUT, exist_ok=True)

def sub_once(text, old, new, tag):
    n = text.count(old)
    assert n == 1, f"[{tag}] anchor count={n} (want 1)"
    return text.replace(old, new)

def finish(text, name, tag):
    dst = os.path.join(OUT, name)
    ts = time.strftime("%Y%m%d-%H%M%S")
    if os.path.exists(dst):
        shutil.copy2(dst, f"{dst}.bak-{ts}")
    open(dst, "w").write(text)
    py_compile.compile(dst, doraise=True)
    print(f"[{tag}] wrote {dst}  ({len(text)} bytes, py_compile OK)")
    return dst

# ---------------- PR #2 ----------------
def pr2():
    p = os.path.join(W, "deepseek_v4.py.orig")
    t = open(p).read()
    anchor = ("        if tail_token_indices is not None:\n"
              "            output.hidden_states_token_indices = tail_token_indices\n"
              "        return output\n")
    ins = ("        if output.next_token_logits is not None:\n"
           "            # [P0.46] in-vocabulary multimodal input sentinels are never\n"
           "            # valid assistant output; SGLang does not apply the checkpoint's\n"
           "            # special-token suppression, so they could otherwise leak.\n"
           "            output.next_token_logits[..., 128847:129271] = -torch.inf\n"
           "            output.next_token_logits[..., 129279] = -torch.inf\n")
    t = sub_once(t, anchor, ins + anchor, "pr2/deepseek_v4")
    finish(t, "deepseek_v4.py", "pr2")

    p = os.path.join(W, "dspark_draft.py.orig")
    t = open(p).read()
    a1 = "    fast_sampling = envs.SGLANG_DSPARK_FAST_SAMPLING.get()\n"
    helper = (
        "\n"
        "    def mask_mm_sentinels(step_logits: torch.Tensor) -> torch.Tensor:\n"
        "        # [P0.46] Multimodal input placeholder IDs are never valid assistant\n"
        "        # output. Mask them on the draft side too, so a proposal can never be\n"
        "        # made on a sentinel even if the target side is anomalous.\n"
        "        step_logits[..., 128847:129271] = -torch.inf\n"
        "        step_logits[..., 129279] = -torch.inf\n"
        "        return step_logits\n")
    t = sub_once(t, a1, a1 + helper, "pr2/dspark_draft.helper")
    a2 = ("                SpecTpSyncSite.DSPARK_DRAFT_GREEDY, torch.argmax(step_logits, dim=-1)\n")
    t = sub_once(t, a2,
                 "                SpecTpSyncSite.DSPARK_DRAFT_GREEDY,\n"
                 "                torch.argmax(mask_mm_sentinels(step_logits), dim=-1),\n",
                 "pr2/dspark_draft.greedy")
    a3 = ("            expect(_DRAFT_STEP_LOGITS, step_logits, msg=f\"step {step_idx}\")\n"
          "            if fast_sampling:\n")
    t = sub_once(t, a3,
                 "            expect(_DRAFT_STEP_LOGITS, step_logits, msg=f\"step {step_idx}\")\n"
                 "            step_logits = mask_mm_sentinels(step_logits)\n"
                 "            if fast_sampling:\n",
                 "pr2/dspark_draft.sample")
    finish(t, "dspark_draft.py", "pr2")

# ---------------- #40111 ----------------
def p40111():
    p = os.path.join(W, "dspark_worker_v2.py.orig")
    t = open(p).read()
    a1 = "            repeats = ctx_lens.to(torch.int64)\n"
    t = sub_once(t, a1, a1 + "            num_tokens = sum(batch.extend_lens)\n", "40111/seed")
    a2 = "                batch.req_pool_indices.to(device=device, dtype=torch.int64), repeats\n"
    t = sub_once(t, a2,
                 "                batch.req_pool_indices.to(device=device, dtype=torch.int64),\n"
                 "                repeats,\n"
                 "                output_size=num_tokens,\n", "40111/state_slot")
    a3 = "                (draft_seq_lens + ctx_lens - 1).to(torch.int64), repeats\n"
    t = sub_once(t, a3,
                 "                (draft_seq_lens + ctx_lens - 1).to(torch.int64),\n"
                 "                repeats,\n"
                 "                output_size=num_tokens,\n", "40111/final_pos")
    finish(t, "dspark_worker_v2.py", "40111")

if __name__ == "__main__":
    todo = sys.argv[1:] or ["pr2", "40111"]
    if "pr2" in todo: pr2()
    if "40111" in todo: p40111()
    print("done")
