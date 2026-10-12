from datetime import datetime, timezone

from aggregator import main as collector
from aggregator.run import stamp_undated_new


def test_undated_new_items_get_first_seen_time():
    now = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)
    fresh = [
        {"link": "https://tonar.info/news/new-one", "published_at": None},
        {"link": "https://tonar.info/news/old-one", "published_at": None},
        {"link": "https://uralaz.ru/media/news/dated", "published_at": "2026-10-01T09:00:00+00:00"},
    ]
    existing_keys = {collector.item_key(fresh[1])}
    assert stamp_undated_new(fresh, existing_keys, now) == 1
    assert fresh[0]["published_at"] == "2026-10-12T06:00:00+00:00"
    assert fresh[0]["published_at_estimated"] is True
    assert fresh[1]["published_at"] is None
    assert fresh[2]["published_at"] == "2026-10-01T09:00:00+00:00"


def test_drop_excluded_by_source_title():
    sources = [{"title": "ТОНАР — новости завода", "exclude_keywords": ["помним", "с днём"]}]
    items = [
        {"source": "ТОНАР — новости завода", "title": "Помним. Чтим. Продолжаем..."},
        {"source": "ТОНАР — новости завода", "title": "С Днём машиностроителя!"},
        {"source": "ТОНАР — новости завода", "title": "Рекордно лёгкий Тонар SL4-23"},
        {"source": "Другой", "title": "Помним героев"},
    ]
    kept = collector.drop_excluded(items, sources)
    assert [x["title"] for x in kept] == ["Рекордно лёгкий Тонар SL4-23", "Помним героев"]
