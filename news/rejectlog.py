"""Журнал отказов: что и почему не попало на сайт.

Фильтры проекта строгие: не про ИИ — не берём, не удалёнка — не берём.
Это правильно, но у строгости есть цена. Если правило окажется слишком
широким, хороший материал пропадёт молча: в логе сборки видно только
«отброшено N записей», а какие именно и за что — нет. Однажды так и вышло
с рубрикой «Вакансии»: заголовок приходил пустым, записи отбрасывались,
и источник выглядел рабочим, хотя не давал ничего.

Журнал лежит в data/rejects.json — рядом с накопителями и так же в git.
Он не временный: смысл как раз в том, чтобы через неделю можно было
посмотреть, что и за что отсеялось.

Записи дедуплицируются по паре «заголовок + причина»: ленты отдают одни и
те же материалы шесть раз в день, и без дедупликации журнал превратился бы
в ленту повторов. Вместо этого у записи есть счётчик срабатываний и даты
первого и последнего отказа.
"""

import json
import os

from .config import DATA_DIR
from .store import write_if_changed
from .util import norm_title, now_msk

# Сколько уникальных отказов держим. Полная история не нужна: журнал нужен,
# чтобы разбирать текущие правила, а не восстанавливать архив.
MAX_ITEMS = 400

# Сколько записей одной причины оставляем. Квота нужна потому, что причины
# очень разного веса: «нет признака ИИ» за один прогон даёт больше двух тысяч
# записей, а «не ИИ-профессия (слово в описании)» — девятнадцать. Без квоты
# частые причины вытесняют редкие, и из журнала пропадает ровно то, ради чего
# он заведён: единичные случаи, которые надо разбирать руками.
MAX_PER_REASON = 60

# Порог, после которого причин становится слишком много, чтобы их читать.
# Если он превышен — значит, причина пишется с подробностями, которых не должно
# быть в тексте: в журнал идут короткие формулировки из filters.py.
MAX_REASONS = 40


class RejectLog:
    """Собирает отказы за прогон и хранит их между сборками."""

    def __init__(self, path=None):
        self.path = path or os.path.join(DATA_DIR, "rejects.json")
        self.runs = 0
        self.total = 0
        self.by_reason = {}
        self.items = {}
        self.run_total = 0
        self.run_reasons = {}
        self._load()

    def _load(self):
        """Читает прошлый журнал. Нет файла или он битый — начинаем заново."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return
        self.runs = int(data.get("runs", 0) or 0)
        self.total = int(data.get("total_rejected", 0) or 0)
        self.by_reason = dict(data.get("by_reason", {}) or {})
        for rec in data.get("items", []) or []:
            key = self._key(rec.get("title", ""), rec.get("reason", ""))
            if key:
                self.items[key] = rec

    @staticmethod
    def _key(title, reason):
        return norm_title(title) + "|" + (reason or "")

    def add(self, title, source, reason, link=""):
        """Записывает отказ. Заголовок без текста пропускаем — его не с чем сравнить."""
        title = (title or "").strip()
        if not title:
            return
        today = now_msk().strftime("%Y-%m-%d")

        self.run_total += 1
        self.total += 1
        self.run_reasons[reason] = self.run_reasons.get(reason, 0) + 1
        self.by_reason[reason] = self.by_reason.get(reason, 0) + 1

        key = self._key(title, reason)
        rec = self.items.get(key)
        if rec is None:
            self.items[key] = {
                "title": title,
                "source": source or "",
                "reason": reason,
                "link": link or "",
                "first": today,
                "last": today,
                "count": 1,
            }
        else:
            rec["count"] = int(rec.get("count", 1)) + 1
            rec["last"] = today
            # Ссылка могла не приехать в первом отказе (например, её отсеял
            # safe_link) — заполняем, когда появится.
            if link and not rec.get("link"):
                rec["link"] = link

    def _keep(self):
        """Отбирает записи для хранения: не больше MAX_PER_REASON на причину."""
        rows = sorted(self.items.values(),
                      key=lambda r: (r.get("last", ""), r.get("count", 0)),
                      reverse=True)
        kept, per_reason = [], {}
        for rec in rows:
            reason = rec.get("reason", "")
            if per_reason.get(reason, 0) >= MAX_PER_REASON:
                continue
            per_reason[reason] = per_reason.get(reason, 0) + 1
            kept.append(rec)
            if len(kept) >= MAX_ITEMS:
                break
        return kept

    def save(self):
        """Пишет журнал на диск. Счётчик прогонов растёт здесь же."""
        rows = self._keep()
        self.runs += 1
        data = {
            "updated": now_msk().strftime("%d.%m.%Y, %H:%M"),
            "runs": self.runs,
            "total_rejected": self.total,
            "last_run": {
                "total": self.run_total,
                "by_reason": self._sorted(self.run_reasons),
            },
            "by_reason": self._sorted(self.by_reason),
            "items": rows,
        }
        write_if_changed(self.path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")

    @staticmethod
    def _sorted(counters):
        return dict(sorted(counters.items(), key=lambda kv: (-kv[1], kv[0])))

    def report(self):
        """Печатает сводку по текущему прогону — она идёт в лог сборки."""
        if not self.run_total:
            print("  Отказов за прогон нет")
            return
        print(f"  Отклонено за прогон: {self.run_total}")
        for reason, count in sorted(self.run_reasons.items(), key=lambda kv: -kv[1]):
            print(f"    {count:>5}  {reason}")
        if len(self.by_reason) > MAX_REASONS:
            print(f"    ! причин стало {len(self.by_reason)} — формулировки пора укрупнить")


def note(log, title, source, reason, link=""):
    """Записывает отказ, если журнал подключён. Без журнала — молча ничего.

    Журнал необязателен: разбор лент работает и без него — так его зовут тесты
    и старые скрипты. Проверка на None живёт здесь, а не в каждом месте вызова.
    """
    if log is not None:
        log.add(title, source, reason, link)
