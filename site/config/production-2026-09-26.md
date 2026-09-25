# 生产形态快照 · 2026-09-26（窗口 1 + 窗口 2–4 终态）

> 站点侧记录，**不含站点标识**（IP / API key / 布线一律不入本文件）。
> 权威锚点在部署机 `~/luz028/ANCHORS-0.2.8-W1W4.md`；此处只记**引擎形态键**。

| 键 | 值 | 备注 |
|---|---|---|
| `IMAGE` | `dsv41-sglang-optimized:0.2.8` | 内容身份 `4cca364c46778423`（3 层） |
| `CONTEXT_LENGTH` | **1048576**（1M） | 2026-09-26 由 600000 抬到 1M；945K 冷 needle 实测 PASS（403.5 s） |
| `MAX_RUNNING_REQUESTS` | **9** | 与 1M 配对（9 × 1M ≈ 9.44M ≤ 池 9.6M）；真实并发均值 1.43 / 峰值 4 |
| `MAX_TOTAL_TOKENS` | 9600000 | 池不动 |
| `MEM_FRACTION_STATIC` | 0.90 | |
| `CHUNKED_PREFILL_SIZE` | 8192 | 0.2.8 定板；本栈实测最大单点收益 |
| `EXTRA_SGLANG_ARGS` | `--fp8-gemm-backend flashinfer_cutlass --watchdog-timeout 1800 --enable-metrics --min-free-slots-delay 1 --prefill-decode-interval 8 --max-queued-requests 32` | 比上游定板多 `--max-queued-requests 32`（对齐）· PDI 8（上游定板 4） |
| `DSV41_SKIP_NONFINAL_DECODER` | 1 | **2026-09-25 修回真生效**（此前因少一个空格静默为 false） |
| `DSV41_PREFILL_SHARE_TOKENS` | 0 | 引擎默认即 0 ⇒ 显式写 0 无行为变化 |
| `SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION` | 0 | 对齐上游定板 |
| `DSV41_CACHE_GIB` / `_WAYS` | 1 / 16 | 4 GiB 实测无可测增益（行缓存命中已 96.9%）⇒ 不采用 |
| `SGLANG_DSV4_PAGETABLE_PAGES_GRID` | 1 | **硬前提**（网格关），否则 verify 图捕获崩栈 |
| `DSV41_VERIFY_CAP` | （未设） | 评估件已挂但惰性：`verify_cap` 实测输出中性、收益与跨 boot 变异不可分辨 ⇒ 未采用 |

## 站点层（相对上游 0.2.8 的偏离）

1. **挂载补丁 2 个**：`flashinfer_autotune.py`（钉住 autotune 选型）· `mount/encoding_dsv41.py`（#40758 输入侧占位符转义 **+ reasoning 预算对齐 #39929**）
2. **启动器补丁生成器 3 个**：`patch_start_sh_gidpreflight.py`（GID 洞预检假阳）· `patch_start_sh_clockprobe.py`（head 分支时钟假阳）· **`patch_start_sh_clockprobe_worker.py`（worker 分支时钟假阳，2026-09-26 新增）**
3. **评估件（惰性）**：`site/patches/sp/` → `/sp-adapters` + `zz_sp_loader.pth`（verify_cap 适配器，未开 gate 时不做任何事）
4. **运维**：ring-only 补丁 NCCL 覆盖挂载 · 本地权重 · 自愈 monitor + 重启后性能门禁

## 回退

- **回 600K × 16 路**：改 `.env.tp4` 两行（`CONTEXT_LENGTH` / `MAX_RUNNING_REQUESTS`）+ 重建容器
- **回 0.2.4**：监控 ROOT 改回 `~/luz017` + 起 luz017 栈（其配置原封未动）
