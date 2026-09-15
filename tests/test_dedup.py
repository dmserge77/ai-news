"""Тесты отсева повторов.

Главный случай — «Алиса»: одна статья пришла из двух ИИ-тегов vc.ru
с разными адресами и висела на сайте двумя карточками.
"""

import unittest

from news.dedup import Seen, dedup_key
from news.util import norm_title


def item(title, link, source="vc.ru", date="2026-09-15"):
    return {"title": title, "link": link, "source": source, "date": date}


class TestNormTitle(unittest.TestCase):
    def test_case_and_punctuation_ignored(self):
        self.assertEqual(norm_title("Алиса AI сама выбирает режим!"),
                         norm_title("алиса ai сама выбирает режим"))

    def test_extra_spaces_ignored(self):
        self.assertEqual(norm_title("  Два   пробела "), norm_title("Два пробела"))

    def test_empty(self):
        self.assertEqual(norm_title(None), "")


class TestDedupKey(unittest.TestCase):
    def test_alisa_case_two_links_one_news(self):
        """Реальный случай: статья 3139979 в тегах #ai и #нейросети."""
        a = item("Алиса AI сама выбирает режим. Какие задачи ей теперь поручать",
                 "https://vc.ru/ai/3139979-alisa-ai-vybirayet-rezhim-dlya-zadach")
        b = item("Алиса AI сама выбирает режим. Какие задачи ей теперь поручать",
                 "https://vc.ru/ai/3139979-alisa-ai-sama-vybiraet-rezhim-kakie-zadachi-ei-teper-poruchat")
        self.assertNotEqual(a["link"], b["link"])
        self.assertEqual(dedup_key(a), dedup_key(b))

    def test_different_dates_are_different_news(self):
        """Еженедельный дайджест с одинаковым названием — не дубль."""
        a = item("Дайджест недели", "https://x/1", date="2026-09-08")
        b = item("Дайджест недели", "https://x/2", date="2026-09-15")
        self.assertNotEqual(dedup_key(a), dedup_key(b))

    def test_different_sources_are_different_news(self):
        a = item("Вышла новая модель", "https://a/1", source="Habr AI")
        b = item("Вышла новая модель", "https://b/1", source="vc.ru")
        self.assertNotEqual(dedup_key(a), dedup_key(b))

    def test_missing_fields_do_not_crash(self):
        self.assertEqual(dedup_key({}), ("", "", ""))


class TestSeen(unittest.TestCase):
    def test_same_link_twice(self):
        seen = Seen()
        first = item("Заголовок", "https://x/1")
        second = item("Совсем другой заголовок", "https://x/1")
        self.assertFalse(seen.check(first))
        self.assertTrue(seen.check(second))
        self.assertEqual(seen.dups, 1)

    def test_same_title_different_link(self):
        seen = Seen()
        self.assertFalse(seen.check(item("Заголовок", "https://x/1")))
        self.assertTrue(seen.check(item("Заголовок", "https://x/2")))

    def test_duplicates_counted(self):
        seen = Seen()
        for _ in range(3):
            seen.check(item("Заголовок", "https://x/1"))
        self.assertEqual(seen.dups, 2)

    def test_items_without_link_still_deduped(self):
        """У некоторых источников ссылки нет — тогда работает ключ по заголовку."""
        seen = Seen()
        self.assertFalse(seen.check(item("Заголовок", "")))
        self.assertTrue(seen.check(item("Заголовок", "")))


if __name__ == "__main__":
    unittest.main()
