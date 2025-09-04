# -*- coding: utf-8 -*-
from core.mappings import pick_column, suggest_similar_columns
from .utils import suggest_values_message, suggest_cols_message, handle_value_with_fuzzy
import state

def try_quick_count_structured(entity: str, field: str, value: str, dfs: dict):
    df_var = f"df_{entity}"
    if entity not in dfs:
        return f"⚠ Не найден датафрейм {df_var}. Проверь CSV {entity}.csv."
    df = dfs[entity]
    col = pick_column(df, field)
    if not col:
        suggestions = suggest_similar_columns(df, field, top_n=5)
        # Сохраняем подсказку для !принять_подсказку
        state.LastSuggestion.update({
            "kind": "column",
            "entity": entity,
            "field": field,
            "df_name": entity,
            "asked_value": None,
            "candidates": suggestions
        })
        return suggest_cols_message(entity, field, entity, suggestions)
    out, notes, suggestions = handle_value_with_fuzzy(entity, field, value, df, df_var, col, mode="count")
    if out.startswith("⚠"):
        return out
    notes_text = ("\n" + "\n".join(f"- {n}" for n in notes)) if notes else ""
    sug_text = ("\n" + suggest_values_message(entity, field, value, suggestions, used=suggestions[0])) if suggestions else ""
    return f'**Применяю шаблон:** Сколько "{entity}" по "{field}" = "{value}"{notes_text}{sug_text}\n🧠 **Мой ответ:** {out}'

def try_quick_list_structured(entity: str, field: str, value: str, dfs: dict):
    df_var = f"df_{entity}"
    if entity not in dfs:
        return f"⚠ Не найден датафрейм {df_var}. Проверь CSV {entity}.csv."
    df = dfs[entity]
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
    out, notes, suggestions = handle_value_with_fuzzy(entity, field, value, df, df_var, col, mode="list")
    if out.startswith("⚠"):
        return out
    notes_text = ("\n" + "\n".join(f"- {n}" for n in notes)) if notes else ""
    sug_text = ("\n" + suggest_values_message(entity, field, value, suggestions, used=suggestions[0])) if suggestions else ""
    return f'**Применяю шаблон:** Список "{entity}" по "{field}" = "{value}"{notes_text}{sug_text}\n🧠 **Мой ответ:** {out}'