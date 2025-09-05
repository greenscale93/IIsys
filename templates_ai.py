# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Any, Tuple, Optional, List
import re

from core.mappings import pick_column, resolve_value_info as vm_resolve_info, suggest_similar_values as vm_suggest_vals
import state
from templates_store import (
    list_templates, get_template, match_by_regex,
    render_code, run_template, lookup_alias, lookup_alias_with_values  
)
from llm_qwen import chat_json
import logging
logger = logging.getLogger("ragos")

# --- Хелперы для валидации и отображения схемы ---
def _format_value_suggestions(field: str, asked_value: str, suggestions: list[tuple[str,int]], used: tuple[str,int]) -> str:
    lines = []
    lines.append(f"⚠ Точного значения «{asked_value}» для поля «{field}» не найдено.")
    lines.append(f'→ **Использую ближайшее:** "{used[0]}" (совпадение {used[1]}%).')
    lines.append("**Ближайшие варианты:**")
    for i, (val, score) in enumerate(suggestions[:10], start=1):
        lines.append(f"{i}) {val}  ({score}%)")
    lines.append("")  # пустая строка
    lines.append('Чтобы сохранить алиас и пересчитать — нажмите кнопку ниже «Принять значение».')
    return "\n".join(lines)

def _resolve_params_with_mappings(tpl: dict, params_in: Dict[str, Any], dfs: Dict[str, Any]):
    
    state.LastSuggestion.update({
        "kind": None, "entity": None, "field": None,
        "df_name": None, "asked_value": None, "candidates": []
    })

    params = dict(params_in or {})
    bindings = tpl.get("bindings", {}) or {}
    notes: list[str] = []
    sugg_block: str | None = None
    made_suggestion = False

    for pname, bind in bindings.items():
        if pname not in params:
            continue
        entity = bind.get("entity") or ""
        field  = bind.get("field") or ""
        if not entity or not field or entity not in dfs:
            continue

        df = dfs[entity]
        logger.info("[PARAM.BIND] param=%s entity=%s field=%s", pname, entity, field)
        col = pick_column(df, field)
        if not col:
            logger.warning("[PARAM.NO_COL] entity=%s field=%s", entity, field)
            continue
        logger.info("[PARAM.COL] entity=%s field=%s col=%s", entity, field, col)

        raw = params[pname]
        values = raw if isinstance(raw, list) else [raw]
        resolved_vals = []

        for asked in values:
            asked_s = str(asked)

            # 1) глобальный алиас (value_mappings_user.json)
            canon, origin, bucket = vm_resolve_info(entity, field, asked_s)
            logger.info("[VAL.MAP] entity=%s field=%s asked=%s -> canon=%s origin=%s bucket=%s", entity, field, asked_s, canon, origin, bucket)

            ser = df[col].fillna("").astype(str)

            # 2) точное попадание
            if (ser == str(canon)).any():
                logger.info("[VAL.EXACT] match in column=%s", col)
                resolved_vals.append(canon); continue

            # 3) fuzzy (top-10)
            suggestions = vm_suggest_vals(ser, asked_s, top_n=10)
            if not suggestions:
                logger.warning("[VAL.NOT_FOUND] entity=%s field=%s asked=%s", entity, field, asked_s)
                resolved_vals.append(canon)  # оставим как есть, результат будет 0
                continue

            best_val, best_score = suggestions[0]
            logger.info("[VAL.FUZZY] entity=%s field=%s asked=%s -> used=%s score=%s candidates=%d", entity, field, asked_s, best_val, best_score, len(suggestions))
            resolved_vals.append(best_val)
            notes.append(f'- по полю «{field}»: нет точного «{asked_s}», **использую ближайшее** «{best_val}» ({best_score}%)')

            # Один раз формируем подсказку и показываем кнопку
            if not made_suggestion:
                state.LastSuggestion.update({
                    "kind": "value",
                    "entity": entity,
                    "field": field,
                    "df_name": entity,
                    "asked_value": asked_s,
                    "candidates": suggestions
                })
                state.update_selection(entity, f"df_{entity}", field, col, best_val)
                sugg_block = _format_value_suggestions(field, asked_s, suggestions, (best_val, best_score))
                made_suggestion = True

        params[pname] = resolved_vals if isinstance(raw, list) else resolved_vals[0]

    return params, notes, (sugg_block or "")

