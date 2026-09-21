#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Match parsed maidata to public catalogs; overlay CN fit_diff / JP internals with confidence gates.

Does not read DXRating crowd tags. Water/fake labels come only from high-confidence
diving-fish fit_diff vs CN official ds.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any

from community import annotate_report_patterns, translate_fragment
from maimai_analyzer import DIFFICULTIES, OFFICIAL_SLOT

DISPLAY_TO_SLOT = {v.lower(): k for k, v in DIFFICULTIES.items()}
TYPE_NORM = {"sd": "sd", "standard": "sd", "std": "sd", "dx": "dx", "deluxe": "dx"}

# Copy-chart quality: total relative error, and per-type abs/rel.
COUNT_TOTAL_REL = 0.03
COUNT_TYPE_ABS = 5
COUNT_TYPE_REL = 0.10

# Fit_diff as a regression / overlay number.
FIT_CNT_DEFAULT = 200
FIT_CNT_HIGH_LEVEL = 150
HIGH_LEVEL = 13.0
STD_DEV_P95_FALLBACK = 8.0

# Water / fake: stricter than "usable fit".
WATER_CNT = 400
WATER_GAP = 0.35


def normalize_title(text: str) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).casefold()
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[\"'`´“”‘’]", "", s)
    s = re.sub(r"[\(（\[【].*?[\)）\]】]", "", s)
    for token in ("dx", "sd", "std", "standard", "deluxe", "でらっくす"):
        if s.endswith(token):
            s = s[: -len(token)]
    return s


def display_band(value: float | None, text: str = "") -> str:
    if value is not None and math.isfinite(value):
        base = int(value)
        frac = value - base
        if frac >= 0.6:
            return f"{base}+"
        return str(base)
    text = (text or "").strip()
    if re.fullmatch(r"\d+\+", text) or re.fullmatch(r"\d+", text):
        return text
    return ""


def counts_close(parsed: dict[str, int], official: dict[str, int] | None) -> tuple[bool, float]:
    if not official or not official.get("total"):
        return False, 99.0
    total_err = abs(parsed.get("total", 0) - official["total"]) / max(1, official["total"])
    if total_err > COUNT_TOTAL_REL:
        return False, total_err
    for key in ("tap", "hold", "slide", "touch", "break"):
        a, b = parsed.get(key, 0), official.get(key, 0)
        allow = max(COUNT_TYPE_ABS, COUNT_TYPE_REL * max(b, 1))
        if abs(a - b) > allow:
            return False, total_err
    return True, total_err


def fit_confidence(cn: dict[str, Any] | None, std_dev_p95: float | None = None) -> dict[str, Any]:
    empty = {"usable": False, "reason": "无国服拟合样本", "cnt": 0, "fit_diff": None, "std_dev": None}
    if not cn:
        return empty
    cnt = cn.get("cnt") or 0
    fit = cn.get("fit_diff")
    std = cn.get("std_dev")
    ds = cn.get("ds")
    if not isinstance(cnt, (int, float)) or cnt <= 0 or not isinstance(fit, (int, float)) or not math.isfinite(fit):
        return {**empty, "reason": "拟合字段缺失"}
    need = FIT_CNT_HIGH_LEVEL if isinstance(ds, (int, float)) and ds >= HIGH_LEVEL else FIT_CNT_DEFAULT
    if cnt < need:
        return {"usable": False, "reason": f"样本数 {int(cnt)} < {need}", "cnt": int(cnt), "fit_diff": fit, "std_dev": std}
    cap = std_dev_p95 if isinstance(std_dev_p95, (int, float)) else STD_DEV_P95_FALLBACK
    if isinstance(std, (int, float)) and std > cap:
        return {"usable": False, "reason": f"达成率标准差 {std:.2f} 高于同等级 P95", "cnt": int(cnt), "fit_diff": fit, "std_dev": std}
    return {"usable": True, "reason": "高置信拟合", "cnt": int(cnt), "fit_diff": fit, "std_dev": std}


def water_verdict(cn: dict[str, Any] | None, confidence: dict[str, Any]) -> dict[str, Any]:
    """Only from high-confidence fit vs CN official ds. Never from crowd tags."""
    base = {"label": None, "code": "insufficient", "detail": "证据不足，不标记水/诈称。", "gap": None}
    if not cn or not confidence.get("usable"):
        return base
    ds, fit, cnt = cn.get("ds"), confidence.get("fit_diff"), confidence.get("cnt") or 0
    if not isinstance(ds, (int, float)) or not isinstance(fit, (int, float)):
        return base
    if cnt < WATER_CNT:
        return {**base, "detail": f"拟合可用，但样本 {cnt} < {WATER_CNT}，仍不标记水/诈称。"}
    gap = fit - ds
    if abs(gap) < WATER_GAP:
        return {"label": None, "code": "aligned", "detail": f"拟合与官标差 {gap:+.2f}，未达 {WATER_GAP} 门槛。", "gap": round(gap, 3)}
    if gap <= -WATER_GAP:
        return {"label": "水", "code": "water", "detail": f"高置信拟合 {fit:.2f} 低于国服官标 {ds:.2f}（差 {gap:.2f}，n={cnt}）。", "gap": round(gap, 3)}
    return {"label": "诈称", "code": "overrated", "detail": f"高置信拟合 {fit:.2f} 高于国服官标 {ds:.2f}（差 {gap:+.2f}，n={cnt}）。", "gap": round(gap, 3)}


def _sheet_key(sheet: dict[str, Any]) -> str:
    return f"{sheet.get('id')}:{sheet.get('type')}:{sheet.get('diff_index')}"


