# -*- coding: utf-8 -*-
import json, os, shutil
from typing import Dict
from config import MAPPINGS_USER_FILE, MAPPINGS_DEFAULTS_FILE

def _read_json(path: str) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _deep_merge_dicts(a: Dict, b: Dict) -> Dict:
    """возвращает merge(a,b) = b поверх a (только для одноуровневых словарей и списков в field_aliases)."""
    out = {}
    # простые словари: entity_en2ru, entity_ru2canon, field_ru2canon
    for k in ("entity_en2ru", "entity_ru2canon", "field_ru2canon"):
        ad = {kk.lower(): vv for kk, vv in (a.get(k, {}) or {}).items()}
        bd = {kk.lower(): vv for kk, vv in (b.get(k, {}) or {}).items()}
        ad.update(bd)
        out[k] = ad
    # field_aliases: списки объединяем уникально
    fa = a.get("field_aliases", {}) or {}
    fb = b.get("field_aliases", {}) or {}
    merged = {}
    keys = set(fa.keys()) | set(fb.keys())
    for key in keys:
        lst = []
        for src in (fa.get(key, []), fb.get(key, [])):
            for x in (src or []):
                if x not in lst:
                    lst.append(x)
        merged[key] = lst
    out["field_aliases"] = merged
    return out

def load_all() -> Dict[str, dict]:
    """Всегда мерджим defaults + user, чтобы нормализации полей были доступны."""
    defaults = _read_json(MAPPINGS_DEFAULTS_FILE)
    user = _read_json(MAPPINGS_USER_FILE)
    if not user and os.path.exists(MAPPINGS_DEFAULTS_FILE) and not os.path.exists(MAPPINGS_USER_FILE):
        # если пользовательский отсутствует — скопируем дефолт в user (для дальнейших правок)
        try:
            shutil.copyfile(MAPPINGS_DEFAULTS_FILE, MAPPINGS_USER_FILE)
        except Exception:
            pass
    merged = _deep_merge_dicts(defaults, user)
    return merged

def save_all(entity_en2ru, entity_ru2canon, field_ru2canon, field_aliases):
    data = {
        "entity_en2ru": entity_en2ru,
        "entity_ru2canon": entity_ru2canon,
        "field_ru2canon": field_ru2canon,
        "field_aliases": field_aliases
    }
    with open(MAPPINGS_USER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)