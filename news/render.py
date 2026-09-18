"""Сборка HTML.

Всё, что попадает на сайт, пишется в docs/. Это единственный выход проекта —
раньше файлы лежали и в корне, и в dist/, и было непонятно, что из них
настоящее. Ручные страницы (about/) лежат отдельно и просто копируются.
"""

import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

from .config import (
    ABOUT_DIR, BASE_DIR, CATEGORIES, CATEGORY_DESCRIPTIONS, DOCS_DIR,
    MAX_AGE_DAYS, OG_IMAGE, SITE_DESCRIPTION, SITE_FOOTER, SITE_ICON, SITE_NAME,
    SITE_TAGLINE, SITE_TITLE, SITE_URL, TEMPLATE_PATH,
)
from .store import write_if_changed
from .util import now_msk

METRIKA_ID = "112543447"

METRIKA_SNIPPET = f"""<!-- Yandex.Metrika counter -->
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){{
        m[i]=m[i]||function(){{(m[i].a=m[i].a||[]).push(arguments)}};
        m[i].l=1*new Date();
        for (var j=0; j<document.scripts.length; j++) {{if (document.scripts[j].src === r) {{ return; }}}}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    }})(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id={METRIKA_ID}', 'ym');

    ym({METRIKA_ID}, 'init', {{ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true}});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/{METRIKA_ID}" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->"""

FAVICON = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
           f"<text y='.9em' font-size='90'>{SITE_ICON}</text></svg>")

MAIN_CSS = """
:root {
  --bg: #f5f5f7; --card-bg: #ffffff; --text: #1d1d1f;
  --text2: #6e6e73; --border: #e5e5ea; --accent: #0071e3;
  --shadow: 0 2px 12px rgba(0,0,0,0.08);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1c1c1e; --card-bg: #2c2c2e; --text: #f5f5f7;
    --text2: #98989d; --border: #3a3a3c; --shadow: 0 2px 12px rgba(0,0,0,0.3);
  }
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.5; padding: 20px;
}
.container { max-width: 1100px; margin: 0 auto; }

header {
  text-align: center;
  padding: 30px 0 20px;
}
header h1 {
  font-size: 2.5rem; font-weight: 700;
  background: linear-gradient(135deg, #0071e3, #5856d6);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}
header p { color: var(--text2); margin-top: 4px; font-size: 1.1rem; }
#lastUpdated { font-size: .85rem; color: var(--text2); margin-top: 4px; }

.cat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  margin-top: 24px;
}
.cat-card {
  display: block;
  background: var(--card-bg);
  border: 1.5px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  text-decoration: none;
  color: var(--text);
  box-shadow: var(--shadow);
  transition: transform .15s ease, box-shadow .15s ease;
}
.cat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,.12);
  border-color: var(--accent);
}
.cat-emoji {
  font-size: 2.2rem;
  margin-bottom: 12px;
  display: inline-block;
  line-height: 1;
}
.cat-name {
  font-size: 1.1rem;
  font-weight: 600;
  margin-top: 10px;
  line-height: 1.3;
}
.cat-count {
  font-size: .85rem;
  color: var(--text2);
  margin-top: 4px;
}
.cat-card:last-child {
  margin-bottom: 0;
}
.cat-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.cat-card:active {
  transform: translateY(0);
  box-shadow: 0 4px 12px rgba(0,0,0,.08);
}

.search-wrap { margin-top: 22px; }
#q {
  width: 100%; max-width: 560px; margin: 0 auto; display: block;
  padding: 12px 18px; font-size: 1rem; font-family: inherit;
  color: var(--text); background: var(--card-bg);
  border: 1.5px solid var(--border); border-radius: 24px;
  box-shadow: var(--shadow); outline: none;
  transition: border-color .15s ease;
}
#q:focus { border-color: var(--accent); }
#q::placeholder { color: var(--text2); }
.search-info { color: var(--text2); font-size: .85rem; text-align: center; margin-top: 10px; }
.search-results { margin-top: 18px; display: flex; flex-direction: column; gap: 8px; }
.search-results[hidden], .cat-grid[hidden] { display: none; }
.sr-item {
  display: block; background: var(--card-bg); border: 1.5px solid var(--border);
  border-radius: 12px; padding: 12px 16px; text-decoration: none; color: var(--text);
  box-shadow: var(--shadow); transition: border-color .15s ease, transform .15s ease;
}
.sr-item:hover { border-color: var(--accent); transform: translateY(-1px); }
.sr-title { font-size: .95rem; font-weight: 600; line-height: 1.4; }
.sr-meta { font-size: .75rem; color: var(--text2); margin-top: 3px; }
.sr-desc { font-size: .85rem; color: var(--text2); margin-top: 6px; line-height: 1.5; }

footer { color: var(--text2); font-size: 0.85rem; padding: 30px 0; text-align: center; }
"""

