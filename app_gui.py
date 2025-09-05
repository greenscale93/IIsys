import sys, os
# --- Пути ---
BASE_DIR = r"C:\RAGOS"
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
VENV_PYTHON = os.path.join(BASE_DIR, "rag_env", "Scripts", "python.exe")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from templates_store import list_templates, get_template, add_alias, add_template as store_add_template, run_template as store_run_template
from templates_ai import answer_via_templates, generate_template_with_llm

# -*- coding: utf-8 -*-
import subprocess, threading, traceback, io, html, math
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTabWidget, QTextEdit, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtGui import QAction, QFont, QTextDocument
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
import re
from core.mappings import add_value_alias
import logging, traceback
from datetime import datetime
from config import LOGS_DIR
from engine.repl import register_dataframes, register_graph

SESSION_LOG = os.path.join(LOGS_DIR, f"gui_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(SESSION_LOG, encoding="utf-8", delay=True)]
)

def install_excepthook():
    def _hook(exc_type, exc, tb):
        logging.exception("UNHANDLED: %s", "".join(traceback.format_exception(exc_type, exc, tb)))
        # опционально покажем в UI-консоли текстом — не завершаем процесс
        print(f"⚠ Необработанная ошибка: {exc}")
    sys.excepthook = _hook

install_excepthook()

def safe_remove_widget(w):
    if not w:
        return
    try:
        w.setParent(None)
    except Exception:
        pass
    try:
        w.deleteLater()
    except Exception:
        pass

# --- Настройки внешнего вида ---
USER_BUBBLE_BG = "#DCF8C6"   # зелёный для пользователя
BOT_BUBBLE_BG  = "#E9EEF6"   # спокойный нейтральный (голубовато‑серый, не сливается с фоном)

# --- Настройки ширины пузырьков (не меняем как просили) ---
BUBBLE_MAX_RATIO = 0.88   # доля ширины вьюпорта
BUBBLE_MIN_PX    = 520    # базовый минимум в пикселях
BUBBLE_PADDING_H = 20     # 10 слева + 10 справа (для расчёта ширины текста)

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
    G = load_graph()
    if G is not None:
        register_graph(G)

try:
    init_assistant()
except Exception as e:
    print("Ошибка инициализации ассистента:", e)


