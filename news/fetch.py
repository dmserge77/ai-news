"""Загрузка лент и разбор того, что они присылают.

Вся работа с сетью живёт здесь. Если однажды понадобится ходить не через
urllib, а как-то иначе — менять придётся только fetch_url().
"""

import json
import ssl
from html import unescape
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .config import DEAD_SOURCES, SPAM_FILTER_SOURCES
from .filters import (
    classify, classify_job, classify_misc, classify_order, is_ai_order,
    is_ai_relevant, is_real_ai_job, is_seo_spam,
)
from .util import clean_desc, detect_lang, now_msk, parse_date

ATOM = "{http://www.w3.org/2005/Atom}"


def fetch_url(url):
    """Скачивает адрес и возвращает байты."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # Кириллицу в URL (например, теги vc.ru вида /rss/tag/нейросети) urlopen
    # не умеет кодировать сам: падает 'ascii' codec can't encode.
    # quote безопасен для обычных адресов — он кодирует только не-ASCII.
    url = quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    with urlopen(req, timeout=15, context=ctx) as resp:
        return resp.read()


def _build_item(title, link, desc, date_raw, feed):
    """Превращает запись ленты в карточку новости. None — если не подходит.

    Логика одна и та же для RSS (item) и Atom (entry), поэтому живёт здесь,
    а не дублируется в двух ветках разбора.
    """
    text = title + " " + desc
    # SEO-мусор в ИИ-тегах vc.ru («нейросеть для X бесплатно: промпт и ...»)
    if feed.get("source") in SPAM_FILTER_SOURCES and is_seo_spam(title):
        return None
    cat = classify(text, feed["cat"])
    # Вакансии из RSS не берём вообще: настоящие вакансии приходят только
    # с hh.ru (fetch_hh_vacancies). Иначе статьи со словом «работать»
    # просачивались в рубрику «Вакансии».
    if cat == "jobs":
        cat = "misc"
    if not is_ai_relevant(text, cat):
        return None
    item = {
        "title": title, "link": link,
        "desc": clean_desc(desc),
        "date": parse_date(date_raw),
        "source": feed["source"],
        "cat": cat,
        "lang": detect_lang(text),
    }
    if cat == "misc":
        item["misc_type"] = classify_misc(title, desc)
    return item


def parse_rss(xml_text, feed):
    """Разбирает ленту (RSS или Atom) в список карточек."""
    items = []
    # Мёртвый источник — не читаем вовсе (лента могла вернуться в FEEDS случайно).
    if feed.get("source") in DEAD_SOURCES:
        return items

    root = ElementTree.fromstring(xml_text)

    for item in root.iter("item"):
        title = unescape(item.findtext("title", "")).strip()
        link = item.findtext("link", "").strip()
        desc = unescape(item.findtext("description", "")).strip()
        pubdate = item.findtext("pubDate", "")
        if not title or not link:
            continue
        built = _build_item(title, link, desc, pubdate, feed)
        if built:
            items.append(built)

    for entry in root.iter(ATOM + "entry"):
        title = unescape(entry.findtext(ATOM + "title", "")).strip()
        link_el = entry.find(ATOM + "link")
        link = link_el.get("href", "").strip() if link_el is not None else ""
        desc = unescape(entry.findtext(ATOM + "summary", "")).strip()
        updated = entry.findtext(ATOM + "updated", "")
        if not title or not link:
            continue
        built = _build_item(title, link, desc, updated, feed)
        if built:
            items.append(built)

    return items


def fetch_fl_orders():
    """Парсит заказы с fl.ru. Ищет только ИИ-заказы и сайты."""
    items = []
    seen_titles = {}
    errors = []
    keywords = [
        # ИИ
        "нейросети", "искусственный интеллект", "нейросеть", "gpt", "chatgpt",
        "промт", "prompt", "машинное обучение", "llm", "ai агент", "ai-агент",
        "нейрофото", "нейроарт", "генерация изображений", "midjourney",
        "обучение модели", "датасет", "разметка данных", "computer vision",
        "распознавание", "ии", "ai видео", "ai озвучка", "ai аватар",
        "автоматизация", "парсинг", "чат-бот", "telegram бот",
        # Сайты (без требования ИИ)
        "сайт", "лендинг", "верстка", "html", "wordpress", "тильда", "битрикс",
        "интернет-магазин", "доработка сайта", "frontend", "web приложение",
    ]

    for kw in keywords:
        try:
            url = f"https://www.fl.ru/rss/projects.xml?category=all&search={quote(kw)}"
            xml = fetch_url(url).decode("utf-8", errors="replace")
            root = ElementTree.fromstring(xml)
            for item in root.iter("item"):
                title = unescape(item.findtext("title", "")).strip()
                link = item.findtext("link", "").strip()
                desc = unescape(item.findtext("description", "")).strip()
                pubdate = item.findtext("pubDate", "")

                if not title:
                    continue

                title_norm = title.lower().strip()
                if seen_titles.get(title_norm, 0) >= 1:
                    continue
                seen_titles[title_norm] = seen_titles.get(title_norm, 0) + 1

                # Отсекаем всё, что не про ИИ и не про сайты
                if not is_ai_order(title, desc):
                    continue

                if link:
                    items.append({
                        "title": title,
                        "link": link,
                        "desc": clean_desc(desc),
                        "date": parse_date(pubdate),
                        "source": "FL.ru",
                        "cat": "orders",
                        "order_type": classify_order(title, desc),
                        "lang": detect_lang(title + " " + desc),
                    })
        except Exception as e:
            errors.append(f"{kw}: {e}")
    if errors:
        print(f"  ! FL.ru: не ответил на {len(errors)} из {len(keywords)} запросов")
        for err in errors[:3]:
            print(f"      {err}")
    print(f"  -> {len(items)} заказов с FL.ru")
    return items


def fetch_hh_vacancies():
    """Парсит вакансии с hh.ru через RSS. Ищет AI/ML/нейросети."""
    items = []
    keywords = ["искусственный интеллект", "нейросети", "машинное обучение",
                "ai engineer", "data scientist", "gpt", "llm", "prompt engineer"]
    seen_links = set()
    seen_titles = {}  # title -> count

    for kw in keywords:
        try:
            url = f"https://hh.ru/search/vacancy/rss?text={quote(kw)}&area=113"
            xml = fetch_url(url).decode("utf-8", errors="replace")
            root = ElementTree.fromstring(xml)
            for item in root.iter("item"):
                title = unescape(item.findtext("title", "")).strip()
                link = item.findtext("link", "").strip()
                desc = unescape(item.findtext("description", "")).strip()
                pubdate = item.findtext("pubDate", "")

                if not title:
                    continue

                # Отбрасываем курсы/обучения, вебинары
                skip_words = ["курс", "обучение", "школа", "интенсив", "вебинар",
                              "тренинг", "марафон", "академия", "университет",
                              "course", "training", "bootcamp"]
                text_lower = (title + " " + desc).lower()
                if any(w in text_lower for w in skip_words):
                    continue

                # Отбрасываем нерелевантные вакансии
                if not is_real_ai_job(title, desc):
                    continue

                # Дедубликация: одинаковый заголовок не более 1 раза
                title_norm = title.lower().strip()
                if seen_titles.get(title_norm, 0) >= 1:
                    continue
                seen_titles[title_norm] = seen_titles.get(title_norm, 0) + 1

                if link and link not in seen_links:
                    seen_links.add(link)
                    items.append({
                        "title": title,
                        "link": link,
                        "desc": clean_desc(desc),
                        "date": parse_date(pubdate),
                        "source": "hh.ru",
                        "cat": "jobs",
                        "job_type": classify_job(title, desc),
                        "lang": detect_lang(title + " " + desc),
                    })
        except Exception as e:
            print(f"  ! hh.ru ({kw}): {e}")
    print(f"  -> {len(items)} вакансий с hh.ru")
    return items


def fetch_trudvsem_vacancies():
    """Парсит вакансии через API Работа России."""
    items = []
    seen = set()
    now = now_msk().strftime("%Y-%m-%d")
    keywords = ["искусственный интеллект", "нейросети", "машинное обучение"]

    for kw in keywords:
        try:
            url = f"https://opendata.trudvsem.ru/api/v1/vacancies?text={quote(kw)}&limit=50"
            data = fetch_url(url).decode("utf-8", errors="replace")
            parsed = json.loads(data)
            vacancies = parsed.get("results", {}).get("vacancies", [])
            for v in vacancies:
                vdata = v.get("vacancy", {})
                title = vdata.get("title", "")
                if isinstance(title, dict):
                    title = title.get("$", "") or str(title)
                link = vdata.get("vac_url", "")
                desc_raw = vdata.get("requirement", "")
                if isinstance(desc_raw, dict):
                    desc_raw = desc_raw.get("$", "") or str(desc_raw)
                duty_raw = vdata.get("duty", "")
                if isinstance(duty_raw, dict):
                    duty_raw = duty_raw.get("$", "") or str(duty_raw)
                desc = str(desc_raw) + " " + str(duty_raw)
                date_str = vdata.get("creation_date", "")[:10]

                if not title or not title.strip():
                    continue

                skip_words = ["курс", "обучение", "школа", "интенсив", "вебинар",
                              "тренинг", "марафон", "академия", "университет"]
                if any(w in (title + desc).lower() for w in skip_words):
                    continue

                if not is_real_ai_job(title, desc):
                    continue

                if link and link not in seen:
                    seen.add(link)
                    items.append({
                        "title": title,
                        "link": link,
                        "desc": clean_desc(desc),
                        "date": date_str or now,
                        "source": "Работа России",
                        "cat": "jobs",
                        "job_type": classify_job(title, desc),
                        "lang": detect_lang(title + " " + desc),
                    })
        except Exception as e:
            print(f"  ! trudvsem ({kw}): {e}")
    print(f"  -> {len(items)} вакансий с Работа России")
    return items