# Поиск по архиву работает в браузере посетителя: сервера у сайта нет.
# Файл search-index.json читается только когда посетитель начал вводить,
# поэтому на открытие главной он не влияет.
#
# esc() и safeUrl() здесь — копия того, что лежит в _category_template.html.
# Общего файла скриптов у сайта нет: страницы рубрик и главная собираются
# порознь, и связывать их ещё одним запросом ради двух функций не стоит.
# Если правишь одну копию — проверь вторую.
SEARCH_JS = """
var searchIndex = null, searchLoading = false, pendingTerm = '', searchTimer = null;
var SHOW_LIMIT = 50;
var CAT_LABELS = __CAT_LABELS__;
var qEl = document.getElementById('q');
var resEl = document.getElementById('searchResults');
var infoEl = document.getElementById('searchInfo');
var gridEl = document.querySelector('.cat-grid');

function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function safeUrl(u) {
  var s = String(u === null || u === undefined ? '' : u).trim();
  if (/[\\s"'<>\\\\]/.test(s)) return '#';
  return /^https?:\\/\\//i.test(s) ? s : '#';
}

// 2026-09-14 -> 14.09.2026
function fmtDate(s) {
  if (!s) return '';
  var p = String(s).split('-');
  return (p.length === 3) ? (p[2] + '.' + p[1] + '.' + p[0]) : s;
}

function searchReset() {
  pendingTerm = '';
  infoEl.textContent = '';
  resEl.hidden = true;
  resEl.innerHTML = '';
  gridEl.hidden = false;
}

function searchShow(term) {
  var words = term.split(/\\s+/).filter(Boolean);
  var hits = [];
  for (var i = 0; i < searchIndex.length; i++) {
    var n = searchIndex[i];
    var hay = ((n.title || '') + ' ' + (n.source || '') + ' ' + (n.desc || '')).toLowerCase();
    var ok = true;
    for (var j = 0; j < words.length; j++) {
      if (hay.indexOf(words[j]) === -1) { ok = false; break; }
    }
    if (ok) hits.push(n);
  }

  gridEl.hidden = true;
  resEl.hidden = false;

  if (!hits.length) {
    infoEl.textContent = 'Ничего не нашлось по запросу «' + term + '»';
    resEl.innerHTML = '';
    return;
  }
  infoEl.textContent = 'Найдено: ' + hits.length +
    (hits.length > SHOW_LIMIT ? ' · показаны первые ' + SHOW_LIMIT : '');

  var html = '';
  for (var k = 0; k < hits.length && k < SHOW_LIMIT; k++) {
    var it = hits[k];
    html += '<a class="sr-item" href="' + esc(safeUrl(it.link)) + '" target="_blank" rel="noopener">' +
      '<div class="sr-title">' + esc(it.title) + '</div>' +
      '<div class="sr-meta">' + esc(CAT_LABELS[it.cat] || it.cat || '') + ' · ' +
      esc(it.source) + ' · ' + esc(fmtDate(it.date)) + '</div>' +
      (it.desc ? '<div class="sr-desc">' + esc(it.desc) + '</div>' : '') +
      '</a>';
  }
  resEl.innerHTML = html;
}

function searchRun() {
  var term = qEl.value.trim().toLowerCase();
  if (term.length < 2) { searchReset(); return; }
  pendingTerm = term;
  if (searchIndex) { searchShow(term); return; }
  infoEl.textContent = 'Загружаю индекс…';
  resEl.hidden = true;
  gridEl.hidden = true;
  if (searchLoading) return;
  searchLoading = true;
  fetch('search-index.json')
    .then(function(r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function(data) {
      searchIndex = data;
      searchLoading = false;
      if (pendingTerm) searchShow(pendingTerm);
    })
    .catch(function() {
      searchLoading = false;
      infoEl.textContent = 'Поиск недоступен: индекс не загрузился';
    });
}

qEl.addEventListener('input', function() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchRun, 120);
});
qEl.addEventListener('search', searchRun);
"""


