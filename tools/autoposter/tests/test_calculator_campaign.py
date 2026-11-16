"""Pure-offline regression checks for calculator short link packaging."""
import unittest
from urllib.parse import parse_qs, urlsplit

from tools.autoposter.src.crossplatform.calculator_campaign import (
    CAMPAIGN, PLATFORMS, TARGETS, calculator_link, preview_package,
)


class CalculatorCampaignTests(unittest.TestCase):
    def test_exact_target_platform_matrix(self):
        for target, path in TARGETS.items():
            for platform in PLATFORMS:
                with self.subTest(target=target, platform=platform):
                    url = calculator_link(platform=platform, target=target, content_id="axis_001")
                    part = urlsplit(url)
                    self.assertEqual(part.scheme, "https")
                    self.assertEqual(part.netloc, "spec-avtoportal.ru")
                    self.assertEqual(part.path, path)
                    self.assertEqual(part.fragment, "")
                    query = parse_qs(part.query)
                    self.assertEqual(query, {
                        "utm_source": [platform],
                        "utm_medium": ["video"],
                        "utm_campaign": [CAMPAIGN],
                        "utm_content": ["axis_001"],
                    })

    def test_rejects_injections_and_unapproved_destinations(self):
        invalid = [
            {"platform": "instagram", "target": "https://evil.test/", "content_id": "article_1"},
            {"platform": "other", "target": "axle_load", "content_id": "article_1"},
            {"platform": "instagram", "target": "axle_load", "content_id": "../../escape"},
            {"platform": "instagram", "target": "axle_load", "content_id": "id?utm_source=evil"},
            {"platform": "instagram", "target": "axle_load", "content_id": ""},
            {"platform": "instagram", "target": "axle_load", "content_id": "Тест"},
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                calculator_link(**values)

    def test_offline_and_owner_review_only(self):
        data = preview_package(target="trip_cost", content_id="trip_202611")
        self.assertEqual(data["status"], "owner_review_required")
        self.assertEqual(data["production_effect"], "none")
        self.assertFalse(data["publish_called"])
        self.assertEqual(data["paid_api_calls"], 0)
        self.assertEqual(set(data["links"]), set(PLATFORMS))
        self.assertIn("not clickable", data["platform_guidance"]["instagram"])


if __name__ == "__main__":
    unittest.main()