def match_sheet(report: dict[str, Any], catalog: dict[str, Any] | None) -> dict[str, Any] | None:
    if not catalog:
        return None
    title_n = normalize_title(report.get("title") or "")
    artist_n = normalize_title(report.get("artist") or "")
    counts = report.get("note_counts") or {}
    slot = report.get("difficulty")
    index = catalog.get("title_index") or {}
    candidates_idx = list(index.get(title_n) or [])
    sheets = catalog.get("sheets") or []
    if not candidates_idx and title_n:
        # Slow fallback: prefix / containment, still title-based.
        for i, sheet in enumerate(sheets):
            other = sheet.get("title_norm") or normalize_title(sheet.get("title") or "")
            if other and (other == title_n or other in title_n or title_n in other):
                candidates_idx.append(i)
    best = None
    best_score = 1e9
    for i in candidates_idx:
        if i < 0 or i >= len(sheets):
            continue
        sheet = sheets[i]
        if slot in OFFICIAL_SLOT and sheet.get("diff_index") not in (OFFICIAL_SLOT.get(slot), None):
            if sheet.get("slot") != slot:
                continue
        ok, err = counts_close(counts, sheet.get("counts"))
        if not ok:
            continue
        artist_penalty = 0.0
        sheet_artist = sheet.get("artist_norm") or normalize_title(sheet.get("artist") or "")
        if artist_n and sheet_artist and artist_n != sheet_artist:
            artist_penalty = 0.02
        score = err + artist_penalty
        if sheet.get("slot") == slot:
            score -= 0.001
        if score < best_score:
            best, best_score = sheet, score
    return best


def percentile_of(score: float, grid: list[float] | None) -> float | None:
    if not grid or len(grid) < 2:
        return None
    xs = list(grid)
    if score <= xs[0]:
        return 0.0
    if score >= xs[-1]:
        return 100.0
    step = 100.0 / (len(xs) - 1)
    for i in range(len(xs) - 1):
        a, b = xs[i], xs[i + 1]
        if a <= score <= b:
            span = b - a if b != a else 1e-9
            return round(i * step + (score - a) / span * step, 1)
    return None


def attach_percentiles(report: dict[str, Any], percentiles: dict[str, Any] | None, band: str) -> None:
    axes = []
    table = (percentiles or {}).get("by_band") or {}
    grid_for_band = table.get(band) or table.get("all") or {}
    for axis in report.get("radar") or []:
        pct = percentile_of(axis.get("score") or 0, grid_for_band.get(axis.get("label")))
        axes.append({**axis, "peer_percentile": pct, "peer_band": band if pct is not None else None})
    if axes:
        report["radar"] = axes
        report["radar_percentile_note"] = "同等级带百分位来自校准语料的雷达分位数，不是命中率；未进入该等级带则留空。"


def enrich_report(report: dict[str, Any], catalog: dict[str, Any] | None = None, percentiles: dict[str, Any] | None = None) -> dict[str, Any]:
    annotate_report_patterns(report)
    match = match_sheet(report, catalog)
    meta = (catalog or {}).get("meta") or {}
    p95_map = meta.get("std_dev_p95_by_band") or {}
    overlay: dict[str, Any] = {
        "matched": False,
        "reason": "未匹配到公开曲库（曲名+物量）。社区抄谱与官谱不完全一致时会落到这一条。",
        "cn": None,
        "jp": None,
        "water": water_verdict(None, {"usable": False}),
        "community": None,
        "fit_confidence": fit_confidence(None),
    }
    band = display_band(report.get("declared_constant"), report.get("declared_level_text") or "")
    if match:
        cn = match.get("cn")
        band = display_band((cn or {}).get("ds"), (cn or {}).get("display") or band) or band
        conf = fit_confidence(cn, p95_map.get(band))
        overlay.update(
            matched=True,
            reason="曲名与物量通过抄谱质量门槛。",
            key=_sheet_key(match),
            id=match.get("id"),
            title=match.get("title"),
            artist=match.get("artist"),
            type=match.get("type"),
            difficulty_name=match.get("difficulty_name"),
            counts=match.get("counts"),
            count_error=counts_close(report.get("note_counts") or {}, match.get("counts"))[1],
            cn=cn,
            jp=match.get("jp"),
            fit_confidence=conf,
            water=water_verdict(cn, conf),
            community=match.get("community"),
        )
        if overlay.get("community") and overlay["community"].get("bullets"):
            overlay["community"] = {
                **overlay["community"],
                "bullets_zh": [translate_fragment(x) for x in overlay["community"]["bullets"]],
                "role": "日服社群对照，不是本分析器的判定依据。",
            }
        if conf.get("usable") and report.get("prediction") and report["prediction"].get("estimated_level") is not None:
            report["prediction"]["diving_fish_fit"] = round(float(conf["fit_diff"]), 3)
            report["prediction"]["cn_official_ds"] = cn.get("ds") if cn else None
    report["catalog"] = overlay
    attach_percentiles(report, percentiles, band)
    return report


def quantile_grid(values: list[float], steps: int = 20) -> list[float]:
    if not values:
        return []
    xs = sorted(values)
    out = []
    for i in range(steps + 1):
        p = i / steps
        pos = p * (len(xs) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(xs) - 1)
        frac = pos - lo
        out.append(round(xs[lo] * (1 - frac) + xs[hi] * frac, 3))
    return out


def compact_chart_stats_entry(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw:
        return None
    cnt = raw.get("cnt") or 0
    if not cnt:
        return None
    return {
        "cnt": int(cnt),
        "diff": raw.get("diff"),
        "fit_diff": raw.get("fit_diff"),
        "avg": raw.get("avg"),
        "std_dev": raw.get("std_dev"),
        "display": str(raw.get("diff") or ""),
    }
