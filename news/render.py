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
from html import escape as html_escape
from urllib.parse import urlsplit
from xml.sax.saxutils import escape as xml_escape

from .config import (
    ABOUT_DIR, BASE_DIR, CATEGORIES, CATEGORY_DESCRIPTIONS, DOCS_DIR,
    MAX_AGE_DAYS, OG_IMAGE, SITE_DESCRIPTION, SITE_FOOTER, SITE_ICON, SITE_NAME,
    SITE_TAGLINE, SITE_TITLE, SITE_URL, TEMPLATE_PATH,
)
from .store import write_if_changed
from .util import now_msk, safe_link

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
  position: relative;
  display: block;
  overflow: hidden;
  /* Подложка — тот же цвет рубрики, но полупрозрачный. Готовый светлый
     оттенок пришлось бы задавать отдельно для тёмной темы, а rgba поверх
     фона работает в обеих. Составляющие цвета приходят из --accent-rgb. */
  background:
    linear-gradient(150deg, rgba(var(--accent-rgb), .13), rgba(var(--accent-rgb), 0) 62%),
    var(--card-bg);
  border: 1.5px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  text-decoration: none;
  color: var(--text);
  box-shadow: var(--shadow);
  transition: transform .15s ease, box-shadow .15s ease;
}
/* Полоска сверху: рубрики различаются не только значком, и цвет видно
   боковым зрением, не читая подпись. */
.cat-card::before {
  content: "";
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--accent), rgba(var(--accent-rgb), 0));
}
.cat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,.12);
  border-color: var(--accent);
}
.cat-emoji {
  font-size: 1.8rem;
  width: 52px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  background: rgba(var(--accent-rgb), .13);
  margin-bottom: 12px;
  line-height: 1;
}
.cat-name {
  font-size: 1.1rem;
  font-weight: 600;
  line-height: 1.3;
}
/* Счётчик — плашка, а не серая строка: число новостей это то, ради чего
   в рубрику и заходят. Цвет текста оставлен основным: акцентные оттенки
   вроде оранжевого на белом дают слишком слабый контраст. */
.cat-count {
  display: inline-block;
  font-size: .78rem;
  font-weight: 600;
  color: var(--text);
  background: rgba(var(--accent-rgb), .15);
  border-radius: 20px;
  padding: 2px 10px;
  margin-top: 8px;
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
.search-results[hidden], #hub[hidden] { display: none; }
.sr-item {
  display: block; background: var(--card-bg); border: 1.5px solid var(--border);
  border-radius: 12px; padding: 12px 16px; text-decoration: none; color: var(--text);
  box-shadow: var(--shadow); transition: border-color .15s ease, transform .15s ease;
}
.sr-item:hover { border-color: var(--accent); transform: translateY(-1px); }
.sr-title { font-size: .95rem; font-weight: 600; line-height: 1.4; }
.sr-meta { font-size: .75rem; color: var(--text2); margin-top: 3px; }
.sr-desc { font-size: .85rem; color: var(--text2); margin-top: 6px; line-height: 1.5; }

/* --- Тикер свежего --------------------------------------------------------
   Полоса заголовков едет справа налево. Дорожка внутри продублирована
   скриптом, поэтому сдвиг ровно на -50% стыкуется без рывка: половина
   дорожки — это ровно одна копия. Ширина ячейки включает разделитель
   (он нарисован через ::after), иначе копии были бы разной длины. */
.ticker {
  margin-top: 20px;
  padding: 10px 0;
  overflow: hidden;
  background: var(--card-bg);
  border: 1.5px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow);
}
/* Маска гасит края: заголовок не обрезается рамкой, а уходит в прозрачность. */
.ticker-clip {
  overflow: hidden;
  -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 28px, #000 calc(100% - 28px), transparent 100%);
  mask-image: linear-gradient(90deg, transparent 0, #000 28px, #000 calc(100% - 28px), transparent 100%);
}
.ticker-track { display: flex; width: max-content; }
.ticker-track.ready { animation: ticker-run 90s linear infinite; }
.ticker:hover .ticker-track.ready { animation-play-state: paused; }
@keyframes ticker-run {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); }
}
.ticker-cell { display: inline-flex; align-items: center; white-space: nowrap; }
.ticker-cell::after { content: "·"; color: var(--text2); margin: 0 14px 0 28px; }
.ticker-cell a {
  display: inline-flex; align-items: baseline; gap: 7px;
  font-size: .85rem; color: var(--text); text-decoration: none;
}
.ticker-cell a:hover { color: var(--accent); }
.ticker-cat { font-size: .95rem; }
/* Кому движение мешает — полоса просто стоит и прокручивается рукой. */
@media (prefers-reduced-motion: reduce) {
  .ticker { overflow-x: auto; }
  .ticker-clip { overflow-x: auto; -webkit-mask-image: none; mask-image: none; }
  .ticker-track.ready { animation: none; }
}

