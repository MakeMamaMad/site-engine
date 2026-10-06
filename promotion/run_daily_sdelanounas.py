#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "frontend/data/news.json"
HISTORY_PATH = ROOT / "frontend/data/promotion/editorial_history.json"
PUBLISHER = ROOT / "promotion/publish_sdelanounas.py"
MSK = timezone(timedelta(hours=3))

TARGET_ID = "sdelanounas"

PRODUCTION_MARKERS = (
    "выпуст", "произвел", "произвёл", "представил", "запустил", "запущен",
    "начал выпуск", "начало выпуска", "открыл", "открыт", "собрал", "собран",
    "поставил", "поставлен", "локализ", "серийн", "введен", "введён",
    "разработал", "создал", "изготовил", "изготовлен", "модернизировал",
)
RUSSIA_MARKERS = (
    "росси", "камаз", "газ", "урал", "тонар", "чмзап", "umg", "ростсельмаш",
    "брянск", "челябинск", "миасс", "набережн", "нижн", "твер", "санкт-петербург",
    "петербург", "москв", "татарстан", "башкир", "екатеринбург", "калуга",
)
TECH_MARKERS = (
    "грузов", "тягач", "полуприцеп", "прицеп", "спецтех", "самосвал", "трактор",
    "экскаватор", "автокран", "погрузчик", "машиностро", "транспорт", "автобус",
    "шасси", "коммуналь", "дорожн", "двигател", "завод", "производств",
)
FUTURE_MARKERS = (
    "планирует", "планируют", "представит", "представят", "покажет", "покажут",
    "запустит", "запустят", "начнет", "начнёт", "начнут", "будет выпуск",
    "будут выпуск", "готовится", "намерен", "намерена", "ожидается",
)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("items", "news", "entries"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def clean(value: Any) -> str:
    raw = html.unescape(str(value or ""))
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def parse_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def row_day(row: dict[str, Any]) -> str:
    for key in ("published_at", "submitted_at", "created_at"):
        dt = parse_dt(row.get(key))
        if dt:
            return dt.astimezone(MSK).date().isoformat()
    return ""


def item_key(row: dict[str, Any]) -> str:
    value = str(row.get("id") or row.get("slug") or row.get("canonical_url") or row.get("url") or "").strip()
    return "news:" + value if value else ""


def slug_for(row: dict[str, Any]) -> str:
    slug = str(row.get("slug") or "").strip()
    if slug:
        return slug
    url = str(row.get("site_url") or row.get("canonical_url") or "").strip()
    match = re.search(r"/news/([^/?#]+)/?", url)
    return match.group(1) if match else ""


def haystack(row: dict[str, Any]) -> str:
    source = row.get("source") or {}
    source_name = source.get("name") if isinstance(source, dict) else source
    return " ".join(
        clean(x).lower()
        for x in (
            row.get("title"),
            row.get("summary"),
            row.get("content_html"),
            row.get("category"),
            source_name,
            " ".join(str(x) for x in (row.get("tags") or [])),
        )
    )


def suitable(row: dict[str, Any], now: datetime) -> tuple[bool, float]:
    title = clean(row.get("title"))
    slug = slug_for(row)
    if not title or not slug:
        return False, 0.0

    # Never send «Сделано у нас» its own news back.
    link = str(row.get("link") or row.get("url") or row.get("source_url") or "")
    if "sdelanounas.ru" in link or "sdelanounas.ru" in str(row.get("domain") or ""):
        return False, 0.0

    text = haystack(row)
    if any(marker in text for marker in FUTURE_MARKERS):
        return False, 0.0
    if not any(marker in text for marker in PRODUCTION_MARKERS):
        return False, 0.0
    if not any(marker in text for marker in RUSSIA_MARKERS):
        return False, 0.0
    if not any(marker in text for marker in TECH_MARKERS):
        return False, 0.0

    published = parse_dt(row.get("published_at") or row.get("date"))
    if not published or now - published > timedelta(days=5):
        return False, 0.0

    score = 0.0
    score += 3.0 * sum(1 for marker in PRODUCTION_MARKERS if marker in text)
    score += 1.6 * sum(1 for marker in TECH_MARKERS if marker in text)
    score += 1.2 * sum(1 for marker in RUSSIA_MARKERS if marker in text)
    if published:
        age_h = max(0.0, (now - published).total_seconds() / 3600)
        score += max(0.0, 5.0 - age_h / 12.0)
    return True, score


def make_body(row: dict[str, Any], tracking_url: str) -> str:
    title = clean(row.get("title"))
    summary = clean(row.get("summary"))
    content = clean(row.get("content_html"))
    base = content if len(content) >= 350 else summary
    if len(base) < 120:
        return ""
    if len(base) > 3200:
        base = base[:3200].rsplit(" ", 1)[0].rstrip(" ,.;:-") + "…"
    if title and base.lower().startswith(title.lower()):
        base = base[len(title):].lstrip(" .:—-")
    return (base + "\n\nИсточник и подробности: " + tracking_url).strip()


def make_tags(row: dict[str, Any]) -> str:
    raw = [clean(x) for x in (row.get("tags") or []) if clean(x)]
    text = haystack(row)
    defaults = ["спецтехника", "машиностроение", "производство"]
    if "груз" in text:
        defaults.append("грузовая техника")
    if "полуприц" in text or "прицеп" in text:
        defaults.append("полуприцепы")
    tags: list[str] = []
    for value in raw + defaults:
        if value and value.lower() not in {x.lower() for x in tags}:
            tags.append(value)
    return ", ".join(tags[:8])


def main() -> int:
    now = datetime.now(timezone.utc)
    today = now.astimezone(MSK).date().isoformat()
    history = load_json(HISTORY_PATH, {"schema": 1, "entries": []})
    rows = [x for x in history.get("entries", []) if isinstance(x, dict)]

    if any(
        row.get("target_id") == TARGET_ID
        and row_day(row) == today
        and str(row.get("status") or "") in {"submitted", "published", "verified_in_author_cabinet"}
        for row in rows
    ):
        print("SDELANOUNAS_DAILY_SKIP already_posted_today")
        return 0

    used = {
        str(row.get("item_key") or "")
        for row in rows
        if row.get("target_id") == TARGET_ID
    }

    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in items(load_json(NEWS_PATH, {"items": []})):
        key = item_key(row)
        if not key or key in used:
            continue
        ok, score = suitable(row, now)
        if ok:
            candidates.append((score, row))

    if not candidates:
        print("SDELANOUNAS_DAILY_NO_TARGET")
        return 0

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    score, picked = candidates[0]
    slug = slug_for(picked)
    key = item_key(picked)
    title = clean(picked.get("title"))[:180]
    tracking_url = (
        f"https://spec-avtoportal.ru/news/{quote(slug)}/"
        f"?utm_source=sdelanounas&utm_medium=editorial"
        f"&utm_campaign=industry_promotion&utm_content={quote(slug)}"
    )
    body = make_body(picked, tracking_url)
    if not body:
        print("SDELANOUNAS_DAILY_NO_TARGET selected_item_too_short")
        return 0

    env = os.environ.copy()
    env.update(
        {
            "PROMOTION_LIVE": "1",
            "SDELANOUNAS_TITLE": title,
            "SDELANOUNAS_SOURCE_URL": tracking_url,
            "SDELANOUNAS_BODY": body,
            "SDELANOUNAS_TAGS": make_tags(picked),
            "SDELANOUNAS_ITEM_KEY": key,
        }
    )
    print(
        "SDELANOUNAS_DAILY_PICK "
        + json.dumps(
            {"title": title, "item_key": key, "slug": slug, "score": round(score, 2)},
            ensure_ascii=False,
        )
    )
    proc = subprocess.run(
        [sys.executable, str(PUBLISHER)],
        cwd=ROOT,
        env=env,
        text=True,
        check=False,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
