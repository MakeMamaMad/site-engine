import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.autoposter.src.content import guides  # noqa: E402


class GuideShortsTest(unittest.TestCase):
    def setUp(self):
        self.config = guides.load_config()

    def test_episodes_link_to_existing_pages(self):
        data = json.loads((ROOT / "frontend" / "data" / "knowledge_articles.json").read_text(encoding="utf-8"))
        items = data["items"] if isinstance(data, dict) else data
        pages = {f"https://spec-avtoportal.ru/knowledge/{a['slug']}/" for a in items}
        sys.path.insert(0, str(ROOT / "tools"))
        from tools_hub import TOOLS
        pages |= {"https://spec-avtoportal.ru" + href for href, *_ in TOOLS}
        ids = [e["id"] for e in self.config["episodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        for episode in self.config["episodes"]:
            self.assertIn(episode["url"], pages, episode["id"])
            self.assertTrue(3 <= len(episode["scenes"]) <= 5)
            for scene in episode["scenes"]:
                self.assertLessEqual(len(scene["overlay"]), 40, scene["overlay"])

    def test_storyboard(self):
        episode = self.config["episodes"][0]
        board = guides.build_storyboard(self.config, episode)
        self.assertEqual(board.format, "explainer")
        self.assertEqual(board.scenes[-1].id, "cta")
        self.assertIn(episode["url"], board.youtube_description)
        self.assertTrue(all(s.visual_prompt for s in board.scenes))

    def test_pick(self):
        first = self.config["episodes"][0]
        self.assertEqual(guides.pick_episode(self.config, [])["id"], first["id"])
        self.assertNotEqual(guides.pick_episode(self.config, [guides.episode_key(first)])["id"], first["id"])
        self.assertIsNone(guides.pick_episode(self.config, [guides.episode_key(e) for e in self.config["episodes"]]))


if __name__ == "__main__":
    unittest.main()
