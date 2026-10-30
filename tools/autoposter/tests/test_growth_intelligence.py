from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


AUTPOSTER_ROOT = Path(__file__).resolve().parents[1]
if str(AUTPOSTER_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTPOSTER_ROOT))

from src.intelligence.audit import audit_posts, load_audit_rows  # noqa: E402
from src.intelligence.common import IntelligenceDataError, read_json  # noqa: E402
from src.intelligence.pipeline import build_recommendation_pipeline, is_enabled  # noqa: E402
from src.intelligence.repurpose import (  # noqa: E402
    build_repurposing_package,
    extract_source_material,
    validate_supported_statement,
)
from src.intelligence.viral import analyze_viral_patterns, load_viral_rows  # noqa: E402
from src.publish import social_v2  # noqa: E402


FIXTURES = AUTPOSTER_ROOT / "tests" / "fixtures" / "growth_intelligence"


def _fixture_data() -> tuple[list[dict], dict, list[dict]]:
    return (
        load_viral_rows(FIXTURES / "viral_examples.csv"),
        read_json(FIXTURES / "transport_article.json"),
        load_audit_rows(FIXTURES / "audit_posts.json"),
    )


class ViralPatternTests(unittest.TestCase):
    def test_outliers_use_each_account_median_not_raw_views(self) -> None:
        rows, _, _ = _fixture_data()
        report = analyze_viral_patterns(rows)
        leader = report["ranked_examples"][0]
        self.assertAlmostEqual(leader["outlier_multiple"], leader["views"] / leader["account_median_views"], places=3)
        self.assertEqual(report["baseline"], "each account's manually supplied median views")
        self.assertTrue(report["provenance_preserved"])

    def test_missing_required_data_is_rejected(self) -> None:
        with self.assertRaisesRegex(IntelligenceDataError, "missing required"):
            analyze_viral_patterns([{"account": "@test"}])

    def test_zero_account_median_is_rejected(self) -> None:
        row = {
            "account": "@test", "source_url": "https://example.com/reel/1", "views": "100",
            "account_median_views": "0", "hook": "Почему это важно?", "dataset_label": "fixture",
        }
        with self.assertRaisesRegex(IntelligenceDataError, "greater than zero"):
            analyze_viral_patterns([row])

    def test_duplicate_examples_are_ignored_with_provenance_warning(self) -> None:
        rows, _, _ = _fixture_data()
        report = analyze_viral_patterns([rows[0], dict(rows[0])])
        self.assertEqual(report["sample_size"], 1)
        self.assertIn("duplicate_example_ignored", {row["code"] for row in report["warnings"]})

    def test_small_samples_are_not_reported_as_adequate_patterns(self) -> None:
        rows, _, _ = _fixture_data()
        report = analyze_viral_patterns(rows[:2])
        self.assertTrue(all(not row["adequate_sample"] for row in report["patterns"]))
        self.assertIn("small_dataset", {row["code"] for row in report["warnings"]})

    def test_recommendations_are_original_russian_templates(self) -> None:
        rows, _, _ = _fixture_data()
        report = analyze_viral_patterns(rows)
        self.assertTrue(report["recommendations"])
        self.assertTrue(any("Подтвержд" in row["russian_hook_template"] for row in report["recommendations"]))
        self.assertFalse(any("make a reel like" in row["russian_hook_template"].lower() for row in report["recommendations"]))


