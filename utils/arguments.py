from typing import Callable

try:  # Assume we're a submodule in a package.
    from base.classes.auto import Auto
    from base.functions.arguments import get_names, get_name, get_value, update
    from utils.decorators import deprecated, deprecated_with_alternative
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ..base.classes.auto import Auto
    from ..base.functions.arguments import get_names, get_name, get_value, update
    from .decorators import deprecated, deprecated_with_alternative


@deprecated
def apply(func: Callable, *args, **kwargs):
    return func(*args, **kwargs)


@deprecated_with_alternative('Auto.is_defined()')
def is_defined(obj, check_name: bool = True) -> bool:
    return Auto.is_defined(obj, check_name=check_name)


@deprecated_with_alternative('Auto.simple_acquire()')
def simple_acquire(current, default):
    return Auto.simple_acquire(current, default)


@deprecated_with_alternative('Auto.delayed_acquire()')
def delayed_acquire(current, func: Callable, *args, **kwargs):
    return Auto.delayed_acquire(current, func, *args, **kwargs)


@deprecated_with_alternative('Auto.acquire()')
def acquire(current, default, delayed=False, *args, **kwargs):
    return Auto.acquire(current, default, delayed=delayed, *args, **kwargs)
