from typing import Optional, Iterable, Callable
import json

try:  # Assume we're a sub-module in a package.
    from utils import (
        arguments as arg,
        selection as sf,
        items as it,
    )
except ImportError:  # Apparently no higher-level package has been imported, fall back to a local import.
    from ..utils import (
        arguments as arg,
        selection as sf,
        items as it,
    )


def composite_key(*functions) -> Callable:
    key_functions = arg.update(functions)

    def func(item) -> tuple:
        return sf.get_composite_key(item=item, keys_descriptions=key_functions)
    return func


def value_by_key(key, default=None) -> Callable:
    def func(item):
        if isinstance(item, dict):
            return item.get(key, default)
        elif isinstance(item, (list, tuple)):
            return item[key] if isinstance(key, int) and 0 <= key <= len(item) else None
    return func


def values_by_keys(keys, default=None) -> Callable:
    def func(item) -> list:
        return [value_by_key(k, default)(item) for k in keys]
    return func


def is_in_sample(sample_rate, sample_bucket=1, as_str=True, hash_func=hash) -> Callable:
    def func(elem_id) -> bool:
        if as_str:
            elem_id = str(elem_id)
        return hash_func(elem_id) % sample_rate == sample_bucket
    return func


def same() -> Callable:
    def func(item):
        return item
    return func


def merge_two_items(default_right_name: str = '_right') -> Callable:
    def func(first, second):
        return it.merge_two_items(first=first, second=second, default_right_name=default_right_name)
    return func


def items_to_dict(
        key_func: Optional[Callable] = None,
        value_func: Optional[Callable] = None,
        get_distinct: bool = False,
):
    def func(
            items: Iterable,
            key_function: Optional[Callable] = None,
            value_function: Optional[Callable] = None,
            of_lists: bool = False,
    ):
        return it.items_to_dict(
            items,
            key_function=key_func or key_function,
            value_function=value_func or value_function,
            of_lists=get_distinct or of_lists,
        )
    return func


def json_loads(default=None, skip_errors: bool = False):
    def func(line: str):
        try:
            return json.loads(line)
        except json.JSONDecodeError as err:
            if default is not None:
                return default
            elif not skip_errors:
                raise json.JSONDecodeError(err.msg, err.doc, err.pos)
    return func
