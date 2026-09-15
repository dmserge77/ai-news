"""Тесты правил отбора.

Каждый случай здесь — не выдумка, а реальная ситуация, которая уже
случалась в проекте. Тест нужен, чтобы она не вернулась.

Запуск из корня проекта: python -m unittest discover -s tests -t .
"""

import unittest

from news.filters import (
    classify, classify_misc, classify_order, has_ai_signal, is_ai_job_theme,
    is_ai_order, is_ai_relevant, is_real_ai_job, is_seo_spam,
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
        self.assertTrue(is_real_ai_job("AI-инженер", "удалённо, python, llm, pytorch"))

    def test_office_without_remote_rejected(self):
        """Про удалёнку не сказано — вакансию не берём."""
        self.assertFalse(is_real_ai_job("Разработчик Python", "работа в офисе, полный день"))

    def test_english_job_rejected(self):
        """Англоязычную вакансию не берём, даже если она удалённая."""
        self.assertFalse(is_real_ai_job(
            "Senior Machine Learning Engineer",
            "Remote position, LLM, PyTorch, competitive salary"))

    def test_hybrid_is_not_remote(self):
        """Гибрид — это частично офис, онлайном не считаем."""
        self.assertFalse(is_real_ai_job("ML-инженер", "гибридный формат, 3 дня в офисе"))

    def test_remote_but_wrong_profession_rejected(self):
        """Удалённый продавец — всё равно не наша вакансия."""
        self.assertFalse(is_real_ai_job("Продавец-консультант", "удалённо, работа из дома"))

    def test_source_filter_is_trusted(self):
        """Если формат отфильтровал сам hh.ru — слова «удалённо» в тексте не требуем.

        В ленте hh.ru формат работы не пишется вообще: только компания, регион
        и доход. При этом в описании бывает «Центральный офис» — это название
        офиса компании, а не место работы. Требовать удалёнку в тексте значило
        бы выбросить все вакансии hh.ru до единой.
        """
        desc = "Вакансия компании: Альфа-Банк. Центральный офис. Регион: Москва"
        self.assertTrue(is_real_ai_job("AI Engineer", desc, remote_confirmed=True))
        self.assertFalse(is_real_ai_job("AI Engineer", desc))

    def test_job_must_be_about_ai(self):
        """Технического слова в заголовке мало — нужен признак ИИ."""
        self.assertFalse(is_ai_job_theme("Дизайнер машинной вышивки Wilcom"))
        self.assertFalse(is_ai_job_theme("Middle Python Developer (Django)"))
        self.assertTrue(is_ai_job_theme("ML-инженер"))
        self.assertTrue(is_ai_job_theme("Data Scientist в команду RecSys"))
        self.assertTrue(is_ai_job_theme("Backend-разработчик / MCP Engineer"))

    def test_short_ai_abbreviations_are_separate_words(self):
        """«ml» не должно ловиться в «html», «ai» — в «email»."""
        self.assertFalse(is_ai_job_theme("Верстальщик HTML-писем"))
        self.assertFalse(is_ai_job_theme("Специалист по email-рассылкам"))
        self.assertTrue(is_ai_job_theme("Computer Vision Engineer"))

    def test_cv_means_resume_not_computer_vision(self):
        """Одиночное «CV» — это резюме, поэтому признаком ИИ не считается."""
        self.assertFalse(is_ai_job_theme("Пришлите своё CV на почту"))
        self.assertTrue(is_ai_job_theme("CV Engineer"))
        self.assertTrue(is_ai_job_theme("Middle CV-инженер"))

    def test_embroidery_designer_rejected(self):
        """Реальный случай: hh.ru вернул это по запросу «машинное обучение»."""
        self.assertFalse(is_real_ai_job(
            "Дизайнер машинной вышивки Wilcom",
            "удалённо, работа из дома, опыт от 1 года", remote_confirmed=True))


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
