from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw


AUTPOSTER_ROOT = Path(__file__).resolve().parents[1]
if str(AUTPOSTER_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTPOSTER_ROOT))

from src.crossplatform.analytics import (  # noqa: E402
    OWNER_BASELINE_SNAPSHOT,
    AnalyticsDataError,
    build_cross_platform_report,
    ingest_observations,
    load_observation_rows,
    parse_count,
    parse_percent,
    snapshot_for_window,
)
from src.crossplatform.hooks import build_platform_packages, validate_rewrite, evidence_sentences  # noqa: E402
from src.crossplatform.pipeline import build_cross_platform_review, is_enabled  # noqa: E402
from src.crossplatform import visual_qa  # noqa: E402
from src.intelligence.common import read_json, similarity  # noqa: E402
import src.publish as publish_package  # noqa: E402


FIXTURES = AUTPOSTER_ROOT / "tests" / "fixtures" / "cross_platform"
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
LABEL = "synthetic_test"


def row(**overrides):
    base = {
        "content_id": "art-1", "platform": "youtube", "post_id": "abc123",
        "published_at": "2026-10-01T09:00:00Z", "collected_at": "2026-10-04T10:00:00Z",
        "views": "100", "dataset_label": LABEL,
    }
    base.update(overrides)
    return base


def fixture_report():
    ingested = ingest_observations(load_observation_rows(FIXTURES / "observations.csv"))
    return ingested, build_cross_platform_report(ingested, owner_context=OWNER_BASELINE_SNAPSHOT)


def article():
    return read_json(FIXTURES / "approved_article.json")


# ------------------------------------------------------------------ analytics

class ThreePlatformMatchingTests(unittest.TestCase):
    def test_fixture_matches_by_explicit_content_id_only(self) -> None:
        _, report = fixture_report()
        by_id = {m["content_id"]: m for m in report["content_matching"]}
        self.assertEqual(by_id["art-001"]["match_status"], "matched_all_three")
        self.assertEqual(by_id["art-001"]["platforms_present"], ["youtube", "instagram", "tiktok"])
        self.assertEqual(by_id["art-007"]["match_status"], "partial_match")
        self.assertEqual(by_id["art-008"]["match_status"], "single_platform")
        self.assertTrue(all(m["matched_by"] == "explicit content_id" for m in report["content_matching"]))

    def test_no_fuzzy_matching_across_different_ids(self) -> None:
        rows = [
            row(content_id="art-1", platform="youtube", post_id="yt1"),
            row(content_id="ART-1 ", platform="tiktok", post_id="7001"),
        ]
        report = build_cross_platform_report(ingest_observations(rows))
        self.assertEqual(len(report["content_matching"]), 2)

    def test_cross_platform_uses_relative_to_own_median_not_raw_views(self) -> None:
        _, report = fixture_report()
        comparison = next(m for m in report["content_matching"] if m["content_id"] == "art-003")["comparison"]
        self.assertFalse(comparison["raw_views_directly_comparable"])
        self.assertEqual(comparison["comparable_window"], "7d")
        for platform, data in comparison["platforms"].items():
            self.assertIn("relative_to_own_platform_median", data)
            self.assertIn(platform, data["post_key"])

    def test_engaged_views_never_compared_with_tiktok_views(self) -> None:
        ingested, report = fixture_report()
        tiktok_rows = [o for o in ingested["observations"] if o["platform"] == "tiktok"]
        self.assertTrue(all(o["metrics"]["engaged_views"] is None for o in tiktok_rows))
        art7_tiktok = next(o for o in tiktok_rows if o["content_id"] == "art-007")
        self.assertIn("ignored_metric_not_defined_for_tiktok", json.dumps(art7_tiktok["notes"]))
        self.assertEqual(art7_tiktok["raw"]["engaged_views"], "40")  # raw preserved
        for match in report["content_matching"]:
            comparison = match["comparison"] or {}
            self.assertNotIn("engaged_views", json.dumps(comparison.get("platforms", {})))
        self.assertNotIn("engaged_views", report["per_platform"]["tiktok"]["metric_coverage_latest_snapshot"])

    def test_owner_snapshot_is_context_not_data(self) -> None:
        _, report = fixture_report()
        context = report["owner_baseline_context"]
        self.assertEqual(context["classification"], "manual_owner_snapshot_not_comparable")
        self.assertEqual(context["youtube"]["views_28d"], 32200)
        self.assertNotIn("owner", " ".join(report["dataset_labels"]))

    def test_website_traffic_not_attributed(self) -> None:
        _, report = fixture_report()
        self.assertEqual(report["website_traffic"]["attribution"], "not_attributed")
        self.assertEqual(report["website_traffic"]["platform_reported_website_clicks_latest"]["youtube"], 3)
        self.assertIsNone(report["website_traffic"]["platform_reported_website_clicks_latest"]["tiktok"])

    def test_descriptive_and_causal_are_separate(self) -> None:
        _, report = fixture_report()
        self.assertTrue(all(o["type"] == "descriptive" for o in report["descriptive_observations"]))
        self.assertTrue(report["noncausal_hypotheses"])
        self.assertTrue(all(h["not_causal_evidence"] and h["confidence"] == "low" for h in report["noncausal_hypotheses"]))


