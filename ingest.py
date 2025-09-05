# -*- coding: utf-8 -*-
import os
import glob
import time
import json
import pickle
import pandas as pd
import networkx as nx
from tqdm import tqdm
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from chromadb.config import Settings
from config import BASE_DIR, DATA_DIR, VECT_DIR, GRAPH_PATH, META_PATH

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors="replace")

# Env
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_PREFER_SAFETENSORS"] = "1"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

os.makedirs(VECT_DIR, exist_ok=True)

def norm_guid(x: str) -> str:
    if x is None:
        return ""
    x = str(x).strip().strip("{}").lower()
    return x if len(x.replace("-", "")) >= 32 else ""

def _read_csv_smart(path: str):
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        for sep in (";", ","):
            try:
                return pd.read_csv(path, sep=sep, dtype=str, low_memory=False, encoding=enc).fillna("")
            except Exception:
                continue
    return pd.read_csv(path, sep=";", dtype=str, low_memory=False, encoding="utf-8", errors="replace").fillna("")

def build_embeddings():
    try:
        emb = HuggingFaceEmbeddings(
            model_name="BAAI/bge-m3",
            model_kwargs={"device": "cuda"},
            encode_kwargs={"normalize_embeddings": True}
        )
        used = "BAAI/bge-m3"
    except Exception as e:
        print(f"⚠ Не удалось загрузить BAAI/bge-m3: {e}\n→ Пытаюсь fallback: intfloat/multilingual-e5-base")
        emb = HuggingFaceEmbeddings(
            model_name="intfloat/multilingual-e5-base",
            model_kwargs={"device": "cuda"},
            encode_kwargs={"normalize_embeddings": True}
        )
        used = "intfloat/multilingual-e5-base"
    return emb, used

def get_embed_dim(embedding):
    try:
        return embedding.client.get_sentence_embedding_dimension()
    except Exception:
        return len(embedding.embed_query("test"))

start_time = time.time()
docs = []
file_stats = []
G = nx.DiGraph()

# 1) Описание
desc_file = os.path.join(DATA_DIR, "описание.txt")
if os.path.exists(desc_file):
    with open(desc_file, "r", encoding="utf-8") as f:
        desc = f.read()
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50, length_function=len)
    chunks = splitter.split_text(desc)
    for i, chunk in enumerate(chunks):
        docs.append(Document(
            page_content="Описание справочников: " + chunk,
            metadata={"source": "описание.txt", "part": i, "entity": "Описание"}
        ))
    file_stats.append(("описание.txt", len(chunks)))

# 2) CSV + граф
csv_files = glob.glob(os.path.join(DATA_DIR, "*.csv"))

for file in tqdm(csv_files, desc="📂 Обработка CSV файлов"):
    try:
        df = _read_csv_smart(file)
    except Exception:
        df = _read_csv_smart(file)

    filename = os.path.basename(file)
    entity_type = os.path.splitext(filename)[0]

    for idx, row in df.iterrows():
        guid = norm_guid(row.get("GUID", ""))
        if not guid:
            continue
        content_parts = [f"{col}: {row[col]}" for col in df.columns if str(row[col]).strip() != ""]
        content = f"Справочник: {entity_type} | " + " | ".join(content_parts)

        docs.append(Document(
            page_content=content,
            metadata={"source": filename, "row": idx, "guid": guid, "entity": entity_type}
        ))

        G.add_node(guid, type=entity_type, name=row.get("Наименование", ""), attrs=row.to_dict())

        for col in df.columns:
            if col.endswith("_GUID"):
                tgt = norm_guid(row[col])
                if tgt:
                    # Прямое направление (Проект → Контрагент)
                    G.add_edge(guid, tgt, relation=col, direction="forward")
                    # Обратное направление (Контрагент → Проект)
                    G.add_edge(tgt, guid, relation=col, direction="reverse")

    record_count = len(df)
    docs.append(Document(
        page_content=f"Справочник {entity_type} содержит {record_count} элементов",
        metadata={"source": filename, "row": "summary", "entity": entity_type}
    ))
    file_stats.append((filename, record_count + 1))

# 3) Эмбеддинги
print("🔄 Создаём эмбеддинги на GPU (BGE-M3, fallback E5)...")
embedding, used_model = build_embeddings()
embed_dim = get_embed_dim(embedding)

# Коллекция по имени модели и размерности
collection_name = f"ragos_{used_model.split('/')[-1]}_{embed_dim}d"
client_settings = Settings(anonymized_telemetry=False)

# 4) Индекс
print(f"🔄 Генерация векторной базы... (collection={collection_name})")
db = Chroma.from_documents(
    documents=docs,
    embedding=embedding,
    persist_directory=VECT_DIR,
    collection_name=collection_name,
    client_settings=client_settings
)

# 5) Сохраняем граф
print("🔄 Сохраняем граф...")
with open(GRAPH_PATH, "wb") as f:
    pickle.dump(G, f)

# 6) Метаданные
meta = {
    "collection_name": collection_name,
    "embedding_model": used_model,
    "embedding_dim": embed_dim,
    "doc_count": len(docs),
    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
}
with open(META_PATH, "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

# 7) Отчёт
elapsed = time.time() - start_time
print("\n📊 Результаты ingest:")
for fname, cnt in file_stats:
    print(f"- {fname}: {cnt} документов")
print(f"\nВсего документов: {len(docs)}")
print(f"✅ Векторная база: {VECT_DIR} (коллекция: {collection_name}, dim={embed_dim})")
print(f"✅ Граф: {GRAPH_PATH}")
print(f"⏱ Время: {elapsed:.2f} секунд")