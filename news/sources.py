"""Реестр RSS-лент.

Добавить источник = добавить одну строку сюда. Больше нигде править не нужно.
Поля:
    url    — адрес ленты
    cat    — рубрика по умолчанию (раскладка всё равно уточняется по тексту)
    source — название издания, как оно будет показано в карточке
"""

FEEDS = [
    # --- Англоязычные ---
    {"url": "https://hnrss.org/frontpage", "cat": "ai", "source": "Hacker News"},
    {"url": "https://lobste.rs/rss", "cat": "ai", "source": "Lobsters"},
    {"url": "https://github.blog/feed/", "cat": "vibe", "source": "GitHub Blog"},
    {"url": "https://github.blog/category/engineering/feed/", "cat": "vibe", "source": "GitHub Eng"},
    {"url": "https://blog.replit.com/feed.xml", "cat": "vibe", "source": "Replit"},
    {"url": "https://huggingface.co/blog/feed.xml", "cat": "platform", "source": "Hugging Face"},
    {"url": "https://vercel.com/blog/feed.xml", "cat": "platform", "source": "Vercel"},
    {"url": "https://blog.railway.app/rss.xml", "cat": "platform", "source": "Railway"},
    # --- Русскоязычные: ИИ и ML ---
    {"url": "https://habr.com/ru/rss/hub/artificial_intelligence/?fl=ru", "cat": "ai", "source": "Habr AI"},
    {"url": "https://habr.com/ru/rss/hub/machine_learning/?fl=ru", "cat": "ai", "source": "Habr ML"},
    {"url": "https://habr.com/ru/rss/hubs/artificial_intelligence/news/?fl=ru", "cat": "ai", "source": "Habr AI Новости"},
    {"url": "https://habr.com/ru/rss/hubs/machine_learning/news/?fl=ru", "cat": "ai", "source": "Habr ML Новости"},
    {"url": "https://habr.com/ru/rss/hub/natural_language_processing/?fl=ru", "cat": "ai", "source": "Habr NLP"},
    {"url": "https://habr.com/ru/rss/hub/bigdata/?fl=ru", "cat": "platform", "source": "Habr Big Data"},
    {"url": "https://habr.com/ru/rss/hub/python/?fl=ru", "cat": "vibe", "source": "Habr Python"},
    {"url": "https://habr.com/ru/rss/hub/open_source/?fl=ru", "cat": "platform", "source": "Habr Open Source"},
    {"url": "https://habr.com/ru/rss/hub/devops/?fl=ru", "cat": "platform", "source": "Habr DevOps"},
    {"url": "https://habr.com/ru/rss/hub/api/?fl=ru", "cat": "platform", "source": "Habr API"},
    {"url": "https://habr.com/ru/rss/hubs/cloud_computing/?fl=ru", "cat": "platform", "source": "Habr Облака"},
    {"url": "https://habr.com/ru/rss/hub/freelance/?fl=ru", "cat": "misc", "source": "Habr Фриланс"},
    {"url": "https://tproger.ru/feed/", "cat": "vibe", "source": "Tproger"},
    {"url": "https://thecode.media/feed/", "cat": "platform", "source": "The Code"},
    {"url": "https://www.kaspersky.ru/blog/feed/", "cat": "platform", "source": "Kaspersky"},
    # ComNews не подключать НИКОГДА: отдаёт по 1 записи и она не про ИИ.
    {"url": "https://te-st.org/feed/", "cat": "platform", "source": "Теплица соцтех"},
    {"url": "https://dtf.ru/rss/", "cat": "misc", "source": "DTF"},
    {"url": "https://rb.ru/feeds/all/", "cat": "misc", "source": "Rusbase"},
    # vc.ru — только ИИ-теги: общая лента тащит бизнес, маркетинг и личные истории,
    # которые фильтр «про ИИ» всё равно не пропустит. Теги дают чистый материал.
    {"url": "https://vc.ru/rss/tag/ai", "cat": "ai", "source": "vc.ru"},
    {"url": "https://vc.ru/rss/tag/нейросети", "cat": "ai", "source": "vc.ru"},
    # ТАСС Наука убран: это научпоп не про ИИ (рачки, ITER, чёрные дыры),
    # он не проходил фильтр и оседал мусором в разных рубриках.
    # --- Русскоязычные: техно-медиа (проходят фильтр по ИИ) ---
    {"url": "https://3dnews.ru/news/rss/", "cat": "misc", "source": "3DNews"},
    {"url": "https://hi-tech.mail.ru/rss/all/", "cat": "misc", "source": "Hi-Tech Mail"},
    # --- Дизайн ---
    {"url": "https://habr.com/ru/rss/hubs/web_design/articles/?fl=ru", "cat": "design", "source": "Habr Веб-дизайн"},
    {"url": "https://habr.com/ru/rss/hubs/web_design/news/?fl=ru", "cat": "design", "source": "Habr Веб-дизайн"},
    {"url": "https://habr.com/ru/rss/hub/design/?fl=ru", "cat": "design", "source": "Habr Дизайн"},
    {"url": "https://www.smashingmagazine.com/feed/", "cat": "design", "source": "Smashing Magazine"},
    {"url": "https://uxdesign.cc/feed", "cat": "design", "source": "UX Collective"},
    {"url": "https://www.awwwards.com/feed/", "cat": "design", "source": "Awwwards"},
]
