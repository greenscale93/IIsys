# -*- coding: utf-8 -*-
import os
import sys
import json
import shutil
import argparse
import chromadb
from chromadb.config import Settings
from config import VECT_DIR, META_PATH

def delete_full(confirm: bool) -> int:
    if not os.path.exists(VECT_DIR):
        print("ℹ Папка VectData уже отсутствует — ничего удалять.")
        return 0
    if not confirm:
        ans = input(f"⚠ Удалить ВСЮ папку {VECT_DIR}? (yes/no): ").strip().lower()
        if ans not in ("y", "yes", "да"):
            print("Отмена.")
            return 1
    try:
        shutil.rmtree(VECT_DIR, ignore_errors=True)
        os.makedirs(VECT_DIR, exist_ok=True)
        print(f"🗑 Полная очистка выполнена. Папка создана заново: {VECT_DIR}")
        return 0
    except Exception as e:
        print(f"⚠ Ошибка при удалении {VECT_DIR}: {e}")
        return 2

def delete_collection(confirm: bool) -> int:
    if not os.path.exists(META_PATH):
        print("⚠ Не найден vect_meta.json — не знаю, какую коллекцию удалять. Используй --full.")
        return 1
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        cname = meta.get("collection_name")
        if not cname:
            print("⚠ В vect_meta.json нет поля collection_name. Используй --full.")
            return 1
    except Exception as e:
        print(f"⚠ Не удалось прочитать {META_PATH}: {e}")
        return 2

    if not confirm:
        ans = input(f"⚠ Удалить коллекцию '{cname}' в {VECT_DIR}? (yes/no): ").strip().lower()
        if ans not in ("y", "yes", "да"):
            print("Отмена.")
            return 1

    try:
        client = chromadb.PersistentClient(
            path=VECT_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
        client.delete_collection(name=cname)
        print(f"🗑 Удалена коллекция: {cname}")
        return 0
    except Exception as e:
        print(f"⚠ Ошибка удаления коллекции {cname}: {e}")
        return 2

def main():
    parser = argparse.ArgumentParser(description="Очистка векторной базы (Chroma).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--full", action="store_true", help="Удалить ВСЮ папку VectData (все коллекции).")
    group.add_argument("--collection", action="store_true", help="Удалить только текущую коллекцию из vect_meta.json.")
    parser.add_argument("--yes", action="store_true", help="Не спрашивать подтверждение.")
    args = parser.parse_args()

    if not args.full and not args.collection:
        print("Что удалить?")
        print("1) Текущую коллекцию (по vect_meta.json)")
        print("2) ВСЮ папку VectData (все коллекции)")
        choice = input("Выбор (1/2): ").strip()
        if choice == "1":
            code = delete_collection(confirm=False)
        elif choice == "2":
            code = delete_full(confirm=False)
        else:
            print("Отмена.")
            code = 1
        sys.exit(code)

    if args.full:
        sys.exit(delete_full(confirm=args.yes))
    if args.collection:
        sys.exit(delete_collection(confirm=args.yes))

if __name__ == "__main__":
    main()