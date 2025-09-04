# -*- coding: utf-8 -*-
from typing import List, Tuple
from core.mappings import pick_column, suggest_similar_columns
from .utils import suggest_values_message, suggest_cols_message, handle_value_with_fuzzy
from engine.repl import python_repl_tool, MAGIC
from state import LastSelection
import state

def count_multi(entity: str, pairs: List[Tuple[str, str]], dfs: dict):
    df_var = f"df_{entity}"
    if entity not in dfs:
        return f"⚠ Не найден датафрейм {df_var}. Проверь CSV {entity}.csv."
    df = dfs[entity]
    resolved = []
    for field, value in pairs:
        col = pick_column(df, field)
        if not col:
            suggestions = suggest_similar_columns(df, field, top_n=5)
            state.LastSuggestion.update({
                "kind": "column",
                "entity": entity,
                "field": field,
                "df_name": entity,
                "asked_value": None,
                "candidates": suggestions
            })
            return suggest_cols_message(entity, field, entity, suggestions)
        out_tmp, notes, suggestions = handle_value_with_fuzzy(entity, field, value, df, df_var, col, mode="count")
        if out_tmp.startswith("⚠"):
            return out_tmp
        used_val = LastSelection.get("value")
        resolved.append((col, used_val, notes, suggestions))
    cond_parts = [f"({df_var}[{repr(col)}]=={repr(val)})" for col, val, *_ in resolved]
    code = f"{MAGIC}\nresult = {df_var}[" + " & ".join(cond_parts) + "].shape[0]"
    out = python_repl_tool(code)
    note_lines = []
    for _, _, notes, sugg in resolved:
        for n in notes: note_lines.append(f"- {n}")
        if sugg: note_lines.append(suggest_values_message(entity, "(см. выше поле)", "(см. исходный запрос)", sugg, used=sugg[0]))
    pairs_text = ", ".join([f'{f} = "{v}"' for (f, _), (_, v, *_s) in zip(pairs, resolved)])
    notes_text = ("\n" + "\n".join(note_lines)) if note_lines else ""
    return f'**Применяю шаблон:** Сколько "{entity}" по {pairs_text}{notes_text}\n🧠 **Мой ответ:** {out}'

def list_multi(entity: str, pairs: List[Tuple[str, str]], dfs: dict):
    df_var = f"df_{entity}"
    if entity not in dfs: return f"⚠ Не найден датафрейм {df_var}. Проверь CSV {entity}.csv."
    df = dfs[entity]
    resolved = []
    for field, value in pairs:
        col = pick_column(df, field)
        if not col:
            suggestions = suggest_similar_columns(df, field, top_n=5)
            state.LastSuggestion.update({
                "kind": "column",
                "entity": entity,
                "field": field,
                "df_name": entity,
                "asked_value": None,
                "candidates": suggestions
            })
            return suggest_cols_message(entity, field, entity, suggestions)
        out_tmp, notes, suggestions = handle_value_with_fuzzy(entity, field, value, df, df_var, col, mode="list")
        if out_tmp.startswith("⚠"): return out_tmp
        used_val = LastSelection.get("value")
        resolved.append((col, used_val, notes, suggestions))
    cond_parts = [f"({df_var}[{repr(col)}]=={repr(val)})" for col, val, *_ in resolved]
    name_col = "Наименование" if "Наименование" in df.columns else "GUID"
    code = f"{MAGIC}\nresult = {df_var}[" + " & ".join(cond_parts) + f"][{repr(name_col)}].tolist()"
    out = python_repl_tool(code)
    note_lines = []
    for _, _, notes, sugg in resolved:
        for n in notes: note_lines.append(f"- {n}")
        if sugg: note_lines.append(suggest_values_message(entity, "(см. выше поле)", "(см. исходный запрос)", sugg, used=sugg[0]))
    pairs_text = ", ".join([f'{f} = "{v}"' for (f, _), (_, v, *_s) in zip(pairs, resolved)])
    notes_text = ("\n" + "\n".join(note_lines)) if note_lines else ""
    return f'**Применяю шаблон:** Список "{entity}" по {pairs_text}{notes_text}\n🧠 **Мой ответ:** {out}'