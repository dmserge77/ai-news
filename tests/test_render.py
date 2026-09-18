"""Тесты сборки страниц и служебных файлов сайта.

Проверяем то, что уезжает посетителю и поисковику: карту сайта, robots,
свою ленту и метки предпросмотра ссылки. Здесь же — сторож на подстановки
шаблона и сверка формулировок, которые живут отдельно от сайта.
"""

import os
import re
import struct
import unittest
import xml.etree.ElementTree as ET
from datetime import timedelta
from unittest import mock

from news import render
from news.config import (
    CATEGORIES, CATEGORY_DESCRIPTIONS, OG_IMAGE, SITE_NAME, SITE_TAGLINE,
    SITE_URL,
)
from news.util import now_msk

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(BASE_DIR, "_category_template.html")
OG_SCRIPT = os.path.join(BASE_DIR, "make_og_image.py")
OG_IMAGE_PATH = os.path.join(BASE_DIR, "og-image.png")


def render_captured(func, *args, **kwargs):
    """Вызывает сборщик, перехватывая запись файлов.

    Функции пишут прямо в docs/, а тестам туда нельзя: это рабочий каталог
    сайта. Подменяем запись и смотрим, что собиралось.
    """
    captured = {}

    def fake_write(path, content):
        captured[os.path.basename(path)] = content

    with mock.patch("news.render.write_if_changed", fake_write):
        func(*args, **kwargs)
    return captured


class TestSitemap(unittest.TestCase):
    def setUp(self):
        self.files = render_captured(render.generate_sitemap)
        self.xml = self.files.get("sitemap.xml", "")

    def test_file_created(self):
        self.assertTrue(self.xml)

    def test_is_valid_xml(self):
        root = ET.fromstring(self.xml)
        self.assertTrue(root.tag.endswith("urlset"))

    def test_all_categories_present(self):
        for key in CATEGORIES:
            self.assertIn(f"{SITE_URL}/{key}/", self.xml,
                          f"рубрики {key} нет в карте сайта")

    def test_main_and_about_present(self):
        self.assertIn(f"<loc>{SITE_URL}/</loc>", self.xml)
        self.assertIn(f"<loc>{SITE_URL}/about/</loc>", self.xml)

    def test_addresses_are_absolute(self):
        """Относительный адрес в карте сайта бесполезен: робот не знает базы."""
        for loc in re.findall(r"<loc>(.*?)</loc>", self.xml):
            self.assertTrue(loc.startswith("https://"), f"не абсолютный адрес: {loc}")


class TestRobots(unittest.TestCase):
    def setUp(self):
        self.files = render_captured(render.generate_robots)
        self.txt = self.files.get("robots.txt", "")

    def test_allows_crawling(self):
        self.assertIn("User-agent: *", self.txt)
        self.assertIn("Allow: /", self.txt)

    def test_points_to_sitemap(self):
        self.assertIn(f"Sitemap: {SITE_URL}/sitemap.xml", self.txt)


