import os
import subprocess
import sys

# Пути
BASE_DIR = r"C:\RAGOS"
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
VENV_PYTHON = os.path.join(BASE_DIR, "rag_env", "Scripts", "python.exe")

def run_onescript(script_name):
    """Запуск скрипта 1С на OneScript (oscript.exe)"""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"⚠ Файл {script_name} не найден в папке scripts!")
        return
    try:
        subprocess.run(["oscript", script_path], check=True)
    except FileNotFoundError:
        print("⚠ Не найден oscript.exe! Установи OneScript и добавь oscript в PATH.")
    input("\n▶ Нажми Enter, чтобы вернуться в меню...")

def run_python(script_name, args=None):
    """Запуск Python скрипта из папки scripts"""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"⚠ Файл {script_name} не найден в папке scripts!")
        return
    cmd = [VENV_PYTHON, script_path]
    if args:
        cmd.extend(args)
    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"⚠ Ошибка при запуске {script_name}: {e}")
    input("\n▶ Нажми Enter, чтобы вернуться в меню...")

def run_reset_and_ingest():
    """Полная очистка VectData и пересборка векторной базы"""
    reset_path = os.path.join(SCRIPTS_DIR, "reset_vect.py")
    ingest_path = os.path.join(SCRIPTS_DIR, "ingest.py")
    if not os.path.exists(reset_path):
        print("⚠ Файл reset_vect.py не найден в папке scripts!")
        input("\n▶ Нажми Enter, чтобы вернуться в меню...")
        return
    if not os.path.exists(ingest_path):
        print("⚠ Файл ingest.py не найден в папке scripts!")
        input("\n▶ Нажми Enter, чтобы вернуться в меню...")
        return

    try:
        subprocess.run([VENV_PYTHON, reset_path, "--full", "--yes"], check=True)
        subprocess.run([VENV_PYTHON, ingest_path], check=True)
    except Exception as e:
        print(f"⚠ Ошибка во время очистки/пересборки: {e}")
    input("\n▶ Нажми Enter, чтобы вернуться в меню...")

def main():
    while True:
        os.system("cls")  # очистка экрана в Windows
        print("=== 📚 Меню RAGOS ===")
        print("1. Выгрузить данные из 1С (ВыгрузкаИз1С.os)")
        print("2. Обновить векторную базу (ingest.py)")
        print("3. Задать вопрос к базе (assistant_main.py)")
        print("4. Очистить и пересоздать векторную базу")
        print("5. Выход")

        choice = input("\nВыбери опцию (1/2/3/4/5): ").strip()
        
        if choice == "1":
            run_onescript("C:\RAGOS\ВыгрузкаИз1С.os")
        elif choice == "2":
            run_python("ingest.py")
        elif choice == "3":
            run_python("assistant_main.py")
        elif choice == "4":
            run_reset_and_ingest()
        elif choice == "5":
            print("👋 Программа завершена.")
            sys.exit(0)
        else:
            print("⚠ Неверный ввод, попробуй снова!")
            input("▶ Нажми Enter, чтобы вернуться в меню...")

if __name__ == "__main__":
    main()