import unittest

from tools.autoposter.src.crossplatform.metricool_posts import SCHEMAS, apply_owner_mapping, import_posts

T = "2026-10-30T10:00:00+03:00"


def sample(platform, rows):
    return import_posts(platform, {"rows": rows}, metric_ids=list(SCHEMAS[platform]), collected_at=T)


class MetricoolPostsTests(unittest.TestCase):
    def test_youtube_nullable_views(self):
        result = sample("youtube", [["20261029162608", "https://www.youtube.com/watch?v=SvIrsKeSnw0", None, "SAT"]])
        self.assertIsNone(result["posts"][0]["views"])
        self.assertEqual(result["posts"][0]["title"], "SAT")
        self.assertEqual(result["posts"][0]["match_status"], "requires_explicit_owner_mapping")

    def test_instagram_and_tiktok(self):
        ig = sample("instagram", [["20261029162902", "https://www.instagram.com/reel/DfFb7_7DPDk/", "86"]])
        tt = sample("tiktok", [["20261029162556", "https://www.tiktok.com/@specavtoportal/video/7702126871189802260?utm_source=metricool", "74"]])
        self.assertEqual(ig["posts"][0]["views"], 86)
        self.assertEqual(tt["posts"][0]["views"], 74)
        self.assertNotIn("utm_source", tt["posts"][0]["post_url"])
        self.assertEqual(apply_owner_mapping([ig, tt], {})["unmapped"], 2)

    def test_owner_mapping_only(self):
        ig = sample("instagram", [["20261029162902", "https://www.instagram.com/reel/DfFb7_7DPDk/", "86"]])
        result = apply_owner_mapping([ig], {"https://www.instagram.com/reel/DfFb7_7DPDk": "article-SAT"})
        self.assertEqual(result["observations"][0]["content_id"], "article-SAT")

    def test_reject_domain_and_duplicate(self):
        r = sample("instagram", [["20261029162902", "https://evil.example/reel/foo", "10"],
                                 ["20261029162902", "https://www.instagram.com/reel/ok", "10"],
                                 ["20261029162902", "https://www.instagram.com/reel/ok?tracking=1", "10"]])
        self.assertEqual(len(r["posts"]), 1)
        self.assertEqual(len(r["rejected"]), 2)

    def test_reject_invalid_count(self):
        r = sample("tiktok", [["20261029162556", "https://www.tiktok.com/@a/video/123", "1.2K"]])
        self.assertEqual(len(r["posts"]), 0)
        self.assertEqual(len(r["rejected"]), 1)

    def test_wrong_field_order(self):
        with self.assertRaises(ValueError):
            import_posts("youtube", {"rows": []}, metric_ids=["YTVP05", "YTVP02", "YTVP06", "YTVP17"], collected_at=T)

    def test_no_publishing_or_prod_flag(self):
        from tools.autoposter.src.crossplatform.pipeline import is_enabled
        self.assertFalse(is_enabled("0"))
        self.assertEqual(apply_owner_mapping([], {})["publication_effect"], "none")


if __name__ == "__main__":
    unittest.main()
