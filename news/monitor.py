"""Наблюдение за источниками: кто отвечает, кто молчит, кого пора в карантин.

Зачем это нужно. Источник, который отвечает кодом 200, но не даёт записей,
в логе сборки не виден: там просто строка «-> 0 записей». Так месяцами молчала
«Работа России» — код читал несуществующие поля `title` и `creation_date`,
рубрика оставалась пустой, а ошибки не было. Так же почти потеряли ComNews
и AiHub: их нашли случайно, а не потому, что сборка пожаловалась.

Журнал лежит в `data/sources.json` и едет в git вместе с накопителем, поэтому
история не теряется между прогонами и одинакова в CI и локально.

Два разных вида молчания, и они означают разное:
  * «лента пуста» — источник отвечает, но записей в ленте нет вовсе. Источник
    закрылся или отдаёт не то, что мы разбираем.
  * «ничего не проходит фильтр» — записи в ленте есть, но ни одна не про ИИ.
    Источник жив, просто не по нашей теме.
  * «не обновляется» — записи есть и проходят фильтр, но все уже видели.
    Значит лента замерла: адрес живой, а новые материалы не приходят.

Первые два случая считаются молчанием — источник ничего не приносит. Третий
случаем молчания НЕ считается и порог у него в двадцать раз длиннее: ленты
обновляются вразнобой, и «новых 0» полдня — это норма.
"""

import json
from datetime import datetime, timedelta

from .config import (
    QUARANTINE_RETRY_DAYS, SILENT_RUNS_TO_QUARANTINE, SILENT_RUNS_TO_WARN,
    SOURCES_LOG_PATH, STALE_RUNS_TO_WARN,
)
from .store import write_if_changed
from .util import now_msk

OK = "ok"              # ответил и дал записи, которые прошли фильтр
EMPTY = "empty"        # ответил, но записей в ленте нет
FILTERED = "filtered"  # записи есть, но ни одна не прошла фильтр
ERROR = "error"        # не ответил вовсе

STAMP = "%Y-%m-%d %H:%M"


def _parse(stamp):
    """Разбирает отметку времени журнала. None — если отметки нет или она битая."""
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp, STAMP)
    except ValueError:
        return None


class SourcesLog:
    """Журнал прогонов по каждому источнику."""

    def __init__(self, path=None):
        self.path = path or SOURCES_LOG_PATH
        self.data = self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            # Битый или отсутствующий журнал — не повод падать. Просто начнём
            # вести его заново.
            return {}

    def should_skip(self, source, at=None):
        """True — источник в карантине, читать его в этот раз не нужно."""
        rec = self.data.get(source)
        if not rec:
            return False
        since = _parse(rec.get("quarantined_at"))
        if since is None:
            return False
        # Карантин не вечный: раз в QUARANTINE_RETRY_DAYS пробуем снова.
        return (at or now_msk()) - since < timedelta(days=QUARANTINE_RETRY_DAYS)

    def note(self, source, status, records=0, new=0, note="", at=None):
        """Записывает итог одного прогона по источнику."""
        at = at or now_msk()
        stamp = at.strftime(STAMP)

        rec = self.data.setdefault(source, {})
        rec["runs"] = rec.get("runs", 0) + 1
        rec["last_run"] = stamp
        rec["status"] = status
        rec["last_records"] = records
        rec["last_new"] = new
        rec["total_records"] = rec.get("total_records", 0) + records
        if note:
            rec["last_note"] = str(note)[:200]

        if records > 0:
            # Источник ожил — карантин и все счётчики молчания снимаем.
            rec["last_ok"] = stamp
            rec["silent_streak"] = 0
            rec["quarantined_at"] = ""
            # Записи есть, а новых нет — лента могла замереть.
            rec["stale_streak"] = rec.get("stale_streak", 0) + 1 if new == 0 else 0
        else:
            rec["silent_streak"] = rec.get("silent_streak", 0) + 1
            rec["stale_streak"] = 0
            if rec["silent_streak"] >= SILENT_RUNS_TO_QUARANTINE:
                # Ставим карантин, а при повторной попытке — продлеваем его,
                # иначе после неудачной проверки источник дёргался бы каждый раз.
                rec["quarantined_at"] = stamp

        return rec

    def save(self):
        body = json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True)
        write_if_changed(self.path, body + "\n")

    def print_report(self, at=None):
        """Печатает таблицу по источникам и предупреждения о молчащих."""
        at = at or now_msk()
        if not self.data:
            print("  (журнал источников пуст)")
            return

        order = {"quarantine": 0, "silent": 1, "stale": 2, "error": 3, "ok": 4}
        rows = []
        for source, rec in self.data.items():
            rows.append((order[self._kind(rec, at)], source, rec))
        rows.sort(key=lambda r: (r[0], r[1]))

        print(f"  {'источник':32} {'записей':>8} {'новых':>6}  состояние")
        for _, source, rec in rows:
            kind, label = self._kind(rec, at), self._label(rec, at)
            print(f"  {source[:32]:32} {rec.get('last_records', 0):>8} "
                  f"{rec.get('last_new', 0):>6}  {label}")

        silent = [s for s, r in self.data.items() if self._kind(r, at) == "silent"]
        stale = [s for s, r in self.data.items() if self._kind(r, at) == "stale"]
        held = [s for s, r in self.data.items() if self._kind(r, at) == "quarantine"]
        broken = [s for s, r in self.data.items() if self._kind(r, at) == "error"]

        if broken:
            print(f"  ! не ответили: {', '.join(sorted(broken))}")
        if silent:
            print(f"  ! молчат {SILENT_RUNS_TO_WARN}+ прогонов подряд: "
                  f"{', '.join(sorted(silent))}")
        if stale:
            print(f"  ! записи есть, но новых нет {STALE_RUNS_TO_WARN}+ прогонов: "
                  f"{', '.join(sorted(stale))}")
        for source in sorted(held):
            rec = self.data[source]
            since = _parse(rec.get("quarantined_at"))
            until = since + timedelta(days=QUARANTINE_RETRY_DAYS) if since else None
            when = f", следующая попытка {until.strftime('%d.%m')}" if until else ""
            print(f"  ! в карантине, не читаем: {source} "
                  f"(молчит {rec.get('silent_streak', 0)} прогонов{when})")

    def _kind(self, rec, at):
        """Классификация состояния источника — по ней строится отчёт."""
        if self._in_quarantine(rec, at):
            return "quarantine"
        if rec.get("status") == ERROR:
            return "error"
        if rec.get("silent_streak", 0) >= SILENT_RUNS_TO_WARN:
            return "silent"
        if rec.get("stale_streak", 0) >= STALE_RUNS_TO_WARN:
            return "stale"
        return "ok"

    def _in_quarantine(self, rec, at):
        since = _parse(rec.get("quarantined_at"))
        if since is None:
            return False
        return at - since < timedelta(days=QUARANTINE_RETRY_DAYS)

    def _label(self, rec, at):
        kind = self._kind(rec, at)
        streak = rec.get("silent_streak", 0)
        if kind == "quarantine":
            return f"карантин, молчит {streak} прогонов"
        if kind == "error":
            return f"ошибка: {rec.get('last_note', '')[:40]}"
        if kind == "silent":
            # Важно различать: пустая лента и «не по нашей теме» — разные
            # поломки, и чинятся они по-разному.
            what = "лента пуста" if rec.get("status") == EMPTY else "не проходит фильтр"
            return f"{what}, {streak} прогонов подряд"
        if kind == "stale":
            return f"не обновляется {rec.get('stale_streak', 0)} прогонов"
        return "работает"
