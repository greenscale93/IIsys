# -*- coding: utf-8 -*-
import sys, os, subprocess, threading, traceback, io, html, math
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTabWidget, QTextEdit, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtGui import QAction, QFont, QTextDocument
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

# --- Настройки внешнего вида ---
USER_BUBBLE_BG = "#DCF8C6"   # зелёный для пользователя
BOT_BUBBLE_BG  = "#CFCFCF"   # более контрастный серый для бота

# --- Настройки ширины пузырьков (не меняем как просили) ---
BUBBLE_MAX_RATIO = 0.88   # доля ширины вьюпорта
BUBBLE_MIN_PX    = 520    # базовый минимум в пикселях
BUBBLE_PADDING_H = 20     # 10 слева + 10 справа (для расчёта ширины текста)

# --- Пути ---
BASE_DIR = r"C:\RAGOS"
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
VENV_PYTHON = os.path.join(BASE_DIR, "rag_env", "Scripts", "python.exe")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# --- Импорт логики ---
import state
from data.loader import load_dataframes
from engine.router import try_quick_count, try_quick_list
from engine.repl import register_dataframes
from graph.tool import load_graph

DFS_REG = None
def init_assistant():
    global DFS_REG
    dfs = load_dataframes()
    DFS_REG = dfs
    register_dataframes(dfs)
    _ = load_graph()

try:
    init_assistant()
except Exception as e:
    print("Ошибка инициализации ассистента:", e)


# === Утилита для безопасной отрисовки текста с переносами длинных слов ===
def as_rich_wrapped(text: str) -> str:
    return f"<div style='white-space: pre-wrap; word-break: break-word'>{html.escape(text)}</div>"


# === Виджет "чат" с пузырьками ===
class BubbleChat(QWidget):
    def __init__(self):
        super().__init__()
        self._rows = []  # список кортежей (bubble, label)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(8)
        self.layout.addStretch(1)

    def add_message(self, who, text: str):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        bubble = QFrame()
        bubble.setFrameShape(QFrame.Shape.NoFrame)
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bubble.setStyleSheet(
            "QFrame { background-color: %s; border-radius: 10px; }" %
            (USER_BUBBLE_BG if who == "user" else BOT_BUBBLE_BG)
        )

        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(10, 8, 10, 8)
        inner.setSpacing(0)

        lbl = QLabel()
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setText(as_rich_wrapped(text))
        lbl.setFont(QFont("Segoe UI Emoji", 11))
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        inner.addWidget(lbl)

        # Выравнивание пузырька к краю
        if who == "user":
            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        else:
            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)

        self.layout.insertLayout(self.layout.count() - 1, row)
        self._rows.append((bubble, lbl))

        # Обновляем размеры и высоту после вставки
        self._update_bubble_metrics_async()

        print(f"[UI] Пузырь {who} добавлен, длина текста={len(text)}")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_bubble_metrics_async()

    # --- helpers ---

    def _viewport_width(self) -> int:
        # Фактическая ширина вьюпорта QScrollArea
        p = self.parentWidget()
        while p is not None and not isinstance(p, QScrollArea):
            p = p.parentWidget()
        if isinstance(p, QScrollArea):
            return p.viewport().width()
        return self.width()

    def _update_bubble_metrics_async(self):
        # Сначала обновим ширины синхронно...
        self._apply_widths()
        # ...а расчёт высоты сделаем после прохода лэйаута
        QTimer.singleShot(0, self._fix_heights)

    def _apply_widths(self):
        vw = max(100, self._viewport_width())
        max_w = int(vw * BUBBLE_MAX_RATIO)
        max_w = max(320, max_w)  # страховка на узких окнах
        min_w = min(max_w, BUBBLE_MIN_PX)

        label_max_w = max(100, max_w - BUBBLE_PADDING_H)
        label_min_w = max(80,  min_w - BUBBLE_PADDING_H)

        for bubble, lbl in self._rows:
            bubble.setMinimumWidth(min_w)
            bubble.setMaximumWidth(max_w)
            # даём лейблу разумный диапазон по ширине
            lbl.setMinimumWidth(label_min_w)
            lbl.setMaximumWidth(label_max_w)

    def _fix_heights(self):
        # Вычисляем высоту по фактической ширине метки, используя QTextDocument
        changed = False
        for bubble, lbl in self._rows:
            w = lbl.width()
            if w <= 0:
                w = lbl.maximumWidth()
            h = self._doc_height_for(lbl, w)
            h = int(math.ceil(h)) + 2  # небольшой запас

            if lbl.minimumHeight() != h or lbl.maximumHeight() != h:
                lbl.setMinimumHeight(0)
                lbl.setMaximumHeight(16777215)
                lbl.setMinimumHeight(h)
                lbl.setMaximumHeight(h)
                changed = True

        if changed:
            self.layout.activate()
            self.updateGeometry()

    @staticmethod
    def _doc_height_for(lbl: QLabel, width: int) -> float:
        # Считаем высоту rich-text через QTextDocument для заданной ширины
        doc = QTextDocument()
        doc.setDefaultFont(lbl.font())
        doc.setHtml(lbl.text())
        doc.setTextWidth(max(1, width))
        return doc.size().height()


