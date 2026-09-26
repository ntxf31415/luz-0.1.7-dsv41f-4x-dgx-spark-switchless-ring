"""B4 adapter loader — b12x_next 路由 MoE（knapcio，EP1）。

经 site-packages 的 .pth 注入；与镜像自带的 sitecustomize、与 sp_loader（verify_cap）正交。
**gate 未开（DSV41_MOE_B12X_NEXT 未设）时不安装任何 finder ⇒ 生产零影响。**
适配器自带 fail-closed 漂移自检（PINNED_COMMIT + 符号/源码锚点），本加载器只负责注入时机。
"""
import importlib.abc
import importlib.machinery
import os
import sys

_ADAPTERS = os.path.dirname(os.path.abspath(__file__))
if _ADAPTERS not in sys.path:
    sys.path.insert(0, _ADAPTERS)

TARGETS = {
    # 挂点必须选**镜像 EngramFinder 不拦截**的模块（见 b12x_bootstrap 顶部说明）
    "sglang.srt.layers.quantization.base_config": ("b12x_bootstrap", "install_all"),
    "sglang.srt.layers.moe.moe_runner.base": ("b12x_bootstrap", "install_all"),
}


def _enabled():
    return os.environ.get("DSV41_MOE_B12X_NEXT", "0").strip().lower() not in (
        "0", "", "off", "false")


def _apply(fullname, module):
    mod_name, fn_name = TARGETS[fullname]
    mod = __import__(mod_name)
    fn = getattr(mod, fn_name)
    try:
        fn(module)
    except Exception as exc:
        print(f"[b12x-loader] FATAL: {fn_name} on {fullname} failed: {exc!r}", file=sys.stderr, flush=True)
        raise
    print(f"[b12x-loader] {fn_name} <- {fullname}", file=sys.stderr, flush=True)


class _Loader(importlib.abc.Loader):
    def __init__(self, original, fullname):
        self.original = original
        self.fullname = fullname

    def create_module(self, spec):
        return self.original.create_module(spec)

    def exec_module(self, module):
        self.original.exec_module(module)
        _apply(self.fullname, module)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in TARGETS:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _Loader(spec.loader, fullname)
        return spec


if _enabled():
    if not any(getattr(f, "_b12x_loader", False) for f in sys.meta_path):
        _f = _Finder()
        _f._b12x_loader = True
        sys.meta_path.insert(0, _f)
        print(f"[b12x-loader] armed for DSV41_MOE_B12X_NEXT="
              f"{os.environ.get('DSV41_MOE_B12X_NEXT')}; targets={len(TARGETS)}",
              file=sys.stderr, flush=True)
