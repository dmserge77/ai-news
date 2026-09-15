"""Отсев повторов.

Одну и ту же новость легко получить дважды, поэтому проверок две:
по ссылке и по «источник + заголовок + дата». Первой мало (одна статья
может прийти по разным адресам), второй тоже мало (две разные новости
могут совпасть по ссылке после редиректа).
"""

from .util import norm_title


def dedup_key(item):
    """Ключ уникальности новости: источник + заголовок + дата.

    Одну и ту же новость можно получить по РАЗНЫМ адресам, поэтому сверки
    по ссылке недостаточно. Реальный случай: vc.ru отдал статью 3139979
    в тегах #ai и #нейросети с разными слагами —
      vc.ru/ai/3139979-alisa-ai-vybirayet-rezhim-dlya-zadach
      vc.ru/ai/3139979-alisa-ai-sama-vybiraet-rezhim-kakie-zadachi-ei-teper-poruchat
    Ссылки разные, а новость одна. Дата в ключе нужна, чтобы не склеить
    разные выпуски с одинаковым названием (например, еженедельные дайджесты).
    """
    return (
        (item.get("source") or "").strip().lower(),
        norm_title(item.get("title")),
        (item.get("date") or "").strip(),
    )


class Seen:
    """Память о том, что уже добавлено в текущей сборке."""

    def __init__(self):
        self.links = set()
        self.keys = set()
        self.dups = 0

    def is_dup(self, item):
        """Новость уже попадалась? Сверяем ссылку и «источник+заголовок+дата»."""
        link = item.get("link") or ""
        if link and link in self.links:
            return True
        return dedup_key(item) in self.keys

    def mark(self, item):
        """Запоминаем новость как уже добавленную."""
        link = item.get("link") or ""
        if link:
            self.links.add(link)
        self.keys.add(dedup_key(item))

    def check(self, item):
        """Совмещает проверку и пометку. True — новость уже была, брать не нужно."""
        if self.is_dup(item):
            self.dups += 1
            return True
        self.mark(item)
        return False
