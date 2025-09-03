# -*- coding: utf-8 -*-
"""
Глобальные алиасы значений по справочникам:
  _by_dict[<Справочник>][<алиас:lower>] = "<Канон>"
Старый вид (по entity/field) мигрируется в by_dict по схеме из описание.txt.
"""
import json
import os
from typing import Optional, Dict, List, Tuple

import pandas as pd

from config import VALUE_MAPPINGS_FILE
from core.schema import load_schema, get_ref_dict
from core.mappings.fields import unify_field_phrase

_STORE: Dict[str, Dict[str, Dict[str, str]]] = {}   # {"_by_dict": {...}}
_LOADED = False

def _ensure_file():
    if not os.path.exists(VALUE_MAPPINGS_FILE):
        with open(VALUE_MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"_by_dict": {}}, f, ensure_ascii=False, indent=2)

def _load_raw() -> Dict[str, dict]:
    _ensure_file()
    try:
        with open(VALUE_MAPPINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {"_by_dict": {}}

def _save_raw(data: Dict[str, dict]):
    with open(VALUE_MAPPINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _migrate_if_needed(data: Dict[str, dict]) -> Dict[str, dict]:
    """
    Старый вид:
    {
      "Проекты": {
        "Подразделение": {"дкп 10": "..."},
        "руководителю": {"сорокин": "..."},
        ...
      }
    }
    Новый вид:
    {"_by_dict": {"Сотрудники": {"сорокин": "..."}, "Подразделения": {"дкп 10": "..."}}}
    """
    if "_by_dict" in data:
        data["_by_dict"] = data.get("_by_dict", {})
        return data

    load_schema()
    out = {"_by_dict": {}}
    for entity, fields in (data or {}).items():
        if not isinstance(fields, dict):
            continue
        for field, amap in fields.items():
            if not isinstance(amap, dict):
                continue
            canonical_field = unify_field_phrase(field) or field
            ref = get_ref_dict(entity, canonical_field)
            # Если смогли определить справочник — пишем туда, иначе складываем под псевдоним «entity.field»
            dict_key = ref if ref else f"{entity}.{canonical_field}"
            bucket = out["_by_dict"].setdefault(dict_key, {})
            for alias_l, canon in amap.items():
                bucket[alias_l.strip().lower()] = canon
    return out

def _ensure_loaded():
    global _STORE, _LOADED
    if _LOADED:
        return
    raw = _load_raw()
    _STORE = _migrate_if_needed(raw)
    _LOADED = True

def resolve_value(entity: str, field: str, value: str) -> str:
    """
    Возвращает канон по алиасу с приоритетом:
      1) по справочнику (из схемы Описание.txt) → _by_dict[ref_dict][alias]
      2) по псевдониму "Entity.CanonicalField" (мигрированные старые записи)
      3) исходное значение
    """
    _ensure_loaded()
    load_schema()
    alias = (value or "").strip().lower()
    canonical_field = unify_field_phrase(field) or field
    # 1) по справочнику
    ref = get_ref_dict(entity, canonical_field)
    if ref:
        canon = _STORE["_by_dict"].get(ref, {}).get(alias)
        if canon:
            return canon
    # 2) fallback — старый «namespaced» ключ (после миграции)
    ns_key = f"{entity}.{canonical_field}"
    canon = _STORE["_by_dict"].get(ns_key, {}).get(alias)
    if canon:
        return canon
    return value

def add_value_alias(entity: str, field: str, alias_value: str, canonical_value: str) -> str:
    """
    Сохраняет алиас ГЛОБАЛЬНО по справочнику (по Описание.txt).
    Если не удалось определить справочник — пишет под ключ «Entity.CanonicalField»,
    но рекомендует обновить описание/схему.
    """
    _ensure_loaded()
    load_schema()
    alias_l = (alias_value or "").strip().lower()
    canonical_field = unify_field_phrase(field) or field
    ref = get_ref_dict(entity, canonical_field)
    if ref:
        _STORE["_by_dict"].setdefault(ref, {})[alias_l] = canonical_value
        _save_raw(_STORE)
        return f"✅ Добавлен алиас значения: {ref}: «{alias_value}» → «{canonical_value}» (сохранено)"
    # fallback (не нашли справочник по описанию)
    ns_key = f"{entity}.{canonical_field}"
    _STORE["_by_dict"].setdefault(ns_key, {})[alias_l] = canonical_value
    _save_raw(_STORE)
    return (f"⚠ Не удалось определить справочник по описанию для {entity}.{canonical_field}. "
            f"Временный алиас сохранён под ключом {ns_key}: «{alias_value}» → «{canonical_value}». "
            f"Проверь файл описание.txt для поля {canonical_field} в сущности {entity}.")

def remove_value_alias(entity: str, field: str, alias_value: str) -> str:
    _ensure_loaded()
    load_schema()
    alias_l = (alias_value or "").strip().lower()
    canonical_field = unify_field_phrase(field) or field
    ref = get_ref_dict(entity, canonical_field)
    if ref:
        b = _STORE["_by_dict"].get(ref, {})
        if alias_l in b:
            del b[alias_l]; _save_raw(_STORE)
            return f"✅ Удалён алиас значения: {ref}: «{alias_value}»"
        return f"ℹ Алиас «{alias_value}» не найден для справочника {ref}"
    ns_key = f"{entity}.{canonical_field}"
    b = _STORE["_by_dict"].get(ns_key, {})
    if alias_l in b:
        del b[alias_l]; _save_raw(_STORE)
        return f"✅ Удалён алиас значения: {ns_key}: «{alias_value}»"
    return f"ℹ Алиас «{alias_value}» не найден для {ns_key}"

def suggest_similar_values(series: pd.Series, asked_value: str, top_n: int = 10) -> List[Tuple[str, int]]:
    try:
        from rapidfuzz import fuzz
        ratio = lambda a,b: int(fuzz.WRatio(a,b))
    except Exception:
        ratio = lambda a,b: 0
    vals = pd.unique(series.fillna("").astype(str))
    asked = (asked_value or "").strip().lower()
    scored = []
    for v in vals:
        vv = str(v).strip()
        if not vv: continue
        scored.append((vv, ratio(vv.lower(), asked)))
    scored.sort(key=lambda x: x[1], reverse=True)
    # dedup
    out, seen = [], set()
    for val, sc in scored:
        if val not in seen:
            out.append((val, sc)); seen.add(val)
        if len(out) >= top_n: break
    return out

def list_all() -> List[Tuple[str, str, str, str]]:
    """Плоский список для UI: ("DICT_OR_NSKEY", "", alias, canon)"""
    _ensure_loaded()
    items: List[Tuple[str, str, str, str]] = []
    for ref, amap in _STORE.get("_by_dict", {}).items():
        for a, c in amap.items():
            items.append((ref, "", a, c))
    items.sort(key=lambda x: (x[0].lower(), x[2]))
    return items

def dump_values(full: bool = False) -> str:
    _ensure_loaded()
    if full:
        return json.dumps(_STORE, ensure_ascii=False, indent=2)
    lines=[]
    lines.append("[by_dict]")
    for ref, amap in _STORE.get("_by_dict", {}).items():
        lines.append(f"  - {ref}: {len(amap)} алиасов")
    return "\n".join(lines) if lines else "Пока нет сохранённых мэппингов значений."