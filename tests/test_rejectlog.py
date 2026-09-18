"""Тесты журнала отказов.

Журнал нужен ровно для одного: чтобы через неделю можно было понять, почему
материала нет на сайте. Поэтому проверяем не только запись и чтение, но и
согласованность причин с самими фильтрами: если фильтр отбрасывает запись,
причина обязана быть названа, и наоборот.
"""

import json
import os
import tempfile
import unittest

from news import fetch, filters, rejectlog
from news.rejectlog import RejectLog, note


class TestRejectLog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "rejects.json")

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_add_and_save(self):
        log = RejectLog(self.path)
        log.add("Рачки в Байкале", "ТАСС Наука", "нет признака ИИ", "https://x.ru/1")
        log.save()
        data = self.read()
        self.assertEqual(data["total_rejected"], 1)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["reason"], "нет признака ИИ")
        self.assertEqual(data["items"][0]["source"], "ТАСС Наука")

    def test_same_title_and_reason_counted_not_duplicated(self):
        """Ленты отдают одно и то же шесть раз в день — журнал не должен пухнуть."""
        log = RejectLog(self.path)
        for _ in range(5):
            log.add("Рачки в Байкале", "ТАСС Наука", "нет признака ИИ")
        log.save()
        data = self.read()
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["count"], 5)
        self.assertEqual(data["total_rejected"], 5)

    def test_same_title_different_reasons_are_separate(self):
        log = RejectLog(self.path)
        log.add("Дизайнер машинной вышивки", "hh.ru", "не ИИ-профессия")
        log.add("Дизайнер машинной вышивки", "hh.ru", "нет признака ИИ или ML")
        log.save()
        self.assertEqual(len(self.read()["items"]), 2)

    def test_survives_broken_file(self):
        """Битый журнал не должен ронять сборку."""
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{это не json")
        log = RejectLog(self.path)
        self.assertEqual(log.total, 0)
        log.add("Что-то", "vc.ru", "нет признака ИИ")
        log.save()
        self.assertEqual(self.read()["total_rejected"], 1)

    def test_history_is_kept_between_runs(self):
        log = RejectLog(self.path)
        log.add("Первое", "vc.ru", "нет признака ИИ")
        log.save()

        second = RejectLog(self.path)
        second.add("Второе", "vc.ru", "нет признака ИИ")
        second.save()

        data = self.read()
        self.assertEqual(data["runs"], 2)
        self.assertEqual(data["total_rejected"], 2)
        self.assertEqual(len(data["items"]), 2)

    def test_last_run_separate_from_total(self):
        """Сводка «за прогон» и «за всё время» — разные числа, их легко перепутать."""
        log = RejectLog(self.path)
        log.add("Старое", "vc.ru", "повтор")
        log.save()

        second = RejectLog(self.path)
        second.add("Новое", "vc.ru", "повтор")
        second.save()

        data = self.read()
        self.assertEqual(data["last_run"]["total"], 1)
        self.assertEqual(data["by_reason"]["повтор"], 2)

    def test_empty_title_skipped(self):
        log = RejectLog(self.path)
        log.add("", "vc.ru", "нет признака ИИ")
        log.add("   ", "vc.ru", "нет признака ИИ")
        self.assertEqual(log.run_total, 0)

    def test_items_are_trimmed(self):
        """Общий потолок журнала: файл не должен расти бесконечно."""
        log = RejectLog(self.path)
        reasons = [f"причина {i}" for i in range(10)]
        for i in range(rejectlog.MAX_ITEMS + 50):
            log.add(f"Новость номер {i}", "vc.ru", reasons[i % 10])
        log.save()
        self.assertLessEqual(len(self.read()["items"]), rejectlog.MAX_ITEMS)

    def test_rare_reason_survives_next_to_common_one(self):
        """Редкая причина не вытесняется частой — ради этого и заведена квота.

        «Нет признака ИИ» даёт больше двух тысяч записей за прогон, а «не
        ИИ-профессия (слово в описании)» — девятнадцать. Без квоты редкие
        случаи пропадали бы из журнала, а разбирать надо именно их.
        """
        log = RejectLog(self.path)
        for i in range(rejectlog.MAX_PER_REASON * 3):
            log.add(f"Обычная новость {i}", "vc.ru", "нет признака ИИ")
        log.add("Редкий случай", "hh.ru", "не ИИ-профессия (слово в описании)")
        log.save()

        reasons = [r["reason"] for r in self.read()["items"]]
        self.assertIn("не ИИ-профессия (слово в описании)", reasons)
        self.assertEqual(reasons.count("нет признака ИИ"), rejectlog.MAX_PER_REASON)

    def test_note_without_log_does_nothing(self):
        """Разбор лент работает и без журнала — так его зовут тесты и старые скрипты."""
        note(None, "Заголовок", "vc.ru", "нет признака ИИ")

    def test_report_prints_run_summary(self):
        log = RejectLog(self.path)
        log.add("Рачки", "ТАСС Наука", "нет признака ИИ")
        log.add("Курьер", "hh.ru", "не ИИ-профессия")
        log.add("Ещё рачки", "ТАСС Наука", "нет признака ИИ")
        out = []
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            log.report()
        out = buf.getvalue()
        self.assertIn("Отклонено за прогон: 3", out)
        self.assertIn("нет признака ИИ", out)


class TestReasonsMatchFilters(unittest.TestCase):
    """Причина отказа и решение фильтра обязаны совпадать.

    Это главный тест файла: если кто-то поправит фильтр и забудет причину,
    журнал начнёт врать — а врать он будет молча.
    """

    AI_CASES = [
        ("Нейросеть нарисовала кота", "ai"),
        ("Пылесос с нейросетью для уборки", "ai"),
        ("Учёные нашли новых рачков в Байкале", "ai"),
        ("любой текст", "jobs"),
        ("Нейросеть", "несуществующая"),
        ("OpenAI выпустила GPT-5", "ai"),
    ]

    JOB_CASES = [
        ("Продавец-консультант", "работа в офисе, полный день", False),
        ("AI-инженер", "удалённо, python, llm, pytorch", False),
        ("Курс по нейросетям", "обучение с нуля, стажировка", False),
        ("Senior ML Engineer", "Remote position, LLM", False),
        ("AI Engineer", "Вакансия компании: Альфа-Банк. Регион: Москва", True),
        ("Дизайнер машинной вышивки Wilcom", "удалённо, опыт от 1 года", True),
    ]

    ORDER_CASES = [
        ("Нужен директолог", "настроить Яндекс Директ"),
        ("OpenAI объявила о релизе", "рассказал в интервью"),
        ("Сделать сайт на Тильде", "нужен лендинг под ключ"),
        ("Нужен телеграм-бот", "с подключением к GPT"),
        ("Покрасить забор", "работа на один день"),
    ]

    def test_ai_reason_matches_filter(self):
        for text, cat in self.AI_CASES:
            with self.subTest(text=text, cat=cat):
                reason = filters.ai_reject_reason(text, cat)
                self.assertEqual(filters.is_ai_relevant(text, cat), reason is None)

    def test_job_reason_matches_filter(self):
        for title, desc, remote in self.JOB_CASES:
            with self.subTest(title=title):
                reason = filters.job_reject_reason(title, desc, remote)
                self.assertEqual(filters.is_real_ai_job(title, desc, remote), reason is None)

    def test_order_reason_matches_filter(self):
        for title, desc in self.ORDER_CASES:
            with self.subTest(title=title):
                reason = filters.order_reject_reason(title, desc)
                self.assertEqual(filters.is_ai_order(title, desc), reason is None)

    def test_reason_says_where_the_word_was_found(self):
        """Заголовок и описание различаются в причине.

        «Продавец» в заголовке — вакансия не наша, спорить не о чем. Слово
        в описании — уже повод присмотреться: у профильных вакансий
        в требованиях бывают «водительские права» и «обучение модели».
        """
        self.assertEqual(
            filters.job_reject_reason("Продавец-консультант", "удалённо, работа из дома"),
            "не ИИ-профессия")
        self.assertEqual(
            filters.job_reject_reason("AI-инженер", "удалённо, llm, требуется курьер"),
            "не ИИ-профессия (слово в описании)")

    def test_professional_jobs_no_longer_lost(self):
        """Профильные вакансии, которые терялись из-за слов в описании.

        Все три случая — с живых лент 18.09.2026, найдены журналом отказов.
        """
        self.assertTrue(filters.is_real_ai_job(
            "Аналитик-инженер по машинному обучению",
            "удалённо, машинное обучение, водительские права приветствуются"))
        self.assertTrue(filters.is_real_ai_job(
            "AI-тренер для обучения нейросетей",
            "удалённо, помогать ИИ отвечать точнее, работа с контентом"))
        self.assertTrue(filters.is_real_ai_job(
            "Разработчик AI / RAG",
            "удалённо, дообучение моделей на новых данных, оптимизация LLM"))

    def test_russian_names_of_wrong_professions_are_seen(self):
        """Латинские «smm»/«seo»/«marketing» не ловили русские заголовки.

        Замер 18.09.2026: «СММ-специалист» и «Специалист по интернет-маркетингу»
        проходили фильтр (в описании у них были нейросети) и попадали в рубрику.
        """
        self.assertEqual(
            filters.job_reject_reason("СММ-специалист",
                                      "удалённо, создание визуалов с помощью нейросетей"),
            "не ИИ-профессия")
        self.assertEqual(
            filters.job_reject_reason("Специалист по интернет-маркетингу",
                                      "удалённо, контент с помощью ИИ и нейросетей"),
            "не ИИ-профессия")

    def test_courses_still_rejected(self):
        """Убрали «обучение» из маркеров курсов — сами курсы отсеиваться не перестали."""
        self.assertEqual(
            filters.job_reject_reason("Курс по нейросетям", "обучение с нуля, стажировка",
                                      remote_confirmed=True),
            "курсы или обучение, а не вакансия")
        self.assertEqual(
            filters.job_reject_reason("Автор курса «Нейросети для соцсетей»",
                                      "удалённо, обучение студентов", remote_confirmed=True),
            "курсы или обучение, а не вакансия")

    def test_reason_is_honest_for_wrong_profession(self):
        """«Машинист крана» попал в ленту по слову «обучение», но причина не в нём.

        Раньше в журнале он значился как «курсы или обучение, а не вакансия» —
        и по такой записи нельзя было понять, что сработало на самом деле.
        """
        self.assertEqual(
            filters.job_reject_reason("Машинист крана (крановщик)",
                                      "обучение, без опыта работы", remote_confirmed=True),
            "нет признака ИИ или ML")

    def test_rejected_records_have_a_reason(self):
        """Причина не пустая строка: пустая причина в журнале бесполезна."""
        for title, desc, remote in self.JOB_CASES:
            reason = filters.job_reject_reason(title, desc, remote)
            if reason is not None:
                self.assertTrue(reason.strip())
        for title, desc in self.ORDER_CASES:
            reason = filters.order_reject_reason(title, desc)
            if reason is not None:
                self.assertTrue(reason.strip())


class TestRejectLogInParsing(unittest.TestCase):
    """Разбор ленты пишет в журнал то, что отбросил.

    Журнал берём временный: с путём по умолчанию он читал бы рабочий
    data/rejects.json, и тест зависел бы от того, что лежит в архиве.
    """

    FEED = {"url": "https://example.com/rss", "source": "Пример", "cat": "ai"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "rejects.json")

    def tearDown(self):
        self.tmp.cleanup()

    def new_log(self):
        return RejectLog(self.path)

    def make_xml(self, title):
        return (f"<rss><channel><item>"
                f"<title>{title}</title>"
                f"<link>https://example.com/news/1</link>"
                f"<description>Описание</description>"
                f"<pubDate>Mon, 15 Sep 2026 10:00:00 +0300</pubDate>"
                f"</item></channel></rss>")

    def test_non_ai_record_is_logged(self):
        log = self.new_log()
        items = fetch.parse_rss(self.make_xml("Учёные нашли новых рачков в Байкале"),
                                self.FEED, log)
        self.assertEqual(items, [])
        self.assertEqual(log.run_total, 1)
        self.assertEqual(list(log.items.values())[0]["reason"], "нет признака ИИ")

    def test_accepted_record_is_not_logged(self):
        log = self.new_log()
        items = fetch.parse_rss(self.make_xml("OpenAI выпустила GPT-5"), self.FEED, log)
        self.assertEqual(len(items), 1)
        self.assertEqual(log.run_total, 0)

    def test_parsing_works_without_log(self):
        items = fetch.parse_rss(self.make_xml("OpenAI выпустила GPT-5"), self.FEED)
        self.assertEqual(len(items), 1)


if __name__ == "__main__":
    unittest.main()
