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

from .config import DEAD_SOURCES, REMOTE_MARKERS, SPAM_FILTER_SOURCES
from .filters import (
    classify, classify_job, classify_misc, classify_order, is_ai_order,
    is_ai_relevant, is_real_ai_job, is_seo_spam,
)
from .util import (
    clean_desc, detect_lang, now_msk, parse_date, safe_link, strip_html,
)

ATOM = "{http://www.w3.org/2005/Atom}"

# Потолок на размер ответа ленты. Обычная лента — десятки-сотни килобайт,
# так что запас многократный. Нужен против гигантских ответов и XML-бомб:
# без него одна лента может съесть всю память сборки.
MAX_FEED_BYTES = 5 * 1024 * 1024


def fetch_url(url):
    """Скачивает адрес и возвращает байты.

    Сертификат проверяем по-настоящему. Раньше здесь стояли
    `check_hostname = False` и `verify_mode = CERT_NONE`, то есть шифрование
    было, а подлинность сервера не проверялась: содержимое ленты можно было
    подменить по пути. Проверено 16.09.2026 — все 36 лент и три кадровых
    источника проходят нормальную проверку, так что отключать её незачем.
    """
    ctx = ssl.create_default_context()
    # Кириллицу в URL (например, теги vc.ru вида /rss/tag/нейросети) urlopen
    # не умеет кодировать сам: падает 'ascii' codec can't encode.
    # quote безопасен для обычных адресов — он кодирует только не-ASCII.
    url = quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    with urlopen(req, timeout=15, context=ctx) as resp:
        data = resp.read(MAX_FEED_BYTES + 1)
    # Лента, которая отдаёт гигабайты, роняет сборку по памяти. Заодно это
    # защита от XML-бомбы: раздутый документ до разбора просто не доедет.
    if len(data) > MAX_FEED_BYTES:
        raise ValueError(f"ответ больше {MAX_FEED_BYTES} байт — отброшен")
    return data


def _build_item(title, link, desc, date_raw, feed):
    """Превращает запись ленты в карточку новости. None — если не подходит.

    Логика одна и та же для RSS (item) и Atom (entry), поэтому живёт здесь,
    а не дублируется в двух ветках разбора.
    """
    # Заголовок и ссылка идут на страницу как есть, поэтому чистим их здесь,
    # на входе: тег в заголовке — это исполняемый код у посетителя, а
    # `javascript:` в ссылке сработает по клику. Это второй эшелон защиты,
    # первый — экранирование в шаблоне страницы.
    title = strip_html(title)
    link = safe_link(link)
    if not title or not link:
        return None

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


