# LuZ 0.1.7 部署层 · 本站点适配

本仓是 [luxingcom/LuZ-0.1.7-DeepSeek-v4.1-Flash-DGXspark-TP4-Ring](https://github.com/luxingcom/LuZ-0.1.7-DeepSeek-v4.1-Flash-DGXspark-TP4-Ring)
（下称「上游」）在某站点 4× DGX Spark 环网上的**部署适配 + 实测记录**。

- **上游树**：完整保留在本仓根目录（基底 = 上游 commit `70a1d02`），未改动——我们的差异全部隔离在 `site/`。
- **本仓形态**：新仓而非 GitHub fork。原因：**GitHub 不允许公开仓库的 fork 设为私有**（本仓最初要求先不公开），且自定义仓名与 fork 互斥。谱系以 `upstream` remote 保留。
- **上游关系**：
  ```bash
  git remote add upstream https://github.com/luxingcom/LuZ-0.1.7-DeepSeek-v4.1-Flash-DGXspark-TP4-Ring.git
  ```

---

## 本站改动一览（vs 上游）

**本仓以上游 `70a1d02` 为基底，其上只有 1 个提交。** 差异可一条命令复现：

```bash
git log --stat upstream/main..HEAD     # 逐文件差异
git diff --stat upstream/main..HEAD    # 只看文件清单
```

| # | 改动 | 类型 | 理由 / 证据 |
|---|---|---|---|
| 1 | **摘除 `DSV41_MOE_B12X` 族** | **引擎行为** | 实测两个量化档都更慢（prose C1 45.5 / 41.5，关闭时 55.0），且让贪心输出不可复现（三次三个值）；非量化档 a16 同样不确定 ⇒ 问题在该融合 MoE 路径本身，与量化无关 |
| 2 | `NCCL_DEBUG_FILE` → `/state/…` | 运维 | 上游 `start.sh` 只在**开发模式**挂 `/nccl-debug`，生产模式日志无处落、环自检只能判失败 |
| 3 | `NCCL_IB_GID_INDEX_FORCE=-1` | 环境 | 本机 kernel-1031 GID 表重排，禁止自动探测（上游模板为 `3`） |
| 4 | 双 served-name 别名 | 兼容 | 下游门户在用旧名 `deepseek-v4-flash-vision-exp`，去掉即断链 |
| 5 | 四机本地权重 + `WORKER_ENGRAM_DIR` 显式指向 | 环境 | 站点四机全本地；复用现成 48 GB engram 分片，免重打 |
| 6 | `site/tools/` 基准工具集 | **新增代码** | 上游没有：`armsuite.sh` / `night-matrix.sh` / `pr-matrix.sh` / `ab-arm.sh` 等 |
| 7 | `site/results/` DE 矩阵原始产物 | **新增数据** | 4 类型 × 5 并发 × 3 波；上游无本栈数据 |
| 8 | `site/config/.env.tp4.example` | 新增配置 | 站点生产配置（已脱敏） |

> 1–5 是**配置层**差异（落在 `site/config/.env.tp4.example` 与 `site/tools/`）；6–8 是**本站新增**，上游完全没有。

---


## 部署形态

镜像 `dsv41-sglang-optimized:v7`（内容身份 `4ebef21b6aedbd70`，SGLang `da64c5cb`），编排层用**上游自带的 `start.sh`**，
站点差异写在 `site/config/.env.tp4.example`。引擎形态 = 上游 **Form A 原样**：

```
600000 ctx / 9,600,000 KV 池 / 16 路 / mem_fraction_static 0.90 / chunked_prefill 4096
```

> 16 × 600000 = 9,600,000 = 池，`start.sh` 的 PIN 守卫（`池 ≥ 路数 × ctx`）等号通过。

## ⭐ 与上游 Form A 的唯一实质偏离

**摘除了 `DSV41_MOE_B12X` 族**（`DSV41_MOE_B12X` / `_CAPS` / `_QUANT`）——上游默认开启。

| 配置 | prose C1（口径 B） | 贪心输出 |
|---|---:|---|
| b12x **关**（本仓采用） | **55.0** t/s | ✅ 两次/三次一致 |
| b12x `QUANT=a8` | 45.5 | ❌ 三次三个值 |
| b12x 默认 `a16` | 41.5 | ❌ 两次两个值 |

**两个量化档都更慢、且都让贪心输出不可复现**；非量化档（a16）同样不确定 ⇒ 问题在该融合 MoE 路径本身，与量化无关。
上游 README 称其「每个 M 都更快」，在本机实测相反。**因此本仓不采用**。

## 其他站点化（不与上游冲突，属环境差异）

| 项 | 本站 | 上游模板 | 说明 |
|---|---|---|---|
| `NCCL_IB_GID_INDEX_FORCE` | `-1` | `3` | 本站 kernel-1031 GID 表重排，禁止自动探测 |
| `SERVED_MODEL_NAME` | 双别名（含旧名） | 单名 | 下游门户在用旧名，去掉即断链 |
| `NCCL_DEBUG` / `_SUBSYS` | `INFO` / `INIT,ENV` | 注释掉 | 环自检需要；`NCCL_DEBUG_FILE` 指向 `/state`（上游只在开发模式挂 `/nccl-debug`） |
| `WORKER_ENGRAM_DIR` | 显式指向现成的 engram 包 | 默认派生 | 复用已有 48 GB 分片，免重打 |
| 权重布局 | 四机全本地 | 两 worker 走 NFS | `WEIGHTS_MODE=local` |

## 目录

```
site/
├── config/.env.tp4.example         # 本站生产配置（已脱敏：API_KEY 与 IP 为占位符）
├── tools/                   # 本站基准工具（上游没有的）
│   ├── armsuite.sh          # 臂基准（指纹→散文→prefill→并发→内存地板）
│   ├── night-matrix.sh      # 按口径矩阵一次跑齐
│   ├── pr-matrix.sh         # PR（prompt-rate）矩阵
│   └── ab-arm.sh            # 轻量 A/B 臂
└── results/                 # DE 矩阵原始产物（SD-1 口径，各类型 de_v3_matrix.json）
```

## 已完成的基准（SD-1 口径，`benchmarks/de_matrix_v3.py`）

**DE 矩阵 20/20 格**（4 类型 × C1/2/4/8/16，格值 = 单流 t/s）：

| 类型 | C1 | C2 | C4 | C8 | C16 | 波次离散度 |
|---|---:|---:|---:|---:|---:|---|
| structured | 77.03 | 72.53 | 49.20 | 30.23 | 25.77 | 6.6–50.1% |
| prose | 50.05 | 37.84 | 27.66 | 17.65 | 14.53 | 0.7–4.4% |
| code（两轮均值） | 89.72 | 74.84 | 57.56 | 40.97 | 37.43 | 0.6–11.1% |
| json | 82.50 | 67.52 | 51.77 | 36.03 | 31.23 | 1.6–3.6% |

**与上游 Form A 对照**（同口径）：

- **json**：五档全部领先（+3.2 ~ +8.3%），离散最紧（1.6–3.6%）
- **prose / code**：C1/C2 扎实领先（+5.9 ~ +14.4%），C4–C16 落在噪声内
- **structured**：C1/C2 自身离散度 50.1% / 45.4%，**不可判**（上游也记录该类型是所有类型里最噪的）

**质量**：`gate --full` 8/8 · GSM8K 0.98（196/200）· 贪心指纹 `13a18f7a4d677ef4`（跨 boot 复现）· 长档 470K needle PASS 127.7 s。

> **PR 矩阵（24 格）尚未测**，网格与口径见上游 `benchmarks/README.md`。

## 一条方法论（本站实测得出）

**判读跨栈差异时看「格中位 + 多轮复测」，不要看单轮内的波次离散度**——
实测同一格两轮之间的格中位差只有 0.2–3.9%，而单轮内波次离散度高达 11% ⇒ **波次离散度高估了真实不确定性**。
有效噪声按 **2–4%** 取；仅凭单轮数据不足以支撑跨栈结论。

## 复现

```bash
# 1) 站点配置
cp site/config/.env.tp4.example .env.tp4     # 填回 API_KEY 与本机 IP
# 2) 起栈（用上游自带的编排）
ENV_FILE=.env.tp4 ./start-tp4.sh doctor
ENV_FILE=.env.tp4 WARMUP=0 ./start-tp4.sh serve
# 3) 门禁
ENV_FILE=.env.tp4 ./start-tp4.sh gate --full
# 4) DE 矩阵（容器内跑，需要 tokenizer.json 与 tokenizers 库）
cp benchmarks/*.py "$STATE_DIR/sdbench/"
docker exec -e TYPES=structured,prose,code,json -e CONCURRENCIES=1,2,4,8,16 \
  -e WAVES=3 -e MAXTOK=2048 -e KEY_FILE=/state/api-key \
  -e OUT_DIR=/state/bench-results/de -w /state/sdbench \
  dsv41-head python3 /state/sdbench/de_matrix_v3.py
```

---

**注意**：本仓含上游代码（AGPL-3.0-or-later 等，见上游 `LICENSE*`），`site/` 为本站点新增。
