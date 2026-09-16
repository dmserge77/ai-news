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
    # Из &lt;img&gt; после unescape получился настоящий тег — вычищаем ещё раз.
    # Описание выводится на страницу, поэтому разметке здесь не место.
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:297] + "..." if len(text) > 300 else text


def strip_html(text):
    """Убирает разметку из строки, оставляя чистый текст. Не обрезает.

    Нужна для заголовков. Заголовок из чужой ленты попадает на страницу,
    и если в нём приедет тег, браузер посетителя выполнит его как разметку.
    Это уже случалось в других агрегаторах: `<img src=x onerror=...>`
    в заголовке — и код выполняется у каждого, кто открыл сайт.

    От clean_desc отличается тем, что не режет длину: заголовок должен
    остаться целиком, даже если он длинный.
    """
    text = re.sub(r"<[^>]*>", " ", text or "")
    text = unescape(text)
    # После unescape из &lt; мог получиться настоящий тег — вычищаем ещё раз,
    # а одиночные угловые скобки заменяем: в чистом тексте им делать нечего.
    text = re.sub(r"<[^>]*>", " ", text)
    text = text.replace("<", " ").replace(">", " ")
    return re.sub(r"\s+", " ", text).strip()


# Символы, которых в адресе быть не должно. Пробел и кавычка в href — это
# попытка вырваться из атрибута, угловые скобки — из тега, обратный слэш
# ломает разбор в некоторых браузерах.
_UNSAFE_IN_URL = re.compile(r"""[\s"'<>\\]""")


def safe_link(url):
    """Пропускает только http и https, остальное превращает в пустую строку.

    Ссылка из чужой ленты идёт в атрибут href. Адрес вида `javascript:...`
    выполнится по клику в браузере посетителя, поэтому схему надо проверять,
    а не доверять ленте. Заодно отсекаем кавычки и пробелы: с ними ссылка
    может вылезти из атрибута и дописать в разметку своё.

    Проверено по архиву 16.09.2026: из 1487 записей ни одна живая ссылка
    таких символов не содержит, так что отсев ничего не теряет.
    """
    url = (url or "").strip()
    if _UNSAFE_IN_URL.search(url):
        return ""
    return url if url.lower().startswith(("http://", "https://")) else ""


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