class DuplicateObservationTests(unittest.TestCase):
    def test_exact_duplicate_removed_once(self) -> None:
        ingested = ingest_observations([row(), row()])
        self.assertEqual(len(ingested["observations"]), 1)
        self.assertEqual(len(ingested["duplicates"]), 1)

    def test_conflicting_snapshot_is_quarantined(self) -> None:
        ingested = ingest_observations([row(views="100"), row(views="150")])
        self.assertEqual(ingested["observations"], [])
        self.assertEqual(ingested["conflicts"][0]["code"], "conflicting_snapshot")

    def test_url_and_id_forms_of_same_post_are_duplicates(self) -> None:
        ingested = ingest_observations([
            row(post_id="abc123"),
            row(post_id="", post_url="https://www.youtube.com/shorts/abc123?feature=share"),
        ])
        self.assertEqual(len(ingested["observations"]), 1)
        self.assertEqual(len(ingested["duplicates"]), 1)

    def test_updated_observation_kept_as_time_series(self) -> None:
        ingested = ingest_observations([
            row(collected_at="2026-10-02T10:00:00Z", views="50"),
            row(collected_at="2026-10-08T10:00:00Z", views="120"),
        ])
        self.assertEqual([o["metrics"]["views"] for o in ingested["observations"]], [50, 120])

    def test_counter_decrease_warned_not_hidden(self) -> None:
        ingested = ingest_observations([
            row(collected_at="2026-10-02T10:00:00Z", views="80"),
            row(collected_at="2026-10-03T10:00:00Z", views="70"),
        ])
        self.assertEqual(len(ingested["observations"]), 2)
        self.assertIn("counter_decreased", [w["code"] for w in ingested["warnings"]])

    def test_post_with_two_content_ids_quarantined(self) -> None:
        ingested = ingest_observations([
            row(content_id="art-1", collected_at="2026-10-02T10:00:00Z"),
            row(content_id="art-2", collected_at="2026-10-03T10:00:00Z"),
        ])
        self.assertEqual(ingested["observations"], [])
        self.assertEqual(ingested["conflicts"][0]["code"], "post_mapped_to_multiple_content_ids")


class WindowTests(unittest.TestCase):
    def test_mismatched_windows_produce_no_comparison(self) -> None:
        _, report = fixture_report()
        art7 = next(m for m in report["content_matching"] if m["content_id"] == "art-007")
        codes = [w["code"] for w in art7["warnings"]]
        self.assertIn("window_mismatch", codes)
        self.assertIn("publication_time_gap", codes)
        self.assertIsNone(art7["comparison"]["comparable_window"])
        self.assertIn("latest_snapshots_not_comparable", art7["comparison"])

    def test_snapshot_outside_tolerance_not_used(self) -> None:
        obs = ingest_observations([row(collected_at="2026-10-02T21:00:00Z")])["observations"]  # 36h old
        self.assertIsNone(snapshot_for_window(obs, 24.0))
        self.assertIsNone(snapshot_for_window(obs, 72.0))

    def test_date_only_publication_excluded_from_short_windows(self) -> None:
        ingested = ingest_observations([row(published_at="2026-10-01", collected_at="2026-10-02T00:30:00Z")])
        self.assertIsNone(snapshot_for_window(ingested["observations"], 24.0))
        self.assertIn("published_at_date_only", [w["code"] for w in ingested["warnings"]])

    def test_small_baseline_gives_no_relative_index(self) -> None:
        rows = [
            row(content_id="a", platform="youtube", post_id="y1"),
            row(content_id="a", platform="tiktok", post_id="7001", published_at="2026-10-01T09:30:00Z", collected_at="2026-10-04T10:30:00Z"),
        ]
        report = build_cross_platform_report(ingest_observations(rows))
        comparison = report["content_matching"][0]["comparison"]
        self.assertEqual(comparison["comparable_window"], "72h")
        for data in comparison["platforms"].values():
            self.assertIsNone(data["relative_to_own_platform_median"])
            self.assertIn("need 5", data["relative_unavailable_reason"])


