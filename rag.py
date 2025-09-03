# -*- coding: utf-8 -*-
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain.prompts import PromptTemplate
from sentence_transformers import CrossEncoder
import json
import os
from config import VECT_DIR, META_PATH

def load_meta():
    if not os.path.exists(META_PATH):
        raise FileNotFoundError(f"Не найден {META_PATH}. Сначала обнови векторную базу (ingest.py).")
    with open(META_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def build_embeddings_by_name(name: str):
    return HuggingFaceEmbeddings(
        model_name=name,
        model_kwargs={"device": "cuda"},
        encode_kwargs={"normalize_embeddings": True}
    )

def open_chroma(embedding, collection_name: str):
    client_settings = Settings(anonymized_telemetry=False)
    db = Chroma(
        persist_directory=VECT_DIR,
        embedding_function=embedding,
        collection_name=collection_name,
        client_settings=client_settings
    )
    return db

def build_reranker():
    try:
        ce = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cuda")
        return CrossEncoderReranker(model=ce, top_n=6)
    except Exception:
        try:
            ce = CrossEncoder("jinaai/jina-reranker-v2-base-multilingual", device="cuda")
            return CrossEncoderReranker(model=ce, top_n=6)
        except Exception:
            return None

def build_retriever(db, reranker):
    if reranker:
        base_retriever = db.as_retriever(search_kwargs={"k": 24})
        return ContextualCompressionRetriever(base_retriever=base_retriever, compressor=reranker)
    return db.as_retriever(search_kwargs={"k": 8})

def build_prompt():
    return PromptTemplate(
        template=(
            "Ты — умный помощник и всегда отвечаешь на русском языке.\n"
            "Всегда соблюдай эти правила:\n{rules}\n\n"
            "История диалога (учитывай контекст):\n{chat_history}\n\n"
            "Используй только факты из контекста. "
            "Если ответа нет в контексте, скажи: \"Нет данных в справочниках\".\n\n"
            "Дополнительные инструкции и примеры:\n{examples}\n\n"
            "Вопрос: {question}\nКонтекст: {context}\nОтвет:\n"
        ),
        input_variables=["question", "context", "rules", "examples", "chat_history"]
    )