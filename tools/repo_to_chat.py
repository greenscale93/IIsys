#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repo_to_chat.py — готовит "снимок" репозитория для отправки в чат по частям.
- фильтрует тяжёлые/бинарные файлы и служебные папки,
- строит дерево файлов,
- добавляет содержимое текстовых файлов с подсветкой,
- бьёт результат на куски заданного размера,
- при желании копирует куски в буфер обмена по одному.

Примеры:
  python tools/repo_to_chat.py               # создать chunks в ./repo_chunks
  python tools/repo_to_chat.py --send        # + копировать куски по очереди в буфер
  python tools/repo_to_chat.py --chunk-size 28000  # под конкретные лимиты чата
"""

from __future__ import annotations
import argparse
import datetime as dt
import os
from pathlib import Path
from typing import List, Tuple
import sys
import re

# Опционально: копирование в буфер обмена
try:
    import pyperclip  # pip install pyperclip
    HAVE_PYPERCLIP = True
except Exception:
    HAVE_PYPERCLIP = False

# Конфиг по умолчанию
DEFAULT_INCLUDE_EXTS = {
    ".py", ".os", ".bat", ".ps1", ".sh",
    ".txt", ".md", ".json", ".yaml", ".yml", ".ini", ".toml", ".cfg",
    ".csv", ".gitignore", ".gitattributes", ".editorconfig", ".env", ".requirements", ".req", ".config"
}
DEFAULT_EXCLUDE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".pdf", ".zip", ".7z", ".rar", ".tar", ".gz",
    ".dll", ".exe", ".pyd", ".so", ".bin",
    ".pt", ".pth", ".gguf", ".onnx",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".sqlite", ".db", ".mdb", ".accdb",
    ".bak", ".log", ".pickle", ".pkl", ".gpickle",
    ".npy", ".npz", ".parquet", ".feather", ".xls", ".xlsx"
}

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".ipynb_checkpoints", ".idea", ".vscode",
    "venv", ".venv", "env", ".conda",
    "dist", "build", "node_modules",
    "ExportedData", "VectData", "models", "logs",
    "repo_chunks"
}

LANG_BY_EXT = {
    ".py": "python",
    ".os": "bsl",          # OneScript / 1C (близко к bsl для подсветки)
    ".bat": "bat",
    ".ps1": "powershell",
    ".sh": "bash",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".md": "markdown",
    ".txt": "",
    ".csv": "csv",
    ".env": "",
}

def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} GB"

def guess_lang(path: Path) -> str:
    return LANG_BY_EXT.get(path.suffix.lower(), "")

def is_probably_binary(sample: bytes) -> bool:
    return b"\x00" in sample

def decode_bytes(b: bytes) -> str:
    for enc in ("utf-8", "utf-16", "cp1251", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("utf-8", errors="replace")

SENSITIVE_KEYS = (
    "password", "passwd", "pass",
    "secret", "token", "api_key", "apikey",
    "access_token", "refresh_token", "client_secret", "bearer_token"
)

# JSON-подобные: "token": "value"
SENSITIVE_JSON_RE = re.compile(
    r'(?i)"(' + "|".join(SENSITIVE_KEYS) + r')"\s*:\s*"([^"\r\n]{1,256})"'
)

# .env/YAML-подобные: TOKEN=..., token: ...
SENSITIVE_ENV_RE = re.compile(
    r'(?i)^\s*(' + "|".join(SENSITIVE_KEYS) + r')\s*[:=]\s*([^\r\n#]+)$'
)

def mask_secrets(text: str, enabled: bool = True) -> str:
    if not enabled:
        return text
    # JSON-like
    text = SENSITIVE_JSON_RE.sub(lambda m: f'"{m.group(1)}": "***"', text)
    # env/yaml-like (построчно, чтобы не задеть обычный код)
    lines = []
    for line in text.splitlines():
        m = SENSITIVE_ENV_RE.match(line)
        if m:
            key = m.group(1)
            lines.append(re.sub(r'[:=].*$', '=***', key + '=***'))
        else:
            lines.append(line)
    return "\n".join(lines)

def read_text_file(path: Path, max_bytes_full: int, sample_lines: int) -> Tuple[str, bool]:
    """
    Возвращает (text, truncated).
    Если файл большой — берём только начало (sample_lines).
    """
    size = path.stat().st_size
    truncated = False

    # Проба на бинарность
    with path.open("rb") as f:
        sample = f.read(4096)
        if is_probably_binary(sample):
            raise ValueError("binary file")

    if size <= max_bytes_full:
        data = path.read_bytes()
        text = decode_bytes(data)
    else:
        truncated = True
        with path.open("rb") as f:
            data = f.read(min(size, max_bytes_full * 2))
        text_all = decode_bytes(data)
        lines = text_all.splitlines()
        head = lines[:sample_lines]
        text = "\n".join(head)
        omitted = len(lines) - len(head)
        if omitted > 0:
            text += f"\n\n# ... truncated ({omitted} more lines not shown) ..."
    text = mask_secrets(text)
    return text, truncated

def collect_files(root: Path,
                  include_exts: set[str],
                  exclude_exts: set[str],
                  exclude_dirs: set[str]) -> List[Path]:
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Фильтр каталогов на месте
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs and not d.startswith(".cache")]
        for name in filenames:
            p = Path(dirpath) / name
            ext = p.suffix.lower()
            if ext in exclude_exts:
                continue
            # Всегда берём без расширения (типа .env, .gitignore)
            if ext or (not ext and p.name.startswith(".")):
                if ext and ext not in include_exts:
                    continue
            # Если совсем без расширения (например, Makefile) — берём как текст
            if not ext and not p.name.startswith("."):
                # можно добавить белый список по именам, но оставим
                pass
            files.append(p)
    # Сортируем
    files = sorted(files, key=lambda x: str(x).lower())
    return files

def build_tree_listing(root: Path, files: List[Path]) -> str:
    rels = [f.relative_to(root) for f in files]
    lines = ["Фильтрованное дерево файлов (только включённые):"]
    for r in rels:
        lines.append(f" - {r.as_posix()}")
    return "\n".join(lines)

def make_blocks(root: Path,
                files: List[Path],
                max_bytes_full: int,
                sample_lines: int) -> List[str]:
    blocks: List[str] = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        lang = guess_lang(p)
        try:
            text, truncated = read_text_file(p, max_bytes_full=max_bytes_full, sample_lines=sample_lines)
        except Exception:
            # пропускаем бинарные или проблемные файлы
            continue
        header = f"\n\n===== FILE: {rel} ({human_size(p.stat().st_size)}) =====\n"
        fence_start = f"```{lang}\n" if lang else "```\n"
        fence_end = "```\n"
        body = header + fence_start + text + "\n" + fence_end
        blocks.append(body)
    return blocks

def chunk_blocks(all_blocks: List[str], chunk_size: int, chunk_header_factory) -> List[str]:
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0

    # Сначала прикинем количество chunks грубо с пустыми заголовками
    # Но нам легче собрать без шапки, а потом добавить шапку постфактум
    # Поэтому собираем тела, а шапку добавим после.
    bodies: List[str] = []
    cur_body = []
    cur_len = 0

    for b in all_blocks:
        if cur_len + len(b) > chunk_size and cur_body:
            bodies.append("".join(cur_body))
            cur_body = [b]
            cur_len = len(b)
        else:
            cur_body.append(b)
            cur_len += len(b)
    if cur_body:
        bodies.append("".join(cur_body))

    total = len(bodies)
    for i, body in enumerate(bodies, 1):
        header = chunk_header_factory(i, total)
        chunks.append(header + body)
    return chunks

def main():
    parser = argparse.ArgumentParser(description="Подготовка репозитория к отправке в чат (частями).")
    parser.add_argument("--root", default=".", help="Корень репозитория (по умолчанию .)")
    parser.add_argument("--outdir", default="repo_chunks", help="Каталог для файлов-частей")
    parser.add_argument("--chunk-size", type=int, default=28000, help="Целевой размер части (в символах)")
    parser.add_argument("--max-file-bytes", type=int, default=512_000, help="Макс. размер файла для полного чтения")
    parser.add_argument("--sample-lines", type=int, default=300, help="Сколько строк показывать из больших файлов")
    parser.add_argument("--send", action="store_true", help="Копировать куски в буфер по очереди (требует pyperclip)")
    parser.add_argument("--include-exts", default=",".join(sorted(DEFAULT_INCLUDE_EXTS)),
                        help="Список расширений через запятую, которые включать")
    parser.add_argument("--exclude-dirs", default=",".join(sorted(DEFAULT_EXCLUDE_DIRS)),
                        help="Список каталогов через запятую, которые исключать")
    parser.add_argument("--exclude-exts", default=",".join(sorted(DEFAULT_EXCLUDE_EXTS)),
                        help="Список расширений через запятую, которые исключать")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    include_exts = set(e.strip().lower() for e in args.include_exts.split(",") if e.strip())
    exclude_dirs = set(e.strip() for e in args.exclude_dirs.split(",") if e.strip())
    exclude_exts = set(e.strip().lower() for e in args.exclude_exts.split(",") if e.strip())

    repo_name = root.name
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    files = collect_files(root, include_exts, exclude_exts, exclude_dirs)
    if not files:
        print("Нечего собирать: проверьте фильтры include/exclude.", file=sys.stderr)
        sys.exit(1)

    tree_block = build_tree_listing(root, files)
    header_meta = (
        f"REPO_SNAPSHOT {repo_name}\n"
        f"Дата: {ts}\n"
        f"Корень: {root}\n"
        f"Файлов включено: {len(files)}\n"
        f"Правила:\n"
        f"  include_exts={sorted(include_exts)}\n"
        f"  exclude_exts={sorted(exclude_exts)}\n"
        f"  exclude_dirs={sorted(exclude_dirs)}\n"
        f"  max_file_bytes={args.max_file_bytes}, sample_lines={args.sample_lines}\n"
        f"\n"
        f"Инструкция: отправляйте части строго по порядку. Я объединю их по маркерам 'Часть i/N'.\n"
        f"\n"
        f"{tree_block}\n"
    )

    file_blocks = make_blocks(root, files, max_bytes_full=args.max_file_bytes, sample_lines=args.sample_lines)

    # Сборка блоков: мета+дерево — только в первой части
    all_blocks = [header_meta] + file_blocks

    def chunk_header_factory(i: int, total: int) -> str:
        return f"\n=== REPO_SNAPSHOT {repo_name} — Часть {i}/{total} ===\n"

    chunks = chunk_blocks(all_blocks, chunk_size=args.chunk_size, chunk_header_factory=chunk_header_factory)

    # Запись на диск
    written = []
    for i, content in enumerate(chunks, 1):
        p = outdir / f"{i:03d}_{repo_name}_snapshot.md"
        p.write_text(content, encoding="utf-8")
        written.append(p)

    print(f"Готово: создано частей: {len(written)} → {outdir}")
    total_chars = sum(len(c) for c in chunks)
    print(f"Символов всего: {total_chars:,}")
    for p in written:
        print(f"- {p.name} ({human_size(p.stat().st_size)})")

    if args.send:
        if not HAVE_PYPERCLIP:
            print("\n--send запрошен, но pyperclip не установлен. Установите: pip install pyperclip", file=sys.stderr)
            return
        print("\nИнтерактивная отправка: по Enter — следующая часть; 'q' — выход, 's' — пропустить.")
        for i, content in enumerate(chunks, 1):
            pyperclip.copy(content)
            print(f"[{i}/{len(chunks)}] Часть скопирована в буфер. Вставьте в чат и нажмите Enter… ", end="", flush=True)
            cmd = input().strip().lower()
            if cmd == "q":
                print("Выход из режима отправки.")
                break
            # s — просто пропускаем копирование следующей части (уже скопировано), идём дальше
        print("Готово.")

if __name__ == "__main__":
    main()