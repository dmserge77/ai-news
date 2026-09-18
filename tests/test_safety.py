"""Тесты безопасности: чужой текст не должен выполняться у посетителя.

Проект публикует заголовки и ссылки из чужих лент. Пока они вставлялись
в страницу как есть, любой мог оформить заголовок тегом — и код выполнился бы
в браузере у каждого, кто открыл сайт. Здесь зафиксировано, что так больше
нельзя: ни на входе (fetch), ни на странице (шаблон рубрики).
"""

import os
import re
import ssl
import unittest
from unittest import mock

from news.fetch import MAX_FEED_BYTES, fetch_url, parse_rss, parse_trudvsem
from news.util import clean_desc, safe_link, strip_html

# Заголовок, которым ломают агрегаторы: браузер выполнит onerror,
# если строка попадёт в разметку без экранирования.
XSS_TITLE = '<img src=x onerror="alert(1)">'

RSS_WITH_XSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<item>
  <title>&lt;img src=x onerror="alert(1)"&gt; новая нейросеть</title>
  <link>https://example.com/a</link>
  <description>Про ИИ</description>
  <pubDate>Tue, 15 Sep 2026 10:00:00 +0300</pubDate>
</item>
<item>
  <title>Нейросеть с опасной ссылкой</title>
  <link>javascript:alert(document.cookie)</link>
  <description>Про ИИ</description>
  <pubDate>Tue, 15 Sep 2026 11:00:00 +0300</pubDate>
