# -*- coding: utf-8 -*-
from __future__ import annotations
import json, os, re
from typing import Dict, List, Tuple, Any
from rapidfuzz import fuzz
from config import TPL_STORE_FILE
from engine.repl import MAGIC, python_repl_tool
import logging

_PATTERNS: list[dict] = []
_PATTERNS_READY = False

DEFAULT_STORE = {"version": 1, "templates": [], "aliases": {}}

logger = logging.getLogger("ragos")

def lookup_alias_with_values(question_text: str) -> tuple[str | None, list[str]]:

    store = _load_store()
    q_full = _normalize_spaces(question_text)        # сохраняем пунктуацию и регистр
    q_full_l = q_full.lower()                        # и вариант в нижнем регистре

    # 1) прямое совпадение по skeleton-ключу
    key = _skeleton_quotes(question_text).replace("{val}", "{VAL}")  # у skeleton всегда финальный '?'
    tid = store["aliases"].get(key)
    if tid:
        rx = _alias_key_to_regex(key)
        # пробуем матчиться и с оригиналом, и с lower, чтобы не терять регистр значений
        m = rx.match(q_full) or rx.match(q_full_l)
        if not m:
            logger.warning("[ALIAS.USE.DIRECT.NOEXTRACT] key=%s -> %s (regex didn't capture)", key, tid)
            return None, []  # считаем, что алиас не сработал — пусть дальше попробуют другие ветки
        vals = list(m.groups())
        logger.info("[ALIAS.USE.DIRECT] key=%s -> %s vals=%s", key, tid, vals)
        return tid, vals

    # 2) перебор всех skeleton-алиасов (регэксп)
    for skey, tid in store["aliases"].items():
        rx = _alias_key_to_regex(skey)
        m = rx.match(q_full) or rx.match(q_full_l)
        if m:
            vals = list(m.groups())
            logger.info("[ALIAS.USE.RE] key=%s -> %s vals=%s", skey, tid, vals)
            return tid, vals

    logger.info("[ALIAS.USE.MISS]")
    return None, []

def _ensure_store():
    if not os.path.exists(TPL_STORE_FILE):
        with open(TPL_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STORE, f, ensure_ascii=False, indent=2)