def df_schema_brief(dfs: Dict[str, Any]) -> str:
    lines=[]
    for name, df in dfs.items():
        try:
            cols = ", ".join(list(df.columns)[:40])
        except Exception:
            cols = ""
        lines.append(f"df_{name}: {cols}")
    return "\n".join(lines)

def validate_code_uses_existing(dfs: Dict[str, Any], code: str) -> Tuple[bool, str]:
    # 1) проверим датафреймы df_<Имя>
    used_dfs = set(re.findall(r"\bdf_([A-Za-zА-Яа-я0-9_]+)\b", code))
    for ent in used_dfs:
        if ent not in dfs:
            return False, f"⚠ В коде используется неизвестный датафрейм df_{ent}"
    # 2) мягкая проверка колонок: только явные литералы в df_Имя['Колонка'] / ["Колонка"]
    for m in re.finditer(r"df_([A-Za-zА-Яа-я0-9_]+)\s*```math\s*[\"']([^\"']+)[\"']\s*```", code):
        ent, col = m.group(1), m.group(2)
        if ent in dfs and col not in dfs[ent].columns:
            return False, f"⚠ В df_{ent} не найдена колонка «{col}»"
    return True, ""

# --- LLM мэппинг параметров ---

def _try_llm_map_one(question: str, tpl: dict) -> tuple[dict|None, dict|None]:
    system = (
        "Ты извлекаешь значения параметров для указанного шаблона. Отвечай строго JSON. "
        "Нельзя придумывать поля или переводить названия."
    )
    user = (
        f"Вопрос пользователя: {question}\n"
        f"Шаблон: {{'id': '{tpl['id']}', 'text': '{tpl['text']}', 'params': {tpl.get('params', [])}}}\n"
        "Верни JSON: {\"params\": {\"имя\": \"значение\" или [..]}, \"confidence\": 0-100}"
    )
    js = chat_json(system, user)
    if not js:
        return None, None
    return js, js.get("params") or {}

def _try_llm_map_any(question: str) -> tuple[dict|None, dict|None]:
    opts = [{"id": t["id"], "text": t["text"], "params": t.get("params", [])} for t in list_templates()]
    if not opts:
        return None, None
    system = ("Ты подбираешь подходящий шаблон и параметры. Строго JSON. "
              "Нельзя придумывать поля или переводить названия.")
    user = (
        f"Вопрос пользователя: {question}\n"
        f"Варианты шаблонов: {opts}\n"
        "Верни JSON: {\"template_id\":\"...\",\"params\":{...},\"confidence\":0-100}"
    )
    js = chat_json(system, user)
    if not js:
        return None, None
    return js, js.get("params") or {}

# --- Основной роутинг ---