/* --- Главное за сутки -----------------------------------------------------
   Слева свежая новость крупно, справа четыре к ней. Блок собран из чужого
   текста, поэтому заголовки и описания приходят сюда уже экранированными,
   а ссылки — прошедшими проверку схемы (см. _esc и safe_link). */
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 14px;
  margin-top: 20px;
}
.hero-main {
  position: relative;
  display: flex; flex-direction: column;
  padding: 24px 24px 20px;
  border: 1.5px solid var(--border);
  border-radius: 16px;
  background:
    linear-gradient(150deg, rgba(var(--accent-rgb), .16), rgba(var(--accent-rgb), .02) 58%),
    var(--card-bg);
  box-shadow: var(--shadow);
  color: var(--text); text-decoration: none;
  transition: border-color .15s ease, box-shadow .15s ease;
}
.hero-main::before {
  content: "";
  position: absolute; top: 0; left: 0; right: 0; height: 4px;
  border-radius: 16px 16px 0 0;
  background: linear-gradient(90deg, var(--accent), rgba(var(--accent-rgb), 0));
}
.hero-main:hover { border-color: var(--accent); box-shadow: 0 8px 24px rgba(0,0,0,.13); }
.hero-badge {
  align-self: flex-start;
  font-size: .75rem; font-weight: 600;
  color: var(--text); background: rgba(var(--accent-rgb), .16);
  border-radius: 20px; padding: 3px 12px;
}
.hero-title { font-size: 1.45rem; font-weight: 700; line-height: 1.3; margin-top: 14px; }
.hero-main:hover .hero-title { color: var(--accent); }
.hero-desc { margin-top: 12px; font-size: .95rem; line-height: 1.6; color: var(--text2); }
.hero-meta { margin-top: auto; padding-top: 18px; font-size: .8rem; color: var(--text2); }
.hero-go { color: var(--accent); font-weight: 600; }
.hero-side { display: flex; flex-direction: column; gap: 8px; }
.hero-item {
  display: block; flex: 1;
  padding: 11px 14px;
  background: var(--card-bg);
  border: 1.5px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow);
  color: var(--text); text-decoration: none;
  transition: border-color .15s ease, transform .15s ease;
}
.hero-item:hover { border-color: var(--accent); transform: translateX(2px); }
.hero-item .t { font-size: .9rem; font-weight: 600; line-height: 1.4; }
.hero-item .m { margin-top: 5px; font-size: .75rem; color: var(--text2); }
.hero-dot {
  display: inline-block; width: 7px; height: 7px;
  border-radius: 50%; margin-right: 7px; vertical-align: middle;
}
@media (max-width: 820px) {
  .hero { grid-template-columns: 1fr; }
  .hero-title { font-size: 1.2rem; }
  .hero-main { padding: 20px 18px 16px; }
}

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
// Прячем весь хаб (тикер, акцентный блок и рубрики), а не одну сетку:
// иначе выдача оказалась бы под ними, за пределами экрана.
var hubEl = document.getElementById('hub');

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
  hubEl.hidden = false;
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

  hubEl.hidden = true;
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
  hubEl.hidden = true;
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

