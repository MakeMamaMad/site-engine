"""Offline deterministic tests for Metricool daily evolution import."""
import unittest

from tools.autoposter.src.crossplatform.metricool_daily import (
    FIELD_IDS, build_daily_report, import_metricool_daily,
)

STAMP = "2026-10-30T12:00:00+03:00"


def ingest(platform, rows):
    return import_metricool_daily(
        platform, {"rows": rows},
        metric_ids=list(FIELD_IDS[platform].values()), collected_at=STAMP,
    )


class MetricoolDailyTests(unittest.TestCase):
    def test_sparse_and_unsorted_days(self):
        data = ingest("youtube", [["15.0", "70.0", "20261030"], ["7.0", None, "20261028"]])
        self.assertEqual(data["daily"][0]["date"], "2026-10-28")
        self.assertEqual(data["summary"]["sum_daily_views"], 22)
        self.assertEqual(data["summary"]["latest_followers"], 70)

    def test_missing_is_not_zero(self):
        data = ingest("instagram", [[None, None, "20261029"]])
        self.assertIsNone(data["summary"]["sum_daily_views"])
        self.assertIsNone(data["summary"]["latest_followers"])

    def test_empty_is_not_zero(self):
        data = ingest("tiktok", [])
        self.assertIsNone(data["summary"]["sum_daily_views"])
        self.assertIn("no_rows_returned_not_equivalent_to_zero", data["warnings"])

    def test_bad_and_duplicate_days_rejected(self):
        for rows in ([[["12", None, "20260230"]]], [["1", None, "20261030"], ["2", None, "20261030"]]]):
            with self.assertRaises(ValueError):
                ingest("tiktok", rows)

    def test_invalid_counts_rejected(self):
        for bad in ("1.2K", -3, True, "NaN", "7.1"):
            with self.assertRaises(ValueError):
                ingest("youtube", [[bad, None, "20261030"]])

    def test_wrong_field_order_rejected(self):
        with self.assertRaises(ValueError):
            import_metricool_daily("youtube", {"rows": []}, metric_ids=["YTEV01", "YTEV02"], collected_at=STAMP)

    def test_timezone_required(self):
        with self.assertRaises(ValueError):
            import_metricool_daily("youtube", {"rows": []}, metric_ids=list(FIELD_IDS["youtube"].values()), collected_at="2026-10-30T12:00:00")

    def test_reports_never_claim_post_level(self):
        report = build_daily_report([ingest("youtube", [["100", "70", "20261030"]])])
        self.assertTrue(report["not_post_level"])
        self.assertEqual(report["website_attribution"], "unavailable")

    def test_no_production_side_effects(self):
        from tools.autoposter.src.crossplatform.pipeline import is_enabled
        self.assertFalse(is_enabled("0"))
        self.assertFalse(is_enabled(""))
        self.assertTrue(is_enabled("1"))


if __name__ == "__main__":
    unittest.main()
