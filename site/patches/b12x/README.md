# b12x 评估件（B4）

`b12x_next` 路由 MoE（knapcio 谱系）在本站的**注入件**。`DSV41_MOE_B12X_NEXT` 未设时完全惰性。

## 为什么是"包一层"而不是自建 finder

镜像自带的 `/opt/dsv41/adapter/sitecustomize.py` 在 **`DSV41_SOURCE` 设了时**（我们的 start.sh 会设）
会 `sys.meta_path.insert(0, EngramFinder())`，而它**同样拦截**：

- `sglang.srt.layers.quantization.mxfp4_flashinfer_cutlass_moe`
- `sglang.srt.layers.moe.moe_runner.flashinfer_cutlass`

并把它们送进 LuZ 自己的 `moe_b12x`（挂在 `DSV41_MOE_B12X` 门后，对我们等于 no-op）。
⇒ 我们自己挂在 `.pth` 的 finder **永远轮不到**（它在 `meta_path[1]`），而挂更早的模块
（`base_config` / `moe_runner.base`）又会撞**循环导入**。

**正解**：在 `.pth` 阶段把 `moe_b12x.install` / `install_scale_snapshot` **包一层**
（`b12x_bootstrap.py`）—— 镜像的 `EngramLoader` 在目标模块 exec 完成后才 `from moe_b12x import install`，
拿到的就是我们的版本，**时机天然正确**（无循环、且在 `create_weights` 之前）。

⚠️ 另一个坑：**加载器里不能有 stdout 输出** —— 适配器用子进程解析 b12x_next 的 `SOURCE_COMMIT`，
任何 stdout 噪声都会被当成 commit。所有日志走 stderr。

## 未随本仓分发的部分

`b12x_next/`（13 MB 包，`SOURCE_COMMIT=a7d7d29b…`，Apache-2.0）**不 vendored 进本仓**。
获取方式：`knapcio/DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4` 的 `runtime/b12x_next/b12x_next`
（或用它仓里的 `scripts/build_b12x_next.sh` 从 `local-inference-lab/b12x` 构建）。

## 未打的上游运行时补丁（要再评须先补）

- `scripts/b12x_next-compact-n64-m64.patch`
- `scripts/b12x_next-prequant-input.patch`
- `scripts/b12x_next-det-triton-planner.patch`

## 结论

见 `维护手册` P0.51 与 `4DGX-基准演进总表` §3.12：**否决**（慢 26× + 指纹不可复现）。
