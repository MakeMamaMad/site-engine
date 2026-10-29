from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Scene:
    id: str
    seconds: float
    overlay: str
    narration: str
    visual_prompt: str
    highlight_words: list[str] = field(default_factory=list)
    source_image_url: str = ""
    # Ending card only: two short lines above the partner domain
    # (default: «ЦЕНЫ И КОМПЛЕКТАЦИИ / — У ПРОИЗВОДИТЕЛЯ»).
    cta_lead: list[str] = field(default_factory=list)


@dataclass
class Storyboard:
    version: int
    format: str
    title: str
    hook: str
    voiceover: str
    instagram_caption: str
    tiktok_caption: str
    youtube_title: str
    youtube_description: str
    hashtags: list[str]
    source_urls: list[str]
    scenes: list[Scene]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _title(item: dict[str, Any]) -> str:
    return _clean(item.get("title") or item.get("headline") or item.get("name"))


def _summary(item: dict[str, Any]) -> str:
    return _clean(item.get("summary") or item.get("description") or item.get("excerpt"))


SITE_BASE = "https://spec-avtoportal.ru"


def _url(item: dict[str, Any]) -> str:
    """Our own article page for the news item — never the original source.

    Videos get ~1k views each; the "details" link must bring viewers to
    spec-avtoportal.ru, not to the source site.
    """
    explicit = _clean(item.get("site_url"))
    if explicit.startswith(SITE_BASE):
        return explicit
    slug = _clean(item.get("slug"))
    if slug and _has_site_page(item):
        return f"{SITE_BASE}/news/{slug}/"
    return f"{SITE_BASE}/"


def _has_site_page(item: dict[str, Any]) -> bool:
    """Only news that pass the site's quality gate get a /news/<slug>/ page."""
    try:
        import sys
        from pathlib import Path

        tools_dir = str(Path(__file__).resolve().parents[3])
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import build_seo  # type: ignore

        return build_seo.is_public_news(item)
    except Exception:
        return True


def _image(item: dict[str, Any]) -> str:
    value = _clean(item.get("image_url") or item.get("image") or item.get("thumbnail"))
    return value if value.startswith("http") else ""


def _scene_prompt(subject: str, angle: str) -> str:
    return (
        "Cinematic editorial photograph for a premium commercial-transport news reel. "
        f"Subject: {subject}. Scene: {angle}. "
        "Realistic European heavy truck / semi-trailer industry, physically plausible machinery, "
        "charcoal industrial palette with restrained orange light accents, dramatic but credible lighting, "
        "high detail, vertical composition, strong depth, clean negative space for editorial overlays. "
        "No text, no captions, no logos, no watermarks, no fake brand marks, no readable license plates."
    )


def fallback_storyboard(item: dict[str, Any]) -> Storyboard:
    title = _title(item) or "Главная новость отрасли"
    summary = _summary(item) or "Разбираем, что произошло и почему это важно для рынка коммерческого транспорта."
    url = _url(item)
    image = _image(item)

    hook = title
    if len(hook) > 72:
        hook = hook[:69].rsplit(" ", 1)[0] + "…"

    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", summary) if x.strip()]
    key_fact = sentences[0] if sentences else summary
    why = sentences[1] if len(sentences) > 1 else "Это может повлиять на перевозчиков, стоимость эксплуатации и планы закупок."

    scenes = [
        Scene(
            id="hook",
            seconds=4.2,
            overlay=hook,
            narration=f"{title}.",
            visual_prompt=_scene_prompt(title, "hero shot, immediate visual hook"),
            highlight_words=[w for w in re.findall(r"[0-9+%]+|[А-ЯA-ZЁ]{3,}", title)[:3]],
            source_image_url=image,
        ),
        Scene(
            id="fact",
            seconds=6.2,
            overlay="ЧТО ПРОИЗОШЛО",
            narration=key_fact,
            visual_prompt=_scene_prompt(title, "documentary detail showing the core event"),
            highlight_words=[],
            source_image_url=image,
        ),
        Scene(
            id="meaning",
            seconds=6.4,
            overlay="ПОЧЕМУ ЭТО ВАЖНО",
            narration=why,
            visual_prompt=_scene_prompt(title, "operational context: fleet, logistics, workshop or road transport"),
            highlight_words=["важно"],
            source_image_url=image,
        ),
        Scene(
            id="impact",
            seconds=6.0,
            overlay="ДЛЯ РЫНКА",
            narration="Следим за развитием темы и тем, как она отразится на технике, логистике и стоимости владения.",
            visual_prompt=_scene_prompt(title, "wide industrial transport scene, analytical mood"),
            highlight_words=["рынка"],
            source_image_url=image,
        ),
        Scene(
            id="cta",
            seconds=4.2,
            overlay="ПОДРОБНЕЕ НА САЙТЕ",
            narration="Полная новость — на сайте СпецАвтоПортал. Подписывайтесь, чтобы не пропустить главное.",
            visual_prompt=_scene_prompt(title, "clean closing hero shot with dark negative space"),
            highlight_words=["СпецАвтоПортале"],
            source_image_url=image,
        ),
    ]
    voiceover = " ".join(scene.narration for scene in scenes)
    hashtags = ["#СпецАвтоПортал", "#грузовики", "#полуприцепы", "#логистика", "#автоновости"]
    caption = f"{title}\n\n{key_fact}\n\nПодробности: {url or 'spec-avtoportal.ru'}\n\n{' '.join(hashtags)}"
    return Storyboard(
        version=2,
        format="breaking",
        title=title,
        hook=hook,
        voiceover=voiceover,
        instagram_caption=caption,
        tiktok_caption=f"{hook} — коротко разбираем, что это значит. {' '.join(hashtags[:4])}",
        youtube_title=hook,
        youtube_description=caption,
        hashtags=hashtags,
        source_urls=[url] if url else [],
        scenes=scenes,
    )