class MissingMetricTests(unittest.TestCase):
    def test_missing_optional_metrics_tracked_and_not_inferred(self) -> None:
        ingested = ingest_observations([row(platform="instagram", post_id="", post_url="https://www.instagram.com/reel/XYZ/", likes="5")])
        obs = ingested["observations"][0]
        self.assertIsNone(obs["metrics"]["reach"])
        self.assertIsNone(obs["metrics"]["completion_rate"])
        self.assertIn("reach", obs["missing_metrics"])
        self.assertIn("saves", obs["missing_metrics"])
        self.assertNotIn("likes", obs["missing_metrics"])
        self.assertNotIn("engaged_views", obs["missing_metrics"])

    def test_required_fields_reported(self) -> None:
        ingested = ingest_observations([{"platform": "tiktok", "views": "5"}])
        errors = " ".join(ingested["rejected"][0]["errors"])
        for field in ("content_id is required", "post ID or post URL", "published_at is required", "collected_at is required"):
            self.assertIn(field, errors)

    def test_fixture_coverage_reports_partial_reach(self) -> None:
        _, report = fixture_report()
        coverage = report["per_platform"]["instagram"]["metric_coverage_latest_snapshot"]["reach"]
        self.assertEqual(coverage, {"present": 5, "posts": 6})


class InvalidNumberTests(unittest.TestCase):
    def test_counts_reject_abbreviation_decimal_negative(self) -> None:
        for value in ("1.2K", "12.5", "-3", "1,234", "nan", "∞"):
            with self.subTest(value=value), self.assertRaises(AnalyticsDataError):
                parse_count(value, "views")
        self.assertEqual(parse_count("1 234", "views"), 1234)

    def test_percent_rules(self) -> None:
        self.assertEqual(parse_percent("71%", "completion_rate"), (71.0, "percent"))
        self.assertEqual(parse_percent("0.18", "completion_rate"), (18.0, "fraction_to_percent"))
        self.assertEqual(parse_percent("140", "average_percentage_viewed"), (140.0, "percent"))
        with self.assertRaises(AnalyticsDataError):
            parse_percent("140", "completion_rate")

    def test_fixture_invalid_rows_rejected_with_reasons(self) -> None:
        ingested, _ = fixture_report()
        errors = json.dumps(ingested["rejected"], ensure_ascii=False)
        self.assertEqual(len(ingested["rejected"]), 3)
        self.assertIn("1.2K", errors)
        self.assertIn("collected_at is earlier than published_at", errors)
        self.assertIn("timezone offset required", errors)
        self.assertIn("cannot be negative", errors)

    def test_url_must_belong_to_platform(self) -> None:
        ingested = ingest_observations([row(platform="tiktok", post_id="", post_url="https://www.youtube.com/shorts/abc")])
        self.assertIn("does not belong to platform", ingested["rejected"][0]["errors"][0])

    def test_post_id_url_mismatch_rejected(self) -> None:
        ingested = ingest_observations([row(post_id="aaa", post_url="https://youtu.be/bbb")])
        self.assertIn("does not match", " ".join(ingested["rejected"][0]["errors"]))


# ------------------------------------------------------------------ hooks

class SafeHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = build_platform_packages(article())
        self.evidence, _ = evidence_sentences(article())
        self.text = " ".join(self.evidence)

    def test_three_platforms_have_distinct_hooks_and_captions(self) -> None:
        packages = self.result["packages"]
        hooks = [packages[p]["hook"] for p in ("youtube", "instagram", "tiktok")]
        self.assertEqual(len(set(hooks)), 3)
        self.assertIn("title", packages["youtube"])
        self.assertLess(similarity(packages["instagram"]["caption"], packages["tiktok"]["caption"]), 0.82)
        self.assertNotEqual(packages["instagram"]["cta"], packages["tiktok"]["cta"])

    def test_every_factual_statement_has_exact_evidence(self) -> None:
        for platform, pkg in self.result["packages"].items():
            self.assertTrue(pkg["source_evidence"], platform)
            for entry in pkg["source_evidence"]:
                self.assertIn(entry["exact_source_text"], self.evidence + [article()["title"]])
                self.assertEqual(entry["source_url"], "https://sdelanounas.ru/blogs/179124/")
            self.assertIn(pkg["hook"], [e["statement"] for e in pkg["source_evidence"]])
            self.assertEqual(pkg["cta_type"], "non_factual_template")
            self.assertEqual(pkg["approval_status"], "pending_owner_approval")

    def test_numbers_and_qualifiers_preserved_verbatim(self) -> None:
        caption = self.result["packages"]["instagram"]["caption"]
        self.assertIn("почти 1,8 тысячи тонн", caption)
        self.assertIn("36,8 метра", self.result["packages"]["youtube"]["hook"])

    def test_truncated_source_tail_never_used(self) -> None:
        dumped = json.dumps(self.result["packages"], ensure_ascii=False)
        self.assertNotIn("Стоимость", dumped)
        self.assertIn("truncated_source_text_excluded", [w["code"] for w in self.result["warnings"]])

    def test_emotive_source_language_kept_out_of_hooks(self) -> None:
        for pkg in self.result["packages"].values():
            self.assertNotRegex(pkg["hook"].lower(), "гигантск|мегапроект|величествен")

    def test_production_untouched_and_no_paid_calls(self) -> None:
        self.assertEqual(self.result["production_effect"], "none")
        self.assertFalse(self.result["replaces_production_narration"])
        self.assertEqual(self.result["paid_model_calls"], 0)

    def test_unapproved_source_requires_editorial_review(self) -> None:
        source = article()
        source["editorial_status"] = "draft"
        result = build_platform_packages(source)
        self.assertEqual(result["status"], "editorial_review_required")
        self.assertTrue(all(p["confidence"] == "low" for p in result["packages"].values()))

    def test_overlong_title_not_truncated(self) -> None:
        source = article()
        source["title"] = source["title"] + " и других регионов Уральского федерального округа по данным дорожников"
        result = build_platform_packages(source)
        self.assertIsNone(result["packages"]["youtube"]["title"])
        self.assertEqual(result["packages"]["youtube"]["status"], "editorial_review_required")


class UnverifiedRewriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence, _ = evidence_sentences(article())

    def test_fabricated_number_and_hype_flagged(self) -> None:
        result = validate_rewrite("Невероятно: эстакада длиной 2 километра уже в асфальте!", self.evidence, "https://x.example/", origin="editor")
        self.assertEqual(result["status"], "editorial_review_required")
        self.assertIn("unsupported_numbers", result["reasons"])
        self.assertIn("unverified_emotional_language", result["reasons"])
        self.assertFalse(result["applied_to_package"])

    def test_shortened_claim_that_drops_qualifier_flagged(self) -> None:
        # Source: "почти 1,8 тысячи тонн" — dropping "почти" changes meaning.
        result = validate_rewrite("До конца года на объекте уложат 1,8 тысячи тонн асфальтобетона.", self.evidence, "u", origin="editor")
        self.assertEqual(result["status"], "editorial_review_required")

    def test_verified_fact_not_in_source_rejected(self) -> None:
        source = article()
        source["verified_facts"] = source["verified_facts"] + ["Стоимость эстакады составила 2 млрд рублей."]
        result = build_platform_packages(source)
        reasons = [r["reason"] for r in result["rejected_facts"]]
        self.assertEqual(len(reasons), 1)
        self.assertIn(reasons[0], {"unsupported_numbers", "truncated_in_source", "not_an_exact_complete_source_sentence"})
        self.assertNotIn("млрд", json.dumps(result["packages"], ensure_ascii=False))

    def test_storyboard_overlay_paraphrase_needs_review_and_is_not_applied(self) -> None:
        extras = read_json(FIXTURES / "storyboard_and_rewrites.json")
        result = build_platform_packages(article(), storyboard=extras["storyboard"], candidate_rewrites=extras["candidate_rewrites"])
        by_candidate = {r["candidate"]: r for r in result["rewrite_suggestions"]}
        self.assertEqual(by_candidate["Самая длинная эстакада Урала получает асфальт"]["status"], "editorial_review_required")
        self.assertEqual(by_candidate["Протяжённость эстакады составляет 1060 метров."]["status"], "validated_extractive")
        for pkg in result["packages"].values():
            self.assertNotEqual(pkg["hook"], "Самая длинная эстакада Урала получает асфальт")

    def test_missing_verified_facts_requires_review(self) -> None:
        source = article()
        source.pop("verified_facts")
        result = build_platform_packages(source)
        self.assertEqual(result["status"], "editorial_review_required")