def count_raw(xml_text):
    """Сколько записей в ленте всего — до всех фильтров.

    Нужно, чтобы отличать «лента пуста» от «лента жива, но ничего не прошло
    фильтр». Это разные поломки: первая значит, что источник умер, вторая —
    что он просто не по нашей теме. Вызывается только когда после фильтра
    записей не осталось, поэтому лишнего разбора XML не бывает.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return 0
    return len(list(root.iter("item"))) + len(list(root.iter(ATOM + "entry")))


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
                title = strip_html(unescape(item.findtext("title", "")))
                link = safe_link(item.findtext("link", ""))
                desc = unescape(item.findtext("description", "")).strip()
                pubdate = item.findtext("pubDate", "")

                if not title or not link:
                    continue

                title_norm = title.lower().strip()
                if seen_titles.get(title_norm, 0) >= 1:
                    continue
                seen_titles[title_norm] = seen_titles.get(title_norm, 0) + 1

                # Отсекаем всё, что не про ИИ и не про сайты
                if not is_ai_order(title, desc):
                    continue

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
    """Парсит вакансии с hh.ru через RSS. Только удалённые AI/ML-вакансии.

    schedule=remote — это фильтр самого hh.ru: в ленте остаются только
    вакансии с удалённым форматом работы. Проверено вживую: по запросу
    «промпт-инженер» лента без фильтра отдаёт 18 записей, с фильтром — 11,
    и это строгое подмножество. Параметр work_format=REMOTE даёт ровно тот же
    набор. Параметр area= такой фильтрации не даёт (area=1 возвращал и Москву,
    и Саратов), поэтому регион задаём только как «вся Россия» — area=113.

    Формат работы в RSS не пишется, поэтому в is_real_ai_job передаём
    remote_confirmed=True — иначе мы бы выбросили вообще все вакансии hh.ru.
    """
    items = []
    keywords = ["искусственный интеллект", "нейросети", "машинное обучение",
                "ai engineer", "data scientist", "gpt", "llm", "prompt engineer"]
    seen_links = set()
    seen_titles = {}  # title -> count

    for kw in keywords:
        try:
            url = (f"https://hh.ru/search/vacancy/rss?text={quote(kw)}"
                   f"&area=113&schedule=remote")
            xml = fetch_url(url).decode("utf-8", errors="replace")
            root = ElementTree.fromstring(xml)
            for item in root.iter("item"):
                title = strip_html(unescape(item.findtext("title", "")))
                link = safe_link(item.findtext("link", ""))
                desc = unescape(item.findtext("description", "")).strip()
                pubdate = item.findtext("pubDate", "")

                if not title or not link:
                    continue

                # Курсы и обучения отсекает is_real_ai_job (шаг 4).
                if not is_real_ai_job(title, desc, remote_confirmed=True):
                    continue

                # Дедубликация: одинаковый заголовок не более 1 раза
                title_norm = title.lower().strip()
                if seen_titles.get(title_norm, 0) >= 1:
                    continue
                seen_titles[title_norm] = seen_titles.get(title_norm, 0) + 1

                if link in seen_links:
                    continue
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


def _field(record, key, sub=None):
    """Достаёт строку из поля API. Значение приходит и строкой, и словарём."""
    value = record.get(key)
    if sub and isinstance(value, dict):
        value = value.get(sub)
    if isinstance(value, dict):
        value = value.get("$", "") or str(value)
    return str(value or "")


def parse_trudvsem(vacancies):
    """Разбирает список вакансий из ответа API «Работа России».

    Вынесено в отдельную функцию, чтобы проверялось тестом без сети: имена
    полей здесь неочевидные — `job-name` вместо `title` и `creation-date`
    вместо `creation_date`. Однажды из-за этого рубрика молча осталась пустой:
    заголовок выходил пустым, запись отбрасывалась, а в логах было чисто.
    Источник выглядел работающим, но не давал ничего.

    Возвращает (items, skipped_office): карточки и счётчик отброшенных
    не-удалённых вакансий.
    """
    items = []
    skipped_office = 0
    now = now_msk().strftime("%Y-%m-%d")

    for v in vacancies:
        vdata = v.get("vacancy", {})
        title = strip_html(_field(vdata, "job-name"))
        link = safe_link(vdata.get("vac_url", ""))
        if not title or not link:
            continue

        # Формат работы сообщает само API — верим ему, а не тексту.
        employment = _field(vdata, "employment").lower()
        if not any(w in employment for w in REMOTE_MARKERS):
            skipped_office += 1
            continue

        # duty — это описание вакансии. Поле requirement словарное
        # ({education, experience}), в текст карточки его не кладём.
        duty = _field(vdata, "duty")
        company = _field(vdata, "company", "name")
        region = _field(vdata, "region", "name")
        desc = ". ".join(p for p in (company, region, duty) if p)

        # Курсы и обучения отсекает is_real_ai_job (шаг 4).
        if not is_real_ai_job(title, desc, remote_confirmed=True):
            continue

        items.append({
            "title": title,
            "link": link,
            "desc": clean_desc(desc),
            "date": _field(vdata, "creation-date")[:10] or now,
            "source": "Работа России",
            "cat": "jobs",
            "job_type": classify_job(title, desc),
            "lang": detect_lang(title + " " + desc),
        })

    return items, skipped_office


def fetch_trudvsem_vacancies():
    """Читает вакансии через API «Работа России». Только удалённые и про ИИ.

    Формат работы отдаётся отдельным полем `employment` — например
    «Дистанционная (удаленная) работа». Это такой же надёжный источник, как
    schedule=remote у hh.ru, поэтому в is_real_ai_job уходит
    remote_confirmed=True: искать удалёнку в тексте не нужно.
    """
    items = []
    seen = set()
    keywords = ["искусственный интеллект", "нейросети", "машинное обучение"]
    skipped_office = 0

    for kw in keywords:
        try:
            url = (f"https://opendata.trudvsem.ru/api/v1/vacancies"
                   f"?text={quote(kw)}&limit=50")
            data = fetch_url(url).decode("utf-8", errors="replace")
            parsed = json.loads(data)
            vacancies = parsed.get("results", {}).get("vacancies", [])
            found, skipped = parse_trudvsem(vacancies)
            skipped_office += skipped
            for item in found:
                if item["link"] in seen:
                    continue
                seen.add(item["link"])
                items.append(item)
        except Exception as e:
            print(f"  ! trudvsem ({kw}): {e}")
    if skipped_office:
        print(f"  (не удалённых пропущено: {skipped_office})")
    print(f"  -> {len(items)} вакансий с Работа России")
    return items
