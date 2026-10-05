import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import fine_calculator as fine  # noqa: E402

NODE = shutil.which("node")


def run(expr):
    out = subprocess.run([NODE, "-e", fine.FINE_JS + "\nconsole.log(JSON.stringify(%s));" % expr], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@unittest.skipUnless(NODE, "node is not installed")
class FineTest(unittest.TestCase):
    def test_mass_thresholds(self):
        self.assertEqual(run("overloadFine('mass', 44, 44)")["fine"], 0)
        r = run("overloadFine('mass', 44, 48.4)")  # exactly +10 %
        self.assertTrue(r["belowThreshold"])
        self.assertEqual(r["fine"], 0)
        self.assertEqual(run("overloadFine('mass', 44, 49)")["part"], 4)  # article example, 11.4 %
        self.assertEqual(run("overloadFine('axle', 10, 12)")["part"], 4)   # exactly 20 %
        self.assertEqual(run("overloadFine('axle', 10, 12.5)")["fine"], 450000)
        self.assertEqual(run("overloadFine('axle', 10, 15)")["part"], 5)   # exactly 50 %
        self.assertEqual(run("overloadFine('axle', 10, 15.1)")["fine"], 600000)

    def test_dimensions(self):
        r = run("overloadFine('dim', 4, 4.08)")
        self.assertEqual((r["part"], r["fine"], r["cameraExempt"]), (1, 150000, True))
        self.assertEqual(run("overloadFine('dim', 4, 4.2)")["part"], 4)
        self.assertEqual(run("overloadFine('dim', 2.6, 3.0)")["part"], 5)
        self.assertEqual(run("overloadFine('dim', 20, 20.6)")["part"], 6)
        self.assertFalse(run("overloadFine('dim', 4, 3.9)")["over"])

    def test_limit_without_fine(self):
        self.assertAlmostEqual(run("maxWithoutFine('mass', 40)"), 44)


class PageTest(unittest.TestCase):
    def test_render(self):
        page = fine.render_fine_calculator_page("https://spec-avtoportal.ru", "")
        self.assertIn('href="https://spec-avtoportal.ru/tools/shtraf-za-peregruz/"', page)
        self.assertIn("12.21.1", page)


if __name__ == "__main__":
    unittest.main()