# ------------------------------------------------------------------ visual QA

def _dark_detailed(size=(270, 480), seed=0) -> Image.Image:
    """Night-footage-like frame: low luma everywhere, but real texture."""
    import random

    rng = random.Random(seed)
    small = Image.new("L", (size[0] // 3, size[1] // 3))
    small.putdata([max(0, min(255, int(6 + 30 * (y / small.height) + rng.gauss(0, 6))))
                   for y in range(small.height) for _ in range(small.width)])
    image = small.resize(size).convert("RGB")
    draw = ImageDraw.Draw(image)
    for i in range(40):
        x = rng.randrange(size[0])
        y = rng.randrange(size[1])
        draw.line((x, y, x + size[0] // 10, y + 4), fill=(55, 50, 46), width=max(1, size[0] // 135))
    return image


def _titled(size=(270, 480), seed=0, title_colour=(246, 247, 249), background=(15, 18, 22)) -> Image.Image:
    image = _dark_detailed(size, seed) if background is None else Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    k = size[0] / 270  # coordinates below are on the 270x480 analysis grid
    for i in range(30):
        x, y = (i * 41 + seed * 13) % 250, 40 + (i * 29) % 200
        draw.rectangle((x * k, y * k, (x + 14) * k, (y + 6) * k), fill=(90, 96, 104))
    for line in range(3):
        y = 250 + line * 22
        draw.rectangle((18 * k, y * k, (200 - line * 30) * k, (y + 14) * k), fill=title_colour)
    return image


class VisualFrameTests(unittest.TestCase):
    def test_dark_detailed_frame_is_not_black(self) -> None:
        stats = visual_qa.frame_stats(_dark_detailed())
        self.assertLess(stats["mean_luma"], 30)
        self.assertEqual(visual_qa.classify_frame(stats), "dark_detailed")

    def test_black_and_blank_frames_detected(self) -> None:
        self.assertEqual(visual_qa.classify_frame(visual_qa.frame_stats(Image.new("RGB", (270, 480), (3, 3, 3)))), "near_black")
        self.assertEqual(visual_qa.classify_frame(visual_qa.frame_stats(Image.new("RGB", (270, 480), (128, 128, 128)))), "blank_uniform")

    def test_title_region_present_missing_low_contrast(self) -> None:
        profile = visual_qa.LAYOUT_PROFILES["short_v2"]
        self.assertTrue(visual_qa.title_region_check(_titled(), profile)["title_readable"])
        self.assertFalse(visual_qa.title_region_check(_dark_detailed(), profile)["title_present"])
        washed = visual_qa.title_region_check(_titled(background=(215, 215, 215)), profile)
        self.assertTrue(washed["title_present"])
        self.assertFalse(washed["title_readable"])

    def test_margin_overflow_detected(self) -> None:
        profile = visual_qa.LAYOUT_PROFILES["short_v2"]
        image = _titled()
        ImageDraw.Draw(image).rectangle((0, 250, 270, 264), fill=(250, 250, 250))
        self.assertTrue(visual_qa.margin_overflow_check(image, profile)["overflow_suspected"])
        self.assertFalse(visual_qa.margin_overflow_check(_titled(), profile)["overflow_suspected"])


class LayoutCheckTests(unittest.TestCase):
    def test_short_overlay_fits(self) -> None:
        result = visual_qa.check_text_layout("1060 метров и 27 пролётов")
        self.assertFalse(result["overflow"])
        self.assertLessEqual(len(result["lines"]), 4)

    def test_overlong_overlay_reported_as_overflow(self) -> None:
        text = " ".join(["Асфальтобетонное покрытие эстакады обхода Сима"] * 4)
        result = visual_qa.check_text_layout(text)
        self.assertTrue(result["overflow"])
        self.assertTrue(result["truncated_by_renderer"])


class VisualGateFramesDirTests(unittest.TestCase):
    def _write(self, folder: Path, images: list[tuple[float, Image.Image]]) -> None:
        for t, image in images:
            image.save(folder / f"frame_t{t:.2f}.png")

    def test_single_good_frame_never_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "frames"
            folder.mkdir()
            self._write(folder, [(0.5, _titled(size=(1080, 1920)))])
            report = visual_qa.run_visual_qa(frames_dir=folder, output_dir=Path(tmp) / "out")
        self.assertEqual(report["status"], "fail")
        self.assertIn("insufficient_frame_evidence", [i["code"] for i in report["issues"]])
        self.assertFalse(report["approved_for_publication"])

    def test_dark_footage_sequence_passes_without_black_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "frames"
            folder.mkdir()
            frames = [(t, _titled(size=(1080, 1920), seed=i, background=None)) for i, t in enumerate((0.0, 0.5, 1.0, 1.5, 3.0, 5.0, 7.0))]
            self._write(folder, frames)
            report = visual_qa.run_visual_qa(frames_dir=folder, output_dir=Path(tmp) / "out")
            self.assertTrue((Path(tmp) / "out" / "contact_sheet.jpg").exists())
        codes = [i["code"] for i in report["issues"]]
        self.assertNotIn("black_opening", codes)
        self.assertNotIn("blank_opening_frames", codes)
        self.assertEqual(report["status"], "pass", codes)

    def test_wrong_aspect_ratio_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "frames"
            folder.mkdir()
            self._write(folder, [(t, _titled(size=(1920, 1080), seed=i)) for i, t in enumerate(range(7))])
            report = visual_qa.run_visual_qa(frames_dir=folder, output_dir=Path(tmp) / "out")
        self.assertIn("invalid_aspect_ratio", [i["code"] for i in report["issues"]])

    def test_corrupt_frame_file_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "frames"
            folder.mkdir()
            self._write(folder, [(t, _titled(size=(1080, 1920), seed=i)) for i, t in enumerate(range(7))])
            (folder / "frame_t9.00.png").write_bytes(b"not an image")
            report = visual_qa.run_visual_qa(frames_dir=folder, output_dir=Path(tmp) / "out")
        self.assertIn("corrupt_frame_file", [i["code"] for i in report["issues"]])


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe not installed")
class VisualGateVideoTests(unittest.TestCase):
    def _video(self, folder: Path, name: str, black_seconds: float, size: str = "720x1280") -> Path:
        path = folder / name
        source = f"testsrc2=s={size}:r=15:d=5"
        if black_seconds:
            graph = f"color=c=black:s={size}:r=15:d={black_seconds}[b];{source}[g];[b][g]concat=n=2:v=1:a=0[v]"
            cmd = ["ffmpeg", "-v", "error", "-y", "-filter_complex", graph, "-map", "[v]"]
        else:
            cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source]
        subprocess.run(cmd + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)], check=True)
        return path

    def test_black_opening_detected_with_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video = self._video(Path(tmp), "black.mp4", 1.2)
            report = visual_qa.run_visual_qa(video=video, output_dir=Path(tmp) / "out", title_expected_until=None)
        issue = next(i for i in report["issues"] if i["code"] == "black_opening")
        self.assertEqual(issue["severity"], "error")
        self.assertGreaterEqual(issue["evidence"]["interval"]["duration"], 1.0)
        self.assertIn(0.5, issue["evidence"]["sampled_blank_timestamps"])
        self.assertEqual(report["status"], "fail")

    def test_clean_video_has_no_black_issue_and_reports_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            video = self._video(Path(tmp), "clean.mp4", 0)
            report = visual_qa.run_visual_qa(video=video, output_dir=Path(tmp) / "out", title_expected_until=None)
        codes = [i["code"] for i in report["issues"]]
        self.assertNotIn("black_opening", codes)
        self.assertIn("below_target_resolution", codes)
        self.assertGreaterEqual(report["frames_analysed"], visual_qa.MIN_FRAMES)

    def test_corrupt_and_empty_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.mp4"
            empty.write_bytes(b"")
            junk = Path(tmp) / "junk.mp4"
            junk.write_bytes(b"\x00garbage" * 100)
            r1 = visual_qa.run_visual_qa(video=empty, output_dir=Path(tmp) / "o1")
            r2 = visual_qa.run_visual_qa(video=junk, output_dir=Path(tmp) / "o2")
        self.assertIn("empty_or_missing_file", [i["code"] for i in r1["issues"]])
        self.assertIn("corrupt_or_unreadable_video", [i["code"] for i in r2["issues"]])
        self.assertEqual(r2["status"], "fail")


# ------------------------------------------------------------------ flag & safety

class DisabledFeatureIsolationTests(unittest.TestCase):
    def test_flag_defaults_to_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_enabled())
        with patch.dict(os.environ, {"CROSS_PLATFORM_GROWTH_ENABLED": "0"}):
            self.assertFalse(is_enabled())

    def test_disabled_pipeline_runs_nothing(self) -> None:
        with patch.dict(os.environ, {"CROSS_PLATFORM_GROWTH_ENABLED": "0"}), \
                patch("src.crossplatform.pipeline.build_cross_platform_report") as analytics, \
                patch("src.crossplatform.pipeline.build_platform_packages") as hooks:
            result = build_cross_platform_review(observation_rows=[], article={})
        self.assertEqual(result["status"], "disabled")
        self.assertFalse(result["publishing_invoked"])
        analytics.assert_not_called()
        hooks.assert_not_called()

    def test_existing_flags_and_production_modules_not_imported_or_changed(self) -> None:
        source = "\n".join(p.read_text(encoding="utf-8") for p in (AUTPOSTER_ROOT / "src" / "crossplatform").glob("*.py"))
        for forbidden in ("publish.", "buffer", "youtube_auth", "requests", "openai", "urllib.request", "os.environ[", "setenv"):
            self.assertNotIn(forbidden, source.replace("from urllib.parse", ""), forbidden)
        for module in ("v2_main.py", "main.py"):
            self.assertNotIn("crossplatform", (AUTPOSTER_ROOT / "src" / module).read_text(encoding="utf-8"))


