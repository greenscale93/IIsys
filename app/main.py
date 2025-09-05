# -*- coding: utf-8 -*-
import sys, os, re
from pathlib import Path

# приоритет пути scripts
scripts_dir = Path(__file__).resolve().parents[1]
scripts_dir_str = str(scripts_dir)
if scripts_dir_str not in sys.path:
    sys.path.insert(0, scripts_dir_str)

import state
import rules_io
from data.loader import load_dataframes
from engine.repl import register_dataframes, register_graph
from engine.router import try_quick_count, try_quick_list
from graph.tool import load_graph
from core.mappings import add_field_alias
import core.mappings as mp
from core.mappings import add_value_alias, remove_value_alias  # если у вас отдельный модуль values — импортируйте его как раньше
from templates_ai import answer_via_templates
from templates_store import add_alias as add_tpl_alias
import logging
from datetime import datetime
from config import LOGS_DIR

SESSION_LOG = os.path.join(LOGS_DIR, f"cli_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(SESSION_LOG, encoding="utf-8", delay=True)]
)
logging.getLogger("ragos").setLevel(logging.INFO)

def is_structured(q: str) -> bool:
    return bool(re.search(r'\b(сколько|список|найд[иё])\b', q.lower()))

def handle_accept_col_suggestion(q: str) -> str | None:
    m = re.match(r'!принять_подсказку(?:\s+(\d+))?$', q.strip(), flags=re.I)
    if not m:
        return None
    if not state.LastSuggestion.get("candidates") or state.LastSuggestion.get("kind") != "column":
        return "⚠ Нет сохранённой подсказки по колонкам."
    idx = int(m.group(1)) if m.group(1) else 1
    cands = state.LastSuggestion["candidates"]
    if idx < 1 or idx > len(cands):
        return f"⚠ Неверный номер. Укажи 1..{len(cands)}."
    chosen_col = cands[idx-1][0]
    # защита от GUID
    low = chosen_col.strip().lower()
    if low.endswith("_guid") or low == "guid":
        return f"🚫 Колонка «{chosen_col}» похожа на GUID. Выбери другую."
    field = state.LastSuggestion["field"]
    msg = add_field_alias(chosen_col, field)
    state.LastAddOperation = {"kind":"field","canonical":field,"alias":chosen_col}
    # повтор последнего вопроса
    if state.LastQuestion:
        out = try_quick_count(state.LastQuestion, DFS_REG) or try_quick_list(state.LastQuestion, DFS_REG)
        return msg + ("\nПовторный ответ с учётом алиаса:\n" + out if out else "")
    return msg

def handle_accept_value_suggestion(q: str) -> str | None:
    m = re.match(r'!принять_значение(?:\s+(\d+))?$', q.strip(), flags=re.I)
    if not m:
        return None
    if not state.LastSuggestion.get("candidates") or state.LastSuggestion.get("kind") != "value":
        return "⚠ Нет сохранённой подсказки по значениям."
    idx = int(m.group(1)) if m.group(1) else 1
    cands = state.LastSuggestion["candidates"]
    if idx < 1 or idx > len(cands):
        return f"⚠ Неверный номер. Укажи 1..{len(cands)}."
    chosen_val = cands[idx-1][0]
    entity = state.LastSuggestion["entity"]
    field  = state.LastSuggestion["field"]
    asked  = state.LastSuggestion.get("asked_value") or chosen_val
    msg = add_value_alias(entity, field, asked, chosen_val)
    state.LastAddOperation = {"kind":"value","entity":entity,"field":field,"alias":asked,"canonical":chosen_val}
    if state.LastQuestion:
        out = try_quick_count(state.LastQuestion, DFS_REG) or try_quick_list(state.LastQuestion, DFS_REG)
        return msg + ("\nПовторный ответ с учётом алиаса:\n" + out if out else "")
    return msg

def main():
    global DFS_REG
    user_rules = rules_io.load_rules()
    dfs = load_dataframes()
    DFS_REG = dfs
    register_dataframes(dfs)
    G = load_graph()
    if G is not None:
        register_graph(G)

    print("🤖 Assistant: структурные запросы активны. RAG отключён.")

    while True:
        q = input("\n❓ Вопрос: ").strip()
        if q.lower() in ["exit", "выход", "quit", "q"]:
            print("👋 Выход."); break

        # команды принятия подсказок (значение)
        msg = handle_accept_value_suggestion(q)
        if msg: print(msg); continue

        state.LastQuestion = q
        try:
            text, sugg = answer_via_templates(q, DFS_REG)
            if sugg:
                state.LastSuggestion = sugg  # save_alias для кнопки/команды
            state.LastAnswer = text
            state.remember_exchange(q, text)
            print("\n📌 Ответ:", text)
        except Exception as e:
            print(f"⚠ Ошибка обработки: {e}")