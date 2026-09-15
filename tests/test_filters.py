"""Тесты правил отбора.

Каждый случай здесь — не выдумка, а реальная ситуация, которая уже
случалась в проекте. Тест нужен, чтобы она не вернулась.

Запуск из корня проекта: python -m unittest discover -s tests -t .
"""

import unittest

from news.filters import (
    classify, classify_misc, classify_order, has_ai_signal, is_ai_order,
    is_ai_relevant, is_real_ai_job, is_seo_spam,
)


class TestAiSignal(unittest.TestCase):
    def test_plain_ai_words(self):
        self.assertTrue(has_ai_signal("Нейросеть нарисовала кота"))
        self.assertTrue(has_ai_signal("Новая большая языковая модель"))
        self.assertTrue(has_ai_signal("Anthropic выпустила Claude"))

    def test_ai_as_separate_word(self):
        """«ai» отдельным словом, но не внутри mail/said/captain."""
        self.assertTrue(has_ai_signal("Новый AI-сервис для разработчиков"))
        self.assertFalse(has_ai_signal("I said hello to the captain by mail"))

    def test_graphic_formats_are_not_ai(self):
        """Перечисление форматов svg, ai, pdf — это Adobe Illustrator."""
        self.assertFalse(has_ai_signal("Принимаем макеты в форматах svg, ai, pdf"))
        self.assertFalse(has_ai_signal("Файлы ai, eps, png для печати"))

    def test_llama_inside_domain(self):
        """wisellama.rocks — не про ИИ, хотя внутри есть llama."""
        self.assertFalse(has_ai_signal("Заходите на wisellama.rocks за обоями"))

    def test_llama_as_word_still_works(self):
        self.assertTrue(has_ai_signal("Meta выпустила Llama 4"))

    def test_everyday_words_are_not_ai(self):
        self.assertFalse(has_ai_signal("Придётся работать до 4 месяцев ради iPhone"))


class TestAiRelevant(unittest.TestCase):
    def test_household_tech_is_rejected(self):
        """Бытовая техника с «умными» функциями — не наша тема."""
        self.assertFalse(is_ai_relevant("Пылесос с нейросетью для уборки", "ai"))
        self.assertFalse(is_ai_relevant("Холодильник с ИИ-камерой", "ai"))

    def test_jobs_and_orders_skip_ai_check(self):
        self.assertTrue(is_ai_relevant("любой текст", "jobs"))
        self.assertTrue(is_ai_relevant("любой текст", "orders"))

    def test_unknown_category(self):
        self.assertFalse(is_ai_relevant("Нейросеть", "несуществующая"))


class TestSeoSpam(unittest.TestCase):
    def test_vc_ru_style_ads(self):
        self.assertTrue(is_seo_spam("Нейросеть для генерации текста бесплатно: промпт и сервисы"))
        self.assertTrue(is_seo_spam("Лучшие текстовые ИИ-модели: рейтинг"))
        self.assertTrue(is_seo_spam(""))

    def test_normal_titles_pass(self):
        self.assertFalse(is_seo_spam("Self-Attention — это гениально"))
        self.assertFalse(is_seo_spam("ИИ может убить всех нас"))
        self.assertFalse(is_seo_spam("Claude Code научился оценивать пользу плагинов"))


class TestClassify(unittest.TestCase):
    def test_ai_rubric(self):
        self.assertEqual(classify("OpenAI выпустила GPT-5", "ai"), "ai")

    def test_design_rubric(self):
        self.assertEqual(classify("Лендинг на Тильде за вечер", "design"), "design")

    def test_no_ai_no_keywords_means_none(self):
        self.assertIsNone(classify("Учёные нашли новых рачков в Байкале", "ai"))

    def test_fallback_to_misc(self):
        """Ключевых слов рубрик нет, но материал про ИИ — отправляем в Солянку."""
        self.assertEqual(classify("Система распознавания лиц в аэропорту", "platform"), "misc")


class TestJobs(unittest.TestCase):
    def test_office_jobs_rejected(self):
        self.assertFalse(is_real_ai_job("Продавец-консультант", "работа в офисе, полный день"))
        self.assertFalse(is_real_ai_job("Курьер", "доставка по городу"))

    def test_courses_rejected(self):
        self.assertFalse(is_real_ai_job("Курс по нейросетям", "обучение с нуля, стажировка"))

    def test_remote_ai_job_accepted(self):
        self.assertTrue(is_real_ai_job("AI Engineer", "удалённо, python, llm, pytorch"))

    def test_office_without_remote_rejected(self):
        self.assertFalse(is_real_ai_job("Разработчик Python", "работа в офисе, полный день"))


class TestOrders(unittest.TestCase):
    def test_seo_and_ads_rejected(self):
        self.assertFalse(is_ai_order("Нужен директолог", "настроить Яндекс Директ"))
        self.assertFalse(is_ai_order("Раскрутка сайта", "продвижение, таргет"))

    def test_news_articles_rejected(self):
        self.assertFalse(is_ai_order("OpenAI объявила о релизе", "рассказал в интервью"))

    def test_websites_accepted_without_ai(self):
        self.assertTrue(is_ai_order("Сделать сайт на Тильде", "нужен лендинг под ключ"))

    def test_ai_order_accepted(self):
        self.assertTrue(is_ai_order("Нужен телеграм-бот", "с подключением к GPT"))

    def test_order_subcategories(self):
        self.assertEqual(classify_order("Сделать лендинг", ""), "sites")
        self.assertEqual(classify_order("Написать промпт для GPT", ""), "prompts")


class TestMisc(unittest.TestCase):
    def test_curio(self):
        self.assertEqual(classify_misc("Нейросеть пошутила над пользователем", ""), "curio")
        self.assertEqual(classify_misc("ИИ сгенерировал ерунду и попал в скандал", ""), "curio")

    def test_raznoe(self):
        self.assertEqual(classify_misc("Новая модель вышла в свет", ""), "raznoe")


if __name__ == "__main__":
    unittest.main()
