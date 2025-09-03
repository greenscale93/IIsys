# -*- coding: utf-8 -*-
import json
from typing import List
from config import RULES_FILE

DEFAULT_RULES = [
    "Не переводить русские названия и термины на английский язык.",
    "Не использовать SQL-запросы или pyodbc.",
    "Всегда работать только с CSV-данными (df_<ИмяСправочника>) и графом G.",
    "Если вопрос просит посчитать/найти/отфильтровать по полям CSV, используй встроенные шаблоны (маршрутизатор).",
    "GraphQueryTool используй только для нахождения связей через GUID по Наименованию в кавычках."
]

def load_rules() -> List[str]:
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return DEFAULT_RULES.copy()

def save_rules(rules: List[str]):
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)