</item>
</channel>
</rss>"""

FEED = {"url": "https://example.com/rss", "cat": "ai", "source": "Пример"}

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "_category_template.html",
)


class TestStripHtml(unittest.TestCase):
    def test_tag_removed(self):
        self.assertEqual(strip_html("<b>Нейросеть</b>"), "Нейросеть")

    def test_script_tag_removed(self):
        self.assertEqual(strip_html("<script>alert(1)</script>"), "alert(1)")

    def test_xss_title_neutralised(self):
        """Заголовок с onerror не должен оставить ни одной угловой скобки."""
        result = strip_html(XSS_TITLE)
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)

    def test_tag_hidden_behind_entities_removed(self):
        """&lt;script&gt; после unescape становится тегом — его тоже убираем."""
        self.assertNotIn("<", strip_html("&lt;script&gt;alert(1)&lt;/script&gt;"))

    def test_long_title_not_truncated(self):
        """В отличие от clean_desc заголовок не режем — он должен остаться целиком."""
        long_title = "Нейросеть " * 60
        self.assertEqual(strip_html(long_title), long_title.strip())

    def test_plain_title_untouched(self):
        self.assertEqual(strip_html("OpenAI выпустила GPT-5"),
                         "OpenAI выпустила GPT-5")


class TestSafeLink(unittest.TestCase):
    def test_https_passes(self):
        self.assertEqual(safe_link("https://example.com/a"), "https://example.com/a")

    def test_http_passes(self):
        self.assertEqual(safe_link("http://example.com/a"), "http://example.com/a")

    def test_javascript_dropped(self):
        self.assertEqual(safe_link("javascript:alert(1)"), "")

    def test_data_url_dropped(self):
        self.assertEqual(safe_link("data:text/html,<script>alert(1)</script>"), "")

    def test_quote_in_link_dropped(self):
        """Ссылка не может вырваться из атрибута href."""
        self.assertEqual(safe_link('https://x/" onmouseover="alert(1)'), "")

    def test_space_in_link_dropped(self):
        self.assertEqual(safe_link("https://example.com/a b"), "")

    def test_angle_bracket_in_link_dropped(self):
        self.assertEqual(safe_link("https://example.com/<script>"), "")

    def test_empty_and_none(self):
        self.assertEqual(safe_link(""), "")
        self.assertEqual(safe_link(None), "")


class TestParseRssSafety(unittest.TestCase):
    def test_xss_title_cleaned(self):
        items = parse_rss(RSS_WITH_XSS, FEED)
        self.assertTrue(items, "запись про нейросеть должна была пройти фильтр")
        for item in items:
            self.assertNotIn("<", item["title"])
            self.assertNotIn(">", item["title"])

    def test_javascript_link_dropped(self):
        """Запись с javascript:-ссылкой не попадает в архив вообще."""
        items = parse_rss(RSS_WITH_XSS, FEED)
        self.assertFalse(any("javascript" in i["link"] for i in items))

    def test_normal_title_not_broken(self):
        """Обычный заголовок доходит до архива ровно таким, каким пришёл."""
        rss = RSS_WITH_XSS.replace(
            '&lt;img src=x onerror="alert(1)"&gt; новая нейросеть', "Новая нейросеть")
        items = parse_rss(rss, FEED)
        self.assertTrue(any(i["title"] == "Новая нейросеть" for i in items))


class TestTrudvsemSafety(unittest.TestCase):
    def test_title_cleaned_and_link_checked(self):
        sample = [{"vacancy": {
            "job-name": "<b>Инженер</b> машинного обучения",
            "vac_url": "javascript:alert(1)",
            "creation-date": "2026-09-04",
            "employment": "Дистанционная (удаленная) работа",
            "duty": "ML-проекты",
        }}]
        items, _ = parse_trudvsem(sample)
        self.assertEqual(items, [], "ссылка без http не должна давать карточку")

        sample[0]["vacancy"]["vac_url"] = "https://trudvsem.ru/vacancy/card/1/aaa"
        items, _ = parse_trudvsem(sample)
        self.assertEqual(items[0]["title"], "Инженер машинного обучения")


class TestCleanDescSafety(unittest.TestCase):
    def test_tag_after_unescape_removed(self):
        self.assertNotIn("<", clean_desc("&lt;img src=x onerror=alert(1)&gt;"))


class TestFetchUrlGuards(unittest.TestCase):
    """Сетевые предохранители: подлинность сервера и потолок на размер ответа."""

    def _fake_response(self, payload):
        resp = mock.MagicMock()
        resp.read = lambda n=None: payload if n is None else payload[:n]
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: False
        return resp

    def test_certificate_is_verified(self):
        """Проверка сертификата не должна быть отключена.

        Раньше здесь стояли check_hostname=False и CERT_NONE: шифрование было,
        а подлинность сервера не проверялась — ленту можно было подменить.
        """
        seen = {}

        def fake_urlopen(req, timeout=None, context=None):
            seen["context"] = context
            return self._fake_response(b"<rss></rss>")

        with mock.patch("news.fetch.urlopen", fake_urlopen):
            fetch_url("https://example.com/rss")

        ctx = seen["context"]
        self.assertIsNotNone(ctx, "контекст должен передаваться явно")
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_oversized_response_rejected(self):
        big = b"a" * (MAX_FEED_BYTES + 10)

        def fake_urlopen(req, timeout=None, context=None):
            return self._fake_response(big)

        with mock.patch("news.fetch.urlopen", fake_urlopen):
            with self.assertRaises(ValueError):
                fetch_url("https://example.com/rss")

    def test_normal_response_passes(self):
        def fake_urlopen(req, timeout=None, context=None):
            return self._fake_response(b"<rss><channel></channel></rss>")

        with mock.patch("news.fetch.urlopen", fake_urlopen):
            self.assertTrue(fetch_url("https://example.com/rss").startswith(b"<rss>"))


class TestTemplateEscapes(unittest.TestCase):
    """Сторож на шаблон рубрики: чужие поля обязаны идти через esc()/safeUrl().

    Шаблон — ручной файл, и вставку легко вернуть «как было» при следующей
    правке вёрстки. Этот тест это заметит.
    """

    @classmethod
    def setUpClass(cls):
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            cls.html = f.read()

    def test_template_exists(self):
        self.assertIn("window.NEWS_DATA", self.html)

    def test_fields_in_innerhtml_are_escaped(self):
        """В строках, которые уходят в innerHTML, не должно быть голых полей."""
        offenders = []
        for line in self.html.splitlines():
            if "html +=" not in line and "innerHTML" not in line:
                continue
            for m in re.finditer(r"n\.(title|source|link)\b", line):
                before = line[:m.start()]
                if not (before.endswith("esc(") or before.endswith("safeUrl(")):
                    offenders.append(line.strip()[:100])
        self.assertEqual(offenders, [], f"поля без экранирования: {offenders}")

    def test_helpers_present(self):
        self.assertIn("function esc(", self.html)
        self.assertIn("function safeUrl(", self.html)

    def test_safe_url_rejects_attribute_breakers(self):
        """safeUrl в шаблоне обязан отсекать кавычки и пробелы, а не только схему.

        Проверка найдена на живом прогоне: ссылка вида
        `https://x/" onmouseover="alert(1)` проходила по схеме, потому что
        начиналась с https. Схемы мало — нужен ещё отсев символов.
        """
        body = re.search(r"function safeUrl\(u\) \{.*?\n\}", self.html, re.S).group(0)
        self.assertRegex(body, r"/\[\\s", "нет отсева пробельных символов")
        self.assertIn('"', body, "нет отсева кавычек")


if __name__ == "__main__":
    unittest.main()
