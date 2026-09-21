#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import unittest

from community import GLOSSARY, PATTERN_ZH, REFUSED_TAG_SOURCES, translate_fragment


class GlossaryTests(unittest.TestCase):
    def test_required_terms_present(self):
        zh = {row["zh"] for row in GLOSSARY}
        for term in ("纵连", "交互", "转圈", "一笔画", "错位", "拍划", "诈称", "水", "Wifi"):
            self.assertIn(term, zh)

    def test_refuses_dxrating(self):
        self.assertIn("dxrating", REFUSED_TAG_SOURCES)

    def test_pattern_map_covers_core_detectors(self):
        for label in ("交互", "纵连", "海底捞型错位", "同位拍划", "Wifi"):
            self.assertIn(label, PATTERN_ZH)

    def test_keeps_unknown_japanese(self):
        text = "これは未知の用語xyzです"
        self.assertEqual(translate_fragment(text), text)


if __name__ == "__main__":
    unittest.main()