# Тикер: дорожка дублируется в браузере, а не в разметке. Две копии в HTML —
# это два одинаковых заголовка для поисковика; копия в скрипте такого не даёт.
# Число копий всегда чётное: анимация сдвигает дорожку ровно на половину её
# ширины, и при нечётном числе копий на стыке был бы рывок.
# Скрипт не сработал — полоса просто стоит и прокручивается рукой.
TICKER_JS = """
var track = document.getElementById('tickerTrack');
if (track && track.children.length) {
  var base = track.offsetWidth;
  if (base > 0) {
    var copies = 2;
    while (base * copies < window.innerWidth * 2 && copies < 8) copies += 2;
    var markup = track.innerHTML;
    for (var i = 1; i < copies; i++) track.insertAdjacentHTML('beforeend', markup);
    track.classList.add('ready');
  }
}
"""

# --- Главная страница: что и сколько показываем ---------------------------
# Тикер — «живая лента» под шапкой. Каждая строка — чужой заголовок, поэтому
# останавливаемся на двенадцати: полоса успевает пройти круг за полторы минуты
# и не превращается в бесконечную простыню.
TICKER_LIMIT = 12
# Главная новость и четыре к ней. Больше на один экран не влезает, а список
# начинает выглядеть обычным архивом — для этого ниже есть рубрики.
HERO_LIMIT = 5
# Описание под главным заголовком. Полное (до 300 знаков) раздувает блок,
# а о чём материал, понятно уже по первым фразам.
HERO_DESC_LIMIT = 220
# Вакансии и заказы в главный блок не берём: это объявление, а не новость дня.
# В тикере они остаются — там лента общая, как и на страницах рубрик.
HERO_SKIP_CATS = frozenset({"jobs", "orders"})
# Сколько записей с одного сайта пускаем на первый экран. Без этого его
# занимает одна лента: 18.09.2026 из двенадцати свежих русских записей
# одиннадцать были с habr.com. Ограничение по домену, а не по имени
# источника: у habr.com их четыре — «Habr AI», «Habr AI Новости», «Habr ML»
# и «Habr Дизайн», — и как разные источники они и дают перекос.
TICKER_PER_HOST = 2
HERO_PER_HOST = 2


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


def _esc(value):
    """Чужой текст для разметки главной страницы.

    Заголовок, название источника и описание приезжают из чужих лент.
    На странице рубрики их экранирует браузерный esc(), а главная собирается
    в Python — значит, экранировать надо здесь, до подстановки в HTML.
    """
    return html_escape("" if value is None else str(value), quote=True)


def _fmt_date(date_str):
    """«2026-09-15» -> «15.09.2026»; сегодняшняя и вчерашняя — словами.

    Свежесть важнее точной даты: «сегодня» читается сразу, а «18.09.2026»
    ещё надо сравнить с сегодняшним числом.
    """
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return ""
    today = now_msk().date()
    if day == today:
        return "сегодня"
    if day == today - timedelta(days=1):
        return "вчера"
    return day.strftime("%d.%m.%Y")


def _short(text, limit):
    """Обрезает чужой текст по границе слова, а не по середине."""
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:.—-") + "…"


def _meta(*parts):
    """«vc.ru · вчера» — без пустых кусков и висячих разделителей.

    Экранирует сама: строка собирается из чужого текста, и полагаться на то,
    что каждый вызов не забудет _esc, тут не стоит.
    """
    return " · ".join(_esc(p) for p in parts if p)