def _plural(n, one, few, many):
    """«1 запись», «2 записи», «5 записей».

    Мелочь, но она на главной странице: «1 новостей» в карточке рубрики
    читается как небрежность, и доверия к остальным числам меньше.
    """
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} {few}"
    return f"{n} {many}"


def _leftover_placeholders(html):
    """Подстановки вида %%ИМЯ%%, которые остались в готовой странице.

    Шаблон — ручной файл. Добавили в него %%OG_IMAGE%%, а замену в сборщике
    забыли — и этот текст увидит посетитель. Такое уже случалось в соседнем
    проекте. Лучше упасть на сборке, чем показывать людям %%ИМЯ%%.
    """
    return set(re.findall(r"%%[A-Z_]+%%", html))


def generate_category_page(cat_key, cat_info):
    """Генерируем index.html для конкретной рубрики из шаблона."""
    if not os.path.exists(TEMPLATE_PATH):
        print(f"  ! нет шаблона {TEMPLATE_PATH} — страница {cat_key} не собрана")
        return
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("%%SITE%%", SITE_NAME)
    html = html.replace("%%TAGLINE%%", SITE_TAGLINE)
    html = html.replace("%%ICON%%", FAVICON)
    html = html.replace("%%TITLE%%", cat_info["emoji"] + " " + cat_info["label"])
    html = html.replace("%%ACCENT%%", cat_info["accent"])
    # Своё описание у каждой рубрики: общий текст на всех — признак,
    # что рубрику завели, а описание забыли.
    html = html.replace("%%OG_DESC%%", CATEGORY_DESCRIPTIONS.get(cat_key, SITE_DESCRIPTION))
    html = html.replace("%%OG_URL%%", f"{SITE_URL}/{cat_key}/")
    html = html.replace("%%OG_IMAGE%%", OG_IMAGE)
    for k in CATEGORIES:
        html = html.replace(f"%%ACT_{k}%%", "active" if k == cat_key else "")
    # Незаменённая подстановка уехала бы на сайт текстом — лучше упасть здесь.
    left = _leftover_placeholders(html)
    if left:
        raise ValueError(f"в шаблоне остались подстановки: {sorted(left)}")
    write_if_changed(os.path.join(DOCS_DIR, cat_key, "index.html"), html)


def generate_main_page(all_news):
    """Генерируем главную страницу — хаб со ссылками и счётчиками рубрик."""
    counts = {k: 0 for k in CATEGORIES}
    for n in all_news:
        if n["cat"] in counts:
            counts[n["cat"]] += 1
    total = len(all_news)
    build_time = now_msk().strftime("%d.%m.%Y, %H:%M:%S")

    cards = ""
    for k, cat in CATEGORIES.items():
        cards += f'''<a href="{k}/index.html" class="cat-card" style="--accent:{cat['accent']}">
<div class="cat-emoji">{cat['emoji']}</div>
<div class="cat-name">{cat['label']}</div>
<div class="cat-count">{_plural(counts[k], "новость", "новости", "новостей")}</div>
</a>
'''

    # Подписи рубрик для выдачи поиска. Отдаём данными, а не кодом: список
    # рубрик живёт в конфиге, и второй его копии в скрипте быть не должно.
    cat_labels_js = json.dumps(
        {k: f"{v['emoji']} {v['label']}" for k, v in CATEGORIES.items()},
        ensure_ascii=False,
    )
    search_js = SEARCH_JS.replace("__CAT_LABELS__", cat_labels_js)

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{SITE_TITLE}</title>
<meta name="description" content="{SITE_DESCRIPTION}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="ru_RU">
<meta property="og:title" content="{SITE_TITLE}">
<meta property="og:description" content="{SITE_DESCRIPTION}">
<meta property="og:url" content="{SITE_URL}/">
<meta property="og:image" content="{OG_IMAGE}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{SITE_NAME} — {SITE_TAGLINE}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{SITE_TITLE}">
<meta name="twitter:description" content="{SITE_DESCRIPTION}">
<meta name="twitter:image" content="{OG_IMAGE}">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="rss.xml">
<link rel="icon" href="{FAVICON}">
{METRIKA_SNIPPET}
<style>{MAIN_CSS}</style>
</head>
<body>
<div class="container">
  <header>
    <h1>{SITE_NAME}</h1>
    <p>{SITE_TAGLINE}</p>
    <div id="lastUpdated"></div>
  </header>

  <div class="search-wrap">
    <input type="search" id="q" autocomplete="off" aria-label="Поиск по архиву"
           placeholder="🔍 Поиск по архиву — {_plural(total, 'запись', 'записи', 'записей')} за {MAX_AGE_DAYS} дней">
    <div class="search-info" id="searchInfo"></div>
    <div class="search-results" id="searchResults" hidden></div>
  </div>

  <nav class="cat-grid">
{cards}  </nav>

  <footer>
    {SITE_FOOTER} · <a href="about/index.html" style="color:var(--text2)">ℹ️ О проекте</a> · <a href="rss.xml" style="color:var(--text2)">📡 RSS</a>
  </footer>