def _load_store() -> Dict[str, Any]:
    _ensure_store()
    try:
        with open(TPL_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("templates", [])
                data.setdefault("aliases", {})
                if _migrate_aliases_if_needed(data):
                    _save_store(data)
                return data
    except Exception:
        pass
    return DEFAULT_STORE.copy()

def _save_store(data: Dict[str, Any]):
    with open(TPL_STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _esc_ws(lit: str) -> str:
    # Экранируем и позволяем гибкие пробелы
    s = re.escape(lit)
    s = re.sub(r"\\\s+", r"\\s+", s)
    s = s.replace(r"\ ", r"\s+")
    return s

def _is_trailing_punct_or_space(s: str) -> bool:
    return re.fullmatch(r"\s*[\?\.!\:;]*\s*", s or "") is not None

def _build_regex_for_template(text: str) -> tuple[re.Pattern, list[str]]:
    param_names: list[str] = []
    pattern = r"^\s*"
    pos = 0
    for m in re.finditer(r"\{([^}]+)\}", text):
        lit = text[pos:m.start()]
        pattern += _esc_ws(lit)
        pname = m.group(1).strip()
        param_names.append(pname)

        # смотрим следующий литерал в шаблоне
        next_m = re.search(r"\{([^}]+)\}", text[m.end():])
        raw_tail = text[m.end(): m.end() + (next_m.start() if next_m else len(text[m.end():]))]

        if _is_trailing_punct_or_space(raw_tail):
            # дальше только пробелы/знаки препинания → ловим до конца строки
            group = rf'[\"«]?(?P<{pname}>.+?)[\"»]?\s*'
        else:
            look = _esc_ws(raw_tail)
            group = rf'[\"«]?(?P<{pname}>.+?)[\"»]?(?={look})'

        pattern += group
        pos = m.end()

    pattern += _esc_ws(text[pos:]) + r'\s*[\?\.!\:;]*\s*$'
    return re.compile(pattern, flags=re.I), param_names

def _compile_patterns():
    global _PATTERNS, _PATTERNS_READY
    if _PATTERNS_READY:
        return
    _PATTERNS = []
    for t in list_templates():
        rx, names = _build_regex_for_template(t.get("text",""))
        _PATTERNS.append({"id": t["id"], "re": rx, "params": names})
    _PATTERNS_READY = True

def _split_maybe_list(s: str) -> list[str] | str:
    raw = (s or "").strip().strip(' "\'«»')
    parts = [p.strip(' "\'«»') for p in re.split(r"\s*(?:,|;| и | или |/|\|)\s*", raw) if p.strip()]
    return parts if len(parts) > 1 else raw

def _normalize_spaces(s: str) -> str:
    return " ".join((s or "").strip().split())

def _skeleton_quotes(s: str) -> str:
    t = (s or "").lower()
    t = re.sub(r'[\"«][^\"»]+[\"»]', "{VAL}", t)  # всегда ВЕРХНИЙ регистр
    t = _normalize_spaces(t)
    t = re.sub(r"\s*[\?\.!\:;]+\s*$", "?", t)
    return t

def _skeleton_for_template(question: str, tpl: dict) -> str:
    sk = _skeleton_quotes(question)
    if "{VAL}" not in sk and len(tpl.get("params", [])) == 1:
        sk = re.sub(r"(\s+)([^\s\?!.:;«»\"]+)(\s*[\?!.:;]*)$", r"\1{VAL}\3", sk)
        sk = _normalize_spaces(sk)
    return sk

def _migrate_aliases_if_needed(store: dict) -> bool:
    aliases = store.get("aliases", {}) or {}
    changed = False
    new_aliases = {}
    for k, v in aliases.items():
        # приведение к скелету и к {VAL}
        sk = _skeleton_quotes(k).replace("{val}", "{VAL}")
        if sk in new_aliases and new_aliases[sk] == v:
            changed = True
            continue
        if sk != k:
            changed = True
        new_aliases[sk] = v
    if changed:
        store["aliases"] = new_aliases
    return changed

def match_by_regex(question: str) -> tuple[dict, dict] | None:
    _compile_patterns()
    for it in _PATTERNS:
        m = it["re"].search(question)
        if not m:
            continue
        params = {}
        for pname in it["params"]:
            val = m.group(pname)
            params[pname] = _split_maybe_list(val)
        logger.info("[TPL.REGEX.HIT] id=%s params=%s", it["id"], params)
        tpl = get_template(it["id"])
        if tpl:
            return tpl, params
    return None

def normalize_alias(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def list_templates() -> List[Dict[str, Any]]:
    return _load_store()["templates"]

def get_template(tid: str) -> Dict[str, Any] | None:
    for t in list_templates():
        if t.get("id") == tid:
            return t
    return None

def add_template(t: Dict[str, Any]) -> str:
    for k in ("id", "text", "params", "code_template"):
        if k not in t:
            return f"⚠ В шаблоне отсутствует поле: {k}"
    store = _load_store()
    if any(x.get("id") == t["id"] for x in store["templates"]):
        return f"⚠ Шаблон «{t['id']}» уже существует"
    store["templates"].append(t)
    _save_store(store)
    return f"✅ Шаблон «{t['id']}» добавлен"

def delete_template(tid: str) -> str:
    store = _load_store()
    n = len(store["templates"])
    store["templates"] = [t for t in store["templates"] if t.get("id") != tid]
    if len(store["templates"]) == n:
        return f"ℹ Шаблон «{tid}» не найден"
    _save_store(store)
    return f"✅ Шаблон «{tid}» удалён"

def add_alias(question_text: str, template_id: str) -> str:
    store = _load_store()
    tpl = get_template(template_id)
    if not tpl:
        return f"⚠ Шаблон «{template_id}» не найден"
    key = _skeleton_for_template(question_text, tpl).replace("{val}", "{VAL}")
    if store["aliases"].get(key) == template_id:
        return f"ℹ Привязка уже существует: «{key}» → «{template_id}»"
    store["aliases"][key] = template_id
    _save_store(store)
    logger.info("[ALIAS.SAVE] key=%s -> %s", key, template_id)
    return f"✅ Привязка сохранена: «{key}» → «{template_id}»"

def _alias_key_to_regex(skey: str) -> re.Pattern:
    # нормализация и гибкие пробелы
    norm = _normalize_spaces(skey).lower().replace("{val}", "{VAL}")
    norm = re.sub(r"\s*[\?\.!\:;]+\s*$", "", norm)
    pat = re.escape(norm)
    pat = pat.replace(r"\{VAL\}", r'[\"«]?(.+?)[\"»]?')
    pat = pat.replace(r"\ ", r"\s+")
    pat = r"^\s*" + pat + r"\s*[\?\.!\:;]*\s*$"
    return re.compile(pat, flags=re.I)

def lookup_alias(question_text: str) -> str | None:
    store = _load_store()
    # 1) прямая проверка по скелету
    key = _skeleton_quotes(question_text).replace("{val}", "{VAL}")
    tid = store["aliases"].get(key)
    if tid:
        logger.info("[ALIAS.USE.DIRECT] key=%s -> %s", key, tid)
        return tid
    # 2) регэксп по всем skeleton-алиасам
    qn = _normalize_spaces(question_text).lower()
    qn = re.sub(r"\s*[\?\.!\:;]+\s*$", "", qn)
    for skey, tid in store["aliases"].items():
        rx = _alias_key_to_regex(skey)
        if rx.match(qn):
            logger.info("[ALIAS.USE.RE] key=%s -> %s", skey, tid)
            return tid
    return None

def search_by_text(q: str, top_n: int = 5) -> List[Tuple[Dict[str, Any], int]]:
    ql = (q or "").strip().lower()
    scored: List[Tuple[Dict[str, Any], int]] = []
    for t in list_templates():
        base = " ".join([str(t.get("text","")), str(t.get("id",""))]).lower()
        scored.append((t, int(fuzz.WRatio(ql, base))))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]

def render_code(code_template: str, params: Dict[str, Any]) -> str:
    # Подставляем repr(value) для простых подстановок {param}
    # и сырые списки для {param_list} если value — list
    fmt: Dict[str, Any] = {}
    for k, v in (params or {}).items():
        if isinstance(v, list):
            fmt[k] = v
        else:
            fmt[k] = repr(v)
    body = code_template.format(**fmt)
    # гарантируем MAGIC во главе
    body = body.strip()
    if not body.startswith(MAGIC):
        body = f"{MAGIC}\n" + body
    return body

def run_template(tpl: Dict[str, Any], params: Dict[str, Any]) -> str:
    code = render_code(tpl["code_template"], params)
    return python_repl_tool(code)