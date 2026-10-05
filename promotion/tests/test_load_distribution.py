import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import axle_calculator as axle  # noqa: E402
import load_distribution_calculator as dist  # noqa: E402

NODE = shutil.which("node")


def run(expr, cfg):
    script = dist.DISTRIBUTION_JS + "\nconst cfg=%s, L=%s, M=%s;\nconsole.log(JSON.stringify(%s));" % (
        json.dumps(cfg), json.dumps(axle.AXLE_LIMITS),
        json.dumps({"train": {str(k): v for k, v in axle.MASS_LIMITS["train"].items()}}), expr,
    )
    return json.loads(subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout)


EURO = {
    "tractor": {"rear": "single", "rearSpacing": 0, "wheelbase": 4, "fifth": 1, "front0": 5, "rear0": 3},
    "trailer": {"group": "triple", "count": 3, "spacing": 1.31, "tyres": "single", "kingpinToBogie": 8,
                "kingpinFromFront": 1, "body": 13.6, "kingpin0": 2, "bogie0": 4},
}


@unittest.skipUnless(NODE, "node is not installed")
class DistributionTest(unittest.TestCase):
    def test_lever_rule(self):
        # 16 t at 5 m from the front wall = 4 m behind the kingpin = half of 8 m
        l = run("axleLoads(cfg, 16, 5)", EURO)
        self.assertAlmostEqual(l["kingpin"], 2 + 8)
        self.assertAlmostEqual(l["bogie"], 4 + 8)
        self.assertAlmostEqual(l["front"], 5 + 10 * 1 / 4)
        self.assertAlmostEqual(l["rear"], 3 + 10 * 3 / 4)
        self.assertAlmostEqual(l["total"], 5 + 3 + 2 + 4 + 16)

    def test_limits_and_mass(self):
        self.assertEqual(run("limitsFor(cfg, L, 1)", EURO), {"front": 9, "rear": 10, "bogie": 21})
        self.assertEqual(run("[axleCount(cfg), massLimit(M, axleCount(cfg))]", EURO), [5, 40])
        seven = json.loads(json.dumps(EURO))
        seven["tractor"].update(rear="double", rearSpacing=1.35)
        seven["trailer"].update(group="multi", count=4, spacing=1.36)
        self.assertEqual(run("[axleCount(cfg), massLimit(M, axleCount(cfg))]", seven), [7, 44])
        self.assertEqual(run("limitsFor(cfg, L, 1)", seven), {"front": 9, "rear": 16, "bogie": 26})

    def test_safe_range_moves_cargo_off_the_drive_axle(self):
        r = run("safeRange(cfg, L, 1, 20)", EURO)
        self.assertIsNotNone(r["from"])
        self.assertLess(r["from"], r["to"])
        at_front = run("axleLoads(cfg, 20, 0)", EURO)
        self.assertGreater(at_front["rear"], 10)  # cargo at the front wall overloads the drive axle
        best = run("axleLoads(cfg, 20, %s)" % r["best"], EURO)
        self.assertLessEqual(best["rear"], 10)
        self.assertLessEqual(best["bogie"], 21)

    def test_truck_mode(self):
        truck = {"kind": "truck", "tractor": {"rear": "double", "rearSpacing": 1.32, "wheelbase": 4, "front0": 6, "rear0": 6,
                                               "bodyFromFront": 2, "truckBody": 6}, "trailer": {}}
        # 8 t centred 2 m behind the body start = 4 m from the front axle = right over the bogie
        l = run("axleLoads(cfg, 8, 2)", truck)
        self.assertAlmostEqual(l["front"], 6)
        self.assertAlmostEqual(l["rear"], 14)
        self.assertEqual(run("[axleCount(cfg), massLimit(M2, axleCount(cfg), 'truck')]".replace("M2", "{truck:{'2':18,'3':25,'4':32,'5':38}}"), truck), [3, 25])
        lim = run("limitsFor(cfg, L, 1)", truck)
        self.assertEqual(lim["rear"], 16)
        r = run("safeRange(cfg, L, 1, 8)", truck)
        self.assertIsNotNone(r["from"])
        self.assertLessEqual(r["to"], 6)

    def test_cargo_centre(self):
        c = run("cargoCentre([{mass: 10, start: 0, length: 2}, {mass: 10, start: 8, length: 2}])", EURO)
        self.assertAlmostEqual(c["centre"], 5)
        self.assertAlmostEqual(c["mass"], 20)


class PageTest(unittest.TestCase):
    def test_page_renders(self):
        page = dist.render_distribution_calculator_page("https://spec-avtoportal.ru", "")
        self.assertIn('<link rel="canonical" href="https://spec-avtoportal.ru/tools/raspredelenie-gruza-po-osyam/"', page)
        self.assertIn('id="dist-data"', page)
        for p in dist.PRESETS:
            self.assertIn(p["name"], page)
        self.assertIn('id="d-kind"', page)


if __name__ == "__main__":
    unittest.main()