class RepurposeTests(unittest.TestCase):
    def _assert_long_claim_stays_evidence(self, claim: str) -> None:
        filler_one = "Подробное описание оборудования содержит дополнительные технические сведения для владельцев коммерческого транспорта и сервисных специалистов отрасли."
        filler_two = "Редакционный материал также перечисляет контекст эксплуатации автомобиля на разных маршрутах без выводов о будущих результатах использования."
        package = build_repurposing_package({
            "title": "Проверка безопасного хука",
            "source_url": "https://example.com/safety-review",
            "summary": f"{claim} {filler_one} {filler_two}",
        })
        self.assertIn(claim, package["extraction"]["claims"])
        self.assertEqual(package["reel_concepts"], [])
        rejected = [row["source_evidence"]["exact_text"] for row in package["hook_rejections"]]
        self.assertIn(claim, rejected)
        self.assertIn("no_safe_reel_hook", {row["code"] for row in package["warnings"]})

    def test_source_grounded_package_preserves_links_and_specifications(self) -> None:
        _, source, _ = _fixture_data()
        package = build_repurposing_package(source)
        self.assertEqual(package["source"]["source_url"], source["source_url"])
        self.assertTrue(package["reel_concepts"])
        self.assertTrue(package["carousel_outlines"])
        self.assertIn("12 тонн", " ".join(package["extraction"]["numbers_and_specifications"]))
        self.assertTrue(all(row["factual_validation"]["supported"] for row in package["reel_concepts"]))

    def test_unsupported_claim_and_number_are_rejected(self) -> None:
        _, source, _ = _fixture_data()
        source_text = source["summary"] + " " + source["content"]
        validation = validate_supported_statement("ECO Meter выдерживает 999 тонн.", source_text)
        self.assertFalse(validation["supported"])
        self.assertIn("999 тонн", validation["unsupported_numbers"])

    def test_reordered_relationship_is_not_approved_by_token_overlap(self) -> None:
        source_text = "Счётчик записывает пробег прицепа независимо от тягача."
        validation = validate_supported_statement(
            "Тягач записывает пробег независимо от прицепа.", source_text
        )
        self.assertFalse(validation["supported"])
        self.assertGreater(validation["token_overlap"], 0.5)

    def test_thin_source_does_not_become_five_repetitive_posts(self) -> None:
        package = build_repurposing_package({
            "title": "Короткая новость",
            "source_url": "https://example.com/thin",
            "summary": "Компания показала новый прицеп.",
        })
        self.assertEqual(package["status"], "insufficient_source")
        self.assertEqual(package["reel_concepts"], [])
        self.assertEqual(package["carousel_outlines"], [])
        self.assertIn("thin_source", {row["code"] for row in package["warnings"]})

    def test_duplicate_source_sentences_are_deduplicated(self) -> None:
        source = {
            "title": "Повтор",
            "source_url": "https://example.com/repeat",
            "summary": "Система фиксирует пробег прицепа. Система фиксирует пробег прицепа. Данные доступны механику.",
        }
        extraction = extract_source_material(source)
        self.assertEqual(extraction["claims"].count("Система фиксирует пробег прицепа."), 1)

    def test_quote_requires_explicit_attribution_for_story_use(self) -> None:
        _, source, _ = _fixture_data()
        package = build_repurposing_package(source)
        quotes = package["extraction"]["quotable_statements"]
        self.assertEqual(quotes[0]["attribution_status"], "explicit")
        self.assertTrue(any(row["type"] == "attributed_quote" for row in package["story_concepts"]))

    def test_truncated_conditional_claim_is_not_turned_into_a_hook(self) -> None:
        self._assert_long_claim_stays_evidence(
            "Если температура опустится ниже минус двадцати градусов, систему разрешено запускать только после обязательного предпускового прогрева двигателя."
        )

    def test_truncated_regulatory_claim_is_not_turned_into_a_hook(self) -> None:
        self._assert_long_claim_stays_evidence(
            "Согласно проекту регламента, новые требования могут начать действовать после утверждения документа правительством и официального опубликования текста."
        )

    def test_truncated_causal_claim_is_not_turned_into_a_hook(self) -> None:
        self._assert_long_claim_stays_evidence(
            "Расход топлива снизился после изменения маршрута, поскольку водитель исключил длительные остановки с работающим двигателем на загруженных участках дороги."
        )

    def test_truncated_numerical_claim_is_not_turned_into_a_hook(self) -> None:
        self._assert_long_claim_stays_evidence(
            "Допустимая нагрузка составляет 12 тонн только при использовании шин указанного размера и соблюдении рекомендованного производителем давления."
        )

    def test_final_suggested_hook_is_the_exact_validated_statement(self) -> None:
        _, source, _ = _fixture_data()
        package = build_repurposing_package(source)
        source_text = source["summary"] + " " + source["content"]
        for concept in package["reel_concepts"]:
            self.assertTrue(validate_supported_statement(concept["suggested_hook"], source_text)["supported"])
            self.assertEqual(concept["suggested_hook"], concept["source_evidence"][0]["exact_text"])


