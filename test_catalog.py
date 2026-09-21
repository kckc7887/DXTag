#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json
import math
import unittest
from pathlib import Path

from catalog import (
    counts_close,
    display_band,
    enrich_report,
    fit_confidence,
    match_sheet,
    normalize_title,
    percentile_of,
    water_verdict,
)
from community import translate_fragment
from maimai_analyzer import analyze, analyze_maidata, load_source, load_source_text, official_style_counts, parse_chart


UMIYURI = Path(__file__).parent / "regression" / "umiyuri_user_maidata.txt"


class NormalizeTests(unittest.TestCase):
    def test_strips_width_and_dx_suffix(self):
        self.assertEqual(normalize_title("ウミユリ海底譚"), normalize_title(" ウミユリ 海底譚 "))
        self.assertEqual(normalize_title("PANDORA PARADOXXX [DX]"), normalize_title("PANDORA PARADOXXX"))

    def test_display_band(self):
        self.assertEqual(display_band(13.4), "13")
        self.assertEqual(display_band(13.7), "13+")
        self.assertEqual(display_band(None, "14+"), "14+")


class CountMatchTests(unittest.TestCase):
    def test_umiyuri_master_matches_gamerch_table(self):
        source = load_source(UMIYURI)
        parsed = parse_chart(source, 5)
        counts = official_style_counts(parsed.notes)
        official = {"tap": 648, "hold": 21, "slide": 76, "touch": 0, "break": 14, "total": 759}
        ok, err = counts_close(counts, official)
        self.assertTrue(ok, (counts, err))
        self.assertLessEqual(err, 0.03)

    def test_rejects_large_total_error(self):
        parsed = {"tap": 100, "hold": 0, "slide": 0, "touch": 0, "break": 0, "total": 100}
        official = {"tap": 200, "hold": 0, "slide": 0, "touch": 0, "break": 0, "total": 200}
        self.assertFalse(counts_close(parsed, official)[0])


class ConfidenceTests(unittest.TestCase):
    def test_low_cnt_not_usable(self):
        cn = {"ds": 13.4, "fit_diff": 13.1, "cnt": 40, "std_dev": 2.0}
        self.assertFalse(fit_confidence(cn)["usable"])
        self.assertEqual(water_verdict(cn, fit_confidence(cn))["code"], "insufficient")

    def test_water_requires_gap_and_cnt(self):
        cn = {"ds": 13.4, "fit_diff": 12.6, "cnt": 800, "std_dev": 2.0}
        conf = fit_confidence(cn)
        self.assertTrue(conf["usable"])
        verdict = water_verdict(cn, conf)
        self.assertEqual(verdict["code"], "water")
        self.assertEqual(verdict["label"], "水")

    def test_overrated(self):
        cn = {"ds": 13.0, "fit_diff": 13.8, "cnt": 900, "std_dev": 1.5}
        self.assertEqual(water_verdict(cn, fit_confidence(cn))["code"], "overrated")

    def test_small_gap_not_labeled(self):
        cn = {"ds": 13.4, "fit_diff": 13.45, "cnt": 900, "std_dev": 1.2}
        self.assertEqual(water_verdict(cn, fit_confidence(cn))["code"], "aligned")

    def test_high_std_dev_rejected(self):
        cn = {"ds": 13.4, "fit_diff": 13.1, "cnt": 900, "std_dev": 20}
        self.assertFalse(fit_confidence(cn, std_dev_p95=4.0)["usable"])