def _accent_rgb(color):
    """«#0071e3» -> «0,113,227».

    Нужно, чтобы покрасить подложку карточки в её же цвет с прозрачностью.
    Готовый светлый оттенок пришлось бы задавать дважды — для светлой темы
    и для тёмной, — а rgba поверх фона работает в обеих.
    """
    h = (color or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    except ValueError:
        return "0,113,227"


def _host(link):
    """Домен ссылки: «habr.com», «vc.ru» — без www.

    Нужен, чтобы ограничить однообразие первого экрана. Четыре ленты Habr —
    это один сайт, и считать их разными источниками значит пустить его
    занять всю главную. Пустая строка вместо домена ограничение не ломает:
    такие записи просто считаются одной группой.
    """
    try:
        host = urlsplit(link).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def _fresh(all_news, limit, skip_cats=frozenset(), only_ru=False, per_host=None):
    """Свежие записи, готовые к показу: с заголовком и рабочей ссылкой.

    all_news уже отсортирован по дате (шаг 4 сборки), поэтому своей сортировки
    здесь нет: порядок на сайте обязан совпадать с порядком в накопителе.

    per_host — сколько записей одного сайта допустимо в отобранном. Это
    жёсткий предел, а не пожелание: список короче ожидаемого лучше, чем
    первый экран из одной ленты.
    """
    picked = []
    by_host = {}
    for n in all_news:
        if n.get("cat") in skip_cats:
            continue
        if only_ru and n.get("lang") != "ru":
            continue
        if not (n.get("title") or "").strip():
            continue
        link = safe_link(n.get("link"))
        if not link:
            continue
        host = _host(link)
        if per_host is not None and by_host.get(host, 0) >= per_host:
            continue
        by_host[host] = by_host.get(host, 0) + 1
        picked.append(n)
        if len(picked) >= limit:
            break
    return picked


def _prefer_ru(items, all_news, limit, skip_cats=frozenset(), per_host=None):
    """Сначала русские записи, англоязычные — только если своих не хватило.

    Страницы рубрик открываются с фильтром «Русский»: сайт русскоязычный,
    и англоязычный заголовок на первом экране главной из него выбивается.
    Но прятать такие записи совсем нельзя — у Hacker News бывают свежие
    материалы, которых ещё нет в русских лентах. Поэтому добор, а не запрет.
    """
    if len(items) >= limit:
        return items
    links = {safe_link(n.get("link")) for n in items}
    for n in _fresh(all_news, limit * 3, skip_cats, per_host=per_host):
        link = safe_link(n.get("link"))
        if link in links:
            continue
        links.add(link)
        items.append(n)
        if len(items) >= limit:
            break
    return items


def _ticker_html(all_news):
    """Полоса свежих заголовков. Пустая строка — показывать нечего."""
    items = _prefer_ru(_fresh(all_news, TICKER_LIMIT, only_ru=True,
                              per_host=TICKER_PER_HOST),
                       all_news, TICKER_LIMIT, per_host=TICKER_PER_HOST)
    if not items:
        return ""
    cells = ""
    for n in items:
        cat = CATEGORIES.get(n.get("cat"), {})
        cells += (
            '<span class="ticker-cell">'
            f'<a href="{_esc(safe_link(n["link"]))}" target="_blank" rel="noopener">'
            f'<span class="ticker-cat">{cat.get("emoji", "")}</span>'
            f'{_esc(n.get("title"))}'
            "</a></span>"
        )
    return (
        '<div class="ticker" aria-label="Последние заголовки">'
        '<div class="ticker-clip">'
        f'<div class="ticker-track" id="tickerTrack">{cells}</div>'
        "</div></div>\n"
    )


def _hero_html(all_news):
    """Акцентный блок: главная новость крупно и четыре к ней.

    Если новостей нет вовсе (например, архив занят одними вакансиями),
    блок не рисуется: пустая рамка на первом экране хуже, чем её отсутствие.
    """
    items = _prefer_ru(_fresh(all_news, HERO_LIMIT, HERO_SKIP_CATS, only_ru=True,
                              per_host=HERO_PER_HOST),
                       all_news, HERO_LIMIT, HERO_SKIP_CATS, per_host=HERO_PER_HOST)
    if not items:
        return ""
    main, side = items[0], items[1:]

    cat = CATEGORIES.get(main.get("cat"), {})
    accent = cat.get("accent", "#0071e3")
    badge = f'{cat.get("emoji", "")} {cat.get("label", "")}'.strip()
    desc = _short(main.get("desc"), HERO_DESC_LIMIT)
    desc_html = f'<div class="hero-desc">{_esc(desc)}</div>' if desc else ""
    meta = _meta(main.get("source"), _fmt_date(main.get("date")))

    side_html = ""
    for n in side:
        c = CATEGORIES.get(n.get("cat"), {})
        side_html += (
            f'<a class="hero-item" href="{_esc(safe_link(n["link"]))}"'
            ' target="_blank" rel="noopener">'
            f'<div class="t">{_esc(n.get("title"))}</div>'
            '<div class="m">'
            f'<span class="hero-dot" style="background:{c.get("accent", "#0071e3")}"></span>'
            f'{_meta(c.get("label"), n.get("source"), _fmt_date(n.get("date")))}'
            "</div></a>\n"
        )

    return (
        '<section class="hero">\n'
        f'<a class="hero-main" style="--accent:{accent};'
        f'--accent-rgb:{_accent_rgb(accent)}" href="{_esc(safe_link(main["link"]))}"'
        ' target="_blank" rel="noopener">\n'
        f'<span class="hero-badge">{_esc(badge)}</span>\n'
        f'<div class="hero-title">{_esc(main.get("title"))}</div>\n'
        f'{desc_html}\n'
        f'<div class="hero-meta">{meta + " · " if meta else ""}'
        '<span class="hero-go">Читать в источнике →</span></div>\n'
        "</a>\n"
        f'<div class="hero-side">\n{side_html}</div>\n'
        "</section>\n"
    )


def _category_cards(counts):
    """Карточки рубрик.

    Цвет рубрики уезжает в две переменные: сам цвет и его составляющие —
    из второй собирается полупрозрачная подложка.
    """
    cards = ""
    for k, cat in CATEGORIES.items():
        cards += (
            f'<a href="{k}/index.html" class="cat-card" '
            f'style="--accent:{cat["accent"]};--accent-rgb:{_accent_rgb(cat["accent"])}">\n'
            f'<div class="cat-emoji">{cat["emoji"]}</div>\n'
            f'<div class="cat-name">{cat["label"]}</div>\n'
            f'<div class="cat-count">{_plural(counts[k], "новость", "новости", "новостей")}</div>\n'
            "</a>\n"
        )
    return cards


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
    """Главная страница: поиск, свежее, главное за сутки и рубрики.

    Порядок блоков не случаен. Сверху поиск — единственный способ попасть
    вглубь архива. Ниже «хаб»: тикер свежего, акцентный блок и сетка рубрик.
    При поиске хаб скрывается целиком, а выдача встаёт на его место: иначе
    результаты оказались бы под свёрстанными блоками, за пределами экрана.
    """
    counts = {k: 0 for k in CATEGORIES}
    for n in all_news:
        if n["cat"] in counts:
            counts[n["cat"]] += 1
    total = len(all_news)
    build_time = now_msk().strftime("%d.%m.%Y, %H:%M:%S")
    # Время сборки подставляем текстом, а не скриптом: число записей должно
    # склоняться («1 запись», «2 записи»), а склонять в браузере — лишний код.
    updated = (f"Обновлено: {build_time} (МСК) · всего "
               f"{_plural(total, 'запись', 'записи', 'записей')}")

    cards = _category_cards(counts)
    ticker = _ticker_html(all_news)
    hero = _hero_html(all_news)
    ticker_js = f"<script>\n{TICKER_JS}</script>\n" if ticker else ""

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
    <div id="lastUpdated">{updated}</div>
  </header>

  <div class="search-wrap">
    <input type="search" id="q" autocomplete="off" aria-label="Поиск по архиву"
           placeholder="🔍 Поиск по архиву — {_plural(total, 'запись', 'записи', 'записей')} за {MAX_AGE_DAYS} дней">
    <div class="search-info" id="searchInfo"></div>
    <div class="search-results" id="searchResults" hidden></div>
  </div>

  <div id="hub">
{ticker}{hero}  <nav class="cat-grid">
{cards}  </nav>
  </div>

  <footer>
    {SITE_FOOTER} · <a href="about/index.html" style="color:var(--text2)">ℹ️ О проекте</a> · <a href="rss.xml" style="color:var(--text2)">📡 RSS</a>
  </footer>
</div>
{ticker_js}<script>
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