class AnalyticsAuditTests(unittest.TestCase):
    def test_invalid_csv_values_fail_with_row_and_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("post_id,views\np1,not-a-number\n", encoding="utf-8")
            rows = load_audit_rows(path)
            with self.assertRaisesRegex(IntelligenceDataError, "row 2: views"):
                audit_posts(rows)

    def test_missing_reach_and_retention_are_not_invented(self) -> None:
        report = audit_posts([
            {"post_id": "p1", "views": 100, "dataset_label": "fixture"},
            {"post_id": "p2", "views": 200, "dataset_label": "fixture"},
            {"post_id": "p3", "views": 300, "dataset_label": "fixture"},
        ])
        self.assertTrue(all(row["shares_per_reach"] is None for row in report["top_posts"] + report["bottom_posts"]))
        absent = {row.get("metric") for row in report["warnings"] if row["code"] == "metric_absent"}
        self.assertIn("reach", absent)
        self.assertIn("three_second_retention", absent)

    def test_zero_median_disables_relative_ranking(self) -> None:
        report = audit_posts([
            {"post_id": "p1", "views": 0},
            {"post_id": "p2", "views": 0},
        ])
        self.assertEqual(report["account_median_views"], 0)
        self.assertEqual(report["top_posts"], [])
        self.assertIn("zero_account_median", {row["code"] for row in report["warnings"]})

    def test_metrics_are_calculated_only_when_denominators_exist(self) -> None:
        report = audit_posts([
            {"post_id": "p1", "views": 100, "reach": 80, "shares": 8},
            {"post_id": "p2", "views": 200, "shares": 5},
            {"post_id": "p3", "views": 300, "reach": 0, "shares": 3},
        ])
        by_id = {row["post_id"]: row for row in report["posts"]}
        self.assertEqual(by_id["p1"]["shares_per_reach"], 0.1)
        self.assertIsNone(by_id["p2"]["shares_per_reach"])
        self.assertIsNone(by_id["p3"]["shares_per_reach"])

    def test_descriptive_patterns_and_hypotheses_are_separate(self) -> None:
        _, _, rows = _fixture_data()
        report = audit_posts(rows)
        self.assertTrue(report["observed_metrics"])
        self.assertTrue(report["descriptive_patterns"])
        self.assertTrue(report["hypotheses"])
        self.assertTrue(all(row["not_causal"] for row in report["hypotheses"]))
        self.assertTrue(all("sample_size" in row for row in report["descriptive_patterns"]))

    def test_small_incomplete_dataset_only_proposes_low_confidence_experiment(self) -> None:
        _, _, rows = _fixture_data()
        report = audit_posts(rows)
        self.assertFalse(report["dataset_quality"]["sample_sufficient"])
        self.assertFalse(report["dataset_quality"]["optional_metrics_complete"])
        self.assertEqual(report["dataset_quality"]["confidence_ceiling"], "low")
        self.assertTrue(report["proposed_experiments"])
        self.assertTrue(all(row["exploratory_only"] for row in report["proposed_experiments"]))
        self.assertTrue(all(not row["causal_claim"] for row in report["proposed_experiments"]))
        self.assertTrue(all(row["automatic_change"] is False for row in report["proposed_experiments"]))

    def test_metrics_patterns_hypotheses_and_experiments_are_separate(self) -> None:
        _, _, rows = _fixture_data()
        report = audit_posts(rows)
        self.assertIn("account_median_views", report["observed_metrics"])
        self.assertTrue(report["descriptive_patterns"])
        self.assertTrue(all(row["classification"] == "descriptive_pattern" for row in report["descriptive_patterns"]))
        self.assertTrue(all(row["not_causal"] for row in report["descriptive_patterns"]))
        self.assertTrue(all(row["not_causal"] for row in report["hypotheses"]))
        self.assertTrue(all(row["basis"] == "descriptive_pattern_not_causal" for row in report["proposed_experiments"]))


