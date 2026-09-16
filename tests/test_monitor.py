"""Тесты наблюдения за источниками.

Главное здесь — карантин и его сроки. Проверяем временем, а не ожиданием:
все функции принимают отметку времени параметром `at`.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from news import monitor
from news.config import (
    QUARANTINE_RETRY_DAYS, SILENT_RUNS_TO_QUARANTINE, SILENT_RUNS_TO_WARN,
    STALE_RUNS_TO_WARN,
)
from news.monitor import SourcesLog

START = datetime(2026, 9, 16, 3, 0)


def quiet():
    """Глушит вывод отчёта: иначе в логе CI появится поддельная таблица
    источников рядом с настоящей, и их будет не различить."""
    return contextlib.redirect_stdout(io.StringIO())


class MonitorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "sources.json")
        self.log = SourcesLog(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def silent_runs(self, source, count, at=START):
        """Прогоняет источник count раз с пустой лентой."""
        for _ in range(count):
            self.log.note(source, monitor.EMPTY, 0, 0, at=at)
        return self.log.data[source]


class TestSilence(MonitorCase):
    def test_empty_runs_are_counted(self):
        rec = self.silent_runs("AiHub", 2)
        self.assertEqual(rec["silent_streak"], 2)
        self.assertEqual(rec["runs"], 2)
        self.assertFalse(self.log.should_skip("AiHub", at=START))

    def test_warning_threshold(self):
        rec = self.silent_runs("AiHub", SILENT_RUNS_TO_WARN)
        self.assertEqual(self.log._kind(rec, START), "silent")

    def test_broken_feed_is_not_confused_with_off_topic(self):
        """Пустая лента и «ничего не прошло фильтр» — разные диагнозы."""
        self.silent_runs("AiHub", SILENT_RUNS_TO_WARN)
        empty = self.log._label(self.log.data["AiHub"], START)
        self.assertIn("лента пуста", empty)

        self.log.note("ForkLog", monitor.FILTERED, 0, 0, at=START)
        for _ in range(SILENT_RUNS_TO_WARN):
            self.log.note("ForkLog", monitor.FILTERED, 0, 0, at=START)
        filtered = self.log._label(self.log.data["ForkLog"], START)
        self.assertIn("не проходит фильтр", filtered)

    def test_error_is_reported(self):
        self.log.note("ComNews", monitor.ERROR, 0, 0, note="HTTP 404", at=START)
        self.assertEqual(self.log._kind(self.log.data["ComNews"], START), "error")
        self.assertIn("HTTP 404", self.log._label(self.log.data["ComNews"], START))

    def test_first_silent_run_is_visible_in_the_table(self):
        """Источник, давший ноль записей, не должен подписываться «работает».

        Ради этой видимости журнал и заводился: тревога включается на третьем
        прогоне, но уже первый обязан быть виден в таблице.
        """
        self.log.note("ForkLog", monitor.FILTERED, 0, 0, at=START)
        label = self.log._label(self.log.data["ForkLog"], START)
        self.assertEqual(label, "не проходит фильтр")

        self.log.note("DTF", monitor.EMPTY, 0, 0, at=START)
        self.assertEqual(self.log._label(self.log.data["DTF"], START), "лента пуста")

    def test_one_silent_run_does_not_raise_alarm(self):
        """Ярлык честный, но предупреждения на первом прогоне ещё нет."""
        self.log.note("ForkLog", monitor.FILTERED, 0, 0, at=START)
        self.assertEqual(self.log._kind(self.log.data["ForkLog"], START), "ok")


class TestQuarantine(MonitorCase):
    def test_quarantine_kicks_in(self):
        self.silent_runs("AiHub", SILENT_RUNS_TO_QUARANTINE)
        self.assertTrue(self.log.should_skip("AiHub", at=START))
        self.assertEqual(self.log._kind(self.log.data["AiHub"], START), "quarantine")

    def test_quarantine_expires_and_source_is_retried(self):
        """Карантин не вечный: через неделю источник читаем снова."""
        self.silent_runs("AiHub", SILENT_RUNS_TO_QUARANTINE)
        almost = START + timedelta(days=QUARANTINE_RETRY_DAYS, hours=-1)
        after = START + timedelta(days=QUARANTINE_RETRY_DAYS, hours=1)
        self.assertTrue(self.log.should_skip("AiHub", at=almost))
        self.assertFalse(self.log.should_skip("AiHub", at=after))

    def test_failed_retry_postpones_next_attempt(self):
        """Если проверка после карантина не удалась, следующая — ещё через неделю.

        Без продления даты источник дёргался бы на каждом прогоне.
        """
        self.silent_runs("AiHub", SILENT_RUNS_TO_QUARANTINE)
        retry = START + timedelta(days=QUARANTINE_RETRY_DAYS, hours=1)
        self.log.note("AiHub", monitor.EMPTY, 0, 0, at=retry)
        self.assertTrue(self.log.should_skip("AiHub", at=retry + timedelta(hours=2)))
        self.assertFalse(self.log.should_skip(
            "AiHub", at=retry + timedelta(days=QUARANTINE_RETRY_DAYS, hours=1)))

    def test_source_recovering_leaves_quarantine(self):
        self.silent_runs("AiHub", SILENT_RUNS_TO_QUARANTINE)
        self.assertTrue(self.log.should_skip("AiHub", at=START))

        later = START + timedelta(days=QUARANTINE_RETRY_DAYS, hours=1)
        rec = self.log.note("AiHub", monitor.OK, 12, 3, at=later)
        self.assertEqual(rec["silent_streak"], 0)
        self.assertEqual(rec["quarantined_at"], "")
        self.assertFalse(self.log.should_skip("AiHub", at=later))

    def test_unknown_source_is_never_skipped(self):
        self.assertFalse(self.log.should_skip("Новый источник", at=START))


class TestStale(MonitorCase):
    def test_quiet_feed_is_not_a_problem(self):
        """«Записи есть, новых нет» полсутки — это норма, а не поломка."""
        for _ in range(SILENT_RUNS_TO_WARN * 3):
            self.log.note("Блог", monitor.OK, 20, 0, at=START)
        rec = self.log.data["Блог"]
        self.assertEqual(self.log._kind(rec, START), "ok")
        self.assertEqual(rec["silent_streak"], 0)

    def test_frozen_feed_is_noticed(self):
        for _ in range(STALE_RUNS_TO_WARN):
            self.log.note("Блог", monitor.OK, 20, 0, at=START)
        rec = self.log.data["Блог"]
        self.assertEqual(self.log._kind(rec, START), "stale")

    def test_fresh_records_reset_stale_counter(self):
        for _ in range(STALE_RUNS_TO_WARN):
            self.log.note("Блог", monitor.OK, 20, 0, at=START)
        self.log.note("Блог", monitor.OK, 20, 5, at=START)
        self.assertEqual(self.log.data["Блог"]["stale_streak"], 0)


class TestStorage(MonitorCase):
    def test_saved_and_loaded(self):
        self.log.note("Хабр ИИ", monitor.OK, 20, 4, at=START)
        self.log.save()

        again = SourcesLog(self.path)
        self.assertEqual(again.data["Хабр ИИ"]["last_records"], 20)
        self.assertEqual(again.data["Хабр ИИ"]["total_records"], 20)

    def test_broken_journal_does_not_crash(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ это не json")
        self.assertEqual(SourcesLog(self.path).data, {})

    def test_journal_is_a_dict_not_a_list(self):
        """Битый по форме журнал тоже не должен ломать сборку."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(["не", "словарь"], f)
        self.assertEqual(SourcesLog(self.path).data, {})

    def test_report_does_not_crash_on_empty_journal(self):
        with quiet():
            self.log.print_report(at=START)

    def test_report_does_not_crash_with_problems(self):
        self.silent_runs("AiHub", SILENT_RUNS_TO_QUARANTINE)
        self.log.note("ComNews", monitor.ERROR, 0, 0, note="HTTP 404", at=START)
        self.log.note("ForkLog", monitor.FILTERED, 0, 0, at=START)
        for _ in range(STALE_RUNS_TO_WARN):
            self.log.note("Блог", monitor.OK, 20, 0, at=START)
        self.log.note("Хабр ИИ", monitor.OK, 20, 4, at=START)
        with quiet():
            self.log.print_report(at=START)


if __name__ == "__main__":
    unittest.main()
