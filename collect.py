#!/usr/bin/env python3
"""«Нейрорадар» — автосборщик новостей о мире искусственного интеллекта.

Читает RSS-ленты, отбирает материалы про ИИ, раскладывает по рубрикам
и собирает статический сайт в docs/.

Запуск: python collect.py
"""

import os
import sys
from datetime import datetime, timedelta

from news.config import CATEGORIES, DEAD_SOURCES, DOCS_DIR, JOB_SOURCES, MAX_AGE_DAYS
from news.dedup import Seen
from news.fetch import (
    count_raw, fetch_fl_orders, fetch_hh_vacancies, fetch_trudvsem_vacancies,
    fetch_url, parse_rss,
)
from news import monitor
from news.filters import is_ai_order, is_ai_relevant
from news.monitor import SourcesLog
from news.render import (
    copy_static, generate_category_page, generate_main_page, generate_robots,
    generate_rss, generate_sitemap,
)
from news.sources import FEEDS
from news.store import load_news, save_data_js, save_news
from news.util import now_msk

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def collect_feeds(seen, log):
    """Шаг 1. Читаем ленты и собираем свежие новости.

    Итоги складываются по источнику, а не по ленте: у vc.ru и «Habr Веб-дизайна»
    по две ленты, и в журнал должна попасть общая картина.
    """
    fresh = []
    totals = {}  # источник -> {записей, новых, ошибка}
    for feed in FEEDS:
        source = feed["source"]
        if log.should_skip(source):
            print(f"Пропускаю (в карантине): {source}")
            continue
        acc = totals.setdefault(source, {"records": 0, "new": 0, "error": "", "raw": 0})
        try:
            print(f"Читаю: {feed['url']}")
            xml = fetch_url(feed["url"]).decode("utf-8", errors="replace")
            items = parse_rss(xml, feed)
            added = 0
            for item in items:
                if seen.check(item):
                    continue
                fresh.append(item)
                added += 1
            print(f"  -> {len(items)} записей, новых: {added}")
            acc["records"] += len(items)
            acc["new"] += added
            if not items:
                # Пустая лента и «не по нашей теме» — разные диагнозы.
                acc["raw"] += count_raw(xml)
        except Exception as e:
            print(f"  ! Ошибка: {e}")
            acc["error"] = str(e)

    for source, acc in totals.items():
        if acc["records"]:
            status = monitor.OK
        elif acc["error"]:
            status = monitor.ERROR
        elif acc["raw"]:
            status = monitor.FILTERED
        else:
            status = monitor.EMPTY
        log.note(source, status, acc["records"], acc["new"], note=acc["error"])

    return fresh


def _absorb(seen, items, fresh):
    """Добавляет новые записи в общий поток. Возвращает, сколько оказалось новых."""
    added = 0
    for item in items:
        if not seen.check(item):
            fresh.append(item)
            added += 1
    return added


def collect_extra(seen, log):
    """Шаг 1б и 1в. Вакансии и заказы — они приходят не из RSS."""
    fresh = []
    for what, fetch, source in (
        ("вакансии с hh.ru", fetch_hh_vacancies, "hh.ru"),
        ("вакансии с Работа России", fetch_trudvsem_vacancies, "Работа России"),
        ("заказы с FL.ru", fetch_fl_orders, "FL.ru"),
    ):
        print(f"Собираю {what}...")
        items = fetch()
        added = _absorb(seen, items, fresh)
        # Если внутри источника была ошибка, он вернёт пустой список —
        # и это честно попадёт в журнал как молчание.
        log.note(source, monitor.OK if items else monitor.EMPTY, len(items), added)
    return fresh


def _to_unfiltered(item, bucket):
    """Переводит запись в подрубрику «Не фильтрованное» вместо удаления."""
    item["cat"] = "misc"
    item["misc_type"] = "unfiltered"
    bucket.append(item)


