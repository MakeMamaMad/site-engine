import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import trip_cost_calculator as trip  # noqa: E402

NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node is not installed")
class TripCostTest(unittest.TestCase):
    def run_js(self, o):
        out = subprocess.run([NODE, "-e", trip.TRIP_JS + "\nconsole.log(JSON.stringify(tripCost(%s)));" % json.dumps(o)],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_breakdown(self):
        r = self.run_js({"km": 1000, "consumption": 30, "fuelPrice": 70, "platon": True, "federalShare": 50, "platonRate": 5.19,
                         "tolls": 2000, "speed": 60, "dayDrive": 9, "driverPerKm": 10, "perDiem": 1000, "runningPerKm": 15, "marginPct": 10})
        self.assertAlmostEqual(r["fuel"], 300 * 70)
        self.assertAlmostEqual(r["platon"], 500 * 5.19)
        self.assertEqual(r["days"], 2)  # 16.7 h of driving at 9 h a day
        self.assertAlmostEqual(r["driver"], 10000 + 2000)
        cost = 21000 + 2595 + 2000 + 12000 + 15000
        self.assertAlmostEqual(r["cost"], cost)
        self.assertAlmostEqual(r["price"], cost * 1.1)
        self.assertAlmostEqual(r["perKm"], cost / 1000)

    def test_no_platon(self):
        self.assertEqual(self.run_js({"km": 100, "platon": False, "federalShare": 100, "platonRate": 5})["platon"], 0)


class PageTest(unittest.TestCase):
    def test_page(self):
        page = trip.render_trip_cost_page("https://spec-avtoportal.ru", "")
        self.assertIn("5,19", page)
        self.assertIn('href="https://spec-avtoportal.ru/tools/stoimost-reysa/"', page)


if __name__ == "__main__":
    unittest.main()