def _extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    fence = chr(96) * 3
    if value.startswith(fence):
        first_newline = value.find("\n")
        value = value[first_newline + 1 :] if first_newline >= 0 else value
        if value.rstrip().endswith(fence):
            value = value.rstrip()[:-3].rstrip()
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        value = value[start : end + 1]
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("AI storyboard must be a JSON object")
    return parsed


def _validate_ai_storyboard(data: dict[str, Any], item: dict[str, Any]) -> Storyboard:
    fallback = fallback_storyboard(item)
    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list) or not (4 <= len(raw_scenes) <= 6):
        raise ValueError("AI storyboard must contain 4-6 scenes")

    scenes: list[Scene] = []
    for index, raw in enumerate(raw_scenes, 1):
        if not isinstance(raw, dict):
            raise ValueError("Invalid scene")
        narration = _clean(raw.get("narration"))
        overlay = _clean(raw.get("overlay"))
        prompt = _clean(raw.get("visual_prompt"))
        if not narration or not overlay or not prompt:
            raise ValueError("Scene is missing narration/overlay/visual_prompt")
        seconds = float(raw.get("seconds") or 5.5)
        seconds = max(3.0, min(8.0, seconds))
        highlights = raw.get("highlight_words") if isinstance(raw.get("highlight_words"), list) else []
        scenes.append(Scene(
            id=_clean(raw.get("id")) or f"scene-{index}",
            seconds=seconds,
            overlay=overlay[:90],
            narration=narration[:340],
            visual_prompt=prompt[:1600],
            highlight_words=[_clean(x) for x in highlights[:5] if _clean(x)],
            source_image_url=fallback.scenes[min(index - 1, len(fallback.scenes) - 1)].source_image_url,
        ))

    total = sum(x.seconds for x in scenes)
    if total < 20 or total > 40:
        factor = 30.0 / max(total, 1.0)
        for scene in scenes:
            scene.seconds = max(3.0, min(8.0, scene.seconds * factor))

    # Every short ends with our own call-to-action scene (big site address and
    # subscribe prompt are drawn by the renderer on the last frame). An AI
    # closing line about "the site" is replaced; real content is kept.
    cta = next(x for x in fallback.scenes if x.id == "cta")
    last = scenes[-1]
    if last.id.lower() == "cta" or re.search(r"сайт|подпис|подробн", last.narration.lower()):
        scenes[-1] = cta
    else:
        scenes.append(cta)

    hashtags = data.get("hashtags") if isinstance(data.get("hashtags"), list) else fallback.hashtags
    hashtags = [str(x).strip() for x in hashtags if str(x).strip()][:8]
    voiceover = " ".join(x.narration for x in scenes)
    return Storyboard(
        version=2,
        format=(_clean(data.get("format")).lower() if _clean(data.get("format")).lower() in {"breaking", "explainer"} else "breaking"),
        title=_clean(data.get("title")) or fallback.title,
        hook=_clean(data.get("hook")) or fallback.hook,
        voiceover=voiceover,
        instagram_caption=_clean(data.get("instagram_caption")) or fallback.instagram_caption,
        tiktok_caption=_clean(data.get("tiktok_caption")) or fallback.tiktok_caption,
        youtube_title=_clean(data.get("youtube_title")) or fallback.youtube_title,
        youtube_description=_clean(data.get("youtube_description")) or fallback.youtube_description,
        hashtags=hashtags or fallback.hashtags,
        source_urls=fallback.source_urls,
        scenes=scenes,
    )