class TestRssFeed(unittest.TestCase):
    def setUp(self):
        self.news = [
            {"title": "OpenAI выпустила GPT-5", "link": "https://example.com/a",
             "desc": "Новая модель", "date": "2026-09-15", "source": "Тест",
             "cat": "ai"},
            {"title": "Модель <b>с тегом</b> и & амперсандом",
             "link": "https://example.com/b", "desc": "Описание <script>",
             "date": "2026-09-14", "source": "Тест", "cat": "ai"},
        ]
        self.files = render_captured(render.generate_rss, self.news)
        self.xml = self.files.get("rss.xml", "")

    def test_is_valid_xml(self):
        ET.fromstring(self.xml)

    def test_items_present(self):
        root = ET.fromstring(self.xml)
        items = root.findall("./channel/item")
        self.assertEqual(len(items), 2)

    def test_channel_metadata(self):
        root = ET.fromstring(self.xml)
        channel = root.find("./channel")
        self.assertEqual(channel.findtext("title"), SITE_NAME)
        self.assertTrue(channel.findtext("link").startswith("https://"))

    def test_foreign_text_is_escaped(self):
        """Тег и амперсанд в чужом заголовке не должны ломать ленту.

        Это та же ошибка, что была в HTML, только в XML: `<` в заголовке
        разваливает документ, и лента перестаёт читаться целиком.
        """
        root = ET.fromstring(self.xml)
        titles = [i.findtext("title") for i in root.findall("./channel/item")]
        self.assertIn("Модель <b>с тегом</b> и & амперсандом", titles)

    def test_link_present_for_every_item(self):
        root = ET.fromstring(self.xml)
        for item in root.findall("./channel/item"):
            self.assertTrue(item.findtext("link", "").startswith("https://"))

    def test_limit_respected(self):
        many = [dict(self.news[0], link=f"https://example.com/{i}") for i in range(80)]
        files = render_captured(render.generate_rss, many, 50)
        root = ET.fromstring(files["rss.xml"])
        self.assertEqual(len(root.findall("./channel/item")), 50)

    def test_bad_link_does_not_break_feed(self):
        """Запись без нормальной ссылки в ленту не попадает."""
        news = self.news + [{"title": "Мусор", "link": "", "desc": "", "date": "2026-09-15",
                             "source": "Тест", "cat": "ai"}]
        files = render_captured(render.generate_rss, news)
        root = ET.fromstring(files["rss.xml"])
        self.assertEqual(len(root.findall("./channel/item")), 2)


class TestCategoryPage(unittest.TestCase):
    def setUp(self):
        self.files = render_captured(render.generate_category_page, "ai", CATEGORIES["ai"])
        self.html = self.files.get("index.html", "")

    def test_no_leftover_placeholders(self):
        """Незаменённая подстановка уехала бы на сайт текстом."""
        self.assertFalse(re.findall(r"%%[A-Z_]+%%", self.html),
                         "в готовой странице остались подстановки шаблона")

    def test_title_present(self):
        self.assertIn("<title>", self.html)

    def test_og_tags_present(self):
        for tag in ("og:title", "og:description", "og:url", "og:image", "twitter:card"):
            self.assertIn(tag, self.html, f"нет метки {tag}")

    def test_og_image_is_absolute(self):
        self.assertIn(OG_IMAGE, self.html)

    def test_og_url_points_to_category(self):
        self.assertIn(f"{SITE_URL}/ai/", self.html)

    def test_category_description_is_own(self):
        """У каждой рубрики своё описание, а не общий текст."""
        self.assertIn(CATEGORY_DESCRIPTIONS["ai"], self.html)

    def test_all_categories_have_description(self):
        for key in CATEGORIES:
            self.assertIn(key, CATEGORY_DESCRIPTIONS,
                          f"у рубрики {key} нет описания")

    def test_rss_link_present(self):
        self.assertIn('type="application/rss+xml"', self.html)


