# site/patches — 生产用站点补丁

补丁**不在此目录存被修改的上游文件**（体积大、且可从镜像重新生成）。这里只放生成器，
每个生成器都带锚点断言 + 语法自检，镜像内文件一变就拒绝生成。

| 补丁 | 生成器 | 改什么 | 为什么 |
|---|---|---|---|
| `flashinfer_autotune.py` | `site/tools/make_flashinfer_autotune_patch.py` | `_drop_diverged_autotune_cache()` 里的 `cache_path.unlink(missing_ok=True)` → 日志 + 保留 | TP4/EP2 下各 rank 的 MoE 形状集天然不相交 ⇒ 四份缓存摘要永远不一致 ⇒ 原逻辑每 boot 删缓存、全量重调、tactic 重新抽签（实测同配置跨 boot 长 prefill 差 1.5 倍） |

挂载：`start.sh` 生产分支单文件挂载（head + worker 两处），见 `site/tools/patch_start_sh_sitepatch.py`。

⚠️ 安全前提：四份 per-rank 缓存必须各自完整，否则会出现「部分 rank 命中、部分去调优」，
调优走 TP 计时归约集合 ⇒ 挂死。