def generate_storyboard(item: dict[str, Any]) -> Storyboard:
    """Build an AI storyboard when configured, otherwise use a deterministic fallback."""
    from .growth_agent import (
        build_fallback_storyboard,
        enhance_storyboard,
        is_enabled,
        mark_legacy_fallback,
        validate_storyboard,
    )

    growth_enabled = is_enabled()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or os.getenv("AI_SCRIPT", "1").strip() != "1":
        if growth_enabled:
            try:
                return build_fallback_storyboard(item, reason="AI script generation is unavailable")
            except Exception as exc:
                print(f"[growth] safe fallback unavailable: {exc}")
                return mark_legacy_fallback(fallback_storyboard(item), str(exc))
        return fallback_storyboard(item)

    try:
        from openai import OpenAI

        model = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna").strip()
        client = OpenAI(api_key=api_key)
        source = {
            "title": _title(item),
            "summary": _summary(item),
            "url": _url(item),
            "original_url": _clean(item.get("link") or item.get("source_url")),
            "source": _clean(item.get("source") or item.get("domain")),
            "tags": item.get("tags") or [],
        }
        if growth_enabled:
            source["content_excerpt"] = _clean(item.get("content"))[:12000]
        system = (
            "You are the short-form video editor for SpecAvtoPortal, a Russian professional media outlet about "
            "commercial trucks, trailers, logistics and regulations. Create factual, compact vertical-video storyboards. "
            "Never invent numbers, quotes, companies or consequences that are absent from the supplied source. "
            "Aim for 24-34 seconds, 4-6 scenes, a strong factual hook in the first 2 seconds, then context and practical meaning. "
            "Each scene narration must be one short spoken sentence, normally 8-16 Russian words, so the presenter can speak naturally without rushing. "
            "Write idiomatic professional Russian. Avoid literal calques from English such as using 'приложения' when 'сферы применения' is meant. "
            "Set format to exactly 'breaking' for a straight news item or 'explainer' only when the source supports an explanatory angle. "
            "Visual prompts must describe realistic premium editorial industrial photography and MUST request no text, logos or watermarks. "
            "Return ONLY valid JSON with keys: format,title,hook,instagram_caption,tiktok_caption,youtube_title,"
            "youtube_description,hashtags,scenes. Each scene must contain id,seconds,overlay,narration,visual_prompt,highlight_words."
        )
        if growth_enabled:
            system += (
                " Also return hook_candidates as exactly three different Russian hook lines. "
                "Every hook and every scene claim must be directly supported by the source. "
                "Reject a dramatic angle if the source does not prove it. Use one CTA only. "
                "Prefer an operational takeaway only when the source explicitly supports it."
            )
        user = "Source item:\n" + json.dumps(source, ensure_ascii=False)
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_output_tokens=2600,
        )
        data = _extract_json(response.output_text)
        board = _validate_ai_storyboard(data, item)
        if growth_enabled:
            raw_validation = validate_storyboard(board, item)
            if not raw_validation["valid"]:
                raise ValueError(f"Growth Agent rejected raw AI output: {raw_validation['errors']}")
            board = enhance_storyboard(board, item, supplied_hooks=data.get("hook_candidates") or [])
        print(f"[AI] storyboard generated with {model}: {len(board.scenes)} scenes")
        return board
    except Exception as exc:
        print(f"[AI] storyboard fallback: {exc}")
        if growth_enabled:
            try:
                return build_fallback_storyboard(item, reason=str(exc)[:800])
            except Exception as growth_exc:
                print(f"[growth] safe fallback unavailable: {growth_exc}")
                return mark_legacy_fallback(fallback_storyboard(item), str(growth_exc))
        return fallback_storyboard(item)
