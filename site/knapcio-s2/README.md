# 步2：把 knapcio 的栈跑在本站四机上（2026-09-26）

同机同尺对照用。**结论见 `维护手册` P0.52 / `4DGX-基准演进总表` §3.13**：
它的栈在我们硬件上 decode **+36%**、prefill **+38~40%**；但它自报的绝对数（散文 89.8 / step 31.2–32.5 ms）
在本机**复现不出**（66.6 / 51.0）⇒ 其优势约 26% 与环境（fabric + RoCEnante / sparkring NCCL）绑定。

## 四步就位（脚本在本目录）

1. `gen_knapcio_env.py` —— 由它的 `.env.tp4.example` 生成 `~/knapcio/.env.tp4`：
   站点 20 键 + 生产 EXTRA 行（**去掉 RoCE 系**，环网上要关）+ 补 ring 参数。
2. `make_knapcio_weights_vol.sh` —— 建本地权重卷 `dsv41-weights`（bind 到本机权重目录；NFS_SHARE=0 需要）。
3. `patch_knapcio_peer_hca.py` —— 给它的 launcher 注入 per-rank `NCCL_IB_PEER_HCA`（**放在 if/elif 之外**）。
4. `fix_knapcio_ring.py` + `fix_knapcio_overlay.py` —— 环网两处关键修复：
   - 它原代码只在 `NCCL_SWITCHLESS_RING_ONLY=1` 分支调 `nccl_mount_args`（把库**覆盖到 pip 路径**，
     因为 **torch 走自己的 RPATH，`LD_LIBRARY_PATH` 不生效**）⇒ 让 `elif` 分支也调它 + `NCCL_OVERLAY_PIP=1`；
   - **不能启 SWITCHLESS**（我们的 LuZ 库没有 sparkring 的 `SWITCHLESS_RING_ONLY` 标记，预检会拒），
     所以走上面的绕法。
   - 端口：8888 被本站 concurrency-proxy 占用 ⇒ 它的 `PORT` 改 **8899**。

## 复跑

`~/knapcio`（四机）+ 镜像 `dsv41-4x-spark:knapcio`（各 33.5 GB）**原封保留** ⇒ 无需重建；
停我们的栈 → `cd ~/knapcio && ENV_FILE=.env.tp4 ./start-tp4.sh serve`。
⚠️ 两栈**容器同名**（`dsv41-head`/`dsv41-worker`）且同端口 ⇒ 必须先后起、不可并存。