class RecommendationPipelineTests(unittest.TestCase):
    def test_disabled_flag_preserves_existing_behavior_without_running_modules(self) -> None:
        with patch.dict(os.environ, {"GROWTH_INTELLIGENCE_ENABLED": "0"}, clear=False), patch(
            "src.intelligence.pipeline.analyze_viral_patterns"
        ) as viral, patch(
            "src.intelligence.pipeline.build_repurposing_package"
        ) as repurpose, patch(
            "src.intelligence.pipeline.audit_posts"
        ) as audit:
            report = build_recommendation_pipeline(viral_rows=[], source={}, audit_rows=[])
        self.assertFalse(report["enabled"])
        self.assertEqual(report["content_plan_suggestions"], [])
        self.assertFalse(report["production_topic_weights_changed"])
        self.assertFalse(report["publishing_invoked"])
        self.assertEqual(report["scheduling_effect"], "none")
        viral.assert_not_called()
        repurpose.assert_not_called()
        audit.assert_not_called()

    def test_feature_flag_defaults_to_disabled(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_enabled())

    def test_enabled_pipeline_is_read_only_and_source_grounded(self) -> None:
        viral_rows, source, audit_rows = _fixture_data()
        report = build_recommendation_pipeline(
            viral_rows=viral_rows, source=source, audit_rows=audit_rows, enabled=True
        )
        self.assertTrue(report["enabled"])
        self.assertFalse(report["publishing_invoked"])
        self.assertEqual(report["scheduling_effect"], "none")
        self.assertFalse(report["production_topic_weights_changed"])
        self.assertTrue(report["content_plan_suggestions"])
        self.assertTrue(all(row["approval_required"] for row in report["content_plan_suggestions"]))
        reel = next(row for row in report["content_plan_suggestions"] if row["format"] == "reel")
        self.assertNotEqual(reel["recommended_hook_formula"], "number_first")
        self.assertEqual(reel["evidence_based_pattern_experiment"]["hook_formula"], "number_first")
        self.assertTrue(reel["evidence_based_pattern_experiment"]["requires_editorial_rewrite"])
        self.assertEqual(reel["analytics_confidence_ceiling"], "low")
        self.assertNotEqual(reel["confidence"], "medium")

    def test_fixtures_are_never_labeled_as_real_performance(self) -> None:
        viral_rows, source, audit_rows = _fixture_data()
        report = build_recommendation_pipeline(
            viral_rows=viral_rows, source=source, audit_rows=audit_rows, enabled=True
        )
        labels = json.dumps(report["data_classification"], ensure_ascii=False)
        self.assertIn("synthetic", labels)
        self.assertIn("not_real", labels)

    def test_pipeline_never_calls_existing_publishers(self) -> None:
        viral_rows, source, audit_rows = _fixture_data()
        with patch.object(social_v2, "publish_all") as publish:
            report = build_recommendation_pipeline(
                viral_rows=viral_rows, source=source, audit_rows=audit_rows, enabled=True
            )
        publish.assert_not_called()
        self.assertFalse(report["publishing_invoked"])


if __name__ == "__main__":
    unittest.main()
