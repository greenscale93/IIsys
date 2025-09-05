# -*- coding: utf-8 -*-
import os
import datetime

# ENV
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_PREFER_SAFETENSORS"] = "1"
os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

# Пути
BASE_DIR = r"C:\RAGOS"
DATA_DIR = os.path.join(BASE_DIR, "ExportedData")
VECT_DIR = os.path.join(BASE_DIR, "VectData")
GRAPH_PATH = os.path.join(BASE_DIR, "graph.gpickle")
META_PATH = os.path.join(VECT_DIR, "vect_meta.json")
MODEL_PATH = os.path.join(BASE_DIR, "models", "qwen2-7b-instruct-q4_k_m.gguf")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

RULES_FILE = os.path.join(SCRIPTS_DIR, "rules.json")
PROMPT_EXAMPLES = os.path.join(SCRIPTS_DIR, "prompt_examples.txt")
BAD_CASES_FILE = os.path.join(SCRIPTS_DIR, "bad_cases.jsonl")
TEMPLATES_FILE = os.path.join(SCRIPTS_DIR,"templates.json")
TPL_STORE_FILE = os.path.join(SCRIPTS_DIR, "tpl_store.json")

# Мэппинги
MAPPINGS_USER_FILE = os.path.join(SCRIPTS_DIR, "mappings_user.json")
MAPPINGS_DEFAULTS_FILE = os.path.join(SCRIPTS_DIR, "mappings_defaults.json")
VALUE_MAPPINGS_FILE = os.path.join(SCRIPTS_DIR, "value_mappings_user.json")

# RAG — отключён по умолчанию
ENABLE_RAG = False

os.makedirs(LOGS_DIR, exist_ok=True)

def log_path():
    return os.path.join(LOGS_DIR, f"{datetime.date.today()}_assistant_gpu.log")

def log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path(), "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")