def answer_via_templates(question: str, dfs: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Маршрутизация вопросов через шаблоны (tpl_store.json) с подробным логированием.
    Источники параметров:
      - [PARAM.SOURCE=REGEX] при прямом попадании регуляркой из текста шаблона
      - [PARAM.SOURCE=ALIAS] при совпадении skeleton-алиаса (без LLM)
      - [PARAM.SOURCE=LLM]   при LLM-подборе (fallback)
    """
    import logging, re
    logger = logging.getLogger("ragos")

    logger.info("[Q] %s", question)

    # 1) Прямое совпадение текста с шаблоном (регэксп)
    mm = match_by_regex(question)
    if mm:
        tpl, params = mm
        logger.info("[TPL.MATCH.REGEX] id=%s", tpl["id"])
        logger.info("[PARAM.SOURCE=REGEX] id=%s params=%s", tpl["id"], params)

        params_resolved, notes, sugg_block = _resolve_params_with_mappings(tpl, params, dfs)
        code = render_code(tpl["code_template"], params_resolved)
        ok, err = validate_code_uses_existing(dfs, code)
        logger.info("[CODE.VALIDATE] ok=%s err=%s", ok, err if not ok else "")
        if not ok:
            return (f'**Применяю шаблон:** {tpl["text"]}\n'
                    f'Параметры: {params_resolved}\n'
                    f'⚠ Предупреждение: {err}\n'
                    f'Открой вкладку «🧩 Генератор шаблонов», чтобы скорректировать.', None)

        logger.info("[CODE.RUN] tpl=%s lines=%d preview=%s", tpl["id"], code.count("\n")+1, code[:200].replace("\n","⏎"))
        out = run_template(tpl, params_resolved)
        logger.info("[CODE.RESULT] tpl=%s len=%d preview=%s", tpl["id"], len(str(out)), str(out)[:200].replace("\n","⏎"))
        notes_text = ("\n" + "\n".join(notes)) if notes else ""
        return (f'**Применяю шаблон:** {tpl["text"]}\nПараметры: {params_resolved}{notes_text}'
                f'{("\n" + sugg_block) if sugg_block else ""}\n'
                f'🧠 **Мой ответ:** {out}', None)

    logger.info("[TPL.REGEX.MISS]")

    # 2) Совпадение по skeleton-алиасу (без LLM) — извлекаем значения из {VAL}
    tid, val_list = lookup_alias_with_values(question)
    if tid:
        tpl = get_template(tid)
        if tpl:
            logger.info("[TPL.MATCH.ALIAS] tid=%s", tid)
            logger.info("[PARAM.SOURCE=ALIAS] tid=%s values=%s", tid, val_list)

            # сопоставим извлечённые значения с параметрами по порядку
            names = tpl.get("params", []) or []
            def _split_maybe_list(s: str):
                raw = (s or "").strip().strip(' "\'«»')
                parts = [p.strip(' "\'«»') for p in re.split(r"\s*(?:,|;| и | или |/|\|)\s*", raw) if p.strip()]
                return parts if len(parts) > 1 else raw
            params = {}
            for i, name in enumerate(names):
                params[name] = _split_maybe_list(val_list[i]) if i < len(val_list) else ""
            logger.info("[PARAM.EXTRACT.ALIAS] tid=%s params=%s", tid, params)

            params_resolved, notes, sugg_block = _resolve_params_with_mappings(tpl, params, dfs)
            code = render_code(tpl["code_template"], params_resolved)
            ok, err = validate_code_uses_existing(dfs, code)
            logger.info("[CODE.VALIDATE] ok=%s err=%s", ok, err if not ok else "")
            if not ok:
                return (f'Подходит шаблон: «{tid}» → {tpl["text"]}\n'
                        f'Извлечённые параметры: {params_resolved}\n'
                        f'⚠ Предупреждение: {err}\n'
                        f'Открой вкладку «🧩 Генератор шаблонов», чтобы скорректировать.', None)

            logger.info("[CODE.RUN] tpl=%s lines=%d preview=%s", tpl["id"], code.count("\n")+1, code[:200].replace("\n","⏎"))
            out = run_template(tpl, params_resolved)
            logger.info("[CODE.RESULT] tpl=%s len=%d preview=%s", tpl["id"], len(str(out)), str(out)[:200].replace("\n","⏎"))
            notes_text = ("\n" + "\n".join(notes)) if notes else ""
            return (f'**Применяю шаблон:** {tpl["text"]}\nПараметры: {params_resolved}{notes_text}'
                    f'{("\n" + sugg_block) if sugg_block else ""}\n'
                    f'🧠 **Мой ответ:** {out}', None)

    logger.info("[ALIAS.USE.MISS]")

    # 3) Fallback — LLM-подбор шаблона и параметров (с последующей валидацией кода)
    js, params = _try_llm_map_any(question)
    if js and js.get("template_id"):
        tid = js["template_id"]
        tpl = get_template(tid)
        if tpl:
            logger.info("[TPL.MATCH.LLM] tid=%s confidence=%s", tid, js.get("confidence"))
            logger.info("[PARAM.SOURCE=LLM] tid=%s params=%s", tid, params)

            # первичная валидация кода на видимость df/колонок
            code = render_code(tpl["code_template"], params)
            ok, err = validate_code_uses_existing(dfs, code)
            logger.info("[CODE.VALIDATE] ok=%s err=%s", ok, err if not ok else "")
            if not ok:
                return (f'Подходит шаблон: «{tid}» → {tpl["text"]}\n'
                        f'Извлечённые параметры: {params}\n'
                        f'⚠ Предупреждение: {err}\n'
                        f'Открой вкладку «🧩 Генератор шаблонов», чтобы скорректировать.', None)

            params_resolved, notes, sugg_block = _resolve_params_with_mappings(tpl, params, dfs)
            code = render_code(tpl["code_template"], params_resolved)
            ok, err = validate_code_uses_existing(dfs, code)
            logger.info("[CODE.VALIDATE] ok=%s err=%s", ok, err if not ok else "")
            if not ok:
                return (f'Подходит шаблон: «{tid}» → {tpl["text"]}\n'
                        f'Извлечённые параметры: {params_resolved}\n'
                        f'⚠ Предупреждение: {err}\n'
                        f'Открой вкладку «🧩 Генератор шаблонов», чтобы скорректировать.', None)

            logger.info("[CODE.RUN] tpl=%s lines=%d preview=%s", tpl["id"], code.count("\n")+1, code[:200].replace("\n","⏎"))
            out = run_template(tpl, params_resolved)
            logger.info("[CODE.RESULT] tpl=%s len=%d preview=%s", tpl["id"], len(str(out)), str(out)[:200].replace("\n","⏎"))
            text = (f'Подходит шаблон: «{tid}» → {tpl["text"]}\n'
                    f'Извлечённые параметры: {params_resolved}'
                    f'{("\n" + "\n".join(notes)) if notes else ""}'
                    f'{("\n" + sugg_block) if sugg_block else ""}\n'
                    f'🧪 **Предполагаемый ответ:** {out}')
            sugg = {"kind": "save_alias", "template_id": tid, "question": question}
            return text, sugg

    logger.info("[TPL.MATCH.NONE]")
    return ("ℹ Не удалось подобрать шаблон. Открой вкладку «🧩 Генератор шаблонов», чтобы создать его.", None)

# --- Генерация нового шаблона для вкладки "🧩 Генератор шаблонов" ---

def generate_template_with_llm(question: str, dfs: Dict[str, Any], known: List[Dict[str,Any]]) -> Optional[Dict[str,Any]]:
    """
    Возвращает dict:
      {id, text, params, code_template, [validation_error]}
    """
    schema = df_schema_brief(dfs)
    system = (
        "Ты конструктор шаблонов для Pandas. Отвечай строго JSON. "
        "Используй только существующие датафреймы и колонки. Никаких SQL. "
        "Код должен начинаться с '# RAGOS_AUTOCODE' и класть результат в переменную result."
    )
    user = (
        f"Вопрос: {question}\n"
        f"Доступные датафреймы и колонки:\n{schema}\n"
        f"Примеры шаблонов: {[{'id':t['id'],'text':t['text'],'params':t['params']} for t in known[:5]]}\n"
        "Верни JSON вида: {"
        "\"id\": \"человекочитаемый_id\", "
        "\"text\": \"Текст шаблона с {плейсхолдерами}\", "
        "\"params\": [\"список_параметров\"], "
        "\"code_template\": \"Код с использованием {плейсхолдеров} (для строк подставляй {имя}, для списков подставляй {имя})\"}"
    )
    js = chat_json(system, user)
    if not js:
        return None
    for k in ("id","text","params","code_template"):
        if k not in js:
            return None
    # Валидация на соответствие нашим df/колонкам
    code = render_code(js["code_template"], {p:"TEST" for p in js.get("params",[])})
    ok, err = validate_code_uses_existing(dfs, code)
    logger.info("[CODE.VALIDATE] ok=%s err=%s", ok, err if not ok else "")
    if not ok:
        js["validation_error"] = err
    return js