</div>
<script>
document.getElementById('lastUpdated').textContent =
    'Обновлено: {build_time} (МСК)' + ' · всего {total} новостей';
</script>
<script>
{search_js}</script>
</body>
</html>"""
    write_if_changed(os.path.join(DOCS_DIR, "index.html"), html)
    active = len([k for k, v in counts.items() if v > 0])
    print(f"  [OK] Главная страница — {total} новостей по {active} категориям")


def copy_static():
    """Копирует ручные файлы в готовый сайт.

    `docs/` целиком генерируется и перезаписывается при каждой сборке,
    поэтому всё, что не собирается кодом, надо переносить сюда — иначе
    файл пропадёт с сайта при ближайшем прогоне.
    """
    if os.path.isdir(ABOUT_DIR):
        shutil.copytree(ABOUT_DIR, os.path.join(DOCS_DIR, "about"), dirs_exist_ok=True)
    # Картинка карточки предпросмотра. Исходник — в корне проекта, правится
    # скриптом make_og_image.py (ручной, в сборку не входит).
    og_src = os.path.join(BASE_DIR, "og-image.png")
    if os.path.exists(og_src):
        shutil.copy2(og_src, os.path.join(DOCS_DIR, "og-image.png"))


def generate_sitemap():
    """Карта сайта для поисковиков.

    Без неё робот обходит сайт по ссылкам: с главной он видит рубрики,
    а глубже уже ничего — перелинковки у нас нет. Карта сообщает все адреса
    разом, и рубрики индексируются не «когда-нибудь», а сразу.

    `lastmod` — дата сборки: содержимое рубрик меняется каждый прогон,
    а сам сайт собирается шесть раз в день.
    """
    today = now_msk().strftime("%Y-%m-%d")
    pages = [(f"{SITE_URL}/", "1.0", "hourly")]
    for key in CATEGORIES:
        pages.append((f"{SITE_URL}/{key}/", "0.8", "hourly"))
    pages.append((f"{SITE_URL}/about/", "0.3", "monthly"))

    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, priority, freq in pages:
        body += (f"  <url>\n"
                 f"    <loc>{loc}</loc>\n"
                 f"    <lastmod>{today}</lastmod>\n"
                 f"    <changefreq>{freq}</changefreq>\n"
                 f"    <priority>{priority}</priority>\n"
                 f"  </url>\n")
    body += "</urlset>\n"
    write_if_changed(os.path.join(DOCS_DIR, "sitemap.xml"), body)
    print(f"  [OK] Карта сайта — {len(pages)} адресов")


def generate_robots():
    """Разрешаем обход и указываем, где лежит карта сайта."""
    body = ("User-agent: *\n"
            "Allow: /\n"
            "\n"
            f"Sitemap: {SITE_URL}/sitemap.xml\n")
    write_if_changed(os.path.join(DOCS_DIR, "robots.txt"), body)
    print("  [OK] robots.txt")


def _rss_date(date_str):
    """Дата из архива (ГГГГ-ММ-ДД) в формат RFC 2822, как требует RSS."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError):
        return ""
    return format_datetime(dt.replace(tzinfo=timezone(timedelta(hours=3))))


