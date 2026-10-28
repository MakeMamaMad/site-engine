from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .buffer import publish_video as publish_buffer_video
from .youtube import upload_video


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "out_v2"
SOCIAL_STATE_PATH = ROOT / "state" / "social_v2.json"
V2_STATE_PATH = ROOT / "state" / "v2.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_social_state() -> dict[str, Any]:
    state = _read_json(SOCIAL_STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("schema", 1)
    state.setdefault("content", {})
    return state


def _platform_done(entry: dict[str, Any], platform: str) -> bool:
    record = (entry.get("platforms") or {}).get(platform) or {}
    return record.get("status") in {"published", "submitted", "draft_uploaded"}


def _record(
    state: dict[str, Any],
    content_key: str,
    *,
    title: str,
    platform: str,
    result: dict[str, Any],
) -> None:
    content = state.setdefault("content", {})
    entry = content.setdefault(content_key, {
        "title": title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platforms": {},
    })
    entry["title"] = title
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()
    entry.setdefault("platforms", {})[platform] = {
        **result,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(SOCIAL_STATE_PATH, state)


def _mark_v2_used(content_key: str, slug: str, title: str) -> None:
    state = _read_json(V2_STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("schema", 1)
    used = [str(x) for x in state.get("used", []) if str(x)]
    if content_key not in used:
        used.append(content_key)
    state["used"] = used[-2000:]

    renders = state.get("renders", [])
    if not isinstance(renders, list):
        renders = []
    if not any(str(x.get("content_key")) == content_key for x in renders if isinstance(x, dict)):
        renders.append({
            "content_key": content_key,
            "slug": slug,
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "format": "social-v2",
        })
    state["renders"] = renders[-500:]
    _write_json(V2_STATE_PATH, state)


def _configured_platforms(raw: str) -> list[str]:
    allowed = {"youtube", "instagram", "tiktok"}
    values = []
    for value in raw.split(","):
        name = value.strip().lower()
        if name and name in allowed and name not in values:
            values.append(name)
    return values


def _caption(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _tag_site_links(text: str, platform: str) -> str:
    """Add UTM tags to our own links so Metrika shows visits from each platform."""
    def tag(match: "re.Match[str]") -> str:
        url = match.group(0)
        if "utm_source=" in url:
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}utm_source={platform}&utm_medium=video&utm_campaign=shorts"
    return re.sub(r"https://spec-avtoportal\.ru/[^\s)\]]*", tag, text)


def _auth_error(record: dict[str, Any]) -> bool:
    if record.get("status") != "error":
        return False
    text = str(record.get("error") or "")
    return "HTTP 401" in text or "UNAUTHENTICATED" in text or "Access token is not valid" in text


def _with_site_link(text: str, platform: str = "youtube") -> str:
    site_url = os.getenv("SITE_URL", "https://spec-avtoportal.ru/").strip() or "https://spec-avtoportal.ru/"
    clean = text.strip()
    if site_url.rstrip("/") not in clean:
        clean = (clean + "\n\nПодробнее на сайте: " + site_url) if clean else site_url
    return _tag_site_links(clean, platform)


def publish_all(*, dry_run: bool = False) -> dict[str, Any]:
    manifest = _read_json(OUT_DIR / "manifest.json", {})
    board = _read_json(OUT_DIR / "scene_plan.json", {})
    if not isinstance(manifest, dict) or not manifest.get("content_key"):
        raise RuntimeError("Short v2 manifest is missing; run src.v2_main first")
    if not isinstance(board, dict):
        board = {}

    content_key = str(manifest["content_key"])
    slug = str(manifest.get("slug") or "")
    title = str(board.get("title") or manifest.get("title") or "СпецАвтоПортал")
    master = OUT_DIR / "master.mp4"
    if not master.exists():
        raise RuntimeError(f"master video missing: {master}")

    platforms = _configured_platforms(os.getenv("SOCIAL_PLATFORMS", "youtube,tiktok,instagram"))
    state = _load_social_state()
    entry = (state.get("content") or {}).get(content_key) or {}
    summary: dict[str, Any] = {"content_key": content_key, "title": title, "platforms": {}}

    for platform in platforms:
        if _platform_done(entry, platform):
            previous = (entry.get("platforms") or {}).get(platform) or {}
            print(f"[social] {platform}: already {previous.get('status')}, skip")
            summary["platforms"][platform] = {"status": "already_done"}
            continue

        if dry_run:
            print(f"[social] {platform}: dry-run")
            summary["platforms"][platform] = {"status": "dry_run"}
            continue

        try:
            if platform == "youtube":
                token_file = Path(os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json"))
                if not token_file.exists():
                    raise RuntimeError("YOUTUBE_TOKEN_FILE missing")

                youtube_title = str(board.get("youtube_title") or title).strip()[:100]
                description = _with_site_link(_caption(OUT_DIR / "caption_youtube.txt"), "youtube")
                hashtags = board.get("hashtags") if isinstance(board.get("hashtags"), list) else []
                result_id = upload_video(
                    str(master),
                    title=youtube_title,
                    description=description,
                    tags=[str(x).lstrip("#") for x in hashtags[:8]],
                    privacy_status=os.getenv("YOUTUBE_PRIVACY", "public").strip(),
                )
                result = {
                    "platform": "youtube",
                    "status": "published",
                    "video_id": result_id,
                    "url": f"https://www.youtube.com/shorts/{result_id}" if result_id else "",
                }

            elif platform in {"tiktok", "instagram"}:
                api_key = os.getenv("BUFFER_API_KEY", "").strip()
                if not api_key:
                    raise RuntimeError("BUFFER_API_KEY missing")

                if platform == "tiktok":
                    video_url = os.getenv("BUFFER_TIKTOK_VIDEO_URL", "").strip()
                    caption = _with_site_link(_caption(OUT_DIR / "caption_tiktok.txt"), "tiktok")
                    preferred_name = os.getenv("BUFFER_TIKTOK_CHANNEL_NAME", "specavtoportal").strip()
                else:
                    video_url = os.getenv("BUFFER_INSTAGRAM_VIDEO_URL", "").strip()
                    caption = _with_site_link(_caption(OUT_DIR / "caption_instagram.txt"), "instagram")
                    preferred_name = os.getenv("BUFFER_INSTAGRAM_CHANNEL_NAME", "specavtoportal").strip()

                if not video_url:
                    raise RuntimeError(f"BUFFER_{platform.upper()}_VIDEO_URL missing")

                result = publish_buffer_video(
                    api_key=api_key,
                    service=platform,
                    preferred_name=preferred_name,
                    video_url=video_url,
                    text=caption,
                    wait_seconds=int(os.getenv("BUFFER_PUBLISH_WAIT_SECONDS", "120")),
                )

            else:
                continue

            print(f"[social] {platform}: {result.get('status')}")
            _record(state, content_key, title=title, platform=platform, result=result)
            entry = (state.get("content") or {}).get(content_key) or {}
            summary["platforms"][platform] = result

        except Exception as exc:
            error_result = {
                "platform": platform,
                "status": "error",
                "error": str(exc)[:1600],
            }
            print(f"[social] {platform}: ERROR {exc}")
            _record(state, content_key, title=title, platform=platform, result=error_result)
            entry = (state.get("content") or {}).get(content_key) or {}
            summary["platforms"][platform] = error_result

    final_entry = (state.get("content") or {}).get(content_key) or {}
    # An expired/revoked Buffer key is not fixed by retrying: every retry
    # re-rendered the same story and the daily slots stalled (24–27.10.2026).
    # Such platforms are reported and skipped; YouTube still must succeed.
    auth_blocked = [
        platform
        for platform in platforms
        if platform != "youtube" and _auth_error((final_entry.get("platforms") or {}).get(platform) or {})
    ]
    if auth_blocked:
        print(f"[social] WARNING Buffer authorization failed for {auth_blocked}: renew BUFFER_API_KEY; skipping them")
        summary["auth_blocked"] = auth_blocked
    required = [platform for platform in platforms if platform not in auth_blocked]
    all_done = bool(required) and all(_platform_done(final_entry, platform) for platform in required)
    if all_done:
        _mark_v2_used(content_key, slug, title)
        print(f"[social] complete: all configured platforms done for {content_key}")
    else:
        pending = [platform for platform in platforms if not _platform_done(final_entry, platform)]
        print(f"[social] incomplete: pending={pending}")

    if os.getenv("SOCIAL_STRICT", "0").strip() == "1" and not all_done:
        raise RuntimeError(f"social publish incomplete: {summary['platforms']}")

    print("[social] summary", json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    publish_all(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