class TestSearchIndex(unittest.TestCase):
    """Индекс поиска: файл, который читает браузер посетителя."""

    def setUp(self):
        self.news = [
            {"title": "OpenAI выпустила GPT-5", "link": "https://example.com/a",
             "desc": "Новая модель", "date": "2026-09-15", "source": "vc.ru",
             "cat": "ai"},
            {"title": "Старое", "link": "https://example.com/b", "desc": "",
             "date": "2026-08-01", "source": "Habr", "cat": "vibe"},
        ]
        self.files = render_captured(render.generate_search_index, self.news)
        self.raw = self.files.get("search-index.json", "")

    def test_file_created(self):
        self.assertTrue(self.raw)

    def test_is_valid_json(self):
        import json
        self.assertIsInstance(json.loads(self.raw), list)

    def test_newest_first(self):
        import json
        rows = json.loads(self.raw)
        self.assertEqual(rows[0]["title"], "OpenAI выпустила GPT-5")

    def test_all_fields_present(self):
        import json
        row = json.loads(self.raw)[0]
        for field in ("title", "link", "date", "source", "cat", "desc"):
            self.assertIn(field, row, f"в индексе нет поля {field}")

    def test_record_without_link_dropped(self):
        """Строка без ссылки в выдаче никуда не ведёт — ей не место в индексе."""
        import json
        news = self.news + [{"title": "Без ссылки", "link": "", "desc": "",
                             "date": "2026-09-15", "source": "Тест", "cat": "ai"}]
        files = render_captured(render.generate_search_index, news)
        rows = json.loads(files["search-index.json"])
        self.assertEqual(len(rows), 2)
        self.assertNotIn("Без ссылки", [r["title"] for r in rows])

    def test_desc_is_trimmed(self):
        """Длинное описание режется: иначе индекс распухает вдвое."""
        import json
        long_desc = "слово " * 100
        news = [dict(self.news[0], desc=long_desc)]
        files = render_captured(render.generate_search_index, news)
        row = json.loads(files["search-index.json"])[0]
        self.assertLessEqual(len(row["desc"]), render.SEARCH_DESC_LIMIT + 1)

    def test_empty_archive_gives_empty_array(self):
        import json
        files = render_captured(render.generate_search_index, [])
        self.assertEqual(json.loads(files["search-index.json"]), [])

    def test_long_desc_does_not_inflate_index(self):
        """Обрезка описаний — предохранитель от распухания файла.

        Индекс читает браузер посетителя, и он не должен расти вместе с длиной
        чужих описаний. Считаем прирост на запись: без обрезки 1160 знаков
        описания дали бы больше 2000 байт на запись, с обрезкой — около 200.
        """
        count = 200
        short = [{"title": "Новость", "link": f"https://example.com/{i}",
                  "desc": "кратко", "date": "2026-09-15", "source": "vc.ru",
                  "cat": "ai"} for i in range(count)]
        long_desc = [dict(x, desc="очень длинное описание новости " * 40) for x in short]
        a = len(render_captured(render.generate_search_index, short)["search-index.json"].encode())
        b = len(render_captured(render.generate_search_index, long_desc)["search-index.json"].encode())
        growth = (b - a) / count
        self.assertLess(growth, 250,
                        f"на запись прибавилось {growth:.0f} байт — обрезка не работает")

    def test_one_record_per_line(self):
        """Одна запись — одна строка: так дифф в git остаётся читаемым."""
        lines = [ln for ln in self.raw.splitlines() if ln.strip().startswith("{")]
        self.assertEqual(len(lines), 2)


class TestMainPage(unittest.TestCase):
    def setUp(self):
        self.files = render_captured(render.generate_main_page, [])
        self.html = self.files.get("index.html", "")

    def test_og_tags_present(self):
        for tag in ("og:title", "og:description", "og:url", "og:image"):
            self.assertIn(tag, self.html, f"нет метки {tag}")

    def test_rss_link_present(self):
        self.assertIn("rss.xml", self.html)

    def test_search_field_present(self):
        self.assertIn('id="q"', self.html)
        self.assertIn('id="searchResults"', self.html)

    def test_search_loads_index(self):
        self.assertIn("search-index.json", self.html)

    def test_cat_labels_substituted(self):
        """Подписи рубрик подставляются данными, а не остаются заготовкой."""
        self.assertNotIn("__CAT_LABELS__", self.html)
        self.assertIn(CATEGORIES["ai"]["label"], self.html)

    def test_search_escapes_output(self):
        """Заголовок, источник и описание в выдаче обязаны проходить через esc().

        Строка собирается и вставляется через innerHTML — та же дверь, что была
        в карточках рубрик. Ссылка дополнительно проверяется на схему.
        """
        for call in ("esc(it.title)", "esc(it.source)", "esc(it.desc)",
                     "esc(safeUrl(it.link))"):
            self.assertIn(call, self.html, f"в выдаче нет {call}")


