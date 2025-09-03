# -*- coding: utf-8 -*-
import os, pickle, re
from rapidfuzz import fuzz
from config import GRAPH_PATH, log

def load_graph():
    if os.path.exists(GRAPH_PATH):
        with open(GRAPH_PATH, "rb") as f:
            G = pickle.load(f)
        log(f"Graph loaded: {len(G.nodes())} nodes, {len(G.edges())} edges")
        return G
    return None

def graph_query(query: str, G) -> str:
    if G is None:
        return "⚠ Граф не загружен."
    # Извлекаем имя в кавычках и необязательный тип (например: граф Проекты "Скаенг")
    m = re.search(r'[\"«]([^\"»]+)[\"»]', query)
    if not m:
        return "⚠ Укажи объект в кавычках."
    target = m.group(1).strip()
    m_type = re.search(r'граф\s+([A-Za-zА-Яа-яЁё0-9_.-]+)\s+[\"«]', query, flags=re.I)
    type_filter = m_type.group(1).strip() if m_type else None

    candidates = []
    for n, data in G.nodes(data=True):
        if type_filter and str(data.get("type", "")).lower() != type_filter.lower():
            continue
        name = data.get("name") or data.get("attrs", {}).get("Наименование") or ""
        if not name:
            continue
        score = fuzz.WRatio(target, name)
        if score >= 80:
            candidates.append((n, name, data.get("type", "?"), data.get("meta", ""), score))
    if not candidates:
        return f"⚠ Объект близкий к «{target}» не найден."
    candidates.sort(key=lambda x: x[4], reverse=True)
    node, node_name, node_type, node_meta, _ = candidates[0]
    projects = [p for p in G.predecessors(node) if G.nodes[p].get("type") in ("Проекты", "Проекты.csv", "Проекты")]
    examples = [G.nodes[p].get("name") or G.nodes[p].get("attrs", {}).get("Наименование", "?") for p in projects[:10]]
    meta_str = f" | meta: {node_meta}" if node_meta else ""
    return (
        f"Найден: {node_name} [{node_type}]{meta_str} (GUID: {node})\n"
        f"Связанных проектов: {len(projects)}\n"
        f"Примеры: {', '.join(examples) if examples else '—'}"
    )