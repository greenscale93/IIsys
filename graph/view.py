# -*- coding: utf-8 -*-
"""
Интерактивный просмотр графа связей (pyvis + networkx).
"""

import sys, io
# ⚡️ фикс кодировок для Windows-консоли: теперь эмодзи печатаются без ошибок
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
scripts_dir = Path(__file__).resolve().parents[1]
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import pickle
import argparse
import os
import networkx as nx

try:
    from pyvis.network import Network
except ImportError:
    print("⚠ Для визуализации нужен пакет pyvis. Установите: pip install pyvis")
    sys.exit(1)

from config import GRAPH_PATH
import random

# Предопределённые цвета
DEFAULT_COLORS = {
    "Проекты": "#1f77b4",        # синий
    "Контрагенты": "#ff7f0e",    # оранжевый
    "Сотрудники": "#2ca02c",     # зелёный
    "Подразделения": "#9467bd",  # фиолетовый
    "Договоры": "#d62728",       # красный
    "Документы": "#8c564b",      # коричневый
}
COLOR_MAP = {}

def get_color_for_type(t: str) -> str:
    if t in DEFAULT_COLORS:
        return DEFAULT_COLORS[t]
    if t not in COLOR_MAP:
        COLOR_MAP[t] = "#%06x" % random.randint(0x100000, 0xFFFFFF)
    return COLOR_MAP[t]

def load_graph(path=GRAPH_PATH):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл графа {path} не найден. Сначала запустите ingest.py")
    with open(path, "rb") as f:
        return pickle.load(f)

def preview_graph(G, max_nodes=None, out_file="graph_preview.html"):
    if max_nodes and max_nodes > 0:
        H = G.subgraph(list(G.nodes())[:max_nodes]).copy()
    else:
        H = G

    net = Network(height="900px", width="100%", notebook=False, directed=True)
    net.force_atlas_2based()

    for n, data in H.nodes(data=True):
        t = data.get("type", "default")
        name = data.get("name") or ""
        short_id = str(n)[:6]

        label = name if name else short_id
        label += f"\n<b>{t}</b>"

        title = f"<b>GUID:</b> {n}<br><b>Тип:</b> {t}<br><b>Имя:</b> {name or '—'}"

        color = get_color_for_type(t)
        size = 8 + 2 * H.degree(n)

        net.add_node(n, label=label, title=title, color=color, size=size, font={"multi": True})

    for u, v, data in H.edges(data=True):
        if data.get("direction") == "forward":
            net.add_edge(u, v, title=data.get("relation", ""))

    net.write_html(out_file, open_browser=True)
    print(f"✅ Визуализация создана: {out_file}")

def export_graphml(G, out_file="graph_full.graphml"):
    nx.write_graphml(G, out_file)
    print(f"✅ Полный граф экспортирован в {out_file}")

def main():
    parser = argparse.ArgumentParser(description="Визуализация графа объектов (из graph.gpickle)")
    parser.add_argument("--max-nodes", type=int, default=0, help="Сколько узлов показывать (0 = все)")
    parser.add_argument("--preview", action="store_true", help="Сделать интерактивный html-просмотр")
    parser.add_argument("--export", action="store_true", help="Экспортировать полный граф в GraphML (для Gephi)")
    args = parser.parse_args()

    G = load_graph(GRAPH_PATH)

    if args.preview:
        preview_graph(G, max_nodes=args.max_nodes)
    if args.export:
        export_graphml(G)
    if not (args.preview or args.export):
        print("⚠ Укажите --preview и/или --export")

if __name__ == "__main__":
    main()