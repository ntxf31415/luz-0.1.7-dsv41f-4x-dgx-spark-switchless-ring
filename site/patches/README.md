# site/patches — 生产用站点补丁

补丁**不在此目录存被修改的上游文件**（体积大、且可从镜像重新生成）。这里只放生成器，
每个生成器都带锚点断言 + 语法自检，镜像内文件一变就拒绝生成。

| 补丁 | 生成器 | 改什么 | 为什么 |
|---|---|---|---|
| `flashinfer_autotune.py` | `site/tools/make_flashinfer_autotune_patch.py` | `_drop_diverged_autotune_cache()` 里的 `cache_path.unlink(missing_ok=True)` → 日志 + 保留 | TP4/EP2 下各 rank 的 MoE 形状集天然不相交 ⇒ 四份缓存摘要永远不一致 ⇒ 原逻辑每 boot 删缓存、全量重调、tactic 重新抽签（实测同配置跨 boot 长 prefill 差 1.5 倍） |
| `mount/deepseek_v4.py`<br>`mount/dspark_draft.py` | `site/tools/make_upstream_patches.py pr2` | 在两处采样点把多模态哨兵 token（词表实测 422 个：ID `128847..129270` + `129279`）的 logit 置 `-inf` | 这些 ID 是**输入侧**哨兵，不该出现在助手输出里；实测**未打补丁时会真泄漏**（要求原样输出 ⇒ 逐字回吐）。上游 LuZ PR #2 |
| `mount/dspark_worker_v2.py` | `site/tools/make_upstream_patches.py 40111` | `repeat_interleave` 传 `output_size=sum(batch.extend_lens)`，省一次 host 同步 | DSpark prefill slot expansion 每步一次 host 同步；消除后长 prefill 实测约 +1~5%（量级未定）。上游 sglang #40111（已合入 main） |

**挂载方式（2026-09-22 起）**：清单驱动。`site/patches/mount.manifest` 逐行 `源\|容器路径`，
`site/tools/make_site_mounts.py` 把它烘进 `start.sh` 的**两处**（head 的 `cache_mounts` 数组 +
worker 的 `CACHE_VOL` 字符串），运行期行为不变；**改配置 = 改清单 + 重跑生成器**。
生成器保证语法（`bash -n`），且断言在写文件**之前**触发。

⚠️ `~/luz017/site-patches/` **不是共享盘**：新文件必须 `scp` 到四机并校验 md5，否则 docker 会把
不存在的宿主路径当目录创建，mount 报 `not a directory`。

⚠️ 安全前提：四份 per-rank 缓存必须各自完整，否则会出现「部分 rank 命中、部分去调优」，
调优走 TP 计时归约集合 ⇒ 挂死。

⚠️ **验证 token 级屏蔽必须看 ID、不能数字符串**：低编号的 `<|place_holder_mm_span_0001|>`
在词表里**不是**特殊 token（会被拆成 14 个普通 token），模型拼出同样字面量并不触碰被屏蔽的 ID。
正当做法是取 `top_logprobs`，把候选 token 串用 tokenizer 反查 ID 再判断
（见 `site/tools/mm-sentinel-logprob-probe.py`）。
