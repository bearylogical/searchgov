import collections.abc
from typing import Any


def recursively_make_hashable(value: Any) -> Any:
    """
    Recursively converts mutable collections (dict, list, set) into their
    hashable, canonical counterparts (tuple of sorted items for dicts,
    tuple for lists, frozenset for sets).
    Other types are returned as is, assuming they are hashable.
    """
    if isinstance(value, dict):
        return tuple(
            sorted(
                (k, recursively_make_hashable(v)) for k, v in value.items()
            )
        )
    elif isinstance(value, list):
        return tuple(recursively_make_hashable(item) for item in value)
    elif isinstance(value, set):
        return frozenset(recursively_make_hashable(item) for item in value)
    elif isinstance(value, tuple):
        return tuple(recursively_make_hashable(item) for item in value)

    if not isinstance(value, collections.abc.Hashable):
        # This is a fallback; ideally, all expected unhashable types are converted.
        # Consider logging or more specific error handling if needed.
        raise TypeError(
            f"Value of type {type(value)} is not hashable and not handled: {value!r}"
        )
    return value
