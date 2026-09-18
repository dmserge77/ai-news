#!/usr/bin/env python3
"""Почему этой новости нет на сайте?

Ищет строку в архиве (data/*.json) и в журнале отказов (data/rejects.json).
Если запись на сайте есть — показывает рубрику и дату. Если её отклонил
фильтр — называет причину, источник и сколько раз она отклонялась.

Запуск:
    python why.py рачки
    python why.py "машинное обучение"
    python why.py              # без аргумента — сводка по причинам отказов

Скрипт ничего не меняет: только читает. Это инструмент разбора, а не сборки.
"""

import json
import os
import sys

from news.config import CATEGORIES, DATA_DIR

REJECTS_PATH = os.path.join(DATA_DIR, "rejects.json")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def plural(n, one, few, many):
    """«1 совпадение», «2 совпадения», «5 совпадений».

    Без этого в выводе появляется «1 совпадений» — мелочь, но по ней видно,
    что отчёт собран на скорую руку, и доверия к цифрам меньше.
    """
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} {few}"
    return f"{n} {many}"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def find_in_archive(term):
    """Ищет строку в накопителях рубрик. Возвращает список совпадений."""
    found = []
    for key in CATEGORIES:
        path = os.path.join(DATA_DIR, key + ".json")
        for item in load_json(path, []):
            haystack = ((item.get("title") or "") + " " + (item.get("desc") or "")).lower()
            if term in haystack:
                found.append((key, item))
    return found


def find_in_rejects(term):
    """Ищет строку в журнале отказов."""
    data = load_json(REJECTS_PATH, {})
    found = []
    for rec in data.get("items", []) or []:
        haystack = ((rec.get("title") or "") + " " + (rec.get("reason") or "")).lower()
        if term in haystack:
            found.append(rec)
    return data, found


def show_summary():
    """Сводка по журналу: сколько отсеялось и за что."""
    data = load_json(REJECTS_PATH, None)
    if not data:
        print("Журнала отказов нет: data/rejects.json не найден.")
        print("Он появится после первой сборки: python collect.py")
        return
    print(f"Журнал обновлён: {data.get('updated', '?')}, прогонов: {data.get('runs', 0)}")
    print(f"Всего отказов за всё время: {data.get('total_rejected', 0)}")
    last = data.get("last_run", {}) or {}
    print(f"За последний прогон: {last.get('total', 0)}")
    print("\nПричины за последний прогон:")
    reasons = last.get("by_reason", {}) or {}
    if not reasons:
        print("  (отказов не было)")
    for reason, count in reasons.items():
        print(f"  {count:>5}  {reason}")
    print("\nПричины за всё время:")
    for reason, count in (data.get("by_reason", {}) or {}).items():
        print(f"  {count:>6}  {reason}")


def main():
    if len(sys.argv) < 2:
        show_summary()
        return

    term = " ".join(sys.argv[1:]).lower().strip()
    print(f"Ищу: «{term}»\n")

    archive = find_in_archive(term)
    if archive:
        print(f"На сайте — {plural(len(archive), 'совпадение', 'совпадения', 'совпадений')}:")
        for key, item in archive[:20]:
            label = CATEGORIES.get(key, {}).get("label", key)
            print(f"  [{label}] {item.get('date', '?')} · {item.get('source', '?')}")
            print(f"      {item.get('title', '')}")
        if len(archive) > 20:
            print(f"  … и ещё {len(archive) - 20}")
    else:
        print("На сайте не найдено.")

    data, rejected = find_in_rejects(term)
    if rejected:
        print(f"\nВ журнале отказов — {plural(len(rejected), 'запись', 'записи', 'записей')}:")
        for rec in rejected[:20]:
            print(f"  причина: {rec.get('reason', '?')}")
            print(f"  источник: {rec.get('source', '?')} · отказов: {rec.get('count', 1)}"
                  f" · с {rec.get('first', '?')} по {rec.get('last', '?')}")
            print(f"      {rec.get('title', '')}")
            if rec.get("link"):
                print(f"      {rec['link']}")
    elif not archive:
        print("\nИ в журнале отказов её нет — возможно, запись старше 90 дней"
              " или её ещё не было в лентах.")

    if not data:
        print("\n(журнала отказов пока нет — он появится после первой сборки)")


if __name__ == "__main__":
    main()
