from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


AUTPOSTER_ROOT = Path(__file__).resolve().parents[1]
if str(AUTPOSTER_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTPOSTER_ROOT))

from src.ai.storyboard import Scene, Storyboard  # noqa: E402
from src import v2_main  # noqa: E402
from src.voice.natural_ru import (  # noqa: E402
    VoiceProfile,
    _synthesize_openai,
    integer_to_russian,
    load_voice_profile,
    natural_voice_enabled,
    prepare_russian_speech,
    scene_durations_from_boundaries,
)


def _board() -> Storyboard:
    scenes = [
        Scene("hook", 3.0, "BPW: 6x2", "BPW показала шасси 6x2.", "visual"),
        Scene("fact", 5.0, "52 ТОННЫ", "Машина перевозит 52 тонны.", "visual"),
    ]
    return Storyboard(
        version=2, format="breaking", title="Test", hook=scenes[0].overlay,
        voiceover=" ".join(scene.narration for scene in scenes),
        instagram_caption="BPW показала шасси 6x2.",
        tiktok_caption="BPW показала шасси 6x2.", youtube_title="Test",
        youtube_description="Test", hashtags=[], source_urls=[], scenes=scenes,
    )


class RussianSpeechPreparationTests(unittest.TestCase):
    def test_required_brands_models_numbers_and_year_are_spoken_naturally(self) -> None:
        source = (
            "ЧМЗАП, Foton, BPW, Michelin, DHL и DAF показали шасси 6x2: "
            "52 тонны, рост 4,6% к 2028 году."
        )
        result = prepare_russian_speech(source)
        self.assertEqual(result.original, source)
        for expected in (
            "Чэмзап", "Фотон", "Би-пи-дабл-ю", "Мишлен", "Ди-эйч-эл", "Даф",
            "шесть на два", "пятьдесят две тонны",
            "четыре целых шесть десятых процента", "две тысячи двадцать восьмой год",
        ):
            self.assertIn(expected, result.spoken)
        self.assertGreaterEqual(len(result.replacements), 10)

    def test_date_is_spoken_but_original_caption_value_is_untouched(self) -> None:
        source = "Правило обсуждают до 29.10.2026. Модель X6000 и K5 остаются в тексте."
        result = prepare_russian_speech(source)
        self.assertEqual(source, result.original)
        self.assertIn("двадцать девятого октября две тысячи двадцать шестого года", result.spoken)
        self.assertIn("X6000", result.spoken)
        self.assertIn("K5", result.spoken)
        self.assertIn("29.10.2026", source)

    def test_integer_inflection_supports_feminine_measurements(self) -> None:
        self.assertEqual(integer_to_russian(52, feminine=True), "пятьдесят две")
        self.assertEqual(integer_to_russian(2028), "две тысячи двадцать восемь")


class NaturalVoiceSafetyTests(unittest.TestCase):
    def test_feature_is_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(natural_voice_enabled())

    def test_profiles_are_explicit_and_paid_profile_is_identified(self) -> None:
        edge = load_voice_profile("edge_svetlana_professional")
        paid = load_voice_profile("openai_cedar_professional")
        self.assertEqual(edge.engine, "edge")
        self.assertEqual(edge.rate, "-2%")
        self.assertFalse(edge.paid)
        self.assertEqual(paid.engine, "openai")
        self.assertTrue(paid.paid)

    def test_paid_openai_call_requires_separate_owner_approval_flag(self) -> None:
        profile = load_voice_profile("openai_cedar_professional")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"ALLOW_PAID_TTS": "0", "OPENAI_TTS": "1", "OPENAI_API_KEY": "must-not-be-used"},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "ALLOW_PAID_TTS"):
                _synthesize_openai(["Тест"], Path(tmp) / "paid.mp3", profile)

    def test_continuous_boundaries_cover_audio_without_scene_gaps(self) -> None:
        boundaries = [
            {"offset": index * 7_000_000, "duration": 3_000_000, "text": str(index)}
            for index in range(8)
        ]
        durations = scene_durations_from_boundaries(
            boundaries,
            ["Первый короткий факт.", "Второй факт содержит больше слов для проверки."],
            6.0,
        )
        self.assertEqual(len(durations), 2)
        self.assertAlmostEqual(sum(durations), 6.0, places=5)
        self.assertTrue(all(value > 0 for value in durations))

    def test_enabled_path_dispatches_once_for_the_whole_storyboard(self) -> None:
        expected = (Path("voice.mp3"), [2.5, 3.5], "natural:edge:test", {})
        with patch.dict(os.environ, {"NATURAL_VOICE_ENABLED": "1"}, clear=False), patch(
            "src.voice.natural_ru.generate_natural_voice_track", return_value=expected
        ) as generate:
            output = v2_main.generate_scene_voice_track(_board(), Path("work"))
        self.assertEqual(output, expected[:3])
        generate.assert_called_once()

    def test_disabled_path_does_not_enter_natural_engine(self) -> None:
        board = _board()

        def fake_voice(_: str, output: Path) -> str:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"x" * 1200)
            return "legacy-test"

        def fake_ffmpeg(command: list[str], **_: object) -> object:
            Path(command[-1]).write_bytes(b"x" * 1200)
            return types.SimpleNamespace(returncode=0, stderr=b"")

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"NATURAL_VOICE_ENABLED": "0"}, clear=False
        ), patch("src.voice.natural_ru.generate_natural_voice_track") as natural, patch.object(
            v2_main, "generate_voice", side_effect=fake_voice
        ), patch.object(v2_main, "media_duration", return_value=3.0), patch(
            "subprocess.run", side_effect=fake_ffmpeg
        ):
            output, durations, mode = v2_main.generate_scene_voice_track(board, Path(tmp))
        natural.assert_not_called()
        self.assertTrue(output.name == "voice.mp3")
        self.assertEqual(durations, [3.0, 3.0])
        self.assertEqual(mode, "legacy-test")


if __name__ == "__main__":
    unittest.main()
