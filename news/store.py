"""Чтение и запись накопителей.

Накопители лежат в data/ и хранятся в git — это архив проекта, а не временный
файл. Поэтому запись идёт через write_if_changed(): если содержимое не
изменилось, файл не переписывается и лишний коммит не появляется.
"""

import json
import os

from .config import CATEGORIES, DATA_DIR
from .util import now_msk


def news_path(cat_key):
    """Путь к накопителю рубрики: data/ai.json, data/misc.json и т.д."""
    return os.path.join(DATA_DIR, cat_key + ".json")


def load_news(cat_key):
    """Читает накопитель рубрики. Нет файла или он битый — возвращаем пустой список."""
    try:
        with open(news_path(cat_key), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_if_changed(filepath, content):
    """Пишет файл только если содержимое изменилось — чтобы не плодить пустые коммиты."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            if f.read() == content:
                return
    except FileNotFoundError:
        pass
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def save_news(cat_key, items):
    """Сохраняет накопитель рубрики."""
    write_if_changed(news_path(cat_key),
                     json.dumps(items, ensure_ascii=False, indent=2))


def save_data_js(filepath, items, cat_keys=None):
    """Пишет data.js — данные для страницы рубрики (её читает браузер).

    Всегда пишем объект {items, cat_keys, updated}, а не голый список.
    Раньше для рубрик уходил список, и поле updated пропадало — страница
    показывала не время сборки, а текущее время посетителя. Это вводило
    в заблуждение: сайт выглядел свежее, чем был.
    """
    ts = now_msk().strftime("%d.%m.%Y, %H:%M:%S")
    data = {
        "items": items,
        "cat_keys": list(cat_keys if cat_keys is not None else CATEGORIES.keys()),
        "updated": ts,
    }
    body = "window.NEWS_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    write_if_changed(filepath, body)
