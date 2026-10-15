"""Weekly partner shorts about SAT semi-trailers (satpricep.by).

Episodes are hand-written in promotion/config/sat_shorts.json so every fact
comes from the manufacturer's catalog — no AI-invented specs or AI images of
a real product. The storyboard uses real photos and ends on a partner card.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..ai.storyboard import Scene, Storyboard

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPO_ROOT / "promotion" / "config" / "sat_shorts.json"
PHOTOS_PATH = REPO_ROOT / "promotion" / "config" / "sat_photos.json"
# SAT Test Drive promo (pricepvtest.online): same partner format, its own
# episodes, repeated in a cycle on Tuesday and Thursday evenings.
TESTDRIVE_PATH = REPO_ROOT / "promotion" / "config" / "sat_testdrive_shorts.json"
KEY_PREFIX = "sat:"


def load_config(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))


def episode_key(episode: dict[str, Any]) -> str:
    return str(episode.get("_key") or KEY_PREFIX + str(episode["id"]))


def pick_episode(config: dict[str, Any], used: list[str]) -> dict[str, Any] | None:
    """Next episode, or None (the slot then falls back to a news short).

    Normal catalogs: the first episode not yet published — never repeated.
    "cycle": true catalogs go round again, each round with its own key
    («testdrive:<id>#2»), so the publisher does not skip a repeat; "active":
    false switches the series off.
    """
    if config.get("active") is False:
        return None
    episodes = [e for e in config.get("episodes", []) if isinstance(e, dict) and e.get("id")]
    prefix = str(config.get("key_prefix") or KEY_PREFIX)
    if config.get("cycle") and episodes:
        count = sum(1 for key in used if str(key).startswith(prefix))
        episode = dict(episodes[count % len(episodes)])
        episode["_key"] = f"{prefix}{episode['id']}#{count // len(episodes) + 1}"
        return episode
    done = set(used)
    for episode in episodes:
        key = prefix + str(episode["id"])
        if key not in done:
            return dict(episode, _key=key)
    return None


def _photo_manifest(path: Path | None = None) -> dict[str, list[str]]:
    try:
        data = json.loads((path or PHOTOS_PATH).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {k: [str(REPO_ROOT / p) for p in v if (REPO_ROOT / p).is_file()] for k, v in data.items() if isinstance(v, list)}


def episode_photos(config: dict[str, Any], episode: dict[str, Any], manifest: dict[str, list[str]] | None = None) -> list[str]:
    """Explicit photos, else the model's catalog photos, else one photo of each model."""
    if episode.get("photos"):
        return [str(x) for x in episode["photos"]]
    manifest = _photo_manifest() if manifest is None else manifest
    own = manifest.get(str(episode.get("photo_url") or episode.get("url") or ""))
    if own:
        return own
    mixed = [photos[0] for photos in manifest.values() if photos]
    return mixed or [str(config.get("default_photo", ""))]


def _tagged(url: str, utm: str) -> str:
    return url + ("&" if "?" in url else "?") + utm if utm else url


def build_storyboard(config: dict[str, Any], episode: dict[str, Any]) -> Storyboard:
    utm = str(config.get("utm") or "")
    url = _tagged(str(episode.get("url") or config.get("url") or "https://satpricep.by/"), utm)
    domain = str(config.get("partner_domain") or "satpricep.by")
    photos = episode_photos(config, episode)
    title = str(episode["title"]).strip()
    hashtags = [str(x) for x in config.get("hashtags", [])][:8]

    scenes: list[Scene] = []
    for index, raw in enumerate(episode["scenes"], 1):
        scenes.append(Scene(
            id=f"sat-{index}",
            seconds=5.5,
            overlay=str(raw["overlay"]).strip(),
            narration=str(raw["narration"]).strip(),
            visual_prompt="",
            highlight_words=[],
            source_image_url=str(photos[(index - 1) % len(photos)]),
        ))
    scenes.append(Scene(
        id="cta-partner",
        seconds=float(config.get("cta_seconds") or 4.5),
        overlay=domain,
        narration=str(config.get("cta_narration") or "Цены и комплектации — на сайте производителя, ссылка в описании. Подписывайтесь на СпецАвтоПортал."),
        visual_prompt="",
        highlight_words=[],
        source_image_url=str(photos[0]),
        cta_lead=[str(x) for x in (config.get("cta_lead") or [])][:2],
    ))

    body = "\n".join(f"— {s.overlay}" for s in scenes[:-1])
    link_line = str(config.get("link_line") or "Цены и комплектации у производителя: {url}").format(url=url)
    disclaimer = str(config.get("disclaimer") or "Реклама. Партнёрский материал о полуприцепах SAT.")
    description = (
        f"{title}\n\n{body}\n\n"
        f"{link_line}\n\n"
        f"{disclaimer}\n\n"
        + " ".join(hashtags)
    )
    return Storyboard(
        version=2,
        format="partner",
        title=title,
        hook=scenes[0].overlay,
        voiceover=" ".join(s.narration for s in scenes),
        instagram_caption=description,
        tiktok_caption=f"{title}. Реклама. {' '.join(hashtags[:4])}",
        youtube_title=title[:100],
        youtube_description=description,
        hashtags=hashtags,
        source_urls=[url],
        scenes=scenes,
    )
