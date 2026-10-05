import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import pallet_calculator as pc  # noqa: E402

NODE = shutil.which("node")


def js_floor(L, W, a, b):
    out = subprocess.run([NODE, "-e", pc.PALLET_JS + "\nconsole.log(JSON.stringify(palletFloor(%s,%s,%s,%s)));" % (L, W, a, b)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


class PalletTest(unittest.TestCase):
    def test_known_counts(self):
        self.assertEqual(pc.pallet_floor(13.6, 2.45, 1.2, 0.8), 34)   # eurotruck, mixed rows
        self.assertEqual(pc.pallet_floor(13.6, 2.45, 1.2, 1.0), 26)   # FIN
        self.assertEqual(pc.pallet_floor(5.9, 2.35, 1.2, 0.8), 11)    # 20-ft container
        self.assertEqual(pc.pallet_floor(12.03, 2.35, 1.2, 0.8), 25)  # 40-ft container, lanes

    @unittest.skipUnless(NODE, "node is not installed")
    def test_js_matches_python(self):
        for b in pc.BODIES:
            for p in pc.PALLETS:
                self.assertEqual(js_floor(b["length"], b["width"], p["a"], p["b"])["count"],
                                 pc.pallet_floor(b["length"], b["width"], p["a"], p["b"]), (b["id"], p["id"]))

    @unittest.skipUnless(NODE, "node is not installed")
    def test_mass_cap(self):
        out = subprocess.run([NODE, "-e", pc.PALLET_JS + "\nconsole.log(JSON.stringify(palletTotal(33, 1, 20, 800)));"],
                             capture_output=True, text=True, check=True).stdout
        r = json.loads(out)
        self.assertEqual((r["total"], r["limitedBy"]), (25, "mass"))

    def test_page(self):
        page = pc.render_pallet_calculator_page("https://spec-avtoportal.ru", "")
        self.assertIn("<td>34</td>", page)
        self.assertIn('href="https://spec-avtoportal.ru/tools/skolko-pallet-v-furu/"', page)


if __name__ == "__main__":
    unittest.main()
