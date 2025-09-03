# -*- coding: utf-8 -*-
import re
import pandas as pd
import state

DF_ENV: dict[str, pd.DataFrame] = {}
G_ENV = None

SAFE_BUILTINS = {
    "len": len, "sum": sum, "min": min, "max": max, "sorted": sorted,
    "list": list, "dict": dict, "set": set, "any": any, "all": all, "abs": abs, "round": round,
    "enumerate": enumerate, "zip": zip
}

# Метка авто-кода (без перевода строки здесь!)
MAGIC = "# RAGOS_AUTOCODE"

def register_dataframes(dfs_by_name: dict):
    global DF_ENV
    DF_ENV = {f"df_{name}": df for name, df in dfs_by_name.items()}

def register_graph(G):
    global G_ENV
    G_ENV = G

def _strip_code_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        code = re.sub(r'^```[^\n]*\n', '', code, flags=re.DOTALL)
        code = re.sub(r'\n?```$', '', code)
    return code.strip()

def _sanitize_code(code: str) -> str:
    code = _strip_code_fences(code)
    lines = []
    for line in code.splitlines():
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            continue
        lines.append(line)
    code = "\n".join(lines)
    if "read_csv" in code.lower() or ".csv" in code.lower():
        return "RAISE: CSV_IO_FORBIDDEN"
    return code

def _patch_code(code: str) -> str:
    # Мини-фиксы опечаток
    code = re.sub(r"```math'([^'```]+)'```'```", r"['\1']", code)
    code = re.sub(r"```\s*```\s*==", r"] ==", code)
    return code

def python_repl_tool(code: str) -> str:
    # Разрешаем только автокод
    if not code.strip().startswith(MAGIC):
        return "🚫 Этот инструмент исполняет только код, сгенерированный шаблонами."
    if "pyodbc" in code.lower() or "select " in code.lower():
        return "🚫 SQL и pyodbc запрещены."
    try:
        code2 = _sanitize_code(code)
        if code2 == "RAISE: CSV_IO_FORBIDDEN":
            return "🚫 Чтение CSV запрещено. Используй уже загруженные df_<ИмяСправочника>."

        code2 = _patch_code(code2)

        # Защитный фикс: если после MAGIC сразу идёт код без перевода строки — вставим
        if code2.startswith(MAGIC) and not code2.startswith(MAGIC + "\n"):
            code2 = code2.replace(MAGIC, MAGIC + "\n", 1)

        env = {"pd": pd}
        env.update(DF_ENV)
        if G_ENV is not None:
            env["G"] = G_ENV

        exec(code2, {"__builtins__": SAFE_BUILTINS}, env)
        result = env.get("result")
        state.LastCode = code2

        if result is None:
            state.LastResultStr = None
            return "Код выполнен, но переменная result не установлена.\n[DEBUG] Выполненный код:\n" + code2

        if isinstance(result, list):
            state.LastResultStr = str(result)
            if len(result) > 50:
                return f"{len(result)} элементов. Первые 50: {result[:50]}"
            return str(result)

        state.LastResultStr = str(result)
        return str(result)

    except Exception as e:
        return f"Ошибка выполнения Python-кода: {e}"