from __future__ import annotations

import json
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

from src.ai.growth_agent import (  # noqa: E402
    GrowthAgentError,
    build_fallback_storyboard,
    content_intelligence_score,
    generate_hook_candidates,
    growth_report,
    is_near_duplicate,
    normalize_russian_text,
    topic_similarity,
    validate_storyboard,
)
from src.ai.storyboard import fallback_storyboard, generate_storyboard  # noqa: E402
from src.content import guides, sat  # noqa: E402
from src.publish.social_v2 import _with_site_link  # noqa: E402
from src import v2_main  # noqa: E402
from src.v2_main import pick_item  # noqa: E402


SOURCE_ITEM = {
    "id": "fixture-1",
    "slug": "bpw-eco-meter",
    "title": "BPW показала счётчик пробега прицепа ECO Meter",
    "summary": (
        "ECO Meter записывает пробег прицепа независимо от тягача. "
        "Данные помогают планировать интервалы обслуживания и проверку шин. "
        "Система рассчитана на распространённые размеры шин при нагрузке до 12 тонн."
    ),
    "source": "BPW",
    "link": "https://example.com/bpw-eco-meter",
    "site_url": "https://spec-avtoportal.ru/news/bpw-eco-meter/",
    "tags": ["полуприцепы", "обслуживание"],
}


