"""Сборка HTML.

Всё, что попадает на сайт, пишется в docs/. Это единственный выход проекта —
раньше файлы лежали и в корне, и в dist/, и было непонятно, что из них
настоящее. Ручные страницы (about/) лежат отдельно и просто копируются.
"""

import os
import shutil

from .config import (
    ABOUT_DIR, CATEGORIES, DOCS_DIR, SITE_FOOTER, SITE_ICON, SITE_NAME,
    SITE_TAGLINE, SITE_TITLE, TEMPLATE_PATH,
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

footer { color: var(--text2); font-size: 0.85rem; padding: 30px 0; text-align: center; }
"""


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
    for k in CATEGORIES:
        html = html.replace(f"%%ACT_{k}%%", "active" if k == cat_key else "")
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
<div class="cat-count">{counts[k]} новостей</div>
</a>
'''

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{SITE_TITLE}</title>
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

  <nav class="cat-grid">
{cards}  </nav>

  <footer>
    {SITE_FOOTER} · <a href="about/index.html" style="color:var(--text2)">ℹ️ О проекте</a>
  </footer>
</div>
<script>
document.getElementById('lastUpdated').textContent =
    'Обновлено: {build_time} (МСК)' + ' · всего {total} новостей';
</script>
</body>
</html>"""
    write_if_changed(os.path.join(DOCS_DIR, "index.html"), html)
    active = len([k for k, v in counts.items() if v > 0])
    print(f"  [OK] Главная страница — {total} новостей по {active} категориям")


def copy_static():
    """Копирует ручные страницы (about/) в готовый сайт."""
    if os.path.isdir(ABOUT_DIR):
        shutil.copytree(ABOUT_DIR, os.path.join(DOCS_DIR, "about"), dirs_exist_ok=True)
