"""Opt-in continuous Russian narration with spoken-only normalization.

The legacy voice path remains the default.  This module never publishes and
never changes storyboard/caption text.  A paid profile additionally requires
an explicit ALLOW_PAID_TTS=1 opt-in so CI and previews cannot spend by accident.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


AUTPOSTER_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = AUTPOSTER_ROOT / "config"
PROFILE_PATH = CONFIG_DIR / "voice_profiles.json"
PRONUNCIATION_PATH = CONFIG_DIR / "pronunciation_ru.json"


@dataclass(frozen=True)
class VoiceProfile:
    name: str
    engine: str
    voice: str
    rate: str = "+0%"
    model: str = ""
    speed: float = 1.0
    instructions: str = ""
    continuous: bool = True
    paid: bool = False
    style: str = ""
    estimated_cost: str = ""


@dataclass(frozen=True)
class PreparedSpeech:
    original: str
    spoken: str
    replacements: tuple[dict[str, str], ...]


def natural_voice_enabled(value: str | None = None) -> bool:
    if value is None:
        value = os.getenv("NATURAL_VOICE_ENABLED", "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"Invalid voice configuration: {path}")
    return raw


def load_voice_profile(name: str | None = None, path: Path = PROFILE_PATH) -> VoiceProfile:
    config = _load_json(path)
    selected = (name or os.getenv("NATURAL_VOICE_PROFILE", "").strip() or config.get("default"))
    profiles = config.get("profiles", {})
    raw = profiles.get(selected) if isinstance(profiles, dict) else None
    if not isinstance(raw, dict):
        raise RuntimeError(f"Unknown NATURAL_VOICE_PROFILE: {selected}")
    engine = str(raw.get("engine", "")).strip().lower()
    if engine not in {"edge", "openai"}:
        raise RuntimeError(f"Unsupported voice engine in profile {selected}: {engine}")
    return VoiceProfile(
        name=str(selected),
        engine=engine,
        voice=str(raw.get("voice", "")).strip(),
        rate=str(raw.get("rate", "+0%")).strip(),
        model=str(raw.get("model", "")).strip(),
        speed=float(raw.get("speed", 1.0)),
        instructions=str(raw.get("instructions", "")).strip(),
        continuous=bool(raw.get("continuous", True)),
        paid=bool(raw.get("paid", False)),
        style=str(raw.get("style", "")).strip(),
        estimated_cost=str(raw.get("estimated_cost", "")).strip(),
    )


_ONES = (
    "ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
    "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
    "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать",
)
_TENS = ("", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто")
_HUNDREDS = ("", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот")
_ORDINAL_YEARS = {
    1: "первый", 2: "второй", 3: "третий", 4: "четвёртый", 5: "пятый",
    6: "шестой", 7: "седьмой", 8: "восьмой", 9: "девятый", 10: "десятый",
    11: "одиннадцатый", 12: "двенадцатый", 13: "тринадцатый", 14: "четырнадцатый",
    15: "пятнадцатый", 16: "шестнадцатый", 17: "семнадцатый", 18: "восемнадцатый",
    19: "девятнадцатый", 20: "двадцатый", 30: "тридцатый", 40: "сороковой",
    50: "пятидесятый", 60: "шестидесятый", 70: "семидесятый", 80: "восьмидесятый",
    90: "девяностый",
}
_DAY_GENITIVE = {
    1: "первого", 2: "второго", 3: "третьего", 4: "четвёртого", 5: "пятого",
    6: "шестого", 7: "седьмого", 8: "восьмого", 9: "девятого", 10: "десятого",
    11: "одиннадцатого", 12: "двенадцатого", 13: "тринадцатого", 14: "четырнадцатого",
    15: "пятнадцатого", 16: "шестнадцатого", 17: "семнадцатого", 18: "восемнадцатого",
    19: "девятнадцатого", 20: "двадцатого", 21: "двадцать первого", 22: "двадцать второго",
    23: "двадцать третьего", 24: "двадцать четвёртого", 25: "двадцать пятого",
    26: "двадцать шестого", 27: "двадцать седьмого", 28: "двадцать восьмого",
    29: "двадцать девятого", 30: "тридцатого", 31: "тридцать первого",
}
_MONTH_GENITIVE = (
    "", "января", "февраля", "марта", "апреля", "мая", "июня", "июля",
    "августа", "сентября", "октября", "ноября", "декабря",
)


def _triplet(value: int, feminine: bool = False) -> list[str]:
    result: list[str] = []
    result.append(_HUNDREDS[value // 100]) if value >= 100 else None
    remainder = value % 100
    if remainder < 20:
        word = _ONES[remainder]
        if feminine and remainder == 1:
            word = "одна"
        elif feminine and remainder == 2:
            word = "две"
        if remainder or not result:
            result.append(word)
    else:
        result.append(_TENS[remainder // 10])
        unit = remainder % 10
        if unit:
            result.append("одна" if feminine and unit == 1 else "две" if feminine and unit == 2 else _ONES[unit])
    return [word for word in result if word]


def integer_to_russian(value: int, *, feminine: bool = False) -> str:
    if value < 0:
        return "минус " + integer_to_russian(-value, feminine=feminine)
    if value < 1000:
        return " ".join(_triplet(value, feminine=feminine))
    if value > 999_999_999:
        return str(value)
    chunks: list[str] = []
    millions, remainder = divmod(value, 1_000_000)
    thousands, units = divmod(remainder, 1000)
    if millions:
        chunks.extend(_triplet(millions))
        last = millions % 100
        chunks.append("миллион" if last % 10 == 1 and last != 11 else "миллиона" if last % 10 in {2, 3, 4} and not 12 <= last <= 14 else "миллионов")
    if thousands:
        chunks.extend(_triplet(thousands, feminine=True))
        last = thousands % 100
        chunks.append("тысяча" if last % 10 == 1 and last != 11 else "тысячи" if last % 10 in {2, 3, 4} and not 12 <= last <= 14 else "тысяч")
    if units:
        chunks.extend(_triplet(units, feminine=feminine))
    return " ".join(chunks) or "ноль"


def _year_ordinal(value: int, *, grammatical_case: str = "nominative", genitive: bool = False) -> str:
    prefix_value = value - value % 100
    tail = value % 100
    if tail in _ORDINAL_YEARS:
        prefix = integer_to_russian(prefix_value) if prefix_value else ""
        result = f"{prefix} {_ORDINAL_YEARS[tail]}".strip()
    elif tail % 10 in _ORDINAL_YEARS:
        prefix = integer_to_russian(value - tail % 10)
        result = f"{prefix} {_ORDINAL_YEARS[tail % 10]}"
    else:
        result = integer_to_russian(value)
    if genitive:
        grammatical_case = "genitive"
    if grammatical_case != "nominative":
        prefix, separator, adjective = result.rpartition(" ")
        if not separator:
            adjective, prefix = prefix, ""
        irregular = {
            ("третий", "genitive"): "третьего",
            ("третий", "dative"): "третьему",
            ("третий", "prepositional"): "третьем",
            ("третий", "instrumental"): "третьим",
        }
        declined = irregular.get((adjective, grammatical_case))
        if not declined and adjective.endswith(("ый", "ой")):
            stem = adjective[:-2]
            endings = {"genitive": "ого", "dative": "ому", "prepositional": "ом", "instrumental": "ым"}
            declined = stem + endings.get(grammatical_case, adjective[-2:])
        if not declined and adjective.endswith("ий"):
            stem = adjective[:-2]
            endings = {"genitive": "его", "dative": "ему", "prepositional": "ем", "instrumental": "им"}
            declined = stem + endings.get(grammatical_case, adjective[-2:])
        result = f"{prefix} {declined or adjective}".strip()
    return result


def _record_replace(text: str, pattern: re.Pattern[str], replacement: Any, kind: str, records: list[dict[str, str]]) -> str:
    def replace(match: re.Match[str]) -> str:
        spoken = replacement(match) if callable(replacement) else str(replacement)
        original = match.group(0)
        if original != spoken:
            records.append({"kind": kind, "original": original, "spoken": spoken})
        return spoken
    return pattern.sub(replace, text)


def prepare_russian_speech(text: str, dictionary_path: Path = PRONUNCIATION_PATH) -> PreparedSpeech:
    original = str(text or "")
    spoken = original
    records: list[dict[str, str]] = []
    dictionary = _load_json(dictionary_path)

    literal = dictionary.get("literal", {})
    if isinstance(literal, dict):
        for source, target in sorted(literal.items(), key=lambda pair: len(pair[0]), reverse=True):
            pattern = re.compile(rf"(?<![\w-]){re.escape(str(source))}(?![\w-])", re.IGNORECASE)
            spoken = _record_replace(spoken, pattern, str(target), "dictionary", records)
    regex_rows = dictionary.get("regex", [])
    if isinstance(regex_rows, list):
        for row in regex_rows:
            if isinstance(row, dict) and row.get("pattern") and row.get("spoken"):
                spoken = _record_replace(spoken, re.compile(str(row["pattern"]), re.IGNORECASE), str(row["spoken"]), "dictionary_regex", records)

    date_pattern = re.compile(r"(?<!\d)(0?[1-9]|[12]\d|3[01])[./-](0?[1-9]|1[0-2])[./-]((?:19|20)\d{2})(?!\d)")
    def date_spoken(match: re.Match[str]) -> str:
        day, month, year = map(int, match.groups())
        try:
            date(year, month, day)
        except ValueError:
            return match.group(0)
        return f"{_DAY_GENITIVE[day]} {_MONTH_GENITIVE[month]} {_year_ordinal(year, grammatical_case='genitive')} года"
    spoken = _record_replace(spoken, date_pattern, date_spoken, "date", records)

    spoken = _record_replace(
        spoken,
        re.compile(r"(?<!\w)(\d+)\s*[xх×]\s*(\d+)(?!\w)", re.IGNORECASE),
        lambda match: f"{integer_to_russian(int(match.group(1)))} на {integer_to_russian(int(match.group(2)))}",
        "axle_formula", records,
    )
    spoken = _record_replace(
        spoken,
        re.compile(r"(?<!\d)(\d+)[,.](\d+)\s*%"),
        lambda match: (
            f"{integer_to_russian(int(match.group(1)))} целых "
            f"{integer_to_russian(int(match.group(2)), feminine=len(match.group(2)) == 1)} "
            f"{'десятых' if len(match.group(2)) == 1 else 'сотых'} процента"
        ),
        "percentage", records,
    )
    spoken = _record_replace(
        spoken,
        re.compile(r"(?<!\d)(\d+)\s*%"),
        lambda match: f"{integer_to_russian(int(match.group(1)))} процентов",
        "percentage", records,
    )
    year_pattern = re.compile(
        r"(?:(к|в|до|после|с)\s+)?((?:19|20)\d{2})\s+(год|года|году|годом|годы)\b",
        re.IGNORECASE,
    )
    def year_spoken(match: re.Match[str]) -> str:
        preposition = (match.group(1) or "").lower()
        suffix = match.group(3).lower()
        if preposition == "к":
            grammatical_case = "dative"
        elif preposition == "в":
            grammatical_case = "prepositional"
        elif preposition in {"до", "после", "с"} or suffix == "года":
            grammatical_case = "genitive"
        elif suffix == "годом":
            grammatical_case = "instrumental"
        elif suffix == "году":
            grammatical_case = "prepositional"
        else:
            grammatical_case = "nominative"
        prefix = f"{match.group(1)} " if match.group(1) else ""
        return f"{prefix}{_year_ordinal(int(match.group(2)), grammatical_case=grammatical_case)} {suffix}"
    spoken = _record_replace(spoken, year_pattern, year_spoken, "year", records)

    unit_pattern = re.compile(
        r"(?<![\d.,])(\d+)(?:[,.](\d+))?\s*(тонн(?:а|ы|у|ой|ами|ах)?|т|кг|километр(?:а|ов|ы)?|км|литр(?:а|ов|ы)?|л)\b",
        re.IGNORECASE,
    )
    def measurement(match: re.Match[str]) -> str:
        whole, decimal, unit = match.groups()
        feminine = unit.lower().startswith("тонн")
        number = integer_to_russian(int(whole), feminine=feminine and not decimal)
        if decimal:
            number += f" целых {integer_to_russian(int(decimal), feminine=len(decimal) == 1)} {'десятых' if len(decimal) == 1 else 'сотых'}"
        return f"{number} {unit}"
    spoken = _record_replace(spoken, unit_pattern, measurement, "measurement", records)

    # Remaining isolated integers are safe to verbalize; model names remain
    # intact because digits adjacent to letters or hyphens do not match.
    spoken = _record_replace(
        spoken,
        re.compile(r"(?<![\w.,-])\d{1,9}(?![\w.,-])"),
        lambda match: integer_to_russian(int(match.group(0))),
        "integer", records,
    )
    spoken = re.sub(r"\s+([,.!?;:])", r"\1", spoken)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    return PreparedSpeech(original=original, spoken=spoken, replacements=tuple(records))


async def _edge_stream(text: str, output: Path, profile: VoiceProfile) -> list[dict[str, Any]]:
    import edge_tts

    communication = edge_tts.Communicate(text=text, voice=profile.voice, rate=profile.rate, boundary="WordBoundary")
    audio = bytearray()
    boundaries: list[dict[str, Any]] = []
    async for chunk in communication.stream():
        if chunk.get("type") == "audio":
            audio.extend(chunk.get("data") or b"")
        elif chunk.get("type") == "WordBoundary":
            boundaries.append({
                "offset": int(chunk.get("offset") or 0),
                "duration": int(chunk.get("duration") or 0),
                "text": str(chunk.get("text") or ""),
            })
    output.write_bytes(bytes(audio))
    return boundaries


def synthesize_edge_continuous(texts: list[str], output: Path, profile: VoiceProfile, retries: int = 3) -> list[dict[str, Any]]:
    output.parent.mkdir(parents=True, exist_ok=True)
    full_text = "\n".join(text.strip() for text in texts if text.strip())
    if not full_text:
        raise RuntimeError("Natural voice received no narration")
    errors: list[str] = []
    for attempt in range(1, max(1, retries) + 1):
        try:
            boundaries = asyncio.run(_edge_stream(full_text, output, profile))
            if output.exists() and output.stat().st_size >= 1000 and boundaries:
                return boundaries
            raise RuntimeError("edge-tts returned incomplete audio or no word boundaries")
        except Exception as exc:
            output.unlink(missing_ok=True)
            errors.append(f"attempt {attempt}: {exc}")
    raise RuntimeError("Continuous Edge narration failed; no fallback was used: " + " | ".join(errors))


def _media_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except Exception:
        return 0.0


def scene_durations_from_boundaries(boundaries: list[dict[str, Any]], scene_texts: list[str], audio_seconds: float) -> list[float]:
    if not scene_texts or audio_seconds <= 0:
        raise RuntimeError("Cannot align natural narration without scenes and audio duration")
    word_counts = [max(1, len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text))) for text in scene_texts]
    total_words = sum(word_counts)
    event_count = len(boundaries)
    ends: list[float] = []
    cumulative = 0
    for count in word_counts[:-1]:
        cumulative += count
        event_index = min(event_count - 1, max(0, round(cumulative / total_words * event_count) - 1))
        current = boundaries[event_index]
        current_end = (int(current["offset"]) + int(current["duration"])) / 10_000_000
        if event_index + 1 < event_count:
            next_start = int(boundaries[event_index + 1]["offset"]) / 10_000_000
            current_end = (current_end + next_start) / 2
        ends.append(min(audio_seconds, current_end))
    ends.append(audio_seconds)
    durations: list[float] = []
    start = 0.0
    for end in ends:
        end = max(start + 0.05, end)
        durations.append(end - start)
        start = end
    return durations


def _synthesize_openai(texts: list[str], output: Path, profile: VoiceProfile) -> None:
    if os.getenv("ALLOW_PAID_TTS", "0").strip() != "1":
        raise RuntimeError("Paid TTS profile blocked: set ALLOW_PAID_TTS=1 only after owner approval")
    if os.getenv("OPENAI_TTS", "0").strip() != "1" or not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OpenAI TTS is not configured")
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with client.audio.speech.with_streaming_response.create(
        model=profile.model,
        voice=profile.voice,
        input="\n".join(texts),
        instructions=profile.instructions,
        speed=profile.speed,
    ) as response:
        response.stream_to_file(output)


def generate_natural_voice_track(board: Any, work_dir: Path) -> tuple[Path, list[float], str, dict[str, Any]]:
    profile = load_voice_profile()
    if not profile.continuous:
        raise RuntimeError(f"Profile {profile.name} is a comparison baseline, not a natural continuous profile")
    prepared = [prepare_russian_speech(scene.narration) for scene in board.scenes]
    spoken_texts = [row.spoken for row in prepared]
    output = work_dir / "voice.mp3"
    output.parent.mkdir(parents=True, exist_ok=True)
    boundaries: list[dict[str, Any]] = []
    if profile.engine == "edge":
        boundaries = synthesize_edge_continuous(spoken_texts, output, profile)
    elif profile.engine == "openai":
        _synthesize_openai(spoken_texts, output, profile)
    else:  # pragma: no cover - load_voice_profile validates this
        raise RuntimeError(f"Unsupported natural voice engine: {profile.engine}")
    audio_seconds = _media_duration(output)
    if audio_seconds <= 0:
        raise RuntimeError("Natural narration has no measurable duration")
    if boundaries:
        durations = scene_durations_from_boundaries(boundaries, spoken_texts, audio_seconds)
    else:
        weights = [max(1, len(text)) for text in spoken_texts]
        durations = [audio_seconds * weight / sum(weights) for weight in weights]

    # The Growth Agent promises a complete spoken hook in the opening.  A
    # natural voice that misses that contract is rejected instead of sped up.
    if hasattr(board, "_growth_report") and durations and durations[0] > 3.10:
        raise RuntimeError(
            f"Natural hook takes {durations[0]:.2f}s; choose a shorter hook instead of accelerating it"
        )
    report = {
        "schema": 1,
        "profile": profile.name,
        "engine": profile.engine,
        "voice": profile.voice,
        "rate": profile.rate,
        "continuous": True,
        "paid": profile.paid,
        "estimated_cost": profile.estimated_cost,
        "audio_seconds": round(audio_seconds, 3),
        "scene_seconds": [round(value, 3) for value in durations],
        "spoken_scenes": [
            {
                "original": row.original,
                "spoken": row.spoken,
                "replacements": list(row.replacements),
            }
            for row in prepared
        ],
    }
    (work_dir / "voice_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output, durations, f"natural:{profile.engine}:{profile.name}", report
