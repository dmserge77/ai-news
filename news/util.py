"""Мелкие помощники: время, разбор дат, чистка текста, определение языка."""

import re
from datetime import datetime, timedelta, timezone
from html import unescape


def now_msk():
    """Текущее время по Москве (UTC+3).

    datetime.utcnow() в Python 3.12+ помечен устаревшим, поэтому берём
    осведомлённое время и убираем зону — на выходе те же наивные UTC+3.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)


def detect_lang(text):
    """Определяет язык: 'ru' если есть кириллица, иначе 'en'."""
    return "ru" if re.search(r"[а-яА-ЯёЁ]", text) else "en"


def clean_desc(html_text):
    """Убирает теги и лишние пробелы, обрезает длинный текст до 300 знаков."""
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:297] + "..." if len(text) > 300 else text


def parse_date(date_str):
    """Приводит дату из ленты к виду ГГГГ-ММ-ДД.

    Ленты присылают даты в десятке разных форматов, поэтому пробуем по очереди.
    Если совсем ничего не подошло — ставим сегодняшний день: лучше неточная дата,
    чем потерянная новость.
    """
    if not date_str:
        return now_msk().strftime("%Y-%m-%d")
    s = date_str.strip()
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                 "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # eTXT шлёт вида "2026-08-27 15:52:27"
    for fmt in ["%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"202\d-\d{2}-\d{2}", s)
    if m:
        return m.group()
    return now_msk().strftime("%Y-%m-%d")


def norm_title(title):
    """Заголовок для сравнения дублей: без регистра, пунктуации и лишних пробелов."""
    t = (title or "").lower()
    t = re.sub(r"[^\w\s]+", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t)
    return t.strip()
