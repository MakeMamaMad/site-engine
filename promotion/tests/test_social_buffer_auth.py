import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# The real uploaders need Google/Buffer client libraries; the test replaces them.
import types  # noqa: E402

for name, attr in (("tools.autoposter.src.publish.youtube", "upload_video"),
                   ("tools.autoposter.src.publish.buffer", "publish_video")):
    if name not in sys.modules:
        stub = types.ModuleType(name)
        setattr(stub, attr, lambda *a, **k: None)
        sys.modules[name] = stub

from tools.autoposter.src.publish import social_v2  # noqa: E402


class BufferAuthTest(unittest.TestCase):
    def run_publish(self, buffer_error):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out = tmp / "out"
            out.mkdir()
            (out / "manifest.json").write_text(json.dumps({"content_key": "k1", "title": "T"}), encoding="utf-8")
            (out / "scene_plan.json").write_text("{}", encoding="utf-8")
            (out / "master.mp4").write_bytes(b"x")
            for name in ("caption_youtube.txt", "caption_tiktok.txt", "caption_instagram.txt"):
                (out / name).write_text("text", encoding="utf-8")
            (tmp / "token.json").write_text("{}", encoding="utf-8")

            def buffer(**kwargs):
                raise RuntimeError(buffer_error)

            env = {"YOUTUBE_TOKEN_FILE": str(tmp / "token.json"), "BUFFER_API_KEY": "k", "SOCIAL_STRICT": "1",
                   "BUFFER_TIKTOK_VIDEO_URL": "u", "BUFFER_INSTAGRAM_VIDEO_URL": "u"}
            with mock.patch.object(social_v2, "OUT_DIR", out), \
                 mock.patch.object(social_v2, "SOCIAL_STATE_PATH", tmp / "social.json"), \
                 mock.patch.object(social_v2, "V2_STATE_PATH", tmp / "v2.json"), \
                 mock.patch.object(social_v2, "upload_video", return_value="vid"), \
                 mock.patch.object(social_v2, "publish_buffer_video", side_effect=buffer), \
                 mock.patch.dict(os.environ, env):
                summary = social_v2.publish_all()
                used = json.loads((tmp / "v2.json").read_text(encoding="utf-8")) if (tmp / "v2.json").exists() else {}
            return summary, used

    def test_expired_buffer_key_does_not_stall_the_slot(self):
        summary, used = self.run_publish("Buffer API HTTP 401: {'errors': [{'message': 'Access token is not valid'}]}")
        self.assertEqual(summary["auth_blocked"], ["tiktok", "instagram"])
        self.assertEqual(summary["platforms"]["youtube"]["status"], "published")
        self.assertIn("k1", json.dumps(used))

    def test_other_buffer_errors_stay_strict(self):
        with self.assertRaises(RuntimeError):
            self.run_publish("Buffer API HTTP 500: boom")


if __name__ == "__main__":
    unittest.main()
