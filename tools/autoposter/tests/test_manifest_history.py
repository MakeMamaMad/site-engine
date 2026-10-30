import tempfile
import unittest
from pathlib import Path
from tools.autoposter.src.crossplatform.manifest_history import archive_render_manifest, load_render_manifests
from tools.autoposter.src.crossplatform.publication_receipts import receipt_mapping


class ManifestHistoryTests(unittest.TestCase):
    def test_history_append_and_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            m = {"content_key": "article-001", "created_at": "2026-10-30T08:00:00Z", "title": "A"}
            p = archive_render_manifest(m, root)
            self.assertEqual(archive_render_manifest(m, root), p)
            self.assertEqual(len(load_render_manifests(root)), 1)
            archive_render_manifest(dict(m, title="B"), root)
            self.assertEqual(len(load_render_manifests(root)), 2)

    def test_reject_invalid_and_no_receipt_inference(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                archive_render_manifest({"title": "X"}, root)
            manifests = [{"content_key": "article-001", "created_at": "2026-10-30T08:00:00Z"}]
            self.assertEqual(receipt_mapping(manifests, [])["url_to_content_id"], {})

if __name__ == "__main__":
    unittest.main()
