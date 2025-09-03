# -*- coding: utf-8 -*-
import re
from .parse import parse_structured
from .single import (
    try_quick_count_structured as _count_single,
    try_quick_list_structured as _list_single,
)
from .multi import (
    count_multi as _count_multi,
    list_multi as _list_multi,
)

__all__ = ["try_quick_count", "try_quick_list"]

def try_quick_count(q: str, dfs: dict):
    parsed = parse_structured(q)
    if not parsed:
        return None
    entity, pairs = parsed
    if len(pairs) == 1:
        field, value = pairs[0]
        return _count_single(entity, field, value, dfs)
    return _count_multi(entity, pairs, dfs)

def try_quick_list(q: str, dfs: dict):
    # Срабатывает только если явно просят список
    if not re.search(r"\b(список|выведи|покажи|перечисли)\b", q, flags=re.I):
        return None
    parsed = parse_structured(q)
    if not parsed:
        return None
    entity, pairs = parsed
    if len(pairs) == 1:
        field, value = pairs[0]
        return _list_single(entity, field, value, dfs)
    return _list_multi(entity, pairs, dfs)