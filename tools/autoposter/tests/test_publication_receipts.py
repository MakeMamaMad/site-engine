import unittest
from tools.autoposter.src.crossplatform.publication_receipts import canonical_post_url, receipt_mapping


class ReceiptTests(unittest.TestCase):
    def test_youtube_video_id_survives_tracking_removal(self):
        a = canonical_post_url("youtube", "https://www.youtube.com/watch?v=SvIrsKeSnw0&utm_source=xx")
        b = canonical_post_url("youtube", "https://youtu.be/SvIrsKeSnw0")
        self.assertEqual(a, b)
        self.assertEqual(a, "https://www.youtube.com/watch?v=SvIrsKeSnw0")

    def test_only_explicit_receipt_maps(self):
        r = receipt_mapping(
            [{"content_key": "article_123"}],
            [{"content_key": "article_123", "platform": "instagram",
              "post_url": "https://www.instagram.com/reel/DfFb7_7DPDk/"}])
        self.assertEqual(r["url_to_content_id"]["https://www.instagram.com/reel/DfFb7_7DPDk"], "article_123")

    def test_unbacked_key_is_rejected(self):
        r = receipt_mapping([{"content_key": "known"}], [
            {"content_key": "unverified", "platform": "tiktok",
             "post_url": "https://www.tiktok.com/@specavtoportal/video/7702126871189802260"}])
        self.assertEqual(r["url_to_content_id"], {})
        self.assertEqual(len(r["rejected"]), 1)

    def test_reject_host_and_duplicate(self):
        r = receipt_mapping([{"content_key": "known"}], [
            {"content_key": "known", "platform": "instagram",
             "post_url": "https://evil.example/reel/123"},
            {"content_key": "known", "platform": "youtube",
             "post_url": "https://youtu.be/SvIrsKeSnw0"},
            {"content_key": "known", "platform": "youtube",
             "post_url": "https://www.youtube.com/watch?v=SvIrsKeSnw0"}])
        self.assertEqual(len(r["rejected"]), 2)

    def test_no_flag_enabled(self):
        from tools.autoposter.src.crossplatform.pipeline import is_enabled
        self.assertFalse(is_enabled("0"))


if __name__ == "__main__":
    unittest.main()
