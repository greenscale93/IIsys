# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json
from typing import List, Dict, Any, Optional
from config import MODEL_PATH

try:
    from llama_cpp import Llama
except Exception:
    Llama = None

_LLM = None

def get_llm() -> Optional["Llama"]:
    global _LLM
    if _LLM is not None:
        return _LLM
    if Llama is None: return None
    if not os.path.exists(MODEL_PATH): return None
    try:
        _LLM = Llama(
            model_path=MODEL_PATH,
            n_ctx=8192,
            n_threads=os.cpu_count() or 4,
            n_gpu_layers=35,  # под RTX 3060 подойдет; если CPU — просто проигнорится
            verbose=False
        )
        return _LLM
    except Exception:
        return None

def chat_json(system_prompt: str, user_prompt: str, temperature=0.1, max_tokens=1024) -> Optional[Dict[str, Any]]:
    llm = get_llm()
    if not llm:
        return None
    out = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=temperature,
        max_tokens=max_tokens
    )
    text = out["choices"][0]["message"]["content"].strip()
    try:
        return json.loads(text)
    except Exception:
        # попробуем вытащить JSON из текста
        import re, json as _json
        m = re.search(r"\{[\s\S]+\}", text)
        if m:
            try:
                return _json.loads(m.group(0))
            except Exception:
                pass
    return None