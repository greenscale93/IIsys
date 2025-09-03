# -*- coding: utf-8 -*-
from typing import Optional, List, Tuple
import pandas as pd
from rapidfuzz import fuzz
from .entities import reload_maps, save_maps, FIELD_RU2CANON, FIELD_ALIASES
from .utils import clean_term, is_guid_col

def unify_field_phrase(text: str) -> Optional[str]:
    if not text: return None
    t = " ".join(text.strip().lower().split())
    for p in t.split():
        if p in FIELD_RU2CANON:
            return FIELD_RU2CANON[p]
    if t in FIELD_RU2CANON:
        return FIELD_RU2CANON[t]
    return None

def pick_column(df: pd.DataFrame, field: str) -> Optional[str]:
    cols = list(df.columns)
    cols = [c for c in cols if not is_guid_col(c)]
    if f"{field}_Наименование" in cols:
        return f"{field}_Наименование"
    if field in cols:
        return field
    lower_map = {c.lower(): c for c in cols}
    for a in FIELD_ALIASES.get(field, []):
        if a.lower() in lower_map:
            return lower_map[a.lower()]
    return None

def suggest_similar_columns(df: pd.DataFrame, field: str, top_n: int = 5) -> List[Tuple[str, int]]:
    bases = set([field, field.lower()])
    for a in FIELD_ALIASES.get(field, []):
        bases.add(str(a)); bases.add(str(a).lower())
    scored = []
    for col in list(df.columns):
        if is_guid_col(col): 
            continue
        cl = col.lower()
        best = max(fuzz.WRatio(cl, b.lower()) for b in bases) if bases else 0
        scored.append((col, int(best)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]

def add_field_alias(alias: str, canonical: str) -> str:
    a = clean_term(alias)
    c = clean_term(canonical)
    FIELD_RU2CANON[a.strip().lower()] = c
    FIELD_ALIASES.setdefault(c, [])
    if a not in FIELD_ALIASES[c]:
        FIELD_ALIASES[c].append(a)
    save_maps()
    return f"✅ Добавлен синоним поля: «{alias}» → «{canonical}» (сохранено)"

def remove_field_alias(canonical: str, alias: str) -> str:
    c = clean_term(canonical)
    a = clean_term(alias)
    removed = False
    if c in FIELD_ALIASES and a in FIELD_ALIASES[c]:
        FIELD_ALIASES[c].remove(a); removed = True
    low = a.strip().lower()
    if low in FIELD_RU2CANON and FIELD_RU2CANON[low] == c:
        del FIELD_RU2CANON[low]; removed = True
    if removed:
        save_maps()
        return f"✅ Удалён синоним поля: «{alias}» из «{canonical}»"
    return f"ℹ Синоним поля «{alias}» для «{canonical}» не найден"

def list_field_aliases():
    items = []
    for canon, aliases in FIELD_ALIASES.items():
        for a in aliases:
            items.append((canon, a))
    items.sort(key=lambda x: (x[0].lower(), x[1].lower()))
    return items