from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image


AUTPOSTER_ROOT = Path(__file__).resolve().parents[1]
if str(AUTPOSTER_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTPOSTER_ROOT))

from src.formats.carousel import build_carousel, render_carousel, validate_slide_grounding  # noqa: E402
from src.formats.pipeline import build_formats_preview, is_enabled  # noqa: E402
from src.formats.profile import BIO_LIMIT, NAME_LIMIT, audit_profile  # noqa: E402
from src.formats.story import build_story_sequence, render_story_sequence  # noqa: E402
from src.intelligence.common import read_json  # noqa: E402


FORMAT_FIXTURES = AUTPOSTER_ROOT / "tests" / "fixtures" / "instagram_formats"
INTELLIGENCE_FIXTURES = AUTPOSTER_ROOT / "tests" / "fixtures" / "growth_intelligence"


def profile_fixture() -> dict:
    return read_json(FORMAT_FIXTURES / "profile_fixture.json")


def article_fixture() -> dict:
    return read_json(INTELLIGENCE_FIXTURES / "transport_article.json")


class ProfileAuditTests(unittest.TestCase):
    def test_scores_all_twelve_criteria_and_marks_fixture_partial(self) -> None:
        report = audit_profile(profile_fixture(), as_of=date(2026, 10, 30))
        self.assertEqual(len(report["criteria"]), 12)
        self.assertEqual(sum(row["maximum"] for row in report["criteria"]), 100)
        self.assertFalse(report["score_is_fully_verified"])
        self.assertEqual(report["verification_status"], "partial_unverified")
        self.assertIn("score_not_fully_verified", {row["code"] for row in report["missing_data_warnings"]})

    def test_name_and_bio_proposals_respect_limits(self) -> None:
        report = audit_profile(profile_fixture())
        self.assertEqual(len(report["proposed_copy"]["profile_names"]), 3)
        self.assertEqual(len(report["proposed_copy"]["bios"]), 3)
        self.assertTrue(all(row["characters"] <= NAME_LIMIT for row in report["proposed_copy"]["profile_names"]))
        self.assertTrue(all(row["characters"] <= BIO_LIMIT for row in report["proposed_copy"]["bios"]))

    def test_missing_important_inputs_never_claims_verified_score(self) -> None:
        report = audit_profile({"handle": "@test"})
        self.assertFalse(report["score_is_fully_verified"])
        missing = {row.get("field") for row in report["missing_data_warnings"]}
        self.assertIn("bio", missing)
        self.assertIn("grid_covers", missing)


class CarouselTests(unittest.TestCase):
    def test_slide_copy_is_source_grounded_and_attributed(self) -> None:
        package = build_carousel(article_fixture())
        self.assertEqual(package["status"], "ready_for_editorial_review")
        self.assertGreaterEqual(len(package["slides"]), 6)
        self.assertLessEqual(len(package["slides"]), 10)
        for slide in package["slides"]:
            self.assertTrue(slide["alt_text"])
            self.assertEqual(slide["source_url"], package["source"]["source_url"])
            if slide.get("evidence"):
                self.assertTrue(slide["factual_validation"]["supported"])
                self.assertEqual(slide["body"], slide["evidence"][0]["exact_text"])

    def test_incorrect_manufacturer_model_and_numbers_are_rejected(self) -> None:
        source_text = "Компания представила Foton R 6x2. Машина относится к категории N3. Модель показали на выставке."
        self.assertTrue(validate_slide_grounding("Компания представила Foton R 6x2.", source_text))
        self.assertFalse(validate_slide_grounding("Компания представила Foton S 8x4.", source_text))

    def test_thin_source_refuses_padded_carousel(self) -> None:
        package = build_carousel({
            "title": "Короткая новость", "source_url": "https://example.com/short",
            "summary": "Компания показала новый прицеп.",
        })
        self.assertEqual(package["status"], "insufficient_source")
        self.assertEqual(package["slides"], [])

    def test_renderer_outputs_1080_by_1350_without_overflow(self) -> None:
        package = build_carousel(article_fixture())
        with tempfile.TemporaryDirectory() as tmp:
            rendered = render_carousel(package, Path(tmp))
            self.assertTrue(rendered["qa"]["all_resolution_ok"])
            self.assertTrue(rendered["qa"]["all_text_fits"])
            self.assertTrue(rendered["qa"]["all_safe_margins_ok"])
            with Image.open(rendered["files"][0]) as image:
                self.assertEqual(image.size, (1080, 1350))

    def test_only_rights_confirmed_local_images_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "approved.png"
            Image.new("RGB", (400, 300), "gray").save(path)
            package = build_carousel(article_fixture(), approved_images=[
                {"path": str(path), "rights_confirmed": False},
                {"path": str(path), "rights_confirmed": True, "credit": "Owner fixture"},
            ])
        self.assertEqual(len(package["attribution_manifest"]["approved_images_used"]), 1)
        self.assertIn("image_rights_not_confirmed", {row["code"] for row in package["warnings"]})


class StoryTests(unittest.TestCase):
    def test_story_sequence_has_manual_nonfunctional_sticker_instruction(self) -> None:
        package = build_story_sequence(article_fixture())
        self.assertGreaterEqual(len(package["frames"]), 3)
        self.assertLessEqual(len(package["frames"]), 7)
        interactions = [row for row in package["frames"] if row["role"] == "interaction"]
        self.assertEqual(len(interactions), 1)
        instruction = interactions[0]["manual_sticker_instruction"]
        self.assertEqual(instruction["sticker"], "link")
        self.assertIn("вручную", instruction["placement"])
        self.assertIn("не изображён", instruction["static_preview_notice"])

    def test_renderer_outputs_1080_by_1920_inside_safe_zone(self) -> None:
        package = build_story_sequence(article_fixture())
        with tempfile.TemporaryDirectory() as tmp:
            rendered = render_story_sequence(package, Path(tmp))
            self.assertTrue(rendered["qa"]["all_resolution_ok"])
            self.assertTrue(rendered["qa"]["all_text_fits"])
            self.assertTrue(rendered["qa"]["all_safe_margins_ok"])
            with Image.open(rendered["files"][0]) as image:
                self.assertEqual(image.size, (1080, 1920))


class FormatsIntegrationTests(unittest.TestCase):
    def test_flag_defaults_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_enabled())

    def test_disabled_pipeline_has_zero_effect_and_runs_no_modules(self) -> None:
        with patch.dict(os.environ, {"INSTAGRAM_FORMATS_ENABLED": "0"}, clear=False), patch(
            "src.formats.pipeline.audit_profile"
        ) as profile, patch(
            "src.formats.pipeline.build_carousel"
        ) as carousel, patch(
            "src.formats.pipeline.build_story_sequence"
        ) as stories:
            report = build_formats_preview(profile={}, source={}, output_dir=Path("unused"))
        profile.assert_not_called()
        carousel.assert_not_called()
        stories.assert_not_called()
        self.assertFalse(report["publishing_invoked"])
        self.assertFalse(report["profile_modified"])
        self.assertFalse(report["messages_sent"])
        self.assertEqual(report["scheduling_effect"], "none")
        self.assertFalse(report["production_state_changed"])

    def test_enabled_preview_never_calls_existing_publisher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch("src.publish.social_v2.publish_all") as publish:
            report = build_formats_preview(
                profile=profile_fixture(), source=article_fixture(), output_dir=Path(tmp), enabled=True
            )
        publish.assert_not_called()
        self.assertFalse(report["publishing_invoked"])
        self.assertFalse(report["production_state_changed"])


if __name__ == "__main__":
    unittest.main()
