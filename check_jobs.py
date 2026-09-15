#!/usr/bin/env python3
"""Перепроверка накопителя вакансий по текущим правилам отбора.

Зачем это нужно. Рубрика «Вакансии» собирается только с hh.ru и «Работы
России» и только по удалёнке. Но записи, попавшие в накопитель раньше, лежат
там до MAX_AGE_DAYS и заново не проверяются. Если правила ужесточили, старые
записи надо разобрать руками — этим и занимается скрипт.

Что проверяется по каждой вакансии:

  1. Формат работы. hh.ru отдаёт его прямо на странице — в служебном элементе
     `data-qa="work-formats-text"` лежит строка вида
     «Формат работы: удалённо», «Формат работы: на месте работодателя»
     или «Формат работы: на месте работодателя, удалённо или гибрид».
     Удалённой считаем ту, где встречается «удалён». Гибрид сам по себе —
     не удалёнка: это частичная работа в офисе.
  2. Остальные правила — через is_real_ai_job(remote_confirmed=True):
     язык, блок-лист профессий, курсы и стажировки, признак ИИ/ML.

Чего скрипт НЕ проверяет и почему: закрыта вакансия или нет. Определить это
по странице нельзя — строки «Вакансия закрыта» и `vacancyArchived` есть в
разметке **каждой** вакансии, включая открытые: это справочник интерфейса.
Проверено сравнением открытых вакансий из живой ленты с заведомо закрытыми.

Почему формат читается со страницы, а не из поиска. Раньше здесь был другой
метод: по заголовку вакансии делались два запроса к ленте hh.ru — без фильтра
и с schedule=remote. Метод работал, но он косвенный (зависит от того, как
поиск проиндексировал вакансию), требовал до 10 запросов на вакансию и
смешивал закрытые вакансии с непроиндексированными. Страница отвечает прямо
и за один запрос.

Со страницы же нельзя было читать формат раньше: поиск по словам «Формат
работы» находил только справочник интерфейса («Удалённо», «Гибрид», «Полный
день» есть на каждой вакансии). Нужен именно служебный элемент
`data-qa="work-formats-text"`.

Запуск из корня проекта:
    python check_jobs.py            — только отчёт, ничего не меняет
    python check_jobs.py --apply    — переписать data/jobs.json
"""

import json
import os
import re
import sys
import time
from datetime import datetime

from news.config import DATA_DIR
from news.fetch import fetch_url
from news.filters import is_real_ai_job

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Формат работы на странице вакансии. Именно этот служебный элемент, а не
# просто поиск слов «удалённо» по HTML: те же слова лежат в справочнике
# интерфейса и присутствуют на каждой вакансии, включая офисные.
WORK_FORMAT_RE = re.compile(r'data-qa="work-formats-text"[^>]*>(.*?)</', re.S)

REMOTE = "remote"      # удалённая — оставляем
OFFICE = "office"      # формат без удалёнки — убираем
RULES = "rules"        # не прошла остальные правила — убираем
UNKNOWN = "unknown"    # не смогли прочитать страницу — не трогаем


def fetch_page(url, attempts=3):
    """Скачивает страницу вакансии. hh.ru иногда отвечает 403 — пробуем ещё."""
    last = None
    for i in range(attempts):
        try:
            return fetch_url(url).decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            if i < attempts - 1:
                time.sleep(1.5)
    raise last


def read_work_format(html):
    """Формат работы со страницы. None — hh.ru его не указал."""
    m = WORK_FORMAT_RE.search(html)
    if not m:
        return None
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    return re.sub(r"\s+", " ", text).strip()


def check_one(job):
    """Возвращает (исход, пояснение) для одной вакансии."""
    try:
        html = fetch_page(job.get("link", ""))
    except Exception as e:
        return UNKNOWN, f"страница не открылась: {e}"

    fmt = read_work_format(html)
    if fmt is None:
        # Формат не отдан. Не выбрасываем: решить нечем, а терять записи
        # без основания проект не должен.
        return UNKNOWN, "формат работы не указан"

    if "удалён" not in fmt.lower():
        return OFFICE, fmt

    # Удалёнка подтверждена страницей — дальше общие правила.
    title, desc = job.get("title", ""), job.get("desc", "")
    if not is_real_ai_job(title, desc, remote_confirmed=True):
        return RULES, f"не прошла правила ({fmt})"

    return REMOTE, fmt


def main():
    apply_changes = "--apply" in sys.argv

    path = os.path.join(DATA_DIR, "jobs.json")
    with open(path, encoding="utf-8") as f:
        jobs = json.load(f)

    print(f"Проверяю вакансий: {len(jobs)}")
    print()

    keep, drop, unknown = [], [], []
    for i, job in enumerate(jobs, 1):
        verdict, why = check_one(job)
        mark = {"remote": "удалённая", "office": "не удалённая",
                "rules": "не по правилам", "unknown": "не проверена"}[verdict]
        print(f"  {i:3}/{len(jobs)}  [{mark:13}] {job.get('title', '')[:52]}")
        if verdict == REMOTE:
            keep.append(job)
        elif verdict == UNKNOWN:
            unknown.append((job, why))
            keep.append(job)  # не смогли проверить — не выбрасываем
        else:
            drop.append((job, verdict, why))
        time.sleep(0.15)  # не частим с запросами

    counts = {}
    for _, verdict, _ in drop:
        counts[verdict] = counts.get(verdict, 0) + 1

    print()
    print("--- Итог ---")
    print(f"  удалённых, оставляем:  {len(keep) - len(unknown)}")
    print(f"  не удалённых:          {counts.get(OFFICE, 0)}")
    print(f"  не прошедших правила:  {counts.get(RULES, 0)}")
    print(f"  не удалось проверить:  {len(unknown)}")

    if drop:
        print()
        print("Будут убраны:")
        names = {OFFICE: "не удалённая", RULES: "не по правилам"}
        for job, verdict, why in drop:
            print(f"  [{names[verdict]:13}] {job.get('title', '')[:50]}")
            print(f"                  {job.get('link', '')}")
            print(f"                  причина: {why}")

    if not apply_changes:
        print()
        print("Это отчёт. Чтобы применить — запустите с ключом --apply.")
        return

    if not drop:
        print()
        print("Убирать нечего — накопитель в порядке.")
        return

    # Копии — чтобы ничего не терялось безвозвратно (правило проекта).
    backup_dir = os.path.join(os.path.dirname(DATA_DIR), "_backup")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")

    removed_path = os.path.join(backup_dir, f"jobs_removed_{stamp}.json")
    with open(removed_path, "w", encoding="utf-8") as f:
        json.dump([j for j, _, _ in drop], f, ensure_ascii=False, indent=2)

    before_path = os.path.join(backup_dir, f"jobs_before_check_{stamp}.json")
    with open(before_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False, indent=2)

    print()
    print(f"Готово. В накопителе осталось: {len(keep)}")
    print(f"  копия накопителя до правки: {before_path}")
    print(f"  копия убранного:            {removed_path}")


if __name__ == "__main__":
    main()
