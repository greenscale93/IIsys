# -*- coding: utf-8 -*-
import re

def clean_term(s: str) -> str:
    """Снимает внешние кавычки/ёлочки, возвращает чистый термин."""
    t = (s or "").strip().strip(' \'"«»')
    m = re.search(r'[\"«]([^\"»]+)[\"»]', t)
    if m:
        return m.group(1).strip()
    return t

def is_guid_col(col_name: str) -> bool:
    c = (col_name or "").strip().lower()
    return c == "guid" or c.endswith("_guid")