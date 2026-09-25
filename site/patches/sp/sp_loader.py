"""站点 adapter 加载器（经 site-packages 的 .pth 注入，与镜像自带的 sitecustomize 正交）。

设计：
  - 只拦截 TARGETS 里的模块；其余返回 None，交给引擎原有的 finder（LuZ 的 sitecustomize 不受影响）。
  - gate 未开时整段不生效（verify_cap 内部 ENABLED=False，install_* 全部直接返回）。
  - 安装失败即 raise（fail-closed）：宁可启动失败，也不带半套补丁跑生产。
"""
import importlib.abc
import importlib.machinery
import os
import sys

_ADAPTERS = os.path.dirname(os.path.abspath(__file__))
if _ADAPTERS not in sys.path:
    sys.path.insert(0, _ADAPTERS)

TARGETS = {
    "sglang.kernels.ops.moe.moe_fused_gate": ("verify_cap", "install_gate"),
    "sglang.srt.models.deepseek_v4": ("verify_cap", "install_model"),
    "sglang.srt.speculative.dspark_components.dspark_verify": ("verify_cap", "install_verify"),
    "sglang.srt.speculative.dspark_components.dspark_draft": ("verify_cap", "install_draft"),
    "sglang.srt.speculative.dspark_components.dspark_planner": ("verify_cap", "install_planner"),
    "sglang.srt.models.deepseek_v4_dspark": ("verify_cap", "install_dspark"),
}


def _enabled():
    v = os.environ.get("DSV41_VERIFY_CAP", "").strip().lower()
    return v not in ("", "0", "off")


def _apply(fullname, module):
    mod_name, fn_name = TARGETS[fullname]
    try:
        mod = __import__(mod_name)
        getattr(mod, fn_name)(module)
    except Exception as exc:
        print(f"[sp-loader] FATAL: {fn_name} on {fullname} failed: {exc!r}", flush=True)
        raise
    print(f"[sp-loader] {fn_name} <- {fullname}", flush=True)


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
    if not any(getattr(f, "_sp_loader", False) for f in sys.meta_path):
        _f = _Finder()
        _f._sp_loader = True
        sys.meta_path.insert(0, _f)
        print(
            f"[sp-loader] armed for DSV41_VERIFY_CAP={os.environ.get('DSV41_VERIFY_CAP')} "
            f"(router_live={os.environ.get('DSV41_ROUTER_LIVE', '0')}); targets={len(TARGETS)}",
            flush=True,
        )
