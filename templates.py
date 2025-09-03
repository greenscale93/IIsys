# -*- coding: utf-8 -*-
"""
DSL-шаблоны: хранение в templates.json и одноразовый запуск ad-hoc (run_template_obj).
"""
import json
import os
from typing import Dict, Any, List, Tuple, Optional

import pandas as pd

from core.mappings import (
    unify_entity_phrase, unify_field_phrase, pick_column,
)
from core.mappings.values import resolve_value as vm_resolve_value, suggest_similar_values
from core.schema import get_ref_dict
from engine.repl import python_repl_tool, MAGIC
from config import TEMPLATES_FILE

def _ensure_templates_file():
    if not os.path.exists(TEMPLATES_FILE):
        with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "templates": []}, f, ensure_ascii=False, indent=2)

def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_json(path: str, data: Dict[str, Any]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_templates() -> Dict[str, Dict[str, Any]]:
    _ensure_templates_file()
    data = _read_json(TEMPLATES_FILE)
    return {t["name"]: t for t in data.get("templates", [])}

def save_templates(templates: Dict[str, Dict[str, Any]]):
    data = {"version": 1, "templates": list(templates.values())}
    _write_json(TEMPLATES_FILE, data)

def add_template(obj: Dict[str, Any]) -> str:
    for key in ("name", "operation"):
        if key not in obj:
            return f"⚠ В шаблоне отсутствует {key}"
    tm = load_templates()
    if obj["name"] in tm:
        return f"⚠ Шаблон «{obj['name']}» уже есть"
    tm[obj["name"]] = obj
    save_templates(tm)
    return f"✅ Шаблон «{obj['name']}» добавлен"

def delete_template(name: str) -> str:
    tm = load_templates()
    if name not in tm:
        return f"ℹ Шаблон «{name}» не найден"
    del tm[name]; save_templates(tm)
    return f"✅ Шаблон «{name}» удалён"

def show_template(name: str) -> str:
    t = load_templates().get(name)
    if not t:
        return f"ℹ Шаблон «{name}» не найден"
    return json.dumps(t, ensure_ascii=False, indent=2)

def run_template(name: str, params: Dict[str, Any], dfs: Dict[str, pd.DataFrame]) -> str:
    t = load_templates().get(name)
    if not t:
        return f"ℹ Шаблон «{name}» не найден"
    return run_template_obj(t, params, dfs)

def run_template_obj(t: Dict[str, Any], params: Dict[str, Any], dfs: Dict[str, pd.DataFrame]) -> str:
    """Одноразовый запуск шаблона без сохранения в файл."""
    # 1) entity
    entity = t.get("entity") or params.get(t.get("entity_param",""))
    if not entity:
        return "⚠ В шаблоне не указана сущность"
    entity = unify_entity_phrase(entity) or entity
    df_var = f"df_{entity}"
    if entity not in dfs:
        return f"⚠ Нет датафрейма {df_var}"
    df = dfs[entity]

    # 2) filters -> resolve cols/values
    pairs = []
    for f in t.get("filters", []):
        field = f.get("field") or params.get(f.get("field_param",""))
        if not field:
            return "⚠ Не указан фильтр field/field_param"
        field = unify_field_phrase(str(field)) or str(field)

        value = f.get("value")
        if value is None:
            p = f.get("param")
            if p not in params:
                return f"⚠ Не указан параметр значения: {p}"
            value = params[p]
        value = str(value)

        col = pick_column(df, field)
        if not col:
            return f"⚠ В {entity} не найдена колонка для поля «{field}»"
        # мэппинг значений глобально по справочнику
        used = vm_resolve_value(entity, field, value)
        pairs.append((col, used, field, value))

    # 3) mask
    if pairs:
        cond = " & ".join([f"(df_{entity}[{repr(col)}]=={repr(val)})" for col, val, *_ in pairs])
        df_expr = f"df_{entity}[{cond}]"
    else:
        df_expr = f"df_{entity}"

    op = t.get("operation","").lower()
    list_field = t.get("list_field","Наименование")
    # list target column
    if list_field and list_field != "Наименование":
        # если list_field — логическое имя поля
        lcol = pick_column(df, unify_field_phrase(list_field) or list_field) or list_field
    else:
        lcol = "Наименование" if "Наименование" in df.columns else "GUID"

    if op == "count":
        code = f"{MAGIC}\nresult = {df_expr}.shape[0]"
    elif op == "list":
        code = f"{MAGIC}\nresult = {df_expr}[{repr(lcol)}].tolist()"
    else:
        return f"⚠ Неизвестная операция: {op}"

    # 4) run
    out = python_repl_tool(code)

    # 5) пояснения (ref_dict)
    notes = []
    for col, used_val, field, orig_val in pairs:
        ref = get_ref_dict(entity, unify_field_phrase(field) or field)
        if ref:
            notes.append(f"- поле «{field}» связано со справочником «{ref}»; использовано значение «{used_val}»")
    notes_text = ("\n" + "\n".join(notes)) if notes else ""
    return f"Шаблон (ad-hoc): {t.get('name','<без имени>')}\nСущность: {entity}\nОперация: {op}\nФильтры: " + \
           ", ".join([f"{f}=\"{v}\"" for _, v, f, v in pairs]) + f"{notes_text}\nОжидаемый результат:\n{out}"