class NoPublishingSideEffectTests(unittest.TestCase):
    def test_enabled_review_never_calls_publishers_or_network(self) -> None:
        rows = load_observation_rows(FIXTURES / "observations.csv")
        publisher = ModuleType("src.publish.social_v2")
        publisher.publish_all = Mock()  # type: ignore[attr-defined]
        with patch.object(publish_package, "social_v2", publisher, create=True), \
                patch.dict(sys.modules, {"src.publish.social_v2": publisher}), \
                patch("socket.socket", side_effect=AssertionError("network used")), \
                patch("subprocess.run", side_effect=AssertionError("subprocess used")):
            result = build_cross_platform_review(observation_rows=copy.deepcopy(rows), article=article(), enabled=True)
        publisher.publish_all.assert_not_called()  # type: ignore[attr-defined]
        self.assertFalse(result["publishing_invoked"])
        self.assertEqual(result["scheduling_effect"], "none")
        self.assertFalse(result["production_weights_changed"])
        self.assertTrue(result["owner_approval_required"])

    def test_input_rows_not_mutated(self) -> None:
        rows = load_observation_rows(FIXTURES / "observations.csv")
        snapshot = copy.deepcopy(rows)
        ingest_observations(rows)
        self.assertEqual(rows, snapshot)


if __name__ == "__main__":
    unittest.main()