class TestMainPageVisual(unittest.TestCase):
    """Первый экран главной: тикер свежего, акцентный блок и карточки рубрик.

    Здесь проверяется то, что видит посетитель и чего не видит: чужой
    заголовок обязан приехать экранированным, ссылка — проверенной на схему,
    а один сайт не должен занимать весь первый экран.
    """

    def setUp(self):
        self.today = now_msk().strftime("%Y-%m-%d")
        self.news = [
            {"title": "Свежая новость про ИИ", "link": "https://habr.com/a",
             "desc": "Короткое описание", "date": self.today, "source": "Habr AI",
             "cat": "ai", "lang": "ru"},
            {"title": "Вторая новость", "link": "https://tproger.ru/b",
             "desc": "Описание", "date": self.today, "source": "Tproger",
             "cat": "ai", "lang": "ru"},
            {"title": "Третья новость", "link": "https://3dnews.ru/c",
             "desc": "", "date": self.today, "source": "3DNews",
             "cat": "platform", "lang": "ru"},
            {"title": "Ищем ML-инженера", "link": "https://hh.ru/v",
             "desc": "", "date": self.today, "source": "hh.ru",
             "cat": "jobs", "lang": "ru"},
        ]
        self.files = render_captured(render.generate_main_page, self.news)
        self.html = self.files.get("index.html", "")
        self.hero = self.html.split('<section class="hero">')[1].split("</section>")[0] \
            if '<section class="hero">' in self.html else ""

    def test_hub_wraps_browse_blocks(self):
        """Хаб — то, что скрывается при поиске, поэтому он должен быть один."""
        self.assertEqual(self.html.count('id="hub"'), 1)
        self.assertIn("hubEl.hidden = true", self.html)
        self.assertIn("hubEl.hidden = false", self.html)

    def test_ticker_present(self):
        self.assertIn('id="tickerTrack"', self.html)
        self.assertEqual(self.html.count('class="ticker-cell"'), 4,
                         "в тикере не все записи")

    def test_ticker_js_only_when_ticker_exists(self):
        """Скрипт без дорожки — обращение к null в браузере посетителя."""
        self.assertIn("getElementById('tickerTrack')", self.html)
        empty = render_captured(render.generate_main_page, [])
        self.assertNotIn("getElementById('tickerTrack')", empty["index.html"])

    def test_hero_present(self):
        self.assertIn('class="hero-main"', self.html)
        self.assertEqual(self.hero.count('class="hero-item"'), 2,
                         "рядом с главной новостью не четыре записи")

    def test_hero_skips_jobs_and_orders(self):
        """Вакансия в главном блоке — объявление на месте новости дня."""
        self.assertNotIn("Ищем ML-инженера", self.hero)

    def test_hero_absent_when_only_jobs(self):
        jobs = [n for n in self.news if n["cat"] == "jobs"]
        files = render_captured(render.generate_main_page, jobs)
        self.assertNotIn('<section class="hero">', files["index.html"])
        self.assertIn('id="hub"', files["index.html"])

    def test_foreign_title_is_escaped(self):
        """Тег в чужом заголовке — это разметка в браузере посетителя.

        Главная собирается в Python, а не в браузерном esc(), поэтому
        экранировать надо на сборке.
        """
        bad = [dict(self.news[0], title='<img src=x onerror="alert(1)">',
                    source="a & b")]
        files = render_captured(render.generate_main_page, bad)
        html = files["index.html"]
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)
        self.assertIn("a &amp; b", html)

    def test_unsafe_link_dropped(self):
        """Адрес вида javascript: выполнится по клику — такой записи не место."""
        bad = [dict(self.news[0], link="javascript:alert(1)")]
        files = render_captured(render.generate_main_page, bad)
        self.assertNotIn("javascript:alert", files["index.html"])

    def test_per_host_limit(self):
        """Один сайт не занимает первый экран.

        Четыре ленты Habr — это один сайт: как разные источники они дают
        перекос, и лечится он ограничением по домену, а не по имени ленты.
        """
        same = [dict(self.news[0], title=f"Новость {i}",
                     link=f"https://habr.com/{i}",
                     source=f"Habr {i}") for i in range(6)]
        files = render_captured(render.generate_main_page, same)
        html = files["index.html"]
        self.assertEqual(html.count('class="ticker-cell"'), render.TICKER_PER_HOST)
        self.assertEqual(html.count('class="hero-item"'), render.HERO_PER_HOST - 1)

    def test_today_is_a_word(self):
        """«сегодня» читается быстрее, чем дата, которую надо сравнивать."""
        self.assertIn("сегодня", self.html)

    def test_accent_rgb_substituted(self):
        """Без составляющих цвета подложка карточки осталась бы серой."""
        self.assertIn("--accent-rgb:0,113,227", self.html)

    def test_counts_are_pluralised(self):
        """«1 новость», а не «1 новостей» — в карточке рубрики и в подписи."""
        one = render_captured(render.generate_main_page, [self.news[0]])
        self.assertIn("1 новость", one["index.html"])
        self.assertIn("всего 1 запись", one["index.html"])


