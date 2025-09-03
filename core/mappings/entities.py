# -*- coding: utf-8 -*-
from typing import Optional
from .io import load_all, save_all
from .utils import clean_term

ENTITY_EN2RU = {}
ENTITY_RU2CANON = {}
FIELD_RU2CANON = {}
FIELD_ALIASES = {}

def reload_maps():
    global ENTITY_EN2RU, ENTITY_RU2CANON, FIELD_RU2CANON, FIELD_ALIASES
    d = load_all()
    ENTITY_EN2RU = d["entity_en2ru"]
    ENTITY_RU2CANON = d["entity_ru2canon"]
    FIELD_RU2CANON = d["field_ru2canon"]
    FIELD_ALIASES = d["field_aliases"]

def save_maps():
    save_all(ENTITY_EN2RU, ENTITY_RU2CANON, FIELD_RU2CANON, FIELD_ALIASES)

reload_maps()

def unify_entity_phrase(text: str) -> Optional[str]:
    if not text: return None
    t = " ".join(text.strip().lower().split())
    if t in ENTITY_RU2CANON:
        return ENTITY_RU2CANON[t]
    last = t.split()[-1]
    return ENTITY_RU2CANON.get(last)

def add_entity_alias(alias: str, canonical: str) -> str:
    a = clean_term(alias).strip().lower()
    c = clean_term(canonical).strip()
    if a.isascii():
        ENTITY_EN2RU[a] = c
    else:
        ENTITY_RU2CANON[a] = c
    save_maps()
    return f"✅ Добавлен синоним сущности: «{alias}» → «{canonical}» (сохранено)"

def remove_entity_alias(alias: str) -> str:
    a = clean_term(alias).strip().lower()
    removed = False
    if a in ENTITY_EN2RU:
        del ENTITY_EN2RU[a]; removed = True
    if a in ENTITY_RU2CANON:
        del ENTITY_RU2CANON[a]; removed = True
    if removed:
        save_maps()
        return f"✅ Удалён синоним сущности: «{alias}»"
    return f"ℹ Синоним сущности «{alias}» не найден"