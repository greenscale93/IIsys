# -*- coding: utf-8 -*-
from typing import List, Tuple

from core.mappings import (
    resolve_value as _resolve_val,
    suggest_similar_values as _sugg_vals,
)

# ВАЖНО: MAGIC/REPL берём из engine.repl (без кругового импорта)
from engine.repl import python_repl_tool, MAGIC
import state

def suggest_cols_message(entity: str, field: str, df_name: str, suggestions: List[Tuple[str, int]]) -> str:
    if not suggestions:
        return f"⚠ В {entity} не найден столбец для реквизита «{field}», и похожих колонок не нашлось."
    lines = [f"⚠ В {entity} не найден столбец для реквизита «{field}».", "Нашёл похожие колонки:"]
    for i, (col, score) in enumerate(suggestions, start=1):
        lines.append(f"  {i}) {col}  (совпадение {score}%)")
    lines += [
        "",
        "Можно принять подсказку командой:",
        "  !принять_подсказку [номер]   (по умолчанию 1)",
        f'Или явно добавить алиас:\n  !запомни_поле {field} ~ "{suggestions[0][0]}"'
    ]
    return "\n".join(lines)

def suggest_values_message(entity: str, field: str, asked_value: str, suggestions: List[Tuple[str, int]], used=None) -> str:
    lines = [
        f"⚠ Точного значения «{asked_value}» для поля «{field}» не найдено в «{entity}».",
        (f'→ **Использую ближайшее:** "{used[0]}" (совпадение {used[1]}%).' if used
         else "→ **Ближайшие варианты:**")
    ]
    for i, (val, score) in enumerate(suggestions, start=1):
        lines.append(f"  {i}) {val}  ({score}%)")
    lines += ["", "Принять подсказку и запомнить алиас:",
              "  !принять_значение [номер]   (по умолчанию 1)"]
    if suggestions:
        top_val = suggestions[0][0]
        lines += ["Или явно добавить алиас значения:",
                  f'  !запомни_значение {field} ~ "{asked_value}" = "{top_val}"']
    return "\n".join(lines)

def handle_value_with_fuzzy(entity: str, field: str, value: str, df, df_var: str, column: str, mode: str):
    """
    Возвращает (out_text, notes, suggestions)
    """
    notes: List[str] = []
    suggestions: List[Tuple[str, int]] = []

    val = _resolve_val(entity, field, value)
    series = df[column].fillna("").astype(str)

    # точное совпадение
    if (series == str(val)).any():
        if mode == "count":
            code = f"{MAGIC}\nresult = {df_var}[{df_var}[{repr(column)}] == {repr(val)}].shape[0]"
        else:
            name_col = "Наименование" if "Наименование" in df.columns else "GUID"
            code = f"{MAGIC}\nresult = {df_var}[{df_var}[{repr(column)}]=={repr(val)}][{repr(name_col)}].tolist()"
        return python_repl_tool(code), notes, suggestions

    # fuzzy
    suggestions = _sugg_vals(series, value, top_n=10)
    if not suggestions:
        return f"⚠ Не нашёл значение «{value}» для поля «{field}», и похожих значений нет.", notes, suggestions

    best_val, best_score = suggestions[0]
    if mode == "count":
        code = f"{MAGIC}\nresult = {df_var}[{df_var}[{repr(column)}] == {repr(best_val)}].shape[0]"
    else:
        name_col = "Наименование" if "Наименование" in df.columns else "GUID"
        code = f"{MAGIC}\nresult = {df_var}[{df_var}[{repr(column)}]=={repr(best_val)}][{repr(name_col)}].tolist()"
    out = python_repl_tool(code)

    state.LastSuggestion.update({
        "kind": "value",
        "entity": entity,
        "field": field,
        "df_name": entity,
        "asked_value": value,
        "candidates": suggestions
    })
    note = f'по полю «{field}»: нет точного «{value}», использовано «{best_val}» ({best_score}%)'
    notes.append(note)
    state.update_selection(entity, df_var, field, column, best_val)

    return out, notes, suggestions