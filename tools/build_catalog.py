#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build compact catalog, optional ridge model, and radar percentile tables.

Training charts stay in corpus/ and are not committed. Outputs in data/ are snapshots
of public stats + model weights only.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from calibrate import cross_validate, fit  # noqa: E402
from catalog import (  # noqa: E402
    compact_chart_stats_entry,
    counts_close,
    display_band,
    fit_confidence,
    normalize_title,
    quantile_grid,
)
from maimai_analyzer import (  # noqa: E402
    DIFFICULTIES,
    MODEL_FEATURES,
    OFFICIAL_SLOT,
    VERSION,
    analyze,
    load_source,
    parse_chart,
)

DIFF_NAME_TO_INDEX = {"basic": 0, "advanced": 1, "expert": 2, "master": 3, "remaster": 4, "re:master": 4, "re:mas": 4}


def lookup_impression(impressions: dict[str, Any] | None, sid: str, typ: str, diff_index: int, title_n: str) -> dict[str, Any] | None:
    if not impressions:
        return None
    by_norm = impressions.get("by_title_norm") or {}
    if by_norm:
        by_norm = {normalize_title(k): v for k, v in by_norm.items()}
    return impressions.get(f"{sid}:{typ}:{diff_index}") or impressions.get(title_n) or by_norm.get(title_n)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def official_counts_from_notes(notes: list[int] | None) -> dict[str, int] | None:
    if not notes:
        return None
    # SD: [tap, hold, slide, break]; DX: [tap, hold, slide, touch, break]
    if len(notes) >= 5:
        tap, hold, slide, touch, brk = [int(x or 0) for x in notes[:5]]
    elif len(notes) == 4:
        tap, hold, slide, brk = [int(x or 0) for x in notes]
        touch = 0
    else:
        return None
    return {"tap": tap, "hold": hold, "slide": slide, "touch": touch, "break": brk, "total": tap + hold + slide + touch + brk}


def dxdata_counts(sheet: dict[str, Any]) -> dict[str, int] | None:
    nc = sheet.get("noteCounts") or {}
    if not nc:
        return None
    tap, hold, slide = int(nc.get("tap") or 0), int(nc.get("hold") or 0), int(nc.get("slide") or 0)
    touch = int(nc.get("touch") or 0)
    brk = int(nc.get("break") or 0)
    total = int(nc.get("total") or (tap + hold + slide + touch + brk))
    return {"tap": tap, "hold": hold, "slide": slide, "touch": touch, "break": brk, "total": total}


def std_dev_p95(chart_stats: dict[str, Any]) -> dict[str, float]:
    buckets: dict[str, list[float]] = defaultdict(list)
    charts = chart_stats.get("charts") or {}
    for _sid, arr in charts.items():
        if not isinstance(arr, list):
            continue
        for ch in arr:
            if not isinstance(ch, dict):
                continue
            std = ch.get("std_dev")
            diff = str(ch.get("diff") or "")
            if isinstance(std, (int, float)) and math.isfinite(std) and diff:
                buckets[diff].append(float(std))
    return {k: (quantile_grid(vs)[19] if len(quantile_grid(vs)) >= 20 else (sorted(vs)[min(len(vs) - 1, int(0.95 * (len(vs) - 1)))] if vs else 8.0)) for k, vs in buckets.items()}


def build_jp_index(dxdata: Any) -> dict[tuple[str, str, int], dict[str, Any]]:
    songs = dxdata.get("songs") if isinstance(dxdata, dict) else dxdata
    if isinstance(dxdata, dict) and not songs and "sheets" in str(dxdata)[:200]:
        songs = dxdata.get("songs") or []
    if isinstance(dxdata, list):
        songs = dxdata
    index: dict[tuple[str, str, int], dict[str, Any]] = {}
    if not isinstance(songs, list):
        return index
    for song in songs:
        if not isinstance(song, dict):
            continue
        title_n = normalize_title(song.get("title") or song.get("songId") or "")
        artist = song.get("artist") or ""
        for sheet in song.get("sheets") or []:
            diff_name = str(sheet.get("difficulty") or "").lower()
            idx = DIFF_NAME_TO_INDEX.get(diff_name)
            if idx is None:
                continue
            typ = str(sheet.get("type") or "dx").lower()
            if typ in ("std", "standard"):
                typ = "sd"
            index[(title_n, typ, idx)] = {
                "display": str(sheet.get("level") or ""),
                "internal": sheet.get("internalLevelValue"),
                "counts": dxdata_counts(sheet),
                "artist": artist,
            }
    return index


