import sys

print("=== ENVIRONMENT CHECK ===")

# Python version
print("Python:", sys.version)

try:
    import numpy as np
    print("NumPy:", np.__version__)
except Exception as e:
    print("NumPy: ERROR:", e)

try:
    import pandas as pd
    print("Pandas:", pd.__version__)
except Exception as e:
    print("Pandas: ERROR:", e)

try:
    import torch
    print("Torch:", torch.__version__, "| CUDA runtime:", torch.version.cuda)
    print("  CUDA available?:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("  GPU Device:", torch.cuda.get_device_name(0))
except Exception as e:
    print("Torch: ERROR:", e)

# LangChain stack
for pkg in ["langchain", "langchain_core", "langchain_community",
            "langchain_chroma", "langchain_huggingface"]:
    try:
        mod = __import__(pkg.replace("-", "_"))
        print(pkg, ":", getattr(mod, "__version__", "OK"))
    except Exception as e:
        print(pkg, ": ERROR:", e)

# Others
try:
    import chromadb
    print("Chromadb:", chromadb.__version__)
except Exception as e:
    print("Chromadb: ERROR:", e)

try:
    import sentence_transformers
    print("SentenceTransformers:", sentence_transformers.__version__)
except Exception as e:
    print("SentenceTransformers: ERROR:", e)

print("=== CHECK COMPLETE ===")