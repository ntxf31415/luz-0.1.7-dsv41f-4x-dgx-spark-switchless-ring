#!/usr/bin/env python3
"""P0.47 upstream ports:
  #40431 -- FP4 indexer: skip fully-invisible tiles (decode path, our sm90_fp4_indexer.py)
  #40758 -- escape a literal <|deepseek_image|> in user text instead of HTTP 400

Anchors asserted unique; output py_compile'd; written to site-patches/mount/.
"""
import os, py_compile, shutil, time

W = os.path.expanduser("~/luz017/site-patches/work")
OUT = os.path.expanduser("~/luz017/site-patches/mount")
os.makedirs(OUT, exist_ok=True)


def sub_once(t, old, new, tag):
    n = t.count(old)
    assert n == 1, "[%s] anchor count=%d (want 1)" % (tag, n)
    return t.replace(old, new)


def finish(t, name, tag):
    dst = os.path.join(OUT, name)
    ts = time.strftime("%Y%m%d-%H%M%S")
    if os.path.exists(dst):
        shutil.copy2(dst, "%s.bak-%s" % (dst, ts))
    open(dst, "w").write(t)
    py_compile.compile(dst, doraise=True)
    print("[%s] wrote %s (%d bytes, py_compile OK)" % (tag, dst, len(t)))


def p40431():
    src = open(os.path.join(W, "sm90_fp4_indexer.py.orig")).read()
    lines = src.splitlines(keepends=True)

    def find(pred, tag):
        hits = [i for i, l in enumerate(lines) if pred(l)]
        assert len(hits) == 1, "[%s] candidates=%d (want 1)" % (tag, len(hits))
        return hits[0]

    i_nvis = find(lambda l: l == "    n_vis = tl.load(lens_ptr + b)\n", "40431/n_vis")
    i_end = find(lambda l: l == "    tl.store(out_ptr + b * L + offs_l, logit, mask=offs_l < L)\n",
                 "40431/final_store")

    body = lines[i_nvis + 1:i_end + 1]
    indented = ["    " + l if l.strip() else l for l in body]

    head = [
        "    # [P0.47] caller guarantees: early return for L == 0 and q.contiguous().\n",
        "    # Express them to Triton; exclude singleton heads, whose stride is not\n",
        "    # constrained by contiguity.\n",
        "    tl.assume(L > 0)\n",
        "    if H > 1:\n",
        "        tl.assume(stride_qh == HALF_D * 2)\n",
        "\n",
    ]
    wrap = [
        "    # [P0.47] CUDA-graph replay keeps the capacity-sized grid even when the live\n",
        "    # context is short; skip whole invisible tiles rather than only masking their\n",
        "    # loads (dequant, dot products and reduction would still run otherwise).\n",
        "    if lb * BLOCK_L >= n_vis:\n",
        "        tl.store(out_ptr + b * L + offs_l, float(\"-inf\"), mask=offs_l < L)\n",
        "    else:\n",
    ]
    out = lines[:i_nvis] + head + [lines[i_nvis]] + wrap + indented + lines[i_end + 1:]
    finish("".join(out), "sm90_fp4_indexer.py", "40431")


def p40758():
    t = open(os.path.join(W, "encoding_dsv41.py.orig")).read()

    a1 = 'IMAGE_PLACEHOLDER = "<｜deepseek_image｜>"\n'
    t = sub_once(t, a1, a1 + "\n"
                 "# [P0.47] ASCII-pipe spelling. User-supplied text containing the literal\n"
                 "# fullwidth-bar token is rewritten to this spelling instead of rejected, so it\n"
                 "# can never be confused with a genuine placeholder inserted for real image\n"
                 "# content.\n"
                 'IMAGE_PLACEHOLDER_ESCAPED = "<|deepseek_image|>"\n', "40758/const")

    a2 = "def _process_image_blocks(\n"
    t = sub_once(t, a2,
                 "def _escape_image_placeholder(text: str) -> str:\n"
                 '    """[P0.47] Rewrite a literal image-placeholder token to its ASCII-pipe spelling."""\n'
                 "    return text.replace(IMAGE_PLACEHOLDER, IMAGE_PLACEHOLDER_ESCAPED)\n"
                 "\n\n" + a2, "40758/helper")

    a3 = '        elif block.get("type") == "text":\n'
    t = sub_once(t, a3,
                 '        elif block.get("type") == "tool_result" and isinstance(\n'
                 '            block.get("content"), str\n'
                 "        ):\n"
                 '            content = block.get("content", "")\n'
                 "            if IMAGE_PLACEHOLDER in content:\n"
                 "                block = copy.copy(block)\n"
                 '                block["content"] = _escape_image_placeholder(content)\n'
                 "            new_blocks.append(block)\n" + a3, "40758/tool_result")

    a4 = ('            if IMAGE_PLACEHOLDER in text:\n'
          "                raise ValueError(\n"
          "                    f\"Text block contains image placeholder '{IMAGE_PLACEHOLDER}': \"\n"
          "                    f\"'{text[:100]}'. Images should be separate content blocks.\"\n"
          "                )\n")
    t = sub_once(t, a4,
                 "            if IMAGE_PLACEHOLDER in text:\n"
                 "                block = copy.copy(block)\n"
                 '                block["text"] = _escape_image_placeholder(text)\n',
                 "40758/text_block")

    t = sub_once(t, "def _validate_no_image_sp_tokens(msg: Dict[str, Any]) -> None:\n",
                 "def _escape_image_sp_tokens(msg: Dict[str, Any]) -> None:\n", "40758/rename")

    a6 = ('    if isinstance(content, str) and IMAGE_PLACEHOLDER in content:\n'
          "        raise ValueError(\n"
          "            f\"Message content contains image special token '{IMAGE_PLACEHOLDER}'. \"\n"
          '            "Images should be provided as image content blocks."\n'
          "        )\n")
    t = sub_once(t, a6,
                 "    if isinstance(content, str) and IMAGE_PLACEHOLDER in content:\n"
                 '        msg["content"] = _escape_image_placeholder(content)\n', "40758/content")

    a7 = ('    if isinstance(reasoning_content, str) and IMAGE_PLACEHOLDER in reasoning_content:\n'
          "        raise ValueError(\n"
          "            f\"reasoning_content contains image special token '{IMAGE_PLACEHOLDER}'\"\n"
          "        )\n")
    t = sub_once(t, a7,
                 "    if isinstance(reasoning_content, str) and IMAGE_PLACEHOLDER in reasoning_content:\n"
                 '        msg["reasoning_content"] = _escape_image_placeholder(reasoning_content)\n',
                 "40758/reasoning")

    t = sub_once(t, "        _validate_no_image_sp_tokens(msg)\n",
                 "        _escape_image_sp_tokens(msg)\n", "40758/callsite")
    finish(t, "encoding_dsv41.py", "40758")


if __name__ == "__main__":
    import sys
    todo = sys.argv[1:] or ["40431", "40758"]
    if "40431" in todo:
        p40431()
    if "40758" in todo:
        p40758()
    print("done")