def build_catalog(music: list[dict[str, Any]], stats: dict[str, Any], jp_index: dict[tuple[str, str, int], dict[str, Any]], impressions: dict[str, Any] | None = None) -> dict[str, Any]:
    p95 = std_dev_p95(stats)
    charts_stats = stats.get("charts") or {}
    sheets: list[dict[str, Any]] = []
    title_index: dict[str, list[int]] = defaultdict(list)
    for song in music:
        sid = str(song.get("id"))
        title = song.get("title") or song.get("basic_info", {}).get("title") or ""
        basic = song.get("basic_info") or {}
        artist = basic.get("artist") or song.get("artist") or ""
        typ = str(song.get("type") or "DX").lower()
        if typ in ("standard", "std"):
            typ = "sd"
        elif typ != "sd":
            typ = "dx"
        ds_list = song.get("ds") or []
        level_list = song.get("level") or []
        chart_list = song.get("charts") or []
        stat_arr = charts_stats.get(sid) or charts_stats.get(str(int(sid) if str(sid).isdigit() else sid)) or []
        title_n = normalize_title(title)
        artist_n = normalize_title(artist)
        for diff_index, chart in enumerate(chart_list):
            slot = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6}.get(diff_index)
            if slot is None:
                continue
            notes = None
            if isinstance(chart, dict):
                notes = official_counts_from_notes(chart.get("notes"))
            ds = ds_list[diff_index] if diff_index < len(ds_list) else None
            display = str(level_list[diff_index]) if diff_index < len(level_list) else ""
            raw_stat = stat_arr[diff_index] if isinstance(stat_arr, list) and diff_index < len(stat_arr) else {}
            compact = compact_chart_stats_entry(raw_stat) if isinstance(raw_stat, dict) else None
            cn = {"display": display, "ds": ds}
            if compact:
                cn.update(compact)
                cn["display"] = compact.get("display") or display
            jp = jp_index.get((title_n, typ, diff_index))
            community = lookup_impression(impressions, sid, typ, diff_index, title_n)
            sheet = {
                "id": sid,
                "title": title,
                "title_norm": title_n,
                "artist": artist,
                "artist_norm": artist_n,
                "type": typ,
                "slot": slot,
                "diff_index": diff_index,
                "difficulty_name": DIFFICULTIES.get(slot, str(diff_index)),
                "counts": notes or ((jp or {}).get("counts")),
                "cn": cn,
                "jp": {"display": (jp or {}).get("display"), "internal": (jp or {}).get("internal")} if jp else None,
                "community": community,
            }
            title_index[title_n].append(len(sheets))
            sheets.append(sheet)
    return {
        "meta": {
            "analyzer_version": VERSION,
            "n_sheets": len(sheets),
            "std_dev_p95_by_band": p95,
            "note": "物量来自水鱼/dxdata 公开统计。拟合定数仅在 catalog.fit_confidence 通过后使用。不含 DXRating 标签。",
        },
        "title_index": dict(title_index),
        "sheets": sheets,
    }


