"""Правила отбора: что считаем новостью про ИИ, что мусором, что вакансией.

Все функции здесь чистые — на вход текст, на выход решение. Ничего не пишут
и не ходят в сеть, поэтому их удобно проверять тестами (tests/test_filters.py).
"""

import re

from .config import (
    AI_NAMES, AI_NAMES_WORD, AI_STRONG, CATEGORIES, CAT_KEYWORDS, CURIO_MARKERS,
    FALSE_POSITIVES, JOB_TYPES, NO_AI_CHECK, SEO_SPAM, SITE_MARKERS,
)


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


def is_real_ai_job(title, desc):
    """Проверяет, что это релевантная онлайн/удалённая AI-вакансия."""
    text = (title + " " + desc).lower()
    # Блок-лист профессий и офлайна
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

    # Блокируем обучение/курсы/стажировки
    edu = ["курс", "обучение", "школа", "интенсив", "вебинар", "тренинг",
           "марафон", "академия", "университет", "course", "training",
           "bootcamp", "internship", "стажировка", "студент", "junior",
           "без опыта", "без опыта работы", "practice", "стажер"]
    if any(w in text for w in edu):
        return False

    # Блокируем офлайн-локации
    office = ["офис", "работа в офисе", "г. ", "офлайн", "offline", "на месте",
              "в офисе", "работа на месте", "не удаленная", "полный день"]
    # Если есть офлайн-слова и нет удалёнки — отбрасываем
    has_office = any(w in text for w in office)
    has_remote = any(w in text for w in ["удален", "remote", "дистанц", "online",
                                          "онлайн", "гибрид", "hybrid", "дома"])
    if has_office and not has_remote:
        return False

    # Должны быть AI-слова или тех. скиллы
    ai_words = ["ai", "нейросет", "искусственный интеллект", "машинное обучение",
                "gpt", "llm", "deep learning", "data science", "prompt",
                "python", "tensorflow", "pytorch", "nlp", "computer vision",
                "нейрон", "чат-бот", "chatbot", "ai agent", "ml engineer"]
    if any(w in text for w in ai_words):
        return True

    tech_words = ["backend", "frontend", "разработчик", "программист", "developer",
                  "software", "qa", "тестировщик", "devops",
                  "data", "инженер", "engineer", "аналитик", "analyst",
                  "design", "дизайн", "ux", "ui", "figma"]
    return any(w in text for w in tech_words)


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