class ChatTab(QWidget):
    answer_ready = pyqtSignal(str)
    def __init__(self, log_debug):
        super().__init__()
        self.log_debug = log_debug
        self.answer_ready.connect(self.on_answer_ready)

        layout = QVBoxLayout()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_widget = BubbleChat()
        self.scroll.setWidget(self.chat_widget)
        layout.addWidget(self.scroll)

        entry_layout = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setFont(QFont("Segoe UI Emoji", 11))
        send_btn = QPushButton("Отправить")
        send_btn.clicked.connect(self.send_query)
        entry_layout.addWidget(self.entry)
        entry_layout.addWidget(send_btn)
        layout.addLayout(entry_layout)

        self.setLayout(layout)

    def _scroll_to_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def send_query(self):
        q = self.entry.text().strip()
        if not q: return
        self.entry.clear()
        self.chat_widget.add_message("user", f"👤 {q}")
        self._scroll_to_bottom()
        self.log_debug(f"[send_query] Вопрос: {repr(q)}")

        def worker():
            try:
                self.log_debug(f"[worker] Начало обработки: {repr(q)}")
                ans = try_quick_count(q, DFS_REG)
                self.log_debug(f"[worker] try_quick_count -> {repr(ans)}")
                if ans is None:
                    ans = try_quick_list(q, DFS_REG)
                    self.log_debug(f"[worker] try_quick_list -> {repr(ans)}")
                if ans is None:
                    ans = "⚠ Не удалось распознать параметры."
                self.log_debug(f"[worker] Итоговый ответ: {repr(ans)[:200]}...")
                self.answer_ready.emit(ans)
            except Exception as e:
                tb = traceback.format_exc()
                self.log_debug(f"[worker EXCEPTION] {tb}")
                self.answer_ready.emit(f"⚠ Ошибка: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def on_answer_ready(self, answer: str):
        self.log_debug(f"[UI] Отрисовка ответа: {repr(answer)[:200]}...")
        self.chat_widget.add_message("bot", f"🤖 {answer}")
        self._scroll_to_bottom()


class IIsys(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🤖 ИИ.sys — Локальный помощник")
        self.resize(1000, 700)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("Файл")
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        data_menu = menubar.addMenu("Данные")
        ingest_action = QAction("📂 Индексация", self)
        ingest_action.triggered.connect(self.run_ingest)
        data_menu.addAction(ingest_action)
        reset_action = QAction("🗑 Очистить+Пересоздать", self)
        reset_action.triggered.connect(self.reset_ingest)
        data_menu.addAction(reset_action)

        settings_menu = menubar.addMenu("Настройки")
        self.toggle_console_action = QAction("Скрыть/показать консоль", self, checkable=True)
        self.toggle_console_action.setChecked(True)
        self.toggle_console_action.triggered.connect(self.toggle_console)
        settings_menu.addAction(self.toggle_console_action)

        central_widget = QWidget()
        self.central_layout = QVBoxLayout()
        central_widget.setLayout(self.central_layout)
        self.setCentralWidget(central_widget)

        self.tabs = QTabWidget()
        self.central_layout.addWidget(self.tabs)

        self.chat_tab = ChatTab(self.log_debug)
        self.tabs.addTab(self.chat_tab, "💬 Ассистент")
        self.tabs.setCurrentWidget(self.chat_tab)

        graph_tab = QWidget()
        g_layout = QVBoxLayout()
        g_layout.addWidget(QLabel("Здесь можно запустить браузер с PyVis-графом."))
        graph_btn = QPushButton("🌐 Открыть визуализацию графа")
        graph_btn.clicked.connect(self.open_graph)
        g_layout.addWidget(graph_btn)
        graph_tab.setLayout(g_layout)
        self.tabs.addTab(graph_tab, "🌐 Граф")

        self.console = QTextEdit()
        self.console.setFont(QFont("Consolas", 9))
        self.console.setReadOnly(True)
        self.console.setVisible(True)
        self.central_layout.addWidget(self.console)

        class EmittingStream(io.TextIOBase):
            def __init__(self, write_func): self.write_func = write_func
            def write(self, text):
                if text.strip(): self.write_func(text.strip())
            def flush(self): pass
        sys.stdout = EmittingStream(self.log_debug)
        sys.stderr = EmittingStream(self.log_debug)

    def toggle_console(self, checked): self.console.setVisible(checked)

    def log_debug(self, text):
        # Потокобезопасная запись в консоль (в GUI-поток)
        QTimer.singleShot(0, lambda: self.console.append(text))

    def post_bot(self, text: str):
        # Потокобезопасное добавление сообщений бота в чат
        QTimer.singleShot(0, lambda: (
            self.chat_tab.chat_widget.add_message("bot", text),
            self.chat_tab._scroll_to_bottom()
        ))

    def run_ingest(self):
        self.chat_tab.chat_widget.add_message("bot", "📂 Индексация запущена…")
        self.chat_tab._scroll_to_bottom()
        threading.Thread(target=self._run_script, args=("ingest.py", "📂 Индексация"), daemon=True).start()

    def reset_ingest(self):
        self.chat_tab.chat_widget.add_message("bot", "🗑 Очистка+Пересоздание…")
        self.chat_tab._scroll_to_bottom()
        threading.Thread(target=self._run_script, args=("reset_vect.py --full --yes", "🗑 Очистка"), daemon=True).start()
        threading.Thread(target=self._run_script, args=("ingest.py", "📂 Индексация"), daemon=True).start()

    def open_graph(self):
        self.chat_tab.chat_widget.add_message("bot", "🌐 Запуск графа…")
        self.chat_tab._scroll_to_bottom()
        threading.Thread(target=self._run_script, args=("-m scripts.graph.view --preview", "🌐 Граф"), daemon=True).start()

    def _run_script(self, cmd_str, tag):
        try:
            cmd = [VENV_PYTHON] + cmd_str.split()
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace")
            for line in process.stdout:
                line = line.strip()
                if not line: continue
                self.post_bot(f"{tag}: {line}")
                self.log_debug(f"{tag}: {line}")
            process.wait()
            if process.returncode != 0:
                self.post_bot(f"{tag}: ⚠ Код {process.returncode}")
                self.log_debug(f"{tag}: Код завершения {process.returncode}")
        except Exception as e:
            tb = traceback.format_exc()
            self.post_bot(f"{tag}: Ошибка {e}")
            self.log_debug(tb)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = IIsys()
    ui.show()
    sys.exit(app.exec())