class TestMainPageHelpers(unittest.TestCase):
    """Мелкие помощники главной — на них держится разметка."""

    def test_short_cuts_at_word_boundary(self):
        text = "слово " * 20
        cut = render._short(text, 50)
        self.assertLessEqual(len(cut), 51)
        self.assertTrue(cut.endswith("…"))
        self.assertNotIn("сл…", cut, "обрезано по середине слова")

    def test_short_keeps_short_text(self):
        self.assertEqual(render._short("коротко", 100), "коротко")

    def test_short_survives_empty(self):
        self.assertEqual(render._short(None, 10), "")
        self.assertEqual(render._short("", 10), "")

    def test_meta_drops_empty_parts(self):
        self.assertEqual(render._meta("vc.ru", "", None, "вчера"), "vc.ru · вчера")
        self.assertEqual(render._meta("", ""), "")

    def test_meta_escapes(self):
        self.assertEqual(render._meta("<b>"), "&lt;b&gt;")

    def test_accent_rgb(self):
        self.assertEqual(render._accent_rgb("#0071e3"), "0,113,227")
        self.assertEqual(render._accent_rgb("#fff"), "255,255,255")
        self.assertEqual(render._accent_rgb("мусор"), "0,113,227")

    def test_host_groups_habr_feeds(self):
        """Четыре ленты Habr — один домен, и группировать надо по нему."""
        for link in ("https://habr.com/ru/news/1/", "https://habr.com/ru/companies/x/2/"):
            self.assertEqual(render._host(link), "habr.com")
        self.assertEqual(render._host("https://www.vc.ru/a"), "vc.ru")
        self.assertEqual(render._host(""), "")

    def test_fmt_date_words_and_date(self):
        today = now_msk()
        self.assertEqual(render._fmt_date(today.strftime("%Y-%m-%d")), "сегодня")
        self.assertEqual(
            render._fmt_date((today - timedelta(days=1)).strftime("%Y-%m-%d")), "вчера")
        self.assertEqual(render._fmt_date("2026-09-15"), "15.09.2026")
        self.assertEqual(render._fmt_date("не дата"), "")


class TestOgImage(unittest.TestCase):
    """Картинка предпросмотра: формат, размер и формулировки."""

    def test_file_exists(self):
        self.assertTrue(os.path.exists(OG_IMAGE_PATH),
                        "нет og-image.png — карточка предпросмотра будет пустой")

    def test_is_png_of_right_size(self):
        """Только растровая картинка и ровно 1200x630.

        SVG и data:-адреса в og:image не принимает ни Telegram, ни VK.
        Размер читаем прямо из заголовка PNG — без Pillow, которого в CI нет.
        """
        with open(OG_IMAGE_PATH, "rb") as f:
            head = f.read(24)
        self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n", "это не PNG")
        width, height = struct.unpack(">II", head[16:24])
        self.assertEqual((width, height), (1200, 630))

    def test_text_matches_site(self):
        """Подпись на картинке обязана совпадать с сайтом слово в слово.

        Текст на картинке запечён в пиксели и не меняется вместе со страницами:
        на сайте «шесть раз в день», на карточке «6 раз в сутки» — число одно,
        а заметит это человек, а не тест. Поэтому читаем константу из скрипта
        и сверяем с конфигом сайта.
        """
        with open(OG_SCRIPT, "r", encoding="utf-8") as f:
            src = f.read()
        m = re.search(r'^TAGLINE = "(.*?)"$', src, re.M)
        self.assertIsNotNone(m, "в make_og_image.py не нашлась константа TAGLINE")
        self.assertEqual(m.group(1), SITE_TAGLINE,
                         "подзаголовок на картинке разошёлся с сайтом")

    def test_image_script_is_marked_manual(self):
        """Скрипт картинки ручной и в сборку не входит — это надо фиксировать.

        Он требует Pillow, а в проекте правило: только стандартная библиотека.
        """
        with open(OG_SCRIPT, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("В СБОРКУ НЕ ВХОДИТ", src)


if __name__ == "__main__":
    unittest.main()
