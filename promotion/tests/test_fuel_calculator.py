import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import fuel_calculator as fuel  # noqa: E402
import build_seo  # noqa: E402

NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node is not installed")
class FuelTripTest(unittest.TestCase):
    def run_js(self, o):
        out = subprocess.run([NODE, "-e", fuel.FUEL_JS + "\nconsole.log(JSON.stringify(fuelTrip(%s)));" % json.dumps(o)],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_loaded_and_empty_legs(self):
        # 16 of 20 t -> 26 + 8 * 0.8 = 32.4 l/100 km on 1000 km, 26 l/100 km on 500 km empty
        r = self.run_js({"km": 1500, "loadedKm": 1000, "emptyL": 26, "fullL": 34, "payload": 20, "cargo": 16,
                         "winterPct": 0, "price": 70, "tank": 600})
        self.assertAlmostEqual(r["loadedRate"], 32.4)
        self.assertAlmostEqual(r["litres"], 324 + 130)
        self.assertAlmostEqual(r["cost"], 454 * 70)
        self.assertEqual(r["stops"], 0)  # 454 l < 540 l usable

    def test_winter_and_refuels(self):
        r = self.run_js({"km": 3000, "loadedKm": 3000, "emptyL": 30, "fullL": 30, "payload": 20, "cargo": 20,
                         "winterPct": 10, "price": 1, "tank": 500})
        self.assertAlmostEqual(r["litres"], 990)
        self.assertEqual(r["stops"], 2)  # 990 / 450 usable -> 3 tanks
        self.assertAlmostEqual(r["range"], 450 / 33 * 100)

    def test_loaded_km_capped(self):
        r = self.run_js({"km": 100, "loadedKm": 500, "emptyL": 20, "fullL": 40, "payload": 10, "cargo": 10})
        self.assertAlmostEqual(r["litres"], 40)


class PageTest(unittest.TestCase):
    def test_page_and_inline_telegram(self):
        page = fuel.render_fuel_calculator_page("https://spec-avtoportal.ru", "")
        self.assertIn('href="https://spec-avtoportal.ru/tools/rashod-topliva/"', page)
        self.assertIn("FAQPage", page)
        with_tg = build_seo.add_inline_telegram(page)
        self.assertEqual(with_tg.count('class="tg-inline"'), 1)
        self.assertLess(with_tg.index('class="tg-inline"'), with_tg.index('class="calc-note"'))
        self.assertEqual(build_seo.add_inline_telegram(with_tg), with_tg)


if __name__ == "__main__":
    unittest.main()
