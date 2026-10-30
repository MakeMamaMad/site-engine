"""Generate a nonpublishing Russian voice comparison bundle.

Only the free Edge configurations are rendered.  The paid OpenAI profile is
documented in the report but is never called by this script.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


AUTPOSTER_ROOT = Path(__file__).resolve().parents[1]
if str(AUTPOSTER_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTPOSTER_ROOT))

from src.voice.natural_ru import (  # noqa: E402
    VoiceProfile,
    load_voice_profile,
    prepare_russian_speech,
    synthesize_edge_continuous,
)


SAMPLE_SCENES = [
    "ЧМЗАП и Foton представили технику для перевозчиков.",
    "Шасси DAF 6x2 рассчитано на 52 тонны, а Michelin и BPW отвечают за колёса и оси.",
    "DHL ожидает рост перевозок на 4,6% к 2028 году.",
]


def _run(command: list[str]) -> None:
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        error = (proc.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(error[-3000:])


def _duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return float(proc.stdout.strip())


async def _save_edge(text: str, output: Path, profile: VoiceProfile) -> None:
    import edge_tts

    await edge_tts.Communicate(text=text, voice=profile.voice, rate=profile.rate).save(str(output))


def _save_edge_with_retries(text: str, output: Path, profile: VoiceProfile, retries: int = 3) -> None:
    errors: list[str] = []
    for attempt in range(1, retries + 1):
        try:
            asyncio.run(_save_edge(text, output, profile))
            if output.exists() and output.stat().st_size >= 1000:
                return
            raise RuntimeError("no audio bytes")
        except Exception as exc:
            output.unlink(missing_ok=True)
            errors.append(f"attempt {attempt}: {exc}")
    raise RuntimeError("Edge baseline failed: " + " | ".join(errors))


def _baseline(output: Path, profile: VoiceProfile) -> None:
    """Reproduce the current scene-reset behavior without paid fallbacks."""
    with tempfile.TemporaryDirectory(prefix="voice-baseline-") as tmp:
        directory = Path(tmp)
        parts: list[Path] = []
        for index, text in enumerate(SAMPLE_SCENES, 1):
            part = directory / f"scene_{index:02d}.mp3"
            _save_edge_with_retries(text, part, profile)
            if not part.exists() or part.stat().st_size < 1000:
                raise RuntimeError(f"Edge baseline scene {index} returned no audio")
            parts.append(part)
        concat = directory / "concat.txt"
        concat.write_text("".join(f"file '{part.resolve()}'\n" for part in parts), encoding="utf-8")
        _run([
            "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat), "-c:a", "libmp3lame", "-q:a", "2", str(output),
        ])


def _profile_report(profile: VoiceProfile, output: Path, *, spoken: str, replacements: list[dict[str, str]], weakness: str) -> dict[str, Any]:
    seconds = round(_duration(output), 3)
    if not 15.0 <= seconds <= 25.0:
        raise RuntimeError(f"{profile.name} sample duration {seconds:.2f}s is outside 15-25s")
    return {
        "label": profile.name,
        "file": output.name,
        "engine": profile.engine,
        "voice": profile.voice,
        "rate": profile.rate,
        "style": profile.style,
        "continuous": profile.continuous,
        "duration_seconds": seconds,
        "paid": profile.paid,
        "estimated_cost": profile.estimated_cost,
        "runtime_requirements": ["network access to the Edge speech endpoint", "edge-tts", "FFmpeg/ffprobe"],
        "spoken_text": spoken,
        "pronunciation_replacements": replacements,
        "known_weakness": weakness,
    }


def generate(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    original = " ".join(SAMPLE_SCENES)
    prepared_scenes = [prepare_russian_speech(text) for text in SAMPLE_SCENES]
    prepared = " ".join(row.spoken for row in prepared_scenes)
    replacements = [replacement for row in prepared_scenes for replacement in row.replacements]

    baseline = load_voice_profile("edge_svetlana_baseline")
    professional = load_voice_profile("edge_svetlana_professional")
    deliberate = load_voice_profile("edge_svetlana_deliberate")
    paid = load_voice_profile("openai_cedar_professional")

    baseline_path = output / "01_current_edge_svetlana_scene_resets.mp3"
    professional_path = output / "02_edge_svetlana_continuous_prepared.mp3"
    deliberate_path = output / "03_edge_svetlana_deliberate_prepared.mp3"
    _baseline(baseline_path, baseline)
    synthesize_edge_continuous([row.spoken for row in prepared_scenes], professional_path, professional)
    synthesize_edge_continuous([row.spoken for row in prepared_scenes], deliberate_path, deliberate)

    samples = [
        _profile_report(
            baseline, baseline_path, spoken=original, replacements=[],
            weakness="Scene-by-scene cold starts; raw Latin brands and numeric forms; fastest and most mechanical comparison.",
        ),
        _profile_report(
            professional, professional_path, spoken=prepared, replacements=replacements,
            weakness="Best free candidate, but expressiveness is limited by the Edge voice and must be judged by the owner.",
        ),
        _profile_report(
            deliberate, deliberate_path, spoken=prepared, replacements=replacements,
            weakness="Useful pace comparison, but the same timbre at -7% can feel too slow for short-form news.",
        ),
    ]
    report = {
        "schema": 1,
        "publishing_invoked": False,
        "paid_api_invoked": False,
        "source_text": original,
        "samples": samples,
        "unrendered_paid_option": {
            "label": paid.name,
            "engine": paid.engine,
            "model": paid.model,
            "voice": paid.voice,
            "speed": paid.speed,
            "instructions": paid.instructions,
            "estimated_cost": paid.estimated_cost,
            "reason_not_rendered": "Owner approval and ALLOW_PAID_TTS=1 are required before any paid request.",
            "compatibility": "Compatible with the installed OpenAI 2.x Speech API client; configured as one continuous utterance.",
            "known_weakness": "OpenAI built-in voices are optimized for English; Russian quality needs a paid listening test before selection.",
            "lifecycle_warning": "gpt-4o-mini-tts is scheduled for shutdown on 2027-01-06; a production choice needs a migration plan.",
            "disclosure_requirement": "End users must be told that the voice is AI-generated.",
        },
        "availability_observation": {
            "edge_catalog": ["ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural"],
            "dmitry_live_result": "Listed by Edge but returned NoAudioReceived during the 2026-10-29 local review run.",
            "handling": "Dmitry remains configurable, but was not mislabeled as an available rendered sample and no fallback engine was substituted."
        },
        "recommendation": (
            "Start owner listening with edge_svetlana_professional. It removes scene resets, keeps a single timbre, "
            "uses spoken-only normalization and costs no API usage. Final selection remains subject to owner listening."
        ),
    }
    (output / "voice_comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "".join(
        f"| {row['label']} | {row['voice']} | {row['rate']} | {row['duration_seconds']:.3f}s | {row['estimated_cost']} |\n"
        for row in samples
    )
    readme = (
        "# Natural Russian voice comparison\n\n"
        "Nonpublishing listening samples generated from one factual test script. No paid API or publisher was called.\n\n"
        "| Profile | Voice | Rate | Duration | Estimated API cost |\n"
        "|---|---|---:|---:|---|\n" + rows +
        "\nThe baseline preserves raw wording and scene resets. The two candidates use one continuous utterance and "
        "the configurable spoken-only dictionary. Inspect `voice_comparison.json` for every substitution and known weakness.\n\n"
        "Recommendation: listen to `02_edge_svetlana_continuous_prepared.mp3` first. This is a technical recommendation, "
        "not approval to activate it in production.\n"
    )
    (output / "README.md").write_text(readme, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.output)
    print(f"Voice comparison written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
