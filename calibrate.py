#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Optional local ridge calibration; standard library only.
CSV columns: path,difficulty,level,group. Paths are relative to the CSV file.
Group is optional; default is title + artist. Related charts MUST share a group.
Requires >=30 unique charts, >=10 groups. No training data is bundled.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any
from maimai_analyzer import VERSION, MODEL_FEATURES, load_source, parse_chart, analyze, predict_model


def solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting; ridge makes this well-conditioned."""
    n = len(rhs)
    a = [list(row) + [y] for row, y in zip(matrix, rhs)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError("回归矩阵不可解；请增加 --alpha")
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [x / scale for x in a[col]]
        for row in range(n):
            if row == col:
                continue
            ratio = a[row][col]
            if ratio:
                a[row] = [x - ratio * y for x, y in zip(a[row], a[col])]
    return [row[-1] for row in a]


def fit(samples: list[dict[str, Any]], alpha: float) -> dict[str, Any]:
    p = len(MODEL_FEATURES)
    xs = [[r["features"][key] for key in MODEL_FEATURES] for r in samples]
    ys = [r["level"] for r in samples]
    means = [statistics.fmean(row[i] for row in xs) for i in range(p)]
    scales = [max(1e-6, statistics.pstdev(row[i] for row in xs)) for i in range(p)]
    center = statistics.fmean(ys)
    z = [[(x - mu) / sd for x, mu, sd in zip(row, means, scales)] for row in xs]
    matrix = [[sum(row[i] * row[j] for row in z) + (alpha if i == j else 0) for j in range(p)] for i in range(p)]
    rhs = [sum(row[i] * (y - center) for row, y in zip(z, ys)) for i in range(p)]
    return {"format": "maimai-ridge-v1", "analyzer_version": VERSION, "feature_names": MODEL_FEATURES, "means": means, "scales": scales, "weights": solve(matrix, rhs), "intercept": center, "alpha": alpha}


def cross_validate(samples: list[dict[str, Any]], alpha: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    groups = sorted(set(s["group"] for s in samples))
    random.Random(42).shuffle(groups)
    fold_for = {group: i % 5 for i, group in enumerate(groups)}
    rows = []
    for fold in range(5):
        training = [s for s in samples if fold_for[s["group"]] != fold]
        test = [s for s in samples if fold_for[s["group"]] == fold]
        model = fit(training, alpha)
        for sample in test:
            value, _ = predict_model(model, sample["features"])
            value = max(1., min(15.5, value))
            rows.append({"path": sample["path"], "difficulty": sample["difficulty"], "group": sample["group"], "fold": fold + 1, "actual": sample["level"], "predicted": value, "heuristic": sample["heuristic"], "error": value - sample["level"]})
    errors = [r["error"] for r in rows]
    baseline = [r["heuristic"] - r["actual"] for r in rows]
    metrics = {"method": "5-fold grouped cross-validation", "seed": 42, "n": len(samples), "groups": len(groups), "mae": statistics.fmean(abs(e) for e in errors), "rmse": math.sqrt(statistics.fmean(e * e for e in errors)), "heuristic_mae": statistics.fmean(abs(e) for e in baseline), "note": "按 group 拆分；缩放和拟合都只在对应训练折执行。没有超参数搜索。MAE 不是单谱置信区间。"}
    return metrics, rows


def main() -> int:
    ap = argparse.ArgumentParser(description="用本地已知定数谱面校准模型；不会联网下载曲库。")
    ap.add_argument("manifest", type=Path, help="含 path,difficulty,level,group 的 CSV")
    ap.add_argument("--out", type=Path, default=Path("model.json"))
    ap.add_argument("--alpha", type=float, default=10.0, help="岭回归正则系数，默认 10")
    args = ap.parse_args()
    try:
        if not math.isfinite(args.alpha) or args.alpha <= 0:
            raise ValueError("--alpha 必须是正有限数")
        with args.manifest.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not {"path", "difficulty", "level"}.issubset(reader.fieldnames or []):
                raise ValueError("CSV 缺少 path,difficulty,level 列")
            source_rows = list(reader)
        samples, seen = [], {}
        for i, row in enumerate(source_rows, 2):
            try:
                path = (args.manifest.resolve().parent / row["path"]).resolve()
                difficulty, level = int(row["difficulty"]), float(row["level"])
                if not math.isfinite(level) or not 1 <= level <= 15.5:
                    raise ValueError("level 必须是 1–15.5 的已知定数，不接受 13+ 等显示标级")
                source = load_source(path)
                parsed = parse_chart(source, difficulty)
                report = analyze(parsed, source, difficulty)
                if report["statistics"]["effective_seconds"] < 20 or report["statistics"]["judged_objects"] < 100:
                    raise ValueError("训练谱面至少 20 秒、100 个判定对象；不要使用随附的短语法测试谱")
                if report["prediction"]["estimated_level"] is None:
                    raise ValueError("此谱面不在模型适用范围内")
                fingerprint = parsed.fingerprint
                if fingerprint in seen:
                    raise ValueError(f"与 CSV 第 {seen[fingerprint]} 行事件完全相同；请去重，避免交叉验证泄漏")
                seen[fingerprint] = i
                default_group = (source.metadata.get("title", path.parent.name) + "|" + source.metadata.get("artist", "")).casefold()
                group = (row.get("group") or default_group).strip()
                if not group:
                    raise ValueError("group 不能为空")
                samples.append({"path": row["path"], "difficulty": difficulty, "level": level, "group": group, "features": report["model_features"], "fingerprint": fingerprint, "heuristic": report["prediction"]["estimated_level"]})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"CSV 第 {i} 行：{exc}") from None
        if len(samples) < 30 or len({s["group"] for s in samples}) < 10:
            raise ValueError("至少需要 30 张不同谱面、10 个不同 group。建议同歌曲不同难度 / SD / DX 使用同一 group。")
        metrics, rows = cross_validate(samples, args.alpha)
        model = fit(samples, args.alpha)
        model.update(validation=metrics, training_fingerprints=[s["fingerprint"] for s in samples], training_level_range=[min(s["level"] for s in samples), max(s["level"] for s in samples)], training_manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(model, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        cvpath = args.out.with_name(args.out.stem + "_validation.csv")
        with cvpath.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f'按组交叉验证：MAE {metrics["mae"]:.3f}；RMSE {metrics["rmse"]:.3f}；启发式基线 MAE {metrics["heuristic_mae"]:.3f}')
        if metrics["mae"] >= metrics["heuristic_mae"]:
            print("注意：校准模型没有优于启发式基线。不要把校准等同于更准确。")
        print(f"模型：{args.out.resolve()}\n逐谱验证结果：{cvpath.resolve()}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