class EnrichTests(unittest.TestCase):
    def test_match_and_community_translation(self):
        source = load_source(UMIYURI)
        report = analyze(parse_chart(source, 5), source, 5)
        catalog = {
            "meta": {"std_dev_p95_by_band": {"13": 6.0}},
            "title_index": {normalize_title(report["title"]): [0]},
            "sheets": [
                {
                    "id": "70",
                    "title": report["title"],
                    "title_norm": normalize_title(report["title"]),
                    "artist": report["artist"],
                    "artist_norm": normalize_title(report["artist"]),
                    "type": "sd",
                    "slot": 5,
                    "diff_index": 3,
                    "difficulty_name": "MASTER",
                    "counts": report["note_counts"],
                    "cn": {"display": "13", "ds": 13.4, "fit_diff": 13.05, "cnt": 5000, "std_dev": 2.0},
                    "jp": {"display": "13", "internal": 13.4},
                    "community": {
                        "source": "gamerch",
                        "url": "https://gamerch.com/maimai/533675",
                        "bullets": ["所謂「ウミユリ配置」でイーチとスライドが混ざる"],
                    },
                }
            ],
        }
        percentiles = {"by_band": {"13": {"错位（估）": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]}}}
        enrich_report(report, catalog, percentiles)
        self.assertTrue(report["catalog"]["matched"])
        self.assertEqual(report["catalog"]["jp"]["internal"], 13.4)
        self.assertEqual(report["catalog"]["water"]["code"], "aligned")
        self.assertTrue(report["catalog"]["community"]["bullets_zh"])
        self.assertIn("海底捞", report["catalog"]["community"]["bullets_zh"][0])
        self.assertTrue(any(t["term"] == "海底捞" for t in report["community_terms"]))
        self.assertIsNotNone(report["radar"][8].get("peer_percentile"))

    def test_real_catalog_umiyuri_is_high_confidence(self):
        path = Path(__file__).parent / "data" / "catalog.json"
        if not path.is_file():
            self.skipTest("catalog snapshot not built")
        catalog = json.loads(path.read_text(encoding="utf-8"))
        source = load_source(UMIYURI)
        report = analyze(parse_chart(source, 5), source, 5)
        enrich_report(report, catalog, None)
        self.assertTrue(report["catalog"]["matched"])
        self.assertEqual(report["catalog"]["id"], "417")
        self.assertTrue(report["catalog"]["fit_confidence"]["usable"])
        self.assertEqual(report["catalog"]["jp"]["internal"], 13.4)
        self.assertEqual(report["catalog"]["water"]["code"], "water")
        self.assertEqual(report["catalog"]["community"]["source"], "gamerch")
        self.assertTrue(any("海底捞" in b for b in report["catalog"]["community"]["bullets_zh"]))
        model_path = Path(__file__).parent / "data" / "model.json"
        if model_path.is_file():
            model = json.loads(model_path.read_text(encoding="utf-8"))
            percentiles = None
            ppath = Path(__file__).parent / "data" / "percentiles.json"
            if ppath.is_file():
                percentiles = json.loads(ppath.read_text(encoding="utf-8"))
            doc = analyze_maidata(UMIYURI.read_text(encoding="utf-8-sig"), origin="umiyuri.txt", model=model, catalog=catalog, percentiles=percentiles)
            master = next(r for r in doc["reports"] if r["difficulty"] == 5)
            self.assertTrue(master["prediction"]["calibrated"])
            self.assertAlmostEqual(master["prediction"]["estimated_level"], 13.0, delta=1.0)

    def test_unmatched_does_not_invent_water(self):
        body = "(120){4}" + ",".join(["1"] * 40) + ",E"
        source = load_source_text(body)
        report = analyze(parse_chart(source, 5), source, 5)
        enrich_report(report, {"sheets": [], "title_index": {}}, None)
        self.assertFalse(report["catalog"]["matched"])
        self.assertEqual(report["catalog"]["water"]["code"], "insufficient")


class PercentileTests(unittest.TestCase):
    def test_interp(self):
        grid = [i * 5 for i in range(21)]
        self.assertEqual(percentile_of(0, grid), 0)
        self.assertEqual(percentile_of(100, grid), 100)
        self.assertAlmostEqual(percentile_of(50, grid), 50, places=0)


class TranslateTests(unittest.TestCase):
    def test_umiyuri_phrase(self):
        zh = translate_fragment("ウミユリ配置は縦連ではない")
        self.assertIn("海底捞", zh)
        self.assertIn("纵连", zh)
        self.assertNotIn("ウミユリ配置", zh)


if __name__ == "__main__":
    unittest.main()