class GrowthAgentTests(unittest.TestCase):
    def test_disabled_flag_preserves_legacy_storyboard(self) -> None:
        expected = fallback_storyboard(SOURCE_ITEM).to_dict()
        with patch.dict(os.environ, {"GROWTH_AGENT_ENABLED": "0", "OPENAI_API_KEY": "", "AI_SCRIPT": "0"}, clear=False):
            actual = generate_storyboard(SOURCE_ITEM)
        self.assertEqual(actual.to_dict(), expected)
        self.assertFalse(growth_report(actual)["enabled"])

    def test_enabled_flag_builds_three_hooks_and_report(self) -> None:
        with patch.dict(os.environ, {"GROWTH_AGENT_ENABLED": "1", "OPENAI_API_KEY": "", "AI_SCRIPT": "0"}, clear=False):
            board = generate_storyboard(SOURCE_ITEM)
        report = growth_report(board)
        self.assertTrue(report["enabled"])
        self.assertEqual(len(report["hook_candidates"]), 3)
        self.assertLessEqual(board.scenes[0].seconds, 3.0)

    def test_storyboard_schema_is_backward_compatible(self) -> None:
        board = build_fallback_storyboard(SOURCE_ITEM)
        self.assertEqual(
            set(board.to_dict()),
            {
                "version", "format", "title", "hook", "voiceover",
                "instagram_caption", "tiktok_caption", "youtube_title",
                "youtube_description", "hashtags", "source_urls", "scenes",
            },
        )
        self.assertNotIn("hook_candidates", board.to_dict())

    def test_factual_validation_rejects_unsupported_number(self) -> None:
        board = build_fallback_storyboard(SOURCE_ITEM)
        board.scenes[1].narration = "Система выдерживает 999 тонн."
        report = validate_storyboard(board, SOURCE_ITEM)
        self.assertFalse(report["valid"])
        self.assertIn("unsupported_number", {row["code"] for row in report["errors"]})

    def test_factual_validation_rejects_unsupported_regulatory_claim(self) -> None:
        board = build_fallback_storyboard(SOURCE_ITEM)
        board.scenes[1].narration = "Новый федеральный закон запрещает эксплуатацию таких прицепов."
        report = validate_storyboard(board, SOURCE_ITEM)
        self.assertFalse(report["valid"])
        self.assertIn("unsupported_sensitive_claim", {row["code"] for row in report["errors"]})

    def test_missing_source_details_are_rejected(self) -> None:
        with self.assertRaises(GrowthAgentError):
            build_fallback_storyboard({"title": "Новость", "summary": "Мало данных."})

    def test_missing_source_integration_reports_legacy_fallback(self) -> None:
        with patch.dict(os.environ, {"GROWTH_AGENT_ENABLED": "1", "OPENAI_API_KEY": "", "AI_SCRIPT": "0"}, clear=False):
            board = generate_storyboard({"title": "Новость", "summary": "Мало данных."})
        report = growth_report(board)
        self.assertTrue(report["enabled"])
        self.assertEqual(report["mode"], "legacy_fallback")
        self.assertFalse(report["validation"]["valid"])

    def test_hook_candidates_are_three_and_grounded(self) -> None:
        hooks = generate_hook_candidates(SOURCE_ITEM)
        self.assertEqual(len(hooks), 3)
        self.assertTrue(all(row["score"] > 0 for row in hooks))
        self.assertTrue(any("12" in row["text"] for row in hooks))

    def test_russian_humanizer_preserves_terms_models_and_numbers(self) -> None:
        text = "В этом видео следует отметить, что ECO Meter рассчитан на 12 тонн."
        normalized, findings = normalize_russian_text(text)
        self.assertNotIn("В этом видео", normalized)
        self.assertNotIn("следует отметить", normalized.lower())
        self.assertIn("ECO Meter", normalized)
        self.assertIn("12 тонн", normalized)
        self.assertGreaterEqual(len(findings), 2)

    def test_platform_captions_have_one_primary_cta(self) -> None:
        board = build_fallback_storyboard(SOURCE_ITEM)
        self.assertNotIn("http", board.instagram_caption)
        self.assertEqual(board.instagram_caption.lower().count("ссылк"), 1)
        self.assertLessEqual(board.instagram_caption.count("#"), 5)
        self.assertIn("https://spec-avtoportal.ru/", board.youtube_description)
        self.assertIn("https://example.com/", board.youtube_description)

    def test_scene_timing_is_valid(self) -> None:
        board = build_fallback_storyboard(SOURCE_ITEM)
        self.assertGreaterEqual(len(board.scenes), 4)
        self.assertLessEqual(len(board.scenes), 6)
        self.assertLessEqual(board.scenes[0].seconds, 3.0)
        self.assertGreaterEqual(sum(scene.seconds for scene in board.scenes), 20.0)
        self.assertLessEqual(sum(scene.seconds for scene in board.scenes), 40.0)

    def test_growth_output_files_are_complete(self) -> None:
        board = build_fallback_storyboard(SOURCE_ITEM)
        with tempfile.TemporaryDirectory() as tmp, patch.object(v2_main, "OUT_DIR", Path(tmp)), patch.dict(
            os.environ, {"GROWTH_AGENT_ENABLED": "1"}, clear=False
        ):
            v2_main.write_outputs(board, {"schema": 2, "content_key": "fixture-1"})
            root = Path(tmp)
            expected = {
                "scene_plan.json", "caption_instagram.txt", "caption_tiktok.txt",
                "caption_youtube.txt", "manifest.json", "growth_report.json",
            }
            self.assertTrue(expected.issubset({path.name for path in root.iterdir()}))
            self.assertNotIn("http", (root / "caption_instagram.txt").read_text(encoding="utf-8"))
            self.assertNotIn("http", (root / "caption_tiktok.txt").read_text(encoding="utf-8"))
            self.assertTrue(json.loads((root / "growth_report.json").read_text(encoding="utf-8"))["validation"]["valid"])

    def test_duplicate_prevention(self) -> None:
        self.assertGreater(topic_similarity("Новый счётчик пробега прицепа BPW", "BPW показала счётчик пробега прицепа"), 0.62)
        self.assertTrue(is_near_duplicate("Новый счётчик пробега прицепа BPW", ["BPW показала счётчик пробега прицепа"]))
        self.assertFalse(is_near_duplicate("Новые правила весового контроля", ["BPW показала счётчик пробега прицепа"]))

    def test_picker_avoids_near_duplicate_when_an_alternative_exists(self) -> None:
        news = [
            {"id": "duplicate", "slug": "duplicate", "title": "BPW показала счётчик пробега прицепа", "summary": SOURCE_ITEM["summary"]},
            {"id": "fresh", "slug": "fresh", "title": "Новые правила весового контроля", "summary": "Перевозчикам следует проверить нагрузку на ось до рейса."},
        ]
        state = {"used": [], "renders": [{"title": "Новый счётчик пробега прицепа BPW"}]}
        with patch.dict(os.environ, {"GROWTH_AGENT_ENABLED": "1"}, clear=False):
            picked = pick_item(news, state)
        self.assertEqual(picked["id"], "fresh")

    def test_content_intelligence_prefers_practical_regulation(self) -> None:
        useful, reasons = content_intelligence_score({
            "title": "Новые правила нагрузки на ось",
            "summary": "Перевозчикам следует проверить документы и нагрузку до рейса, чтобы избежать штрафа.",
        })
        generic, _ = content_intelligence_score({"title": "Компания отметила юбилей", "summary": "Состоялось мероприятие."})
        self.assertGreater(useful, generic)
        self.assertIn("regulation", reasons)
        self.assertIn("practical_takeaway", reasons)

    def test_existing_special_modes_are_unchanged(self) -> None:
        with patch.dict(os.environ, {"GROWTH_AGENT_ENABLED": "1"}, clear=False):
            guide_config = guides.load_config()
            guide = guides.build_storyboard(guide_config, guide_config["episodes"][0])
            sat_config = sat.load_config()
            partner = sat.build_storyboard(sat_config, sat_config["episodes"][0])
        self.assertEqual(guide.version, 2)
        self.assertEqual(partner.format, "partner")
        self.assertFalse(hasattr(guide, "_growth_report"))
        self.assertFalse(hasattr(partner, "_growth_report"))

    def test_ai_validation_failure_uses_grounded_fallback(self) -> None:
        raw = {
            "format": "breaking",
            "title": SOURCE_ITEM["title"],
            "hook": "Неподтверждённые 999 тонн",
            "hook_candidates": ["Неподтверждённые 999 тонн", SOURCE_ITEM["title"], SOURCE_ITEM["summary"].split(". ")[0]],
            "instagram_caption": "caption",
            "tiktok_caption": "caption",
            "youtube_title": SOURCE_ITEM["title"],
            "youtube_description": "description",
            "hashtags": ["#грузовики"],
            "scenes": [
                {"id": "hook", "seconds": 3, "overlay": "999 тонн", "narration": "Система выдерживает 999 тонн.", "visual_prompt": "industrial photo", "highlight_words": []},
                {"id": "fact", "seconds": 6, "overlay": "Факт", "narration": SOURCE_ITEM["summary"].split(". ")[0] + ".", "visual_prompt": "close-up", "highlight_words": []},
                {"id": "meaning", "seconds": 6, "overlay": "Смысл", "narration": SOURCE_ITEM["summary"].split(". ")[1] + ".", "visual_prompt": "workshop", "highlight_words": []},
                {"id": "cta", "seconds": 4, "overlay": "Сайт", "narration": "Подробности на сайте.", "visual_prompt": "closing", "highlight_words": []},
            ],
        }

        class FakeResponses:
            def create(self, **_: object) -> object:
                return types.SimpleNamespace(output_text=json.dumps(raw, ensure_ascii=False))

        class FakeOpenAI:
            def __init__(self, **_: object) -> None:
                self.responses = FakeResponses()

        fake_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
        with patch.dict(sys.modules, {"openai": fake_module}), patch.dict(
            os.environ,
            {"GROWTH_AGENT_ENABLED": "1", "OPENAI_API_KEY": "test", "AI_SCRIPT": "1"},
            clear=False,
        ):
            board = generate_storyboard(SOURCE_ITEM)
        report = growth_report(board)
        self.assertEqual(report["mode"], "deterministic_fallback")
        self.assertTrue(report["validation"]["valid"])
        self.assertNotIn("999", board.voiceover)

    def test_instagram_link_handling_only_changes_under_flag(self) -> None:
        with patch.dict(os.environ, {"GROWTH_AGENT_ENABLED": "0"}, clear=False):
            self.assertIn("https://spec-avtoportal.ru/", _with_site_link("Текст", "instagram"))
        with patch.dict(os.environ, {"GROWTH_AGENT_ENABLED": "1"}, clear=False):
            self.assertEqual(_with_site_link("Текст", "instagram"), "Текст")
            self.assertEqual(_with_site_link("Текст", "tiktok"), "Текст")


if __name__ == "__main__":
    unittest.main()
