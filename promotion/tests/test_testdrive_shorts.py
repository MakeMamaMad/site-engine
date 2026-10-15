import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.autoposter.src.content import sat  # noqa: E402


class TestDriveShortsTest(unittest.TestCase):
    def setUp(self):
        self.config = sat.load_config(sat.TESTDRIVE_PATH)
        self.active = dict(copy.deepcopy(self.config), active=True)

    def test_catalog_is_valid(self):
        ids = [e["id"] for e in self.config["episodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 4)
        for episode in self.config["episodes"]:
            self.assertTrue(3 <= len(episode["scenes"]) <= 5, episode["id"])
            for scene in episode["scenes"]:
                self.assertLessEqual(len(scene["overlay"]), 40, scene["overlay"])

    def test_inactive_series_gives_nothing(self):
        self.assertIsNone(sat.pick_episode(dict(self.config, active=False), []))

    def test_cycle_repeats_with_new_keys(self):
        n = len(self.active["episodes"])
        first = sat.pick_episode(self.active, ["sat:x", "news:y"])
        self.assertEqual(first["id"], self.active["episodes"][0]["id"])
        self.assertEqual(sat.episode_key(first), f"testdrive:{first['id']}#1")
        used = [f"testdrive:e{i}" for i in range(n)]
        again = sat.pick_episode(self.active, used)
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(sat.episode_key(again), f"testdrive:{first['id']}#2")
        second = sat.pick_episode(self.active, used + ["testdrive:z"])
        self.assertEqual(second["id"], self.active["episodes"][1]["id"])

    def test_storyboard_ends_on_signup_card(self):
        episode = sat.pick_episode(self.active, [])
        board = sat.build_storyboard(self.active, episode)
        cta = board.scenes[-1]
        self.assertEqual(cta.id, "cta-partner")
        self.assertEqual(cta.overlay, "pricepvtest.online")
        self.assertEqual(cta.cta_lead, ["ЗАПИСЬ НА ТЕСТ-ДРАЙВ", "— ПО ССЫЛКЕ"])
        self.assertIn("тест-драйв", cta.narration)
        self.assertIn("Записаться на тест-драйв SAT: https://pricepvtest.online/?utm_source=spec-avtoportal", board.youtube_description)
        self.assertIn("Реклама", board.youtube_description)
        self.assertIn("Реклама", board.tiktok_caption)
        self.assertTrue(all(s.source_image_url for s in board.scenes))


if __name__ == "__main__":
    unittest.main()
