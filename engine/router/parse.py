# -*- coding: utf-8 -*-
import re
from typing import Optional, List, Tuple
from core.mappings import unify_entity_phrase, unify_field_phrase

# Предлоги, которые нужно игнорировать как отдельные слова
PRE_WORDS = (
    "в", "во", "по", "у", "на", "из", "с", "со", "к", "ко",
    "от", "для", "за", "о", "об", "обо", "при", "над", "под", "про", "через"
)
# Регулярное выражение «предлог как отдельное слово»
PRE = r"\b(?:%s)\b" % "|".join(PRE_WORDS)

def _clean_field_phrase(s: str) -> str:
    """
    Удаляет ведущий предлог и лишние пробелы.
    'по руководителю' -> 'руководителю'
    'у контрагента'   -> 'контрагента'
    """
    s = (s or "").strip()
    s = re.sub(rf"^{PRE}\s+", "", s, flags=re.I)
    return s.strip()

def extract_entity(q: str) -> Optional[str]:
    # Сколько <entity> <предлог> ...
    m = re.search(rf"Сколько\s+(.+?)\s+{PRE}\s+", q, flags=re.I)
    if not m:
        return None
    return unify_entity_phrase(m.group(1).strip())

def _iter_segments_outside_quotes(text: str) -> List[str]:
    """
    Делит строку по ' и ' вне кавычек (простая эвристика).
    """
    # Грубая, но рабочая эвристика: разбиваем по ' и ', не пытаясь парсить кавычки глубоко.
    # Сегменты, содержащие кавычки, обработаются в «ветке с кавычками» и будут пропущены здесь.
    return re.split(r"\s+и\s+", text)

def extract_pairs(q: str) -> List[Tuple[str, str]]:
    """
    Ищем пары (поле, значение).
    Поддерживаются:
      - с кавычками:  <предлог> <поле> "Значение"
      - без кавычек:  <предлог> <поле> Значение  (значение — последний токен)
    """
    pairs: List[Tuple[str, str]] = []

    # 1) Ветвь «с кавычками»
    for m in re.finditer(rf"{PRE}\s+([^\"«»]+?)\s+[\"«]([^\"»]+)[\"»]", q, flags=re.I):
        field_phrase = _clean_field_phrase(m.group(1))
        value = m.group(2).strip().rstrip('?.!,;')
        field = unify_field_phrase(field_phrase) or field_phrase
        pairs.append((field, value))

    # 2) Ветвь «без кавычек»
    for seg in _iter_segments_outside_quotes(q):
        seg = seg.strip()
        # пропускаем, если в сегменте есть кавычки — такие разобрались в ветке 1
        if any(ch in seg for ch in ['"', '«', '»']):
            continue
        # Ищем "<предлог> <поле> <значение_токен>" до конца сегмента
        # Поле берём "жадно", значение — последний токен (слово/число).
        m2 = re.search(rf"{PRE}\s+(.+)\s+([^\s\"«»]+)\s*$", seg, flags=re.I)
        if not m2:
            continue
        field_phrase = _clean_field_phrase(m2.group(1))
        value = m2.group(2).strip().rstrip('?.!,;')
        field = unify_field_phrase(field_phrase) or field_phrase
        pair = (field, value)
        if pair not in pairs:
            pairs.append(pair)

    return pairs

def parse_structured(q: str):
    entity = extract_entity(q)
    if not entity:
        return None
    pairs = extract_pairs(q)
    if not pairs:
        return None
    return entity, pairs