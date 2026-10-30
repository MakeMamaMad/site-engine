"""Offline Instagram profile audit using the upstream 12-part rubric."""
from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

from ..intelligence.common import clean


NAME_LIMIT = 30  # Conservative limit from the upstream rubric; verify in the live UI before editing.
BIO_LIMIT = 150
RUBRIC = (
    ("name_field", 12), ("bio_first_line", 12), ("bio_body", 8),
    ("pinned_three", 10), ("link", 8), ("highlights", 8),
    ("grid_legibility", 8), ("photo", 6), ("handle", 6),
    ("category_contact", 6), ("recent_activity", 10), ("story_presence", 6),
)
IMPORTANT_INPUTS = {
    "handle", "profile_name", "bio", "website_link", "highlights",
    "pinned_publications", "grid_covers",
}
SEARCH_TERMS = ("груз", "коммерческ", "спецтех", "логист", "перевоз", "автопарк", "полуприцеп")


def _item(criterion: str, score: int, maximum: int, finding: str, verified: bool = True) -> dict[str, Any]:
    return {"criterion": criterion, "score": score, "maximum": maximum, "finding": finding, "verified": verified}


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _name_variants() -> list[str]:
    variants = [
        "СпецАвтоПортал | грузовики",
        "САП | коммерческий транспорт",
        "Грузовая техника | САП",
    ]
    assert all(len(value) <= NAME_LIMIT for value in variants)
    return variants


def _bio_variants() -> list[str]:
    variants = [
        "Новости грузовой техники и рынка. Для перевозчиков и автопарков. Свежие материалы — по ссылке ниже.",
        "Коммерческий транспорт без рекламного шума. Техника, рынок, регламенты. Читать новые разборы ↓",
        "Для водителей, автопарков и логистики: грузовики, прицепы, правила. Полный материал — на сайте ↓",
    ]
    assert all(len(value) <= BIO_LIMIT for value in variants)
    return variants