def load_store(seen):
    """Шаг 2. Поднимаем накопители, чтобы не потерять уже собранное.

    Записи, которые больше не проходят фильтр, НЕ выбрасываем, а переводим
    в Солянку — подрубрику «Не фильтрованное». Иначе старый мусор из
    накопителя возвращался бы в каждую сборку и портил рубрики.
    """
    kept = []
    to_unfiltered = []
    dropped_dead = 0

    for key in CATEGORIES:
        for item in load_news(key):
            if seen.check(item):
                # Здесь же чинится и старый дубль, уже лежащий в накопителе.
                continue
            # Мёртвые источники выкидываем совсем — они не должны висеть на сайте
            # ни в рубриках, ни в «Не фильтрованном».
            if item.get("source") in DEAD_SOURCES:
                dropped_dead += 1
                continue
            # Заказы проверяются отдельной функцией
            if item.get("cat") == "orders":
                if not is_ai_order(item.get("title", ""), item.get("desc", "")):
                    _to_unfiltered(item, to_unfiltered)
                    continue
            # Вакансии: остаются только от источников вакансий (hh.ru, «Работа
            # России»), статьи из RSS уезжают в Солянку.
            elif item.get("cat") == "jobs" and item.get("source") not in JOB_SOURCES:
                _to_unfiltered(item, to_unfiltered)
                continue
            # Остальные рубрики проверяются на тему ИИ
            elif item.get("cat") not in ("jobs", "misc"):
                text = (item.get("title", "") or "") + " " + (item.get("desc", "") or "")
                if not is_ai_relevant(text, item.get("cat")):
                    _to_unfiltered(item, to_unfiltered)
                    continue
            kept.append(item)

    return kept, to_unfiltered, dropped_dead


def main():
    seen = Seen()
    log = SourcesLog()

    all_news = collect_feeds(seen, log)
    all_news += collect_extra(seen, log)

    kept, to_unfiltered, dropped_dead = load_store(seen)
    all_news += kept

    if to_unfiltered:
        # Просто добавляем их к общему потоку: шаг 5 разложит их в misc
        # и запишет накопитель сам.
        for item in to_unfiltered:
            item.pop("job_type", None)
            item.pop("order_type", None)
        all_news += to_unfiltered
        print(f"  [сортировка] в «Не фильтрованное» переведено: {len(to_unfiltered)}")

    if dropped_dead:
        print(f"  [чистка] мёртвых источников удалено: {dropped_dead}")
    if seen.dups:
        print(f"  [дедуп] повторов отброшено: {seen.dups}")

    # 3. Фильтр по дате
    cutoff = now_msk() - timedelta(days=MAX_AGE_DAYS)
    filtered = []
    for item in all_news:
        try:
            d = datetime.strptime(item.get("date", "2000-01-01"), "%Y-%m-%d")
            if d < cutoff:
                continue
        except ValueError:
            pass
        filtered.append(item)

    # 4. Сортируем: свежее — выше
    filtered.sort(key=lambda x: x.get("date", "2000-01-01"), reverse=True)

    # 5. Раскладываем по рубрикам
    for key, cat in CATEGORIES.items():
        items = [n for n in filtered if n["cat"] == key]
        save_news(key, items)
        save_data_js(os.path.join(DOCS_DIR, key, "data.js"), items)
        generate_category_page(key, cat)

    # 6. Главная страница
    generate_main_page(filtered)

    # 7. Ручные страницы (about/)
    copy_static()

    # 8. Служебные файлы сайта: карта для поисковиков, robots и своя лента.
    #    Собираются из того же filtered, что и рубрики, — отдельного источника
    #    правды не заводим, иначе они разъедутся.
    generate_sitemap()
    generate_robots()
    generate_rss(filtered)

    print(f"\n[OK] Всего новостей: {len(filtered)}")

    # 8. Отчёт по источникам — кто отвечает, кто молчит, кого пора в карантин.
    #    Печатаем и сохраняем в любом случае, даже если сборка упала раньше:
    #    иначе молчаливый источник снова останется незамеченным.
    print("\n--- Источники ---")
    log.print_report()
    log.save()


if __name__ == "__main__":
    main()
