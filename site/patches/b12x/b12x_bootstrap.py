"""B4 注入：包一层镜像自带的 moe_b12x.install*，借它的挂点、在正确时机装上 knapcio 的适配器。

为什么这样做（2026-09-26 实测）：
  * 镜像 sitecustomize 在 DSV41_SOURCE 设了时装 EngramFinder，插在 sys.meta_path[0]，
    且**同样拦截** mxfp4_flashinfer_cutlass_moe 与 moe_runner/flashinfer_cutlass（送 LuZ 自己的
    moe_b12x，挂 DSV41_MOE_B12X 门、对我们 no-op）⇒ 我们的 finder 永远轮不到；
  * 自己挂早期模块（base_config / moe_runner.base）又太早 ⇒ 导入目标时循环导入。
  ⇒ 正解：**复用它的挂点**——在 .pth 阶段把 moe_b12x.install / install_scale_snapshot 包一层，
    它的 EngramLoader 在目标模块 exec 完成后 `from moe_b12x import install` 时会拿到我们这版，
    时机天然正确（无循环、且在 create_weights 之前）。
gate 未开时什么都不做。
"""
import os
import sys

_OFF = ("0", "", "off", "false")
_PATCHED = []


def _enabled():
    return os.environ.get("DSV41_MOE_B12X_NEXT", "0").strip().lower() not in _OFF


def patch_luz_adapter():
    if not _enabled() or _PATCHED:
        return
    try:
        import moe_b12x                                   # LuZ 的适配器（PYTHONPATH 首段）
    except Exception as exc:                              # noqa: BLE001
        print(f"[b12x-boot] no moe_b12x to wrap ({exc!r})", file=sys.stderr, flush=True)
        return
    orig_install = getattr(moe_b12x, "install", None)
    orig_scale = getattr(moe_b12x, "install_scale_snapshot", None)

    def install(module):                                  # moe_runner/flashinfer_cutlass
        if orig_install is not None:
            orig_install(module)
        import moe_b12x_next
        moe_b12x_next.install_runner(module)

    def install_scale_snapshot(module):                   # mxfp4_flashinfer_cutlass_moe
        if orig_scale is not None:
            orig_scale(module)
        import moe_b12x_next
        moe_b12x_next.install_method(module)

    moe_b12x.install = install
    moe_b12x.install_scale_snapshot = install_scale_snapshot
    _PATCHED.append(1)
    print("[b12x-boot] wrapped moe_b12x.install + install_scale_snapshot", file=sys.stderr, flush=True)


patch_luz_adapter()
