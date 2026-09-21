#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Japanese community terms -> Chinese player terms. Structural labels stay primary."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Detector labels already use Chinese. Map extras + Japanese wiki wording.
GLOSSARY: list[dict[str, str]] = [
    {"ja": "縦連", "ja_alt": "縦連打", "zh": "纵连", "note": "同一键连续敲击"},
    {"ja": "交互", "ja_alt": "トリル", "zh": "交互", "note": "两键交替，对应 ABAB"},
    {"ja": "回転", "ja_alt": "回る 皿", "zh": "转圈", "note": "沿键位环同向扫；皿在舞萌里常被用来形容转圈扫键"},
    {"ja": "一筆書き", "ja_alt": "連結スライド", "zh": "一笔画", "note": "连接滑条或无头接续"},
    {"ja": "スライド遅延", "ja_alt": "ズレ 遅延スライド", "zh": "错位", "note": "头到起划之间插入其他键"},
    {"ja": "拍スライド", "ja_alt": "同時押しスライド", "zh": "拍划", "note": "起点 TAP 与滑条启动同刻"},
    {"ja": "ウミユリ配置", "ja_alt": "ウミユリ", "zh": "海底捞 / 拍划循环", "note": "等待期异键 + 同位拍划的循环，不是曲名标签"},
    {"ja": "ソフラン", "ja_alt": "BPM変化", "zh": "变速", "note": "谱面内 BPM 变化"},
    {"ja": "詐称", "ja_alt": "定数詐欺", "zh": "诈称", "note": "实际难于官标；本项目只在高置信拟合差上使用"},
    {"ja": "過大評価", "ja_alt": "簡単な譜面", "zh": "水", "note": "实际易于官标；本项目只在高置信拟合差上使用"},
    {"ja": "wifi", "ja_alt": "Wi-Fi wスライド", "zh": "Wifi", "note": "w 形状滑条"},
    {"ja": "タッチ", "ja_alt": "タッチノーツ", "zh": "触摸", "note": "TOUCH / TOUCH HOLD"},
    {"ja": "地力", "ja_alt": "地力譜面", "zh": "地力", "note": "密度/持续输出为主，配置花样相对少"},
    {"ja": "配置", "ja_alt": "配置譜面", "zh": "配置", "note": "手法与形状识别压力大于纯密度"},
    {"ja": "折り返し", "ja_alt": "往復", "zh": "折返", "note": "滑条或扫键方向折返"},
    {"ja": "階段", "ja_alt": "階段押し", "zh": "楼梯", "note": "相邻键连续递进"},
    {"ja": "爆発", "ja_alt": "縦押し地帯", "zh": "爆发", "note": "短时高峰密度"},
    {"ja": "イーチ", "ja_alt": "同時押し", "zh": "同押", "note": "同一时刻多枚外键"},
]

PATTERN_ZH: dict[str, str] = {
    "交互": "交互",
    "纵连": "纵连",
    "扫键": "扫键",
    "转圈": "转圈",
    "连接滑条 / 一笔画": "一笔画",
    "无头滑条接续候选": "一笔画",
    "滑行期间异键并行候选": "滑行并行",
    "等待期异键错位": "错位",
    "同位拍划": "拍划",
    "同位等待 TAP": "拍划",
    "海底捞型错位": "海底捞",
    "连续错位": "连续错位",
    "触摸簇": "触摸",
    "爆发": "爆发",
    "Wifi": "Wifi",
    "位移压力": "位移",
}

# Labels we refuse to invent from unmoderated websites.
REFUSED_TAG_SOURCES = ("dxrating", "dxrating.net")


def glossary_payload() -> dict[str, Any]:
    return {
        "disclaimer": "日服用语对照中国玩家社群通用说法。结构结论以分析器检测为准，不把无审核标签当地面真理。",
        "terms": GLOSSARY,
        "pattern_zh": PATTERN_ZH,
        "refused_tag_sources": list(REFUSED_TAG_SOURCES),
    }


def load_glossary(path: Path | None = None) -> dict[str, Any]:
    if path and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return glossary_payload()


def translate_fragment(text: str) -> str:
    """Replace known Japanese tokens with Chinese. Unknown tokens are kept and marked."""
    if not text:
        return text
    out = text
    # Longer phrases first.
    pairs = sorted(((row["ja"], row["zh"]) for row in GLOSSARY), key=lambda p: len(p[0]), reverse=True)
    extra = []
    for row in GLOSSARY:
        for token in row.get("ja_alt", "").split():
            if token:
                extra.append((token, row["zh"]))
    extra.sort(key=lambda p: len(p[0]), reverse=True)
    for ja, zh in pairs + extra:
        if ja and ja in out:
            out = out.replace(ja, zh)
    return out


def community_terms_for_patterns(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in patterns:
        zh = PATTERN_ZH.get(row.get("label", ""), row.get("label", ""))
        counts[zh] = counts.get(zh, 0) + 1
    return [{"term": term, "count": count, "source": "structure"} for term, count in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]


def annotate_report_patterns(report: dict[str, Any]) -> None:
    report["community_terms"] = community_terms_for_patterns(report.get("patterns") or [])
    for row in report.get("pattern_summary") or []:
        row["zh"] = PATTERN_ZH.get(row.get("label", ""), row.get("label", ""))
