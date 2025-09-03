# -*- coding: utf-8 -*-
"""
Парсер ExportedData/описание.txt → схема полей:
schema[entity][base_field] = {"ref_dict": "...", "name_col": "...", "guid_col": "..."}
где base_field без суффиксов _GUID/_Наименование.
"""
import os
import re
from typing import Dict, Optional
from config import DATA_DIR

_SCHEMA: Dict[str, Dict[str, Dict[str, str]]] = {}
_LOADED = False

def _parse_description(path: str) -> Dict[str, Dict[str, Dict[str, str]]]:
    schema: Dict[str, Dict[str, Dict[str, str]]] = {}
    if not os.path.exists(path):
        return schema

    entity = None
    tmp: Dict[str, str] = {}

    re_entity = re.compile(r"^\s*Справочник:\s*(.+?)\s*$", re.I)
    re_line = re.compile(r"^\s*([A-Za-zА-Яа-яЁё0-9_]+)\s*:\s*(.+?)\s*$")

    def flush_entity(ent: str, bucket: Dict[str, str]):
        if not ent or not bucket:
            return
        ent_map: Dict[str, Dict[str, str]] = {}
        for key, rhs in bucket.items():
            if key.endswith("_GUID") and "GUID справочника" in rhs:
                base = key[:-5]
                ref_dict = rhs.split("GUID справочника", 1)[-1].strip()
                name_col = base + "_Наименование" if (base + "_Наименование") in bucket else ""
                ent_map[base] = {"ref_dict": ref_dict, "guid_col": key, "name_col": name_col}
        if ent_map:
            schema[ent] = ent_map

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            m_ent = re_entity.match(line)
            if m_ent:
                flush_entity(entity, tmp)
                entity = m_ent.group(1).strip()
                tmp = {}
                continue
            if entity:
                m = re_line.match(line)
                if not m:
                    continue
                k = m.group(1).strip()
                v = m.group(2).strip()
                tmp[k] = v

    flush_entity(entity, tmp)
    return schema

def load_schema(force: bool = False) -> None:
    global _LOADED, _SCHEMA
    if _LOADED and not force:
        return
    path = os.path.join(DATA_DIR, "описание.txt")
    _SCHEMA = _parse_description(path)
    _LOADED = True

def get_ref_dict(entity: str, canonical_field: str) -> Optional[str]:
    if not _LOADED:
        load_schema()
    ent = _SCHEMA.get(entity) or {}
    info = ent.get(canonical_field)
    if info:
        return info.get("ref_dict") or None
    for base, info in ent.items():
        if base.lower() == canonical_field.lower():
            return info.get("ref_dict") or None
    return None

def get_name_col(entity: str, canonical_field: str) -> Optional[str]:
    if not _LOADED:
        load_schema()
    ent = _SCHEMA.get(entity) or {}
    info = ent.get(canonical_field)
    if info and info.get("name_col"):
        return info["name_col"]
    for base, info in ent.items():
        if base.lower() == canonical_field.lower() and info.get("name_col"):
            return info["name_col"]
    return None

def get_guid_col(entity: str, canonical_field: str) -> Optional[str]:
    if not _LOADED:
        load_schema()
    ent = _SCHEMA.get(entity) or {}
    info = ent.get(canonical_field)
    if info and info.get("guid_col"):
        return info["guid_col"]
    for base, info in ent.items():
        if base.lower() == canonical_field.lower() and info.get("guid_col"):
            return info["guid_col"]
    return None