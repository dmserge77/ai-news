"""Правила отбора: что считаем новостью про ИИ, что мусором, что вакансией.

Все функции здесь чистые — на вход текст, на выход решение. Ничего не пишут
и не ходят в сеть, поэтому их удобно проверять тестами (tests/test_filters.py).
"""

import re

from .config import (
    AI_NAMES, AI_NAMES_WORD, AI_STRONG, CATEGORIES, CAT_KEYWORDS, CURIO_MARKERS,
    FALSE_POSITIVES, JOB_AI_MARKERS, JOB_AI_SHORT, JOB_TYPES, NO_AI_CHECK,
    REMOTE_MARKERS, SEO_SPAM, SITE_MARKERS,
)
from .util import detect_lang


def is_seo_spam(title):
    """Рекламный пост-заглушка в ИИ-теге (актуально для vc.ru)."""
    t = (title or "").lower().strip()
    if not t:
        return True
    return any(w in t for w in SEO_SPAM)


def has_ai_signal(text):
    """Есть ли в тексте явный признак темы ИИ."""
    t = text.lower()
    if any(w in t for w in AI_STRONG):
        return True
    if any(w in t for w in AI_NAMES):
        # Короткие имена проверяем отдельным словом, чтобы не ловить домены
        # и обычные слова (wisellama.rocks, "sora" в чужом слове).
        for w in AI_NAMES_WORD:
            if w not in t:
                continue
            if re.search(r"(?<![a-zа-я0-9])" + re.escape(w) + r"(?![a-zа-я0-9])", t):
                return True
        # Если ни одно короткое имя не подтвердилось отдельным словом,
        # проверяем остальные имена обычным вхождением.
        if any(w in t for w in AI_NAMES if w not in AI_NAMES_WORD):
            return True
    # "AI" отдельным словом, а не внутри "mail", "said", "captain".
    # Исключение: перечисление графических форматов (svg, ai, pdf, eps) —
    # там "ai" это Adobe Illustrator, а не искусственный интеллект.
    if re.search(r"(?<![a-z])ai(?![a-z])", t):
        if re.search(r"(svg|eps|png|jpg|pdf|cdr|dxf)\s*,\s*ai\b", t):
            return False
        if re.search(r"\bai\s*,\s*(pdf|eps|svg|cdr|dxf|png)", t):
            return False
        return True
    return False


def is_ai_relevant(text, cat):
    """Пропускает только материалы про ИИ. Вакансии и заказы не проверяются."""
    if cat in NO_AI_CHECK:
        return True
    if cat not in CATEGORIES:
        return False
    t = text.lower()
    if any(w in t for w in FALSE_POSITIVES):
        return False
    return has_ai_signal(t)


def classify(text, default_cat):
    """Определяет рубрику по ключевым словам.

    Если ничего не подошло, но материал всё равно про ИИ — отдаём в «Солянку».
    Если и ИИ нет — возвращаем None, новость не берём.
    """
    text = text.lower()
    scores = {cat: 0 for cat in CATEGORIES}
    for cat, keywords in CAT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    if has_ai_signal(text):
        return "misc"
    return None


def classify_job(title, desc):
    """Определяет подкатегорию вакансии."""
    text = (title + " " + desc).lower()
    # Сначала проверяем AI-разработку (она приоритетнее)
    if any(w in text for w in JOB_TYPES["ai_dev"]["kw"]):
        return "ai_dev"
    for key, cat in JOB_TYPES.items():
        if key == "ai_dev":
            continue
        if any(w in text for w in cat["kw"]):
            return key
    return "ai_dev"  # fallback


def is_ai_job_theme(text):
    """Есть ли в вакансии настоящий признак ИИ или ML.

    Отдельная проверка нужна потому, что поиск по тексту на hh.ru нечёткий:
    по запросу «машинное обучение» лента вернула «Дизайнер машинной вышивки
    Wilcom» — вышивальную машину, а не искусственный интеллект. Технического
    слова в заголовке («разработчик», «инженер», «дизайнер») для рубрики мало.
    """
    t = text.lower()
    if any(w in t for w in JOB_AI_MARKERS):
        return True
    for w in JOB_AI_SHORT:
        if re.search(r"(?<![a-zа-я0-9])" + re.escape(w) + r"(?![a-zа-я0-9])", t):
            return True
    return False


def is_real_ai_job(title, desc, remote_confirmed=False):
    """Проверяет, что это релевантная онлайн/удалённая AI-вакансия.

    Правило заказчика: только удалённая работа и только по-русски. «Заумные»
    англоязычные вакансии и работа у работодателя в офисе не нужны.

    remote_confirmed=True значит, что источник уже отфильтровал вакансии по
    формату работы — так делают hh.ru (лента с schedule=remote) и «Работа
    России» (поле employment). В этом случае проверять формат по тексту
    нельзя: hh.ru в RSS его не пишет вовсе (см. REMOTE_MARKERS).
    """
    text = (title + " " + desc).lower()

    # 1. Язык. Кириллицы нет вовсе — вакансия англоязычная, не берём.
    if detect_lang(title + " " + desc) == "en":
        return False

    # 2. Формат работы. Если источник сам не отфильтровал — требуем, чтобы
    #    удалёнка была названа в тексте.
    if not remote_confirmed and not any(w in text for w in REMOTE_MARKERS):
        return False

    # 3. Блок-лист профессий: не AI-направление, хотя слова вроде «нейросети»
    #    в тексте попадаться могут.
    block = ["продавец", "кассир", "грузчик", "мерчендайзер", "уборщик", "водитель",
             "курьер", "кладовщик", "официант", "бармен", "администратор",
             "продавец-консультант", "охранник", "упаковщик", "комплектовщик",
             "сортировщик", "фасовщик", "пекарь", "повар", "швея",
             "продаж", "менеджер по продаж", "менеджер по работе", "account manager",
             "менеджер", "sales", "маркетолог", "marketing", "директолог",
             "seo", "smm", "таргетолог", "копирайтер", "контент", "content",
             "hr", "hr-", "рекрутер", "recruiter"]
    if any(w in text for w in block):
        return False

    # 4. Блокируем обучение/курсы/стажировки — это не вакансии
    edu = ["курс", "обучение", "школа", "интенсив", "вебинар", "тренинг",
           "марафон", "академия", "университет", "course", "training",
           "bootcamp", "internship", "стажировка", "студент", "junior",
           "без опыта", "без опыта работы", "practice", "стажер"]
    if any(w in text for w in edu):
        return False

    # 5. Вакансия должна быть про ИИ или ML. Одного технического слова мало:
    #    поиск hh.ru нечёткий и подсовывает посторонние профессии.
    return is_ai_job_theme(text)


def classify_order(title, desc):
    """Определяет подкатегорию заказа. Сайты идут первыми — с ИИ или без."""
    text = (title + " " + desc).lower()
    if any(w in text for w in SITE_MARKERS):
        return "sites"
    if any(w in text for w in ["промт", "prompt", "промпт", "промт-инжинир",
                                "prompt engineering", "prompt engineer",
                                "chatgpt prompt", "gpt prompt", "текст для нейросет"]):
        return "prompts"
    if any(w in text for w in ["озвуч", "voice over", "voiceover", "дубляж",
                                "липсинк", "lip sync", "lipsync", "подкаст",
                                "аудио", "звук", "музык", "вокал", "синтез речи",
                                "tts", "speech", "клонирован голос", "клонировать голос",
                                "видео", "ролик", "рилс", "reels", "shorts", "шортс",
                                "монтаж", "видеомонтаж", "анимац", "аватар"]):
        return "audio"
    if any(w in text for w in ["нейрофото", "нейрокартинк", "генерац изображен",
                                "генерац картин", "сгенерировать изображен",
                                "иллюстрац", "изображен", "картинк", "баннер",
                                "арт", "midjourney", "stable diffusion", "dall-e",
                                "flux", "обрисовать", "ретуш", "фото", "фотограф"]):
        return "media"
    if any(w in text for w in ["автоматизац", "парсинг", "парсер", "скрипт",
                                "бот", "telegram-бот", "телеграм-бот", "чат-бот",
                                "chatbot", "интеграц", "api", "выгрузк", "спарсить",
                                "собрать данные", "excel", "таблиц", "google sheets"]):
        return "automate"
    return "ai"


def is_ai_order(title, desc):
    """Заказ проходит, если он про ИИ ИЛИ про сайты (сайты — без требования ИИ)."""
    text = (title + " " + desc).lower()
    # Реклама, SEO, лидоген — не разработка, рубрике не подходят
    if any(w in text for w in ["директолог", "яндекс директ", "контекстн", "seo",
                                "сео", "лидген", "аффилиац", "таргет", "обзвон",
                                "посещаемост", "раскрутк", "продвижени"]):
        return False
    # Статьи и новости — не заказы (в заказы попадают только через FL.ru)
    if any(w in text for w in ["объявил", "объявила", "на днях", "в интервью",
                                "рассказал", "рассказала", "выяснил", "я фрилансер",
                                "как я ", "почему бизнес", "обнаружил", "написал свой"]):
        return False
    if any(w in text for w in SITE_MARKERS):
        return True
    if has_ai_signal(text):
        return True
    # Парсинг, боты и автоматизация — профильные темы рубрики
    return any(w in text for w in ["парсинг", "парсер", "спарсить", "автоматизац",
                                    "чат-бот", "chatbot", "telegram бот",
                                    "телеграм бот", "скрипт для", "бот для"])


def classify_misc(title, desc):
    """Определяет подкатегорию «Солянки»: курьёзы или всё остальное."""
    text = (title + " " + desc).lower()
    if any(w in text for w in CURIO_MARKERS):
        return "curio"
    return "raznoe"