def as_rich_wrapped_bot(text: str) -> str:
    # Безопасный «лайт markdown»: **жирный**, остальное экранируем
    safe = html.escape(text)
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    return f"<div style='white-space: pre-wrap; word-break: break-word'>{safe}</div>"

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
    
    def add_action_button(self, who, caption: str, on_click):
        cont = QWidget()
        row = QHBoxLayout(cont)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        btn = QPushButton(caption)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        font = QFont("Segoe UI", 10); font.setWeight(QFont.Weight.DemiBold); btn.setFont(font)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #CDEFD7; color: #0F5132;
                border: 1px solid #86D3A9; border-radius: 10px;
                padding: 8px 14px; font-weight: 600;
            }
            QPushButton:hover   { background-color: #BFE8CC; }
            QPushButton:pressed { background-color: #B2E2C1; }
            QPushButton:disabled{ background-color: #EAF6EF; color: #9AA4B2; border-color: #D5EBDD; }
        """)

        def handler():
            btn.setEnabled(False)
            try:
                on_click()
            except Exception as e:
                logging.exception("Button handler error: %s", e)
                print(f"⚠ Ошибка кнопки: {e}")
            finally:
                QTimer.singleShot(0, lambda w=cont: safe_remove_widget(w))

        btn.clicked.connect(handler)
        align = Qt.AlignmentFlag.AlignLeft if who == "bot" else Qt.AlignmentFlag.AlignRight
        row.addWidget(btn, 0, align)
        self.layout.insertWidget(self.layout.count() - 1, cont)
        self._update_bubble_metrics_async()
        return cont, btn

    def add_message(self, who, text: str):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        bubble = QFrame()
        bubble.setFrameShape(QFrame.Shape.NoFrame)
        bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bubble.setStyleSheet(
            "QFrame { background-color: %s; border-radius: 10px; border: none; }" %
            (USER_BUBBLE_BG if who == "user" else BOT_BUBBLE_BG)
        )

        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(10, 8, 10, 8)
        inner.setSpacing(0)

        lbl = QLabel()
        lbl.setTextFormat(Qt.TextFormat.RichText)
        if who == "user":
            lbl.setText(as_rich_wrapped(text))
        else:
            lbl.setText(as_rich_wrapped_bot(text))
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
        self._sugg_btn_widget = None
        self._last_q = None
        self.answer_ready.connect(self.on_answer_ready)
        self._pending_save_alias = None

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
    
    def _clear_last_suggestion(self):
        state.LastSuggestion.update({
            "kind": None, "entity": None, "field": None,
            "df_name": None, "asked_value": None, "candidates": []
        })

    def _remove_suggestion_button(self):
        for attr in ("_sugg_btn_widget", "_sugg_btn_widget2"):
            w = getattr(self, attr, None)
            safe_remove_widget(w)
            setattr(self, attr, None)

    def _maybe_add_accept_template_button(self):
        s = state.LastSuggestion
        if not s or s.get("kind") != "template":
            return
        tid = s.get("template_id")
        if not tid:
            return
        # 2 кнопки: Предпросмотр и Принять
        cont_prev, _ = self.chat_widget.add_action_button("bot", "🧪 Предпросмотр", on_click=self._preview_template)
        cont_acc, _  = self.chat_widget.add_action_button("bot", f'Принять шаблон: "{tid}"', on_click=self._accept_template_and_run)
        # будем уметь убрать обе
        self._sugg_btn_widget = cont_prev  # запомним хотя бы одну; вторую удалим вместе с сообщением
        self._sugg_btn_widget2 = cont_acc

    def send_query(self):
        q = self.entry.text().strip()
        if not q: return
        self.entry.clear()
        self._last_q = q
        self._remove_suggestion_button()
        self._clear_last_suggestion()
        self.chat_widget.add_message("user", f"👤 {q}")
        self._scroll_to_bottom()
        self.log_debug(f"[send_query] {repr(q)}")

        def worker():
            try:
                text, sugg = answer_via_templates(q, DFS_REG)
                if sugg:
                    if sugg.get("kind") == "save_alias" and state.LastSuggestion.get("kind") == "value":
                        self._pending_save_alias = sugg
                    else:
                        state.LastSuggestion = sugg
                        self._pending_save_alias = None
                else:
                    self._pending_save_alias = None
                self.answer_ready.emit(text)
            except Exception as e:
                self.answer_ready.emit(f"⚠ Ошибка: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def on_answer_ready(self, answer: str):
        self.log_debug(f"[UI] Отрисовка ответа: {repr(answer)[:200]}...")
        self._remove_suggestion_button()
        self.chat_widget.add_message("bot", f"🤖 {answer}")
        self._scroll_to_bottom()

        if state.LastSuggestion.get("kind") == "value":
            self._maybe_add_accept_value_button()
            if self._pending_save_alias:
                self._maybe_add_save_alias_button(self._pending_save_alias)
        elif state.LastSuggestion.get("kind") == "save_alias":
            self._maybe_add_save_alias_button()
    
    def _maybe_add_save_alias_button(self, sugg=None):
        s = sugg or state.LastSuggestion
        if not s or s.get("kind") != "save_alias":
            return
        tid = s.get("template_id")
        if not tid:
            return
        caption = f'Сохранить привязку фразы к шаблону: "{tid}"'
        cont, _ = self.chat_widget.add_action_button("bot", caption, on_click=self._save_alias_for_template)
        self._sugg_btn_widget2 = cont

    def _save_alias_for_template(self):
        s = state.LastSuggestion
        if not s or s.get("kind") != "save_alias":
            self.chat_widget.add_message("bot", "⚠ Нет предложения для привязки.")
            self._scroll_to_bottom(); return
        tid = s.get("template_id")
        q = s.get("question") or self._last_q or ""
        msg = add_alias(q, tid)
        self._clear_last_suggestion()
        self.chat_widget.add_message("bot", f"✅ {msg}")
        self._scroll_to_bottom()
    
    def _accept_template_and_run(self):
        s = state.LastSuggestion
        if not s or s.get("kind") != "template":
            self.chat_widget.add_message("bot", "⚠ Нет предложения по шаблону.")
            self._scroll_to_bottom()
            return
        tid = s.get("template_id")
        params = s.get("params") or {}
        q = s.get("question") or self._last_q or ""
        msg = add_alias(q, tid)
        self.chat_widget.add_message("bot", f"✅ {msg}\nВыполняю шаблон…")
        tpl = get_template(tid)
        if not tpl:
            self.chat_widget.add_message("bot", f"⚠ Шаблон «{tid}» не найден.")
            return
        try:
            preview = store_run_template(tpl, params)
            self.answer_ready.emit(f'**Применяю шаблон:** {tpl["text"]}\nПараметры: {params}\n🧠 **Мой ответ:** {preview}')
        except Exception as e:
            self.answer_ready.emit(f"⚠ Ошибка выполнения шаблона: {e}")
        self._clear_last_suggestion()
        
    def _maybe_add_accept_value_button(self):
        s = state.LastSuggestion
        if not s or s.get("kind") != "value": return
        cands = s.get("candidates") or []
        if not cands: return
        top_val = cands[0][0]
        caption = f'Принять значение: "{top_val}"'
        cont, _ = self.chat_widget.add_action_button("bot", caption, on_click=self._accept_value_and_rerun)
        self._sugg_btn_widget = cont

    def _preview_template(self):
        s = state.LastSuggestion
        if not s or s.get("kind") != "template":
            self.chat_widget.add_message("bot", "⚠ Нет предложения по шаблону.")
            self._scroll_to_bottom()
            return
        tid = s.get("template_id")
        if not tid:
            self.chat_widget.add_message("bot", "⚠ Не указан шаблон.")
            return
        tpl = get_template(tid)
        if not tpl:
            self.chat_widget.add_message("bot", f"⚠ Шаблон «{tid}» не найден.")
            return
        params = s.get("params") or {}
        try:
            preview = store_run_template(tpl, params)
            self.chat_widget.add_message("bot", f'🧪 Предпросмотр «{tid}»\nПараметры: {params}\n🧠 **Мой ответ:** {preview}')
        except Exception as e:
            self.chat_widget.add_message("bot", f"⚠ Ошибка предпросмотра: {e}")
        self._scroll_to_bottom()

    def _accept_value_and_rerun(self):
        try:
            s = state.LastSuggestion
            if not s or s.get("kind") != "value":
                self.chat_widget.add_message("bot", "⚠ Нет сохранённой подсказки по значениям.")
                self._scroll_to_bottom(); return

            entity = s.get("entity"); field = s.get("field")
            asked = s.get("asked_value") or (s["candidates"][0][0] if s.get("candidates") else "")
            chosen = s["candidates"][0][0]

            from core.mappings import add_value_alias
            msg = add_value_alias(entity, field, asked, chosen)
            logging.info("Value alias added: %s / %s / %s -> %s", entity, field, asked, chosen)

            # ВАЖНО: убрать старую подсказку перед повторным запуском
            self._remove_suggestion_button()
            self._clear_last_suggestion()
            self._pending_save_alias = None

            self.chat_widget.add_message("bot", f"✅ {msg}\nПовторяю запрос с учётом алиаса…")
            self._scroll_to_bottom()
            q = self._last_q or state.LastQuestion or ""

            def worker():
                try:
                    text, sugg = answer_via_templates(q, DFS_REG)
                    if sugg:
                        state.LastSuggestion = sugg
                        self._pending_save_alias = None
                    else:
                        self._pending_save_alias = None
                    self.answer_ready.emit(text)
                except Exception as e:
                    logging.exception("Re-run after accept value error: %s", e)
                    self.answer_ready.emit(f"⚠ Ошибка: {e}")

            threading.Thread(target=worker, daemon=True).start()
        except Exception as e:
            logging.exception("Accept value handler error: %s", e)
            self.chat_widget.add_message("bot", f"⚠ Ошибка: {e}")

class TemplatesTab(QWidget):
    def __init__(self):
        super().__init__()
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QPushButton
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.refresh_btn = QPushButton("Обновить список")
        self.refresh_btn.clicked.connect(self.reload)
        top.addWidget(self.refresh_btn); top.addStretch(1)
        lay.addLayout(top)

        mid = QHBoxLayout()
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self.show_selected)
        mid.addWidget(self.list, 2)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setFont(QFont("Consolas", 10))
        mid.addWidget(self.details, 5)
        lay.addLayout(mid)
        self.reload()

    def reload(self):
        self.list.clear()
        for t in list_templates():
            self.list.addItem(f'{t["id"]} — {t["text"]}')
        self.details.setPlainText("")

    def show_selected(self):
        items = self.list.selectedItems()
        if not items: 
            self.details.setPlainText(""); return
        first = items[0].text()
        tid = first.split(" — ",1)[0].strip()
        t = get_template(tid)
        if not t:
            self.details.setPlainText("Не найден"); return
        txt = []
        txt.append(f"ID: {t['id']}")
        txt.append(f"Текст: {t['text']}")
        txt.append(f"Параметры: {t.get('params', [])}")
        txt.append("\nКод:")
        txt.append(t.get("code_template",""))
        self.details.setPlainText("\n".join(txt))

class TemplateGenTab(QWidget):
    answer_ready = pyqtSignal(str)
    def __init__(self, log_debug):
        super().__init__()
        self.log_debug = log_debug
        self.answer_ready.connect(self.on_answer_ready)
        self._last_proposal = None
        layout = QVBoxLayout(self)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.chat_widget = BubbleChat(); self.scroll.setWidget(self.chat_widget)
        layout.addWidget(self.scroll)
        entry_layout = QHBoxLayout()
        self.entry = QLineEdit(); self.entry.setFont(QFont("Segoe UI Emoji", 11))
        send_btn = QPushButton("Сгенерировать"); send_btn.clicked.connect(self.send)
        entry_layout.addWidget(self.entry); entry_layout.addWidget(send_btn)
        layout.addLayout(entry_layout)

    def _scroll_to_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def send(self):
        q = self.entry.text().strip()
        if not q: return
        self.entry.clear()
        self.chat_widget.add_message("user", f"👤 {q}")
        self._scroll_to_bottom()
        def worker():
            try:
                prop = generate_template_with_llm(q, DFS_REG, list_templates())
                if not prop:
                    self.answer_ready.emit("⚠ Не удалось сгенерировать шаблон (LLM недоступна или ошибка).")
                    return
                self._last_proposal = prop
                # предпросмотр исполнения не делаем, т.к. нет параметров
                details = f'ID: {prop["id"]}\nТекст: {prop["text"]}\nПараметры: {prop.get("params", [])}\n\nКод:\n{prop["code_template"]}'
                if prop.get("validation_error"):
                    details += f'\n\n⚠ Предупреждение проверки: {prop["validation_error"]}'
                self.answer_ready.emit(details)
            except Exception as e:
                self.answer_ready.emit(f"⚠ Ошибка генерации: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def on_answer_ready(self, answer: str):
        self.log_debug(f"[UI] Отрисовка ответа: {repr(answer)[:200]}...")
        self._remove_suggestion_button()
        self.chat_widget.add_message("bot", f"🤖 {answer}")
        self._scroll_to_bottom()
        # приоритет значений (кнопка зеленая), затем "сохранить привязку"
        if state.LastSuggestion.get("kind") == "value":
            self._maybe_add_accept_value_button()
        if state.LastSuggestion.get("kind") == "save_alias":
            self._maybe_add_save_alias_button()

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

        self.templates_tab = TemplatesTab()
        self.tabs.addTab(self.templates_tab, "📐 Шаблоны")

        self.tpl_gen_tab = TemplateGenTab(self.log_debug)
        self.tabs.addTab(self.tpl_gen_tab, "🧩 Генератор шаблонов")

        self.console = QTextEdit()
        self.console.setFont(QFont("Consolas", 9))
        self.console.setReadOnly(True)
        self.console.setVisible(True)
        self.central_layout.addWidget(self.console)

        class EmittingStream(io.TextIOBase):
            def __init__(self, write_func): self.write_func = write_func
            def write(self, text):
                if text.strip():
                    logging.info(text.strip())
                    self.write_func(text.strip())
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