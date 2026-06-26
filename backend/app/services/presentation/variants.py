from collections.abc import Callable
from typing import Any

_VARIANTS: dict[str, Callable[..., Any]] = {}


def register_variant(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _VARIANTS[name] = func
        return func
    return decorator


def get_variant(name: str) -> Callable[..., Any] | None:
    return _VARIANTS.get(name)


def all_variants() -> dict[str, Callable[..., Any]]:
    return dict(_VARIANTS)
