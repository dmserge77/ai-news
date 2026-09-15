"""Тесты разбора лент, дат и текста."""

import unittest

from news.fetch import parse_rss
from news.util import clean_desc, detect_lang, parse_date

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Тестовая лента</title>
<item>
  <title>OpenAI выпустила GPT-5</title>
  <link>https://example.com/gpt5</link>
  <description>&lt;p&gt;Новая модель стала умнее&lt;/p&gt;</description>
  <pubDate>Tue, 15 Sep 2026 10:00:00 +0300</pubDate>
</item>
<item>
  <title>Учёные нашли новых рачков в Байкале</title>
  <link>https://example.com/raki</link>
  <description>Биология и экология</description>
  <pubDate>Tue, 15 Sep 2026 11:00:00 +0300</pubDate>
</item>
<item>
  <title>Нейросеть для текстов бесплатно: промпт и сервисы</title>
  <link>https://vc.ru/ai/999999</link>
  <description>Реклама</description>
  <pubDate>Tue, 15 Sep 2026 12:00:00 +0300</pubDate>
</item>
</channel>
</rss>"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Тестовый Atom</title>
<entry>
  <title>Anthropic показала новую модель</title>
  <link href="https://example.com/anthropic"/>
  <summary>Большая языковая модель</summary>
  <updated>2026-09-15T08:30:00Z</updated>
</entry>
</feed>"""

FEED = {"url": "https://example.com/rss", "cat": "ai", "source": "Тест"}
VC_FEED = {"url": "https://vc.ru/rss/tag/ai", "cat": "ai", "source": "vc.ru"}


class TestParseDate(unittest.TestCase):
    def test_rfc822(self):
        self.assertEqual(parse_date("Tue, 15 Sep 2026 10:00:00 +0300"), "2026-09-15")

    def test_iso(self):
        self.assertEqual(parse_date("2026-09-15T08:30:00Z"), "2026-09-15")

    def test_iso_with_offset(self):
        self.assertEqual(parse_date("2026-09-15T08:30:00+03:00"), "2026-09-15")

    def test_plain_date(self):
        self.assertEqual(parse_date("2026-09-15"), "2026-09-15")

    def test_trudvsem_style(self):
        """Работа России присылает вид «2026-08-27 15:52:27»."""
        self.assertEqual(parse_date("2026-08-27 15:52:27"), "2026-08-27")

    def test_russian_style(self):
        self.assertEqual(parse_date("15.09.2026"), "2026-09-15")

    def test_garbage_falls_back_to_today(self):
        """Лучше неточная дата, чем потерянная новость."""
        result = parse_date("позавчера")
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}$")

    def test_empty_falls_back_to_today(self):
        self.assertRegex(parse_date(""), r"^\d{4}-\d{2}-\d{2}$")


class TestCleanDesc(unittest.TestCase):
    def test_tags_removed(self):
        self.assertEqual(clean_desc("<p>Привет</p>"), "Привет")

    def test_entities_decoded(self):
        self.assertEqual(clean_desc("AI &amp; ML"), "AI & ML")

    def test_whitespace_collapsed(self):
        self.assertEqual(clean_desc("много   \n  пробелов"), "много пробелов")

    def test_long_text_truncated(self):
        result = clean_desc("а" * 500)
        self.assertEqual(len(result), 300)
        self.assertTrue(result.endswith("..."))


class TestDetectLang(unittest.TestCase):
    def test_russian(self):
        self.assertEqual(detect_lang("Нейросеть"), "ru")

    def test_english(self):
        self.assertEqual(detect_lang("Neural network"), "en")

    def test_mixed_counts_as_russian(self):
        self.assertEqual(detect_lang("OpenAI выпустила GPT-5"), "ru")


class TestParseRss(unittest.TestCase):
    def test_only_ai_items_pass(self):
        items = parse_rss(RSS_SAMPLE, FEED)
        titles = [i["title"] for i in items]
        self.assertIn("OpenAI выпустила GPT-5", titles)
        self.assertNotIn("Учёные нашли новых рачков в Байкале", titles)

    def test_item_fields(self):
        items = parse_rss(RSS_SAMPLE, FEED)
        gpt = next(i for i in items if "GPT-5" in i["title"])
        self.assertEqual(gpt["link"], "https://example.com/gpt5")
        self.assertEqual(gpt["source"], "Тест")
        self.assertEqual(gpt["date"], "2026-09-15")
        self.assertEqual(gpt["lang"], "ru")
        self.assertEqual(gpt["desc"], "Новая модель стала умнее")

    def test_seo_spam_filtered_only_for_vc(self):
        """Рекламный заголовок режется у vc.ru, но не у обычных лент."""
        vc_items = parse_rss(RSS_SAMPLE, VC_FEED)
        self.assertFalse(any("бесплатно" in i["title"] for i in vc_items))
        plain_items = parse_rss(RSS_SAMPLE, FEED)
        self.assertTrue(any("бесплатно" in i["title"] for i in plain_items))

    def test_dead_source_returns_nothing(self):
        dead = {"url": "https://x/rss", "cat": "ai", "source": "ComNews"}
        self.assertEqual(parse_rss(RSS_SAMPLE, dead), [])

    def test_atom_parsed(self):
        items = parse_rss(ATOM_SAMPLE, FEED)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["link"], "https://example.com/anthropic")
        self.assertEqual(items[0]["date"], "2026-09-15")


if __name__ == "__main__":
    unittest.main()