def parse_corpus(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    samples: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    files = sorted(root.rglob("maidata.txt"))
    for path in files:
        try:
            source = load_source(path)
        except (OSError, ValueError) as exc:
            failures.append({"path": str(path), "error": str(exc), "stage": "load"})
            continue
        title = source.metadata.get("title") or path.parent.name
        artist = source.metadata.get("artist") or ""
        group = f"{normalize_title(title)}|{normalize_title(artist)}"
        for difficulty in sorted(source.charts):
            if difficulty not in OFFICIAL_SLOT:
                continue
            try:
                parsed = parse_chart(source, difficulty)
                if not parsed.notes:
                    continue
                report = analyze(parsed, source, difficulty)
            except (OSError, ValueError) as exc:
                failures.append({"path": str(path), "difficulty": difficulty, "error": str(exc), "stage": "parse"})
                continue
            samples.append(
                {
                    "path": str(path),
                    "title": title,
                    "artist": artist,
                    "group": group,
                    "difficulty": difficulty,
                    "note_counts": report["note_counts"],
                    "features": report["model_features"],
                    "radar": {row["label"]: row["score"] for row in report["radar"]},
                    "heuristic": report["prediction"]["estimated_level"],
                    "fingerprint": parsed.fingerprint,
                    "statistics": {
                        "judged_objects": report["statistics"]["judged_objects"],
                        "effective_seconds": report["statistics"]["effective_seconds"],
                    },
                }
            )
    return samples, failures


def attach_training_labels(samples: list[dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    from catalog import match_sheet

    labeled = []
    p95 = (catalog.get("meta") or {}).get("std_dev_p95_by_band") or {}
    for sample in samples:
        fake_report = {
            "title": sample["title"],
            "artist": sample["artist"],
            "difficulty": sample["difficulty"],
            "note_counts": sample["note_counts"],
        }
        sheet = match_sheet(fake_report, catalog)
        if not sheet:
            continue
        cn = sheet.get("cn") or {}
        band = display_band(cn.get("ds"), cn.get("display") or "")
        conf = fit_confidence(cn, p95.get(band))
        if not conf.get("usable"):
            continue
        if sample["heuristic"] is None:
            continue
        if sample["statistics"]["effective_seconds"] < 20 or sample["statistics"]["judged_objects"] < 100:
            continue
        ok, _ = counts_close(sample["note_counts"], sheet.get("counts"))
        if not ok:
            continue
        labeled.append(
            {
                **sample,
                "level": float(conf["fit_diff"]),
                "cn_ds": cn.get("ds"),
                "cnt": conf.get("cnt"),
                "id": sheet.get("id"),
                "band": band,
            }
        )
    return labeled


def build_percentiles(samples: list[dict[str, Any]]) -> dict[str, Any]:
    by_band: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    all_axes: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        band = sample.get("band") or display_band(sample.get("cn_ds"), "") or "all"
        for label, score in (sample.get("radar") or {}).items():
            by_band[band][label].append(float(score))
            all_axes[label].append(float(score))
    payload = {"by_band": {}, "note": "每个等级带雷达轴的 0–100 分位网格（21 点）。"}
    for band, axes in by_band.items():
        payload["by_band"][band] = {label: quantile_grid(vals) for label, vals in axes.items() if len(vals) >= 8}
    payload["by_band"]["all"] = {label: quantile_grid(vals) for label, vals in all_axes.items() if len(vals) >= 8}
    return payload


def train_model(labeled: list[dict[str, Any]], alpha: float = 10.0) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    unique, seen = [], {}
    for row in labeled:
        fp = row["fingerprint"]
        if fp in seen:
            continue
        seen[fp] = True
        unique.append(row)
    info = {"n_labeled": len(unique), "n_groups": len({r["group"] for r in unique})}
    if len(unique) < 30 or info["n_groups"] < 10:
        return None, {**info, "trained": False, "reason": "高置信样本不足 30 谱 / 10 组，站点回退启发式。"}
    metrics, _rows = cross_validate(unique, alpha)
    model = fit(unique, alpha)
    model.update(
        validation=metrics,
        training_fingerprints=[r["fingerprint"] for r in unique],
        training_level_range=[min(r["level"] for r in unique), max(r["level"] for r in unique)],
        prefer_over_heuristic=metrics["mae"] < metrics["heuristic_mae"],
        training_ids=sorted({str(r.get("id")) for r in unique if r.get("id")}),
    )
    info.update(trained=True, metrics=metrics, prefer_over_heuristic=model["prefer_over_heuristic"])
    return model, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=ROOT / "corpus" / "raw")
    ap.add_argument("--charts", type=Path, default=ROOT / "corpus" / "maisquared")
    ap.add_argument("--impressions", type=Path, default=ROOT / "data" / "impressions.json")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data")
    ap.add_argument("--skip-parse", action="store_true")
    args = ap.parse_args()
    music_path, stats_path, dx_path = args.raw / "music_data.json", args.raw / "chart_stats.json", args.raw / "dxdata.json"
    if not music_path.is_file() or not stats_path.is_file():
        print("缺少 corpus/raw/music_data.json 或 chart_stats.json，先运行 tools/fetch_public.py", file=sys.stderr)
        return 2
    music = load_json(music_path)
    stats = load_json(stats_path)
    jp_index = build_jp_index(load_json(dx_path)) if dx_path.is_file() else {}
    impressions = load_json(args.impressions) if args.impressions.is_file() else {}
    catalog = build_catalog(music, stats, jp_index, impressions)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"catalog sheets: {catalog['meta']['n_sheets']}")

    labeled: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if not args.skip_parse and args.charts.is_dir():
        samples, failures = parse_corpus(args.charts)
        (args.out_dir / "ingest_failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        labeled = attach_training_labels(samples, catalog)
        print(f"parsed {len(samples)} charts, labeled {len(labeled)}, failures {len(failures)}")
        percentiles = build_percentiles(labeled or samples)
        (args.out_dir / "percentiles.json").write_text(json.dumps(percentiles, ensure_ascii=False), encoding="utf-8")
        model, info = train_model(labeled)
        (args.out_dir / "train_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        if model is not None:
            (args.out_dir / "model.json").write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
            print("model", info)
        else:
            print("no model:", info)
    else:
        print("skip parse")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
