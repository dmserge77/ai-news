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
from unittest import mock

from news import render
from news.config import (
    CATEGORIES, CATEGORY_DESCRIPTIONS, OG_IMAGE, SITE_NAME, SITE_TAGLINE,
    SITE_URL,
)

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


class TestMainPage(unittest.TestCase):
    def setUp(self):
        self.files = render_captured(render.generate_main_page, [])
        self.html = self.files.get("index.html", "")

    def test_og_tags_present(self):
        for tag in ("og:title", "og:description", "og:url", "og:image"):
            self.assertIn(tag, self.html, f"нет метки {tag}")

    def test_rss_link_present(self):
        self.assertIn("rss.xml", self.html)


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
