@echo off
chcp 65001 >nul
echo ==================================================
echo   Reinstalling Python virtual environment: rag_env
echo ==================================================

cd /d C:\RAGOS

REM remove old venv if exists
rmdir /s /q rag_env

REM create new venv with Python 3.12
py -3.12 -m venv rag_env

REM activate
call rag_env\Scripts\activate

REM Env vars (предпочитать safetensors и ускоренная закачка)
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set TRANSFORMERS_PREFER_SAFETENSORS=1

REM upgrade pip
python -m pip install --upgrade pip setuptools wheel

:install_deps
echo ==================================================
echo   Installing requirements (numpy, pandas, langchain, chroma...)
echo ==================================================
pip install -r scripts\requirements.txt

echo ==================================================
echo   Installing PyTorch with CUDA 12.1 (for RTX 3060)
echo ==================================================
pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo ==================================================
echo   Installing llama-cpp-python with CUDA 12.1
echo ==================================================
pip install --upgrade llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121

echo ==================================================
echo   Checking key modules (torch + pandas + llama_cpp + rapidfuzz + safetensors)
echo ==================================================
python - <<EOF
import importlib.util, sys
missing = []
for mod in ["pandas","torch","llama_cpp","rapidfuzz","safetensors"]:
    if importlib.util.find_spec(mod) is None:
        missing.append(mod)
if missing:
    print("Missing modules:", missing)
    sys.exit(1)
print("✅ pandas, torch, llama_cpp, rapidfuzz, safetensors installed OK")
EOF

IF %ERRORLEVEL% NEQ 0 (
    echo ==================================================
    echo   Some modules missing, repeating installation...
    echo ==================================================
    GOTO install_deps
)

echo ==================================================
echo   Environment has been reinstalled successfully
echo   Running check_inv.py
echo ==================================================
python scripts\check_inv.py

echo ==================================================
echo   Reinstall process finished.
echo ==================================================
pause