# -*- coding: utf-8 -*-
from typing import Optional
import config

def make_agent():
    if not config.ENABLE_RAG:
        return None
    # Если когда-то включишь RAG — сюда можно вернуть агент (как раньше).
    return object()

def run_agent(agent, question: str) -> str:
    if not agent:
        return "RAG отключён. Уточни запрос в виде структурного вопроса (сколько/список/найти)."
    # Здесь могла бы быть логика вызова RAG — опущено
    return "RAG-ответ"