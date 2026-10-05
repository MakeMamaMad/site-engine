from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import axle_calculator as calc  # noqa: E402


class AxleCalculatorTests(unittest.TestCase):
    def test_limits_shape_and_monotonic(self) -> None:
        for kind, by_tyres in calc.AXLE_LIMITS.items():
            for tyres, bands in by_tyres.items():
                for band, values in bands.items():
                    self.assertEqual(len(values), 3, (kind, tyres, band))
                    # a stronger road never allows less
                    self.assertEqual(values, sorted(values), (kind, tyres, band))
                    # dual tyres never allow less than single tyres
                    self.assertGreaterEqual(by_tyres["dual"][band], by_tyres["single"][band])
            if kind != "single":
                self.assertEqual(list(by_tyres["single"]), calc.SPACING_BANDS)
                # wider spacing never allows less
                for tyres in ("single", "dual"):
                    rows = [by_tyres[tyres][b] for b in calc.SPACING_BANDS]
                    for road in range(3):
                        column = [r[road] for r in rows]
                        self.assertEqual(column, sorted(column), (kind, tyres, road))

    def test_key_values_from_decree_2060(self) -> None:
        # single axle, dual tyres: 6 / 10 / 11.5 t
        self.assertEqual(calc.AXLE_LIMITS["single"]["dual"]["any"], [6, 10, 11.5])
        # triple group 1.3-1.8 m, single tyres (typical semi-trailer): 21 t on a 10 t road
        self.assertEqual(calc.AXLE_LIMITS["triple"]["single"]["1.3-1.8"][1], 21)
        self.assertEqual(calc.MASS_LIMITS["train"][6], 44)
        self.assertEqual(calc.MASS_LIMITS["truck"][2], 18)

    def test_presets_fit_limits_on_10t_road(self) -> None:
        band = lambda d: "lt1" if d < 1 else "1-1.3" if d < 1.3 else "1.3-1.8" if d < 1.8 else "1.8-2.5"
        for preset in calc.PRESETS:
            axles, total = 0, 0.0
            for g in preset["groups"]:
                if g["type"] == "single":
                    limit, n = calc.AXLE_LIMITS["single"][g["tyres"]]["any"][1], 1
                else:
                    d = float(g["spacing"].replace(",", "."))
                    limit, n = calc.AXLE_LIMITS[g["type"]][g["tyres"]][band(d)][1], {"double": 2, "triple": 3}[g["type"]]
                self.assertLessEqual(g["load"], limit, preset["id"])
                axles += n
                total += g["load"]
            table = calc.MASS_LIMITS[preset["kind"]]
            self.assertLessEqual(total, table[max(k for k in table if k <= axles)], preset["id"])

    def test_page_renders_with_data_and_faq(self) -> None:
        page = calc.render_axle_calculator_page("https://spec-avtoportal.ru", "<section class='tg-cta'></section>")
        self.assertIn('<link rel="canonical" href="https://spec-avtoportal.ru/tools/nagruzka-na-os/" />', page)
        data = json.loads(re.search(r'<script type="application/json" id="axle-data">(.*?)</script>', page, re.S).group(1))
        self.assertEqual(data["roads"], [6, 10, 11.5])
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
        self.assertEqual([x["@type"] for x in ld], ["WebApplication", "FAQPage"])
        self.assertIn(calc.OFFICIAL_URL, page)


if __name__ == "__main__":
    unittest.main()


class EmbedTest(unittest.TestCase):
    def test_embed_page_and_snippet(self):
        import axle_calculator as ac
        page = ac.render_axle_embed_page("https://spec-avtoportal.ru")
        self.assertIn('id="calc-groups"', page)
        self.assertIn("noindex", page)
        snippet = ac.embed_snippet("https://spec-avtoportal.ru")
        self.assertIn('src="https://spec-avtoportal.ru/embed/nagruzka-na-os/"', snippet)
        self.assertIn('<a href="https://spec-avtoportal.ru/tools/nagruzka-na-os/">', snippet)