def generate_rss(all_news, limit=50):
    """Своя лента новостей — чтобы на сайт можно было подписаться.

    Собираем чужие RSS шесть раз в день, а своей ленты у сайта не было.
    Отдаём самые свежие записи; описание берём то же, что видно в карточке,
    и всегда оставляем ссылку на источник. Чужие тексты мы не переписываем —
    это позиция проекта, а не техническое ограничение.

    Экранирование обязательно: заголовок и описание приходят из чужих лент,
    и символ `<` в них сломал бы XML. Ровно та же ошибка, что была в HTML,
    только в другом формате.
    """
    items = [n for n in all_news if n.get("title") and n.get("link")][:limit]

    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<rss version="2.0">\n<channel>\n'
    body += f"  <title>{xml_escape(SITE_NAME)}</title>\n"
    body += f"  <link>{SITE_URL}/</link>\n"
    body += f"  <description>{xml_escape(SITE_DESCRIPTION)}</description>\n"
    body += "  <language>ru</language>\n"
    body += f"  <lastBuildDate>{format_datetime(now_msk().replace(tzinfo=timezone(timedelta(hours=3))))}</lastBuildDate>\n"
    for n in items:
        body += "  <item>\n"
        body += f"    <title>{xml_escape(n.get('title', ''))}</title>\n"
        body += f"    <link>{xml_escape(n.get('link', ''))}</link>\n"
        body += f"    <guid isPermaLink=\"true\">{xml_escape(n.get('link', ''))}</guid>\n"
        desc = n.get("desc") or ""
        if desc:
            body += f"    <description>{xml_escape(desc)}</description>\n"
        body += f"    <category>{xml_escape(n.get('cat', ''))}</category>\n"
        pub = _rss_date(n.get("date", ""))
        if pub:
            body += f"    <pubDate>{pub}</pubDate>\n"
        body += f"    <source>{xml_escape(n.get('source', ''))}</source>\n"
        body += "  </item>\n"
    body += "</channel>\n</rss>\n"

    write_if_changed(os.path.join(DOCS_DIR, "rss.xml"), body)
    print(f"  [OK] Лента RSS — {len(items)} записей")


# Длина сниппета в поисковой выдаче. Полное описание (до 300 знаков) удвоило бы
# вес индекса, а в списке результатов всё равно видно только первые строки.
# Замер на архиве 18.09.2026 (1627 записей): без описаний 388 КБ, при 90 знаках
# 575 КБ, при 300 — около 850 КБ. Останавливаемся на 90: поиск по описанию
# сохраняется, а сжатый ответ остаётся в пределах 200 КБ.
SEARCH_DESC_LIMIT = 90

# Порог, после которого индекс пора разбивать по датам. Сейчас он читается
# целиком и один раз, но с ростом архива это перестанет быть безобидным.
SEARCH_INDEX_WARN_KB = 800


def _search_desc(desc):
    """Короткий сниппет для поисковой выдачи."""
    text = (desc or "").strip()
    if len(text) <= SEARCH_DESC_LIMIT:
        return text
    return text[:SEARCH_DESC_LIMIT].rstrip() + "…"


def generate_search_index(all_news):
    """Индекс для поиска по архиву — файл, который читает браузер посетителя.

    Сайт статический, сервера у него нет, искать по нему нечем: страница рубрики
    знает только свою рубрику, а главная — одни счётчики. Поэтому кладём рядом
    с главной один файл со всеми записями архива, а фильтрует его уже браузер.

    Файл читается только когда посетитель начал вводить запрос, так что на
    открытие страницы он не влияет. Записи без ссылки в индекс не попадают:
    такая строка в выдаче всё равно никуда не ведёт.

    Ключи короткие и в одну строку на запись — файл служебный, но дифф в git
    должен оставаться читаемым: индекс меняется при каждой сборке.
    """
    rows = []
    for n in sorted(all_news, key=lambda x: x.get("date", ""), reverse=True):
        title = (n.get("title") or "").strip()
        link = (n.get("link") or "").strip()
        if not title or not link:
            continue
        rows.append({
            "title": title,
            "link": link,
            "date": n.get("date", ""),
            "source": n.get("source", ""),
            "cat": n.get("cat", ""),
            "desc": _search_desc(n.get("desc")),
        })

    if not rows:
        body = "[]\n"
    else:
        body = "[\n" + ",\n".join(
            json.dumps(r, ensure_ascii=False) for r in rows
        ) + "\n]\n"
    write_if_changed(os.path.join(DOCS_DIR, "search-index.json"), body)
    size_kb = len(body.encode("utf-8")) // 1024
    print(f"  [OK] Индекс поиска — {len(rows)} записей, {size_kb} КБ")
    if size_kb > SEARCH_INDEX_WARN_KB:
        print(f"  ! индекс поиска вырос до {size_kb} КБ — пора разбивать его по датам")
