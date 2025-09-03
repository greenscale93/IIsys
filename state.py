# -*- coding: utf-8 -*-
from typing import Optional, List, Dict, Any

# Последний отбор («эти/их»)
LastSelection = {
    "entity": None,   # "Проекты"
    "df_var": None,   # "df_Проекты"
    "field": None,    # "Контрагент"
    "column": None,   # "Контрагент_Наименование"
    "value": None     # "Скаенг"
}

# История
ChatHistory: list[dict] = []
LastQuestion: Optional[str] = None
LastAnswer: Optional[str] = None
LastCode: Optional[str] = None
LastResultStr: Optional[str] = None

# Последняя подсказка (колонки или значения)
LastSuggestion = {
    "kind": None,          # "column" | "value"
    "entity": None,        # "Проекты"
    "field": None,         # "Подразделение"
    "df_name": None,       # "Проекты"
    "asked_value": None,   # запрошенное значение (для kind="value")
    "candidates": []       # [(строка, score), ...]
}

# Последняя операция добавления (для !отменитьДобавление)
LastAddOperation: Optional[dict] = None
# Пример:
# {"kind":"field", "canonical":"Подразделение", "alias":"ОтветственноеПодразделение_Наименование"}
# {"kind":"value", "entity":"Проекты", "field":"Подразделение", "alias":"дкп 10", "canonical":"ДКП 10 (Сорокин)"}
# {"kind":"entity", "alias":"projects"}

# Список для удаления (последний показанный пользователю)
LastForgetList = {
    "section": None,   # "fields" | "values"
    "entries": []      # список словарей с данными для удаления
}

def update_selection(entity, df_var, field, column, value):
    LastSelection.update({
        "entity": entity, "df_var": df_var, "field": field, "column": column, "value": value
    })

def remember_exchange(q: str, a: str):
    ChatHistory.append({"q": q, "a": a})

def history_text(n: int = 5) -> str:
    items = ChatHistory[-n:]
    lines = []
    for it in items:
        lines.append("Пользователь: " + it["q"])
        lines.append("Ассистент: " + it["a"])
    return "\n".join(lines)