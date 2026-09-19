# LuZ 0.1.7 · 本站部署层与实测

> **本页是本站点适配层的说明。上游原文 README 在仓库根目录 [`README.md`](../README.md)，未作任何改动。**

本仓 = 上游 [luxingcom/LuZ-0.1.7-DeepSeek-v4.1-Flash-DGXspark-TP4-Ring](https://github.com/luxingcom/LuZ-0.1.7-DeepSeek-v4.1-Flash-DGXspark-TP4-Ring)
在 **4× DGX Spark（GB10）无交换机 RoCE 环网**上的**站点部署 + 实测数据**。

- **基底**：上游 commit `70a1d02`，根目录原样保留
- **本站改动**：全部隔离在 `site/`，与上游的差异可用一条命令复现 ⬇️
- **部署形态**：**上游 Form A 原样**（`600K ctx / 9.6M KV 池 / 16 路 / mem_fraction_static 0.90`）
- **两处引擎行为偏离**：① 摘除 `DSV41_MOE_B12X` 族（见 §二）② 站点补丁钉住 autotune 选型（见 §六）

---

## 一、本站改动一览（vs 上游）

```bash
git log --oneline upstream/main..HEAD     # → 1 个提交
git diff --stat upstream/main..HEAD       # → 见下表
```

| # | 改动 | 类型 | 理由 / 证据 |
|---|---|---|---|
| 1 | **摘除 `DSV41_MOE_B12X` 族**（`_B12X` / `_CAPS` / `_QUANT`） | **引擎行为** | 实测两个量化档都更慢、且让贪心输出不可复现（见 §二） |
| 2 | `NCCL_DEBUG_FILE` → `/state/…` | 运维 | 上游 `start.sh` 只在**开发模式**挂 `/nccl-debug`；生产模式日志无处落、环自检只能判失败 |
| 3 | `NCCL_IB_GID_INDEX_FORCE=-1` | 环境 | 本机 kernel-1031 GID 表重排，禁止自动探测（上游模板为 `3`） |
| 4 | served-name 双别名 | 兼容 | 下游门户在用旧名 `deepseek-v4-flash-vision-exp`，去掉即断链 |
| 5 | 四机本地权重 + `WORKER_ENGRAM_DIR` 显式指向 | 环境 | 站点四机全本地；复用现成 48 GB engram 分片，免重打 |
| 6 | `site/tools/` 基准工具集 | **新增代码** | 上游没有：`armsuite.sh` / `night-matrix.sh` / `pr-matrix.sh` / `ab-arm.sh` 等 |
| 7 | `site/results/` 原始产物 | **新增数据** | SD-1 DE 矩阵 4 类型 × 5 并发 × 3 波；PR-v3 24 格；b12x A/B；16K/64K 补测 |
| 8 | `site/config/.env.tp4.example` | 新增配置 | 站点生产配置（已脱敏） |
| 9 | **`site/patches/`：autotune 选型钉住补丁** | **引擎行为** | 上游 SGLang 在 EP 分片下每 boot 删掉 autotune 缓存 ⇒ fused-MoE 选型重新抽签（见 §六） |
| 10 | `site/tools/perf-gate.sh` + 挂进 monitor | 运维 | 每次新 boot 自动跑一次性能门禁（口径 D 8K/100K + PR-v3 131072×C1） |
| 11 | `site/tools/` 新增分析/修补脚本 | **新增代码** | `pr-v3-conical.sh` / `merge_pr_v3_batches.py` / `make_flashinfer_autotune_patch.py` / `make_entropy_variant.py` 等 |
| 12 | **`--prefill-decode-interval 8`**（PDI） | **引擎行为** | 冷长 prefill 期间在途解码流被冻到基线的 **5%**；加此旋钮回到 **41%**，而**独跑冷加载零成本**（见 §七） |
| 13 | `site/tools/` 再增：`pdi-storm-probe.py` / `fingerprint.py` / `prose_bench_sparkdash.py` | **新增代码** | 冻结比探针（口径 H）· 贪心指纹（改输出的改动一律先过它）· sparkDash 口径的散文尺 |
| 14 | `site/tools/patch_gsm8k_thinking.py` | **口径修正** | GSM8K harness 显式钉死 `thinking=false`，消除对引擎默认值的隐式依赖（与上游 PR #1 同款修复） |
| 15 | `site/tools/patch_hc_combine_96.py` / `patch_start_sh_hc96.py` | **证据留档** | 上游 `#40208`（融合 `hc_combine_norm` 扩到 9–96 行）的移植件与挂载器 —— 实测**改输出**（指纹 `13a18f7a…`→`ab56c6d6…`），按纪律**否决并撤回**，脚本保留可复核 |

---

## 二、⭐ 与上游 Form A 的差异：摘除 MoE b12x

上游默认开启 `DSV41_MOE_B12X`（b12x 融合 MoE，README 称其「每个 M 都更快」）。**在本机实测相反**：

| 配置 | prose C1（口径 B） | 贪心输出可复现 |
|---|---:|---|
| b12x **关**（本部署采用） | **55.0** t/s | ✅ 两次/三次一致 |
| b12x `QUANT=a8` | 45.5 | ❌ 三轮三个值 |
| b12x 默认 `a16` | 41.5 | ❌ 两轮两个值 |

**两个量化档都更慢 17–25%，且都破坏贪心可复现性；非量化档（a16）同样不确定** ⇒ 问题在该融合 MoE 路径本身，与 a8 量化无关。
「输出不可复现」对生产是不可接受的，故摘除。

> 对照口径：sparkDash DecodeBench（§三 口径 **B**），同机同靴。

---

## 三、本站实测数据（全部口径）

> ⚠️ **跨口径不可混读**——下表刻意把量法列出来。每个数字都能从 `site/results/` 或阵列 `bench-results/` 复算。

| 口径 | 量法 | 结果 |
|---|---|---|
| **B** | sparkDash DecodeBench（散文，单流，n=9 中位） | **54.4** t/s |
| **C** | `bench_tp` 并发阶梯（code，400 tok 预算） | c1 **60.9** · c2 99.7 · c4 157.0 · c6 198.8 · c8 223.6 · c12 219.3 · c16 **314.4** t/s（聚合） |
| **D** | `prefill_distinct` 长档（needle 校验） | 100K **3159** · 200K **5519** · 470K **3840** t/s；470K 墙钟 **127.7 s** |
| **G1** | PR 单流梯度（口径 D 扫输入尺寸） | 8K 3237 · 32K 3742 · 64K **5478** · 128K **5903** · 256K 5137 t/s |
| **G2** | PR 并发（`conc_long.py`，总 prompt token ÷ 墙钟） | ~32K：c1/c2/c4 = **3386 / 3385 / 3384**（**持平**）· ~131K：3194 / 3220 / 3237 |
| **SD-1 DE** | `benchmarks/de_matrix_v3.py`（本节末表） | 4 类型 × C1/2/4/8/16 = **20/20 格** |

**质量门禁**：`gate --full` **8/8** · GSM8K（8-shot CoT, n=200, temp 0.6）**0.98（196/200）** · 贪心指纹 **`13a18f7a4d677ef4`**（跨 boot 复现）· 长档 needle 100K/200K/470K **全 PASS** · 四机时钟一致 · memguard 全程 **0 次 ABORT**、最低内存地板 **7.99 GB**。

### SD-1 DE 矩阵（4 类型 × C1/2/4/8/16）

格值 = 单流 `median_decode_tps`（`WAVES=3`，`MAXTOK=2048`，原生 `/generate`）：

| 类型 | C1 | C2 | C4 | C8 | C16 | 波次离散度 |
|---|---:|---:|---:|---:|---:|---|
| structured | 77.03 | 72.53 | 49.20 | 30.23 | 25.77 | 6.6–50.1% |
| prose | 50.05 | 37.84 | 27.66 | 17.65 | 14.53 | 0.7–4.4% |
| code（两轮均值） | 89.72 | 74.84 | 57.56 | 40.97 | 37.43 | 0.6–11.1% |
| json | 82.50 | 67.52 | 51.77 | 36.03 | 31.23 | 1.6–3.6% |

**与上游 Form A 对照**（同口径）：json 五档全部领先（+3.2 ~ +8.3%）· prose/code 在 C1/C2 扎实领先（+5.9 ~ +14.4%）、C4–C16 落在噪声内 · structured 在 C1/C2 自身离散度 50%/45%，**不可判**。

### 两条形态结论（实测得出，非引自上游）

1. **并发对长 prefill 零增益** —— ~32K 与 ~131K 在 c1/c2/c4 下聚合速率几乎完全持平。原因是结构性的：`--chunked-prefill-size 4096` 之上，prefill 一请求一请求地推进。
2. **单轮波次离散度高估真实不确定性** —— code 同一格两轮之间的格中位差只有 **0.2–3.9%**，而单轮内波次离散度高达 **11%**。⇒ 跨栈判读看「格中位 + 多轮复测」，有效噪声按 **2–4%** 取；补测 `WAVES` 比补复测的边际收益低。

> **PR（prompt-rate）矩阵 24 格尚未测**——上游 `70a1d02` 撤回了 PR-v2 表、新增 `pr_matrix_v3.py`，待确认口径后再跑。

---

## 四、谱系说明（重要，避免误读上游 README）

上游根 `README.md` 里有两处引用 **`ntxf31415/*`**，需要分清它们与本部署的关系：

| 上游 README 的说法 | 实际关系 |
|---|---|
| 起源表：「SGLang serving recipe（boot、adapters、Engram 行存储、DSpark 设置）来自 `ntxf31415/DeepSeek-v4.1-Flash-DGX-Sparks`」 | 这是**上游自己的归属**，本仓不改变它。**本部署直接采用上游 LuZ 0.1.7 的栈**，不是从该仓库派生。 |
| 「Sister projects：`deepseek-v4-vision-exp-…`（vLLM）· `glm-5.3-flash-nvfp4-…`」 | 那两个是**同一环网上的其他栈**（不同模型 / 不同引擎），与本部署并列而非同源。本部署只涉及 **DeepSeek-V4.1-Flash + SGLang** 这一条线。 |

**一句话**：本仓是三件事——① 上游 LuZ 0.1.7 的栈，② 本站的部署适配层，③ 本站的实测数据。它与 `ntxf31415` 名下的 Vision-Exp / GLM 仓库是**同一台机器上的不同栈**，不共享配方。

---

## 五、目录与复现

```
.github/README.md      ← 本页（GitHub 首页渲染的是这个；上游 README.md 保持原样在根目录）
site/
├── config/.env.tp4.example   # 站点生产配置（已脱敏）
├── tools/                    # 本站基准工具（上游没有）
│   ├── armsuite.sh           # 臂基准：指纹 → 散文 → prefill → 并发 → 内存地板
│   ├── night-matrix.sh       # 按口径矩阵一次跑齐
│   ├── pr-matrix.sh          # PR 矩阵驱动
│   └── ab-arm.sh             # 轻量 A/B 臂
└── results/                  # SD-1 DE 矩阵原始产物（各类型 de_v3_matrix.json）
```

```bash
# 1) 站点配置
cp site/config/.env.tp4.example .env.tp4     # 填回 API_KEY 与本机 IP
# 2) 起栈（用上游自带的编排）
ENV_FILE=.env.tp4 ./start-tp4.sh doctor && ENV_FILE=.env.tp4 WARMUP=0 ./start-tp4.sh serve
# 3) 门禁
ENV_FILE=.env.tp4 ./start-tp4.sh gate --full
# 4) SD-1 DE 矩阵（容器内跑；需要 tokenizer.json 与 tokenizers 库）
cp benchmarks/*.py "$STATE_DIR/sdbench/"
docker exec -e TYPES=structured,prose,code,json -e CONCURRENCIES=1,2,4,8,16 \
  -e WAVES=3 -e MAXTOK=2048 -e KEY_FILE=/state/api-key \
  -e OUT_DIR=/state/bench-results/de -w /state/sdbench \
  dsv41-head python3 /state/sdbench/de_matrix_v3.py
```

## 六、站点补丁：钉住 FlashInfer autotune 选型（上游 EP 分片 bug）

**症状**：同配置跨 boot 的长 prefill 吞吐可差 **1.5 倍**（8K 口径 D 3169 vs 2431 t/s），且抽到慢签的那次会**持续整个进程**。

**根因 —— 在上游 SGLang，非本 fork 特有**：`sglang/srt/model_executor/runner/flashinfer_autotune.py` 的 `_drop_diverged_autotune_cache()` 要求四个 rank **各自** autotune 缓存文件的摘要一致，不一致就把缓存 `unlink` 掉、全部重调。而 **TP4 / EP2** 下每个 rank 拥有不同的专家分片 ⇒ **各自的 MoE GEMM 形状集天然不相交**（实测四份交集为 **0**：rank0 含 `(192,2304,320)`、rank1 含 `(64,2304,320)`…）⇒ 该条件**永不满足** ⇒ 缓存每 boot 被删 ⇒ 全量重调 ⇒ 计时选优的 fused-MoE tactic **每次重新抽签**。

**修法**：`site/patches/` 的站点补丁只改一处 —— 把 `cache_path.unlink(missing_ok=True)` 换成日志 + 保留（判定与 all_gather 保留以便观测）。生成器 `site/tools/make_flashinfer_autotune_patch.py` 从镜像内取原文件、打补丁、`py_compile` 自检（带锚点断言，上游文件一变即拒绝生成）；`site/tools/patch_start_sh_sitepatch.py` 在生产编排里做单文件挂载。

**验证**：修复后每次启动的**调优次数为 0**（= 缓存被真正读取并采用，而非仅被写入），性能稳定同档；贪心指纹全程不变；`gate --full` 8/8、GSM8K 无回归。

⚠️ **前提**：各 rank 自己那份缓存必须**完整**。若出现「部分 rank 命中、部分去调优」，调优会落在 TP 计时归约这个集合操作上 ⇒ **栈起不来** —— 这一点我们踩过。

已上报上游：**[sgl-project/sglang#40320](https://github.com/sgl-project/sglang/issues/40320)**。

---

## 七、为什么本站开 `--prefill-decode-interval 8`

本栈 `enable_mixed_chunk=False`（上游默认，且与 `--enable-encoder-swa-bounded-replay` 硬性互斥）⇒ chunked prefill 的每个 step 都是 **prefill-only**，**正在解码的请求不参与 forward**。一条 100K 冷文档 = 约 25 个连续独占 step。

实测（口径 H：3 条 100K **命中**解码流 + 注入 1 条 100K **冷**请求；冻结比 = 窗内解码速率 ÷ 基线速率）：

| | 冻结比 | 风暴窗 | 窗内三流增量 |
|---|---:|---:|---|
| PDI=0 | **0.051** | 33.8 s | 16 / 16 / 15 |
| **PDI=8（本站采用）** | **0.414** | 57.0 s | 211 / 191 / 192 |
| PDI=16 | 0.590 | 80.9 s | 429 / 426 / 428 |

0.051 的含义是：**在途解码流被冻到基线的 5%**（33.8 s 里每流只吐 16 个 token）—— 那是"回答卡住、像挂了"的体验。

**为什么取 8**：收益 `N/(N+K)`（实测 **K≈11.3**，在 N=8 上冻结比与窗长同时验中）是**凹函数**、代价线性 ⇒ 8 已把"像挂了"变成"明显慢但在走"，再往上加边际收益小、冷加载代价翻倍。关键判据：**独跑冷加载零成本** —— 100K 冷 prefill 33.0 s（PDI=8）vs 32.6 s（PDI=0），多出来的时间**只等于解码流实际干的活** ⇒ 它只在有并发受害者时付费。

⚠️ **一条被自己推翻的结论（留档）**：我们曾测得「PDI=8 让 c16 并发快 22~30%」。按"≥3 轮"复跑后**作废** —— 那是**偶发启动段尖峰**（落在随机某一档，该档聚合 ×0.75，机制未识别）的落点差异造成的**选择性偏差**；剔掉尖峰样本后两配置同带。⇒ **单轮并发阶梯不能归因**，且跨配置比较必须先确认尖峰没落在被比的那一档。

**回滚**：删掉生产 `.env.tp4` 的 `EXTRA_SGLANG_ARGS` 里那一项并重建容器（≤10 min）。

---

**许可**：本仓含上游代码（AGPL-3.0-or-later 等，见根目录 `LICENSE*`）；`site/` 与 `.github/README.md` 为本站新增。