def audit_profile(profile: dict[str, Any], *, as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or date.today()
    missing = sorted(key for key in IMPORTANT_INPUTS if not profile.get(key))
    warnings = [{"code": "missing_profile_input", "field": key} for key in missing]
    rows: list[dict[str, Any]] = []

    name = clean(profile.get("profile_name"))
    name_searchable = any(term in name.lower() for term in SEARCH_TERMS)
    if not name:
        rows.append(_item("name_field", 0, 12, "Name field not supplied.", False))
    elif len(name) > NAME_LIMIT:
        rows.append(_item("name_field", 2, 12, f"Name exceeds the conservative {NAME_LIMIT}-character limit."))
    elif name_searchable:
        rows.append(_item("name_field", 12, 12, "Name is concise and includes a searchable transport term."))
    else:
        rows.append(_item("name_field", 6, 12, "Name fits but lacks a searched commercial-transport term."))

    bio = clean(profile.get("bio"))
    first_line = clean(str(profile.get("bio") or "").splitlines()[0] if bio else "")
    audience = any(term in first_line.lower() for term in SEARCH_TERMS)
    outcome = any(term in first_line.lower() for term in ("новост", "разбор", "рынок", "выбор", "правил", "техник"))
    rows.append(_item(
        "bio_first_line", 12 if first_line and audience and outcome else 5 if first_line else 0, 12,
        "First line names the audience and editorial value." if first_line and audience and outcome else "First line does not clearly combine audience and value." if first_line else "Bio not supplied.",
        bool(first_line),
    ))
    body_ok = bool(bio) and len(bio) <= BIO_LIMIT and len(bio) > len(first_line) + 5
    rows.append(_item(
        "bio_body", 8 if body_ok else 3 if bio and len(bio) <= BIO_LIMIT else 0, 8,
        "Bio fits and provides a second concrete reason to follow." if body_ok else f"Bio needs concise proof, offer or next step within {BIO_LIMIT} characters.",
        bool(bio),
    ))

    pinned = profile.get("pinned_publications") or []
    roles = {clean(row.get("role")) for row in pinned if isinstance(row, dict)}
    full_roles = {"proof", "explanation", "introduction"}
    pin_score = 10 if len(pinned) == 3 and full_roles <= roles else 6 if len(pinned) == 3 else min(4, len(pinned))
    rows.append(_item("pinned_three", pin_score, 10, "Three distinct pinned jobs are covered." if pin_score == 10 else "Use exactly three pins: proof, explanation and introduction.", bool(pinned)))

    link = clean(profile.get("website_link"))
    rows.append(_item("link", 8 if _valid_url(link) else 0, 8, "One valid website destination is supplied." if _valid_url(link) else "A single valid destination was not supplied.", bool(link)))

    highlights = [clean(value) for value in profile.get("highlights") or [] if clean(value)]
    highlight_score = 8 if 4 <= len(highlights) <= 6 else 4 if 1 <= len(highlights) <= 8 else 0
    rows.append(_item("highlights", highlight_score, 8, "Highlight count supports buyer questions." if highlight_score == 8 else "Use four to six buyer-question highlights.", bool(highlights)))

    covers = [clean(value) for value in profile.get("grid_covers") or [] if clean(value)]
    legible = sum(1 for value in covers[:9] if 2 <= len(value.split()) <= 8)
    grid_score = 8 if len(covers) >= 9 and legible >= 7 else 4 if covers else 0
    rows.append(_item("grid_legibility", grid_score, 8, f"{legible} of the first {min(9, len(covers))} supplied covers are concise." if covers else "Grid covers not supplied.", bool(covers)))

    photo = clean(profile.get("photo_description"))
    rows.append(_item("photo", 4 if photo else 0, 6, "Photo description supplied; visual crop still needs manual review." if photo else "Profile photo not supplied for review.", bool(photo)))

    handle = clean(profile.get("handle"))
    readable_handle = bool(re.fullmatch(r"@[A-Za-z0-9.]{3,30}", handle)) and "__" not in handle
    rows.append(_item("handle", 6 if readable_handle else 2 if handle else 0, 6, "Handle is readable and sayable." if readable_handle else "Handle is missing or needs manual readability review.", bool(handle)))

    category = clean(profile.get("category"))
    contact = clean(profile.get("contact_method"))
    rows.append(_item("category_contact", 6 if category and contact else 3 if category or contact else 0, 6, "Category and contact method supplied." if category and contact else "Category/contact data is incomplete.", bool(category and contact)))

    last_post = clean(profile.get("last_post_date"))
    recent_score = 0
    if last_post:
        try:
            days = (as_of - date.fromisoformat(last_post[:10])).days
            recent_score = 10 if 0 <= days <= 7 and profile.get("recent_comments_replied") is True else 6 if 0 <= days <= 7 else 2
        except ValueError:
            warnings.append({"code": "invalid_profile_date", "field": "last_post_date"})
    rows.append(_item("recent_activity", recent_score, 10, "Recent posting and replies verified." if recent_score == 10 else "Recent activity/replies not fully verified.", bool(last_post)))

    story_known = "story_active" in profile
    rows.append(_item("story_presence", 6 if profile.get("story_active") is True else 0, 6, "Current Story presence supplied." if story_known else "Story presence not supplied.", story_known))

    total = sum(row["score"] for row in rows)
    unverified = [row["criterion"] for row in rows if not row["verified"]]
    verified = not missing and not unverified
    if unverified:
        warnings.append({"code": "score_not_fully_verified", "criteria": unverified})
    bios = _bio_variants()
    names = _name_variants()
    return {
        "schema": 1,
        "module": "ig-profile-adaptation",
        "advisory_only": True,
        "data_classification": clean(profile.get("data_classification")) or "owner_supplied_profile_snapshot",
        "verification_status": "fully_scored" if verified else "partial_unverified",
        "total_score": total,
        "maximum_score": 100,
        "score_is_fully_verified": verified,
        "criteria": rows,
        "missing_data_warnings": warnings,
        "current_copy": {"handle": handle, "profile_name": name, "bio": bio, "website_link": link},
        "proposed_copy": {
            "profile_names": [{"text": value, "characters": len(value), "limit": NAME_LIMIT} for value in names],
            "bios": [{"text": value, "characters": len(value), "limit": BIO_LIMIT} for value in bios],
        },
        "pinned_strategy": [
            {"slot": 1, "job": "proof", "recommendation": "Закрепить сильный подтверждённый разбор или результат редакционной работы."},
            {"slot": 2, "job": "explanation", "recommendation": "Объяснить, какие темы и форматы получает подписчик."},
            {"slot": 3, "job": "introduction", "recommendation": "Коротко представить СпецАвтоПортал и редакционный подход."},
        ],
        "highlight_recommendations": ["Новости", "Техника", "Регламенты", "Разборы", "О проекте"],
        "grid_cover_suggestions": [
            "Один проверяемый тезис на обложке", "Не более 4–6 слов", "Марка и модель без сокращений",
            "Единая оранжевая метка рубрики", "Контрастный текст в центральной безопасной зоне",
        ],
        "website_conversion_path": {
            "bio_cta": "Свежие материалы — по ссылке ниже.",
            "destination": link or "owner_must_supply_one_canonical_destination",
            "path": "Профиль → одна ссылка → свежий материал или тематическая подборка",
        },
        "limits": {"profile_name_characters": NAME_LIMIT, "bio_characters": BIO_LIMIT, "name_limit_note": "Conservative upstream rubric limit; confirm against the account edit UI before applying."},
        "profile_modified": False,
    }
