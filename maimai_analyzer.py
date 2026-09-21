#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline maidata / Simai chart analysis. Python 3.10+, standard library only.

Usage: python maimai_analyzer.py maidata.txt --open
This is an independent, uncalibrated heuristic demo, NOT AWMC's implementation.
Simai grammar reference: https://w.atwiki.jp/simai/pages/1003.html
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import html
import itertools
import json
import math
import re
import statistics
import sys
import webbrowser
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

VERSION = "1.2.0"
SCHEMA_VERSION = 3
EPS = 1e-7
DIFFICULTIES = {1: "EASY", 2: "BASIC", 3: "ADVANCED", 4: "EXPERT", 5: "MASTER", 6: "Re:MASTER", 7: "ORIGINAL"}
# maidata inote slot -> official chart index used by diving-fish / dxdata (no EASY).
OFFICIAL_SLOT = {2: 0, 3: 1, 4: 2, 5: 3, 6: 4}
AXES = ["持续密度", "瞬时爆发", "交互", "纵连", "扫键 / 转圈", "位移（估）", "节奏变化", "滑条", "错位（估）", "一笔画", "协同（估）", "触摸"]
# Fixed reference scales, NOT percentiles or skill probabilities.
MODEL_FEATURES = ["log_avg_effort", "log_peak_effort", "log_sustained_effort", "trill_fraction", "jack_fraction", "sweep_fraction", "travel_pressure", "rhythm_complexity", "slide_rate", "slide_speed", "slide_overlap_ratio", "chain_fraction", "touch_fraction", "coordination", "break_fraction", "ex_fraction", "waiting_interleave_fraction", "same_origin_launch_fraction", "misalign_run_fraction"]
ANCHORS = [(0, 1), (.5, 2), (1, 4), (2, 7), (3, 9), (4, 10.3), (5, 11.2), (6, 12), (7, 12.6), (8, 13), (10, 13.7), (12, 14.2), (15, 14.8), (20, 15.5)]


class ParseError(ValueError):
    pass


def number(text: str, name: str, minimum: float = 0, strict_positive: bool = False) -> float:
    try:
        x = float(text)
    except (ValueError, TypeError):
        raise ParseError(f"{name} 不是数字：{text!r}") from None
    if not math.isfinite(x) or x < minimum or (strict_positive and x <= 0):
        raise ParseError(f"{name} 超出有效范围：{text!r}")
    return x


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    p = max(0.0, min(1.0, q)) * (len(xs) - 1)
    i = int(p)
    return xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (p - i)


def sat(value: float, scale: float) -> float:
    return 100.0 * (1.0 - math.exp(-max(0.0, value) / scale))


def ring_distance(a: int, b: int) -> int:
    d = abs(a - b) % 8
    return min(d, 8 - d)


def strip_comments(text: str) -> str:
    # Preserve offsets and line numbers. // and || are common editor comments.
    return re.sub(r"(?m)(?:\|\||//)[^\n]*", lambda m: " " * len(m.group()), text)


def split_top(text: str, delimiter: str) -> list[tuple[str, int]]:
    pairs = {"[": "]", "(": ")", "{": "}"}
    stack: list[str] = []
    result, start = [], 0
    for i, c in enumerate(text):
        if c in pairs:
            stack.append(pairs[c])
        elif c in "])}":
            if not stack or stack.pop() != c:
                raise ParseError(f"括号不匹配，字符位置 {i + 1}")
        elif c == delimiter and not stack:
            result.append((text[start:i], start))
            start = i + 1
    if stack:
        raise ParseError("存在未闭合的括号")
    result.append((text[start:], start))
    return result


def read_text(path: Path, encoding: str | None = None) -> tuple[str, str]:
    data = path.read_bytes()
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("文件超过 16 MiB；请只提供 maidata 文本，不要提供音频或压缩包。")
    candidates = [encoding] if encoding else (["utf-16"] if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ["utf-8-sig", "gb18030", "cp932"])
    for enc in candidates:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            pass
    raise ValueError("无法解码文件；请用 --encoding cp932 或 --encoding gb18030 显式指定编码。")


@dataclass
class ChartSource:
    metadata: dict[str, str]
    charts: dict[int, tuple[str, int]]
    encoding: str
    path: str


def parse_source(text: str, encoding: str, origin: str, title_fallback: str = "uploaded") -> ChartSource:
    matches = list(re.finditer(r"(?m)^[ \t]*&([A-Za-z][A-Za-z0-9_]*)[ \t]*=", text))
    metadata: dict[str, str] = {}
    charts: dict[int, tuple[str, int]] = {}
    if not matches:
        return ChartSource({"title": title_fallback}, {5: (text, 1)}, encoding, origin)
    for i, m in enumerate(matches):
        key = m.group(1).lower()
        value = text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        cm = re.fullmatch(r"inote_(\d+)", key)
        if cm:
            idx = int(cm.group(1))
            if idx in charts:
                raise ParseError(f"重复的 &inote_{idx}，拒绝静默覆盖")
            if strip_comments(value).strip():
                charts[idx] = (value, text.count("\n", 0, m.end()) + 1)
        else:
            metadata[key] = value.strip()
    if not charts:
        raise ParseError("未找到非空的 &inote_N 谱面。")
    return ChartSource(metadata, charts, encoding, origin)


def load_source(path: Path, encoding: str | None = None) -> ChartSource:
    path = Path(path)
    text, enc = read_text(path, encoding)
    return parse_source(text, enc, str(path.resolve()), path.stem)


def load_source_text(text: str, origin: str = "<uploaded>", encoding: str = "utf-8") -> ChartSource:
    if len(text.encode("utf-8", errors="replace")) > 16 * 1024 * 1024:
        raise ValueError("文本超过 16 MiB；请只提供 maidata 文本。")
    return parse_source(text, encoding, origin, Path(origin).stem or "uploaded")


def duration_value(signature: str, bpm: float) -> float:
    """HOLD duration and the duration half of SLIDE timing."""
    if signature.count("#") > 1:
        raise ParseError(f"时长格式错误：[{signature}]")
    if "#" in signature:
        left, right = signature.split("#")
        if not left:
            return number(right, "绝对时长")
        bpm = number(left, "独立 BPM", strict_positive=True)
        if ":" not in right:
            raise ParseError("HOLD 的 bpm# 格式后必须为 分母:分子")
        signature = right
    if ":" not in signature:
        raise ParseError(f"缺少 分母:分子 或 #秒数：[{signature}]")
    a, b = signature.split(":", 1)
    return 240.0 * number(b, "时值分子") / (bpm * number(a, "时值分母", strict_positive=True))


def slide_timing(signature: str, bpm: float) -> tuple[float, float]:
    if "##" in signature:
        left, right = signature.split("##", 1)
        wait = number(left, "滑条等待秒数")
        if "##" in right:
            raise ParseError(f"滑条时长格式错误：[{signature}]")
        dur = duration_value(right, bpm) if ":" in right or "#" in right else number(right, "滑条持续秒数")
        return wait, dur
    if "#" in signature:
        left, right = signature.split("#", 1)
        if not left:
            raise ParseError("SLIDE 的 [#秒数] 有歧义；使用 [BPM#秒数] 或 [等待##秒数]")
        local_bpm = number(left, "滑条独立 BPM", strict_positive=True)
        dur = duration_value(right, local_bpm) if ":" in right else number(right, "滑条持续秒数")
        return 60.0 / local_bpm, dur
    return 60.0 / bpm, duration_value(signature, bpm)


@dataclass
class Segment:
    shape: str
    start: int
    end: int
    via: int | None = None
    length: float = 0.0  # screen-radius units; curved shapes are approximations
    duration: float = 0.0


def segment_length(shape: str, a: int, b: int, via: int | None) -> float:
    chord = lambda x, y: 2.0 * math.sin(math.pi * ring_distance(x, y) / 8.0)
    if shape == "-":
        return max(.05, chord(a, b))
    if shape == "v":
        return 2.0
    if shape == "V":
        return max(.05, chord(a, int(via)) + chord(int(via), b))
    if shape == "^":
        return max(.05, ring_distance(a, b) * math.pi / 4)
    if shape in ("<", ">"):
        clockwise = (shape == ">") == (a in (1, 2, 7, 8))
        steps = ((b - a) if clockwise else (a - b)) % 8 or 8
        return steps * math.pi / 4
    if shape in ("p", "q"):
        return 2.6 + .6 * ring_distance(a, b) / 4
    if shape in ("pp", "qq"):
        return 4.4 + .6 * ring_distance(a, b) / 4
    if shape in ("s", "z"):
        return 3.5
    if shape == "w":
        return 2.4
    raise ParseError(f"未知滑条形状：{shape}")


@dataclass
class Note:
    time: float
    beat: float
    bpm: float
    kind: str
    position: str
    duration: float = 0.0
    is_break: bool = False
    ex: bool = False
    is_star: bool = False
    source_time: float = 0.0
    wait: float = 0.0
    segments: list[Segment] = field(default_factory=list)
    line: int = 0
    token: str = ""
    headless: bool = False

    @property
    def end(self) -> float:
        return self.time + self.duration

    @property
    def outer(self) -> bool:
        return self.kind in ("tap", "hold") and self.position.isdigit()


@dataclass
class ParsedChart:
    notes: list[Note]
    warnings: list[str]
    skipped: list[dict[str, Any]]
    tempo: list[dict[str, float]]
    end: float
    first: float
    fingerprint: str
    cell_count: int


SHAPE = re.compile(r"(pp|qq|V|[-<>^vpqszw])([1-8])([1-8])?")


def parse_slide(route: str, start: int, bpm: float) -> tuple[list[Segment], float, float, bool]:
    pos, current, segments, signatures = 0, start, [], []
    slide_break = False
    while pos < len(route):
        m = SHAPE.match(route, pos)
        if not m:
            raise ParseError(f"无法解析滑条路径：{route[pos:]!r}")
        op, a, b = m.groups()
        if op == "V":
            if b is None:
                raise ParseError("V 型滑条必须提供中转键和结束键")
            via, end = int(a), int(b)
        else:
            if b is not None:
                raise ParseError(f"滑条尾部多余数字：{m.group()}")
            via, end = None, int(a)
        pos = m.end()
        seg = Segment(op, current, end, via, segment_length(op, current, end, via))
        segments.append(seg)
        current = end
        # Accept BREAK on either side of a duration bracket, as an explicit extension.
        while pos < len(route) and route[pos] == "b":
            slide_break = True
            pos += 1
        sig = None
        if pos < len(route) and route[pos] == "[":
            stop = route.find("]", pos)
            if stop < 0:
                raise ParseError("未闭合的滑条时长")
            sig = slide_timing(route[pos + 1:stop], bpm)
            pos = stop + 1
        signatures.append(sig)
        while pos < len(route) and route[pos] == "b":
            slide_break = True
            pos += 1
    if not segments:
        raise ParseError("空滑条路径")
    present = [i for i, s in enumerate(signatures) if s is not None]
    if present == [len(segments) - 1]:
        wait, total = signatures[-1]
        length = sum(s.length for s in segments)
        for s in segments:
            s.duration = total * s.length / length
    elif len(present) == len(segments):
        wait = signatures[0][0]
        total = sum(s[1] for s in signatures)
        for seg, sig in zip(segments, signatures):
            seg.duration = sig[1]
    else:
        raise ParseError("连接滑条必须仅在末尾指定总时长，或者逐段全部指定时长")
    return segments, wait, total, slide_break


def parse_note(token: str, t: float, beat: float, bpm: float, line: int) -> list[Note]:
    def make(kind: str, p: str, **kw: Any) -> Note:
        return Note(time=t, beat=beat, bpm=bpm, kind=kind, position=p, source_time=t, line=line, token=token, **kw)
    if re.fullmatch(r"[1-8]+", token):
        return [make("tap", p) for p in token]
    # Compact EACH of decorated taps: 1b5b, 46x, 33b. Not a slide (no shape / duration).
    if re.fullmatch(r"(?:[1-8][bx]*){2,}", token):
        return [make("tap", m.group(1), is_break="b" in m.group(2), ex="x" in m.group(2)) for m in re.finditer(r"([1-8])([bx]*)", token)]
    m = re.fullmatch(r"(C[12]?|[ABDE][1-8]|[1-8])([bxhf$@?!]*)(.*)", token)
    if not m:
        raise ParseError(f"无法识别 note：{token!r}")
    position, mods, rest = m.groups()
    touch = not position.isdigit()
    if "f" in mods and not touch:
        raise ParseError("f 烟花标记只适用于 TOUCH / TOUCH HOLD")
    if touch and any(flag in mods for flag in "$@?!"):
        raise ParseError("星星外形 / 无头标记不适用于 TOUCH")
    if position in ("C1", "C2"):
        position = "C"
    if "h" in mods or re.fullmatch(r"\[[^\]]+\][bxf]*", rest or ""):
        hm = re.fullmatch(r"(?:\[([^\]]+)\])?([bxf]*)", rest or "")
        if not hm or "?" in mods or "!" in mods or "$" in mods or "@" in mods:
            raise ParseError(f"HOLD 格式错误：{token!r}")
        dur = duration_value(hm.group(1), bpm) if hm.group(1) else 240 / bpm / 1280
        flags = mods + hm.group(2)
        return [make("touch_hold" if touch else "hold", position, duration=dur, is_break="b" in flags, ex="x" in flags)]
    if not rest:
        if "?" in mods or "!" in mods:
            raise ParseError("? / ! 只能用于无头 SLIDE")
        return [make("touch" if touch else "tap", position, is_break="b" in mods, ex="x" in mods, is_star="$" in mods)]
    if touch:
        raise ParseError("此 demo 不支持从 TOUCH 位置出发的扩展 SLIDE")
    headless = "?" in mods or "!" in mods
    result = [] if headless else [make("tap", position, is_break="b" in mods, ex="x" in mods, is_star="@" not in mods)]
    for route, _ in split_top(rest, "*"):
        extra_break = extra_ex = False
        while route[:1] in "bx":
            extra_break = extra_break or route[0] == "b"
            extra_ex = extra_ex or route[0] == "x"
            route = route[1:]
        if not route:
            raise ParseError(f"空滑条路径：{token!r}")
        segments, wait, duration, br = parse_slide(route, int(position), bpm)
        note = make("slide", position, duration=duration, is_break=br or extra_break, wait=wait, segments=segments, headless=headless)
        note.ex = extra_ex or note.ex
        note.time = t + wait
        note.beat = beat + wait * bpm / 60
        result.append(note)
    return result


def parse_chart(source: ChartSource, difficulty: int, bpm_override: float | None = None, strict: bool = True) -> ParsedChart:
    body, first_line = source.charts[difficulty]
    cleaned = strip_comments(body)
    md = source.metadata
    first_text = md.get(f"first_{difficulty}", "") or md.get("first", "0")
    try:
        first = float(first_text)
    except ValueError:
        raise ParseError(f"first 不是数字：{first_text!r}") from None
    if not math.isfinite(first):
        raise ParseError("first 必须为有限数值")
    bpm_text = md.get(f"wholebpm_{difficulty}", "") or md.get("wholebpm", "")
    bpm = bpm_override or (number(bpm_text, "wholebpm", strict_positive=True) if bpm_text else None)
    divider, fixed_step, t, beat = 4.0, None, first, 0.0
    divider_seen = False
    notes, warnings, skipped, tempo = [], [], [], []
    if source.encoding not in ("utf-8-sig", "utf-8", "utf-16"):
        warnings.append(f"使用 {source.encoding} 解码；若曲名乱码，请显式设置 --encoding。")
    cells = split_top(cleaned, ",")
    newline_offsets = [i for i, char in enumerate(cleaned) if char == "\n"]
    ended = False
    for cell_index, (raw, offset) in enumerate(cells):
        compact_indices = [i for i, char in enumerate(raw) if not char.isspace()]
        cell = "".join(raw[i] for i in compact_indices)
        controls_consumed = 0
        # line is corrected to the first non-whitespace character in the cell.
        prefix = re.match(r"\s*", raw).group()
        line = first_line + bisect.bisect_left(newline_offsets, offset) + prefix.count("\n")
        if ended:
            if cell:
                raise ParseError(f"第 {line} 行：E 结束标记后仍有内容")
            continue
        while cell and cell[0] in "({":
            close = ")" if cell[0] == "(" else "}"
            end = cell.find(close)
            if end < 0:
                raise ParseError(f"第 {line} 行：控制标记未闭合")
            value = cell[1:end]
            if cell[0] == "(":
                bpm = number(value, "BPM", strict_positive=True)
                tempo.append({"time": t, "bpm": bpm})
            else:
                divider_seen = True
                if value.startswith("#"):
                    fixed_step = number(value[1:], "逗号间隔秒数", strict_positive=True)
                else:
                    divider = number(value, "分音符分母", strict_positive=True)
                    fixed_step = None
            controls_consumed += end + 1
            cell = cell[end + 1:]
        if cell == "E":
            ended = True
            continue
        if not cell and cell_index == len(cells) - 1:
            continue
        if bpm is None:
            raise ParseError(f"第 {line} 行：缺少 BPM；请在谱面中写 (BPM)，或使用 --bpm。")
        if bpm > 100000 or bpm < .01:
            raise ParseError("BPM 超出 demo 支持范围 0.01–100000")
        if not tempo:
            tempo.append({"time": t, "bpm": bpm})
        # Pseudo EACH: every backtick advances 1 ms inside this comma cell only.
        for k, (each, each_offset) in enumerate(split_top(cell, "`")):
            for token, token_offset in split_top(each, "/"):
                if not token:
                    continue
                token_index = controls_consumed + each_offset + token_offset
                token_line = first_line + bisect.bisect_left(newline_offsets, offset + compact_indices[token_index])
                try:
                    notes.extend(parse_note(token, t + .001 * k, beat + .001 * k * bpm / 60, bpm, token_line))
                except ParseError as exc:
                    message = f"第 {token_line} 行，{token!r}：{exc}"
                    if strict:
                        raise ParseError(message) from None
                    skipped.append({"line": token_line, "token": token, "reason": str(exc)})
        step = fixed_step if fixed_step is not None else 240.0 / bpm / divider
        t += step
        beat += step * bpm / 60
        if t - first > 7200:
            raise ParseError("谱面超过两小时；可能是 BPM / 时值写错。")
        if len(notes) > 100000:
            raise ParseError("谱面超过 100000 个判定对象；超出 demo 分析范围。")
    if not divider_seen:
        warnings.append("未设置 {分母}，逗号间隔采用默认四分音符；请确认谱面。")
    if not ended:
        warnings.append("缺少 E 结束标记，已在文件末尾结束。")
    if skipped:
        warnings.append(f"宽松解析跳过了 {len(skipped)} 项；已禁用难度预估，避免输出失真数值。")
    if any(n.kind == "slide" and n.duration <= EPS for n in notes):
        warnings.append("存在零时长 SLIDE；速度特征按 0.08 秒下限限幅，难度预估不可靠。")
    notes.sort(key=lambda n: (n.time, n.kind, n.position))
    # Canonical musical events, not title/level/offset: useful for train-set leakage checks.
    canonical = [{"t": round(n.time - first, 6), "kind": n.kind, "p": n.position, "d": round(n.duration, 6), "break": n.is_break, "ex": n.ex, "path": [(s.shape, s.start, s.end, s.via, round(s.duration, 6)) for s in n.segments]} for n in notes]
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    return ParsedChart(notes, warnings, skipped, tempo, t, first, fingerprint, len(cells))


def note_effort(n: Note) -> float:
    if n.kind == "slide":
        # A route is one judged object, NOT one object per path segment or WiFi arm.
        turns = max(0, len(n.segments) - 1)
        shape_bonus = sum(.3 if s.shape in ("V", "pp", "qq", "s", "z", "w") else .1 for s in n.segments)
        return min(2.4, .85 + .12 * turns + shape_bonus)
    return {"tap": 1.0, "hold": 1.05, "touch": .65, "touch_hold": .8}[n.kind]


def official_style_counts(notes: list[Note]) -> dict[str, int]:
    """Break is counted separately, matching arcade / Gamerch 内訳 tables."""
    tap = hold = slide = touch = brk = 0
    for n in notes:
        if n.is_break:
            brk += 1
            continue
        if n.kind == "tap":
            tap += 1
        elif n.kind == "hold":
            hold += 1
        elif n.kind == "slide":
            slide += 1
        elif n.kind in ("touch", "touch_hold"):
            touch += 1
    return {"tap": tap, "hold": hold, "slide": slide, "touch": touch, "break": brk, "total": tap + hold + slide + touch + brk}


def peak_window(times: list[float], weights: list[float], window: float) -> tuple[float, float]:
    best, best_time, left, total = 0.0, (times[0] if times else 0), 0, 0.0
    for right, t in enumerate(times):
        total += weights[right]
        while left <= right and times[left] <= t - window + EPS:
            total -= weights[left]
            left += 1
        if total > best:
            best, best_time = total, t
    return best / window, best_time


def sampled_rates(times: list[float], weights: list[float], start: float, end: float, window: float, step: float = .25) -> tuple[list[float], list[float]]:
    prefix = [0.0]
    for w in weights:
        prefix.append(prefix[-1] + w)
    points, rates = [], []
    for i in range(int(math.ceil((end - start) / step)) + 1):
        t = min(end, start + i * step)
        lo = bisect.bisect_left(times, t - window / 2 - EPS)
        hi = bisect.bisect_left(times, t + window / 2 - EPS)
        points.append(t)
        rates.append((prefix[hi] - prefix[lo]) / window)
    return points, rates


def grouped_outer(notes: list[Note]) -> list[list[Note]]:
    groups: list[list[Note]] = []
    for n in notes:
        if n.outer:
            if groups and abs(groups[-1][0].time - n.time) < EPS:
                groups[-1].append(n)
            else:
                groups.append([n])
    return groups


def event(label: str, selected: list[Note], evidence: str, strength: float = 1) -> dict[str, Any]:
    return {"label": label, "start": round(min(n.time for n in selected), 4), "end": round(max(n.end for n in selected), 4), "note_count": len(selected), "strength": round(strength, 3), "evidence": evidence, "line": min(n.line for n in selected)}


def detect_runs(groups: list[list[Note]]) -> tuple[list[dict[str, Any]], dict[str, set[int]]]:
    out: list[dict[str, Any]] = []
    covered: dict[str, set[int]] = {k: set() for k in ("trill", "jack", "sweep")}
    def good_gap(i: int, j: int) -> bool:
        return .012 <= groups[j][0].time - groups[i][0].time <= .30
    for mode, label, minimum in (("trill", "交互", 4), ("jack", "纵连", 3), ("sweep", "扫键", 4)):
        i = 0
        while i < len(groups):
            if len(groups[i]) != 1:
                i += 1
                continue
            chain, j, direction = [i], i + 1, 0
            while j < len(groups) and len(groups[j]) == 1 and good_gap(j - 1, j):
                p = int(groups[j][0].position)
                prev = int(groups[j - 1][0].position)
                if mode == "jack":
                    ok = p == prev
                elif mode == "trill":
                    ok = p != prev and (len(chain) < 2 or p == int(groups[j - 2][0].position))
                else:
                    delta = (p - prev) % 8
                    step_dir = 1 if delta == 1 else -1 if delta == 7 else 0
                    ok = step_dir != 0 and (direction == 0 or step_dir == direction)
                    direction = step_dir
                if not ok:
                    break
                chain.append(j)
                j += 1
            if len(chain) >= minimum:
                ns = [groups[k][0] for k in chain]
                speed = (len(ns) - 1) / max(EPS, ns[-1].time - ns[0].time)
                out.append(event(label, ns, f"连续 {len(ns)} 个外键；平均 {speed:.2f} 次/秒；相邻间隔 12–300 ms", speed))
                covered[mode].update(chain)
                if mode == "sweep" and len(ns) >= 9:
                    out.append(event("转圈", ns, "连续同向相邻键移动至少 8 格；不包含滑条圆弧", speed))
                i = j - 1
            else:
                i += 1
    return out, covered


def movement_proxy(groups: list[list[Note]]) -> tuple[float, list[dict[str, Any]], int]:
    """Greedy two-hand minimum travel. No crossing, slide trajectory or palm model."""
    positions, previous, busy = [3, 6], [-1e6, -1e6], [-1e6, -1e6]
    pressure, transitions, events, overfull = 0.0, 0, [], 0
    for group in groups:
        t = group[0].time
        # Canonical sorting makes EACH notation order irrelevant to the result.
        ns = sorted(group, key=lambda n: (int(n.position), n.duration))
        if len(ns) > 2:
            overfull += 1
            ns = [ns[0], ns[-1]]
        choices = []
        for assignment in itertools.permutations((0, 1), len(ns)):
            cost, moves = 0.0, []
            for n, hand in zip(ns, assignment):
                dist = ring_distance(positions[hand], int(n.position))
                dt = max(.04, min(2.0, t - previous[hand]))
                blocked = busy[hand] > t + EPS
                # Zero startup cost and time regularization avoid exaggerated first-note strain.
                speed = 0.0 if previous[hand] < -1e5 else dist / dt
                cost += speed ** 1.25 + (1000 if blocked else 0)
                moves.append((n, hand, dist, speed))
            choices.append((cost, assignment, moves))
        if not choices:
            continue
        _, _, moves = min(choices, key=lambda x: (x[0], x[1]))
        for n, hand, dist, speed in moves:
            if previous[hand] > -1e5:
                transitions += 1
                pressure += min(2.0, max(0.0, speed - 4.0) / 12.0)
                if dist >= 2 and speed >= 8:
                    events.append(event("大位移候选", [n], f"简化分手：移动 {dist} 格，约 {speed:.1f} 格/秒；非真实手序", speed))
            positions[hand], previous[hand] = int(n.position), t
            busy[hand] = n.end if n.kind == "hold" else t
    return pressure / max(1, transitions), events, overfull


def interval_metrics(slides: list[Note]) -> tuple[float, float, int]:
    endpoints = sorted([(n.time, 1) for n in slides if n.duration > EPS] + [(n.end, -1) for n in slides if n.duration > EPS])
    if not endpoints:
        return 0, 0, 0
    active = peak = 0
    previous = endpoints[0][0]
    union = overlap = 0.0
    for t, delta in endpoints:
        if active >= 1:
            union += t - previous
        if active >= 2:
            overlap += t - previous
        active += delta
        peak = max(peak, active)
        previous = t
    return union, overlap, peak


def detect_misalignment(slides: list[Note], outer: list[Note], span: float) -> dict[str, Any]:
    """Recognize delayed-head action structures, not just attacks during tracing.

    The timing source is the parsed slide's source_time -> time -> end.  Explicit
    wait seconds and independent BPM have already been resolved by the parser.
    No title, chart ID, declared level, fixed key pair, or absolute beat phase is
    used.  Rule matches describe chart structure, NOT a proven hand assignment.
    Count raw routes for inspection, but score same-time/same-position heads once.
    """
    # Eight per-position time indices bound each query and its evidence sample;
    # long waits do not require copying every note in the wait interval.
    indexed: dict[str, list[Note]] = {str(i): [] for i in range(1, 9)}
    for note in sorted(outer, key=lambda n: (n.time, n.position)):
        indexed[note.position].append(note)
    indices = {key: [n.time for n in ns] for key, ns in indexed.items()}
    tap_indices = {key: [n.time for n in ns if n.kind == "tap"] for key, ns in indexed.items()}

    def window(lo: float, hi: float) -> tuple[dict[str, int], list[Note]]:
        counts: dict[str, int] = {}
        sample: list[Note] = []
        if hi < lo:
            return counts, sample
        for pos, ns in indexed.items():
            a = bisect.bisect_left(indices[pos], lo)
            b = bisect.bisect_right(indices[pos], hi)
            if b > a:
                counts[pos] = b - a
                # At most four notes per key, including the end of a long run.
                selected = sorted(set([a, min(a + 1, b - 1), max(a, b - 2), b - 1]))
                sample.extend(ns[j] for j in selected)
        return counts, sorted(sample, key=lambda n: (n.time, n.position, n.kind))

    def note_ref(n: Note) -> dict[str, Any]:
        return {"time": round(n.time, 6), "position": n.position, "kind": n.kind,
                "is_star": n.is_star, "line": n.line, "token": n.token}

    def key_text(counts: dict[str, int]) -> str:
        return "/".join(sorted(counts, key=int)) or "无"

    ordered = sorted(slides, key=lambda n: (n.source_time, n.position, n.time, n.end, n.token))
    units: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    heads: dict[tuple[float, str], dict[str, Any]] = {}
    for index, n in enumerate(ordered, 1):
        # A headless route does not have a head to postpone.  A zero-wait route
        # also cannot exhibit delayed-head interleaving merely by being present.
        if n.headless or n.wait <= EPS * 10 or n.duration <= EPS:
            continue
        tol = min(.020, n.wait / 16.0, (60.0 / n.bpm) / 32.0)
        if tol <= EPS:
            continue
        head_keys, head_notes = window(n.source_time - tol, n.source_time + tol)
        wait_keys, wait_notes = window(n.source_time + tol + EPS, n.time - tol - EPS)
        launch_keys, launch_notes = window(n.time - tol, n.time + tol)
        mid = (n.source_time + n.time) / 2.0
        mid_keys, _ = window(mid - tol, mid + tol)
        same_wait = wait_keys.get(n.position, 0)
        foreign_wait = sum(count for pos, count in wait_keys.items() if pos != n.position)
        # HOLD beginning here is not called a tap-and-slide action.  Query TAPs
        # exactly, rather than relying on the bounded general evidence sample.
        a = bisect.bisect_left(tap_indices[n.position], n.time - tol)
        b = bisect.bisect_right(tap_indices[n.position], n.time + tol)
        same_launch = b > a
        midpoint_foreign = any(pos != n.position for pos in mid_keys)
        # Structural Umiyuri family: a chord at the original head, a foreign
        # attack near the middle of the wait, and a chord including the original
        # key at launch. No assertion about left/right hands or exact sensor paths.
        umiyuri = bool(foreign_wait and midpoint_foreign and same_launch
                       and len(head_keys) >= 2 and len(launch_keys) >= 2)
        labels: list[str] = []
        if foreign_wait:
            labels.append("等待期异键错位")
        if same_wait:
            labels.append("同位拍拍划")
        if same_launch:
            labels.append("同位拍划")
        if umiyuri:
            labels.append("海底捞型错位")
        # Explicit human-designed weights, not fitted to any particular song.
        weight = .90 if foreign_wait and same_launch else .75 if foreign_wait else .30 if same_wait else .25 if same_launch else 0.0
        unit = {
            "id": f"slide_{index:04d}", "line": n.line, "token": n.token,
            "origin": n.position, "head_time": round(n.source_time, 6),
            "slide_start": round(n.time, 6), "slide_end": round(n.end, 6),
            "wait_seconds": round(n.wait, 6), "duration_seconds": round(n.duration, 6),
            "tolerance_seconds": round(tol, 8),
            "head_positions": sorted(head_keys, key=int),
            "waiting_counts_by_position": wait_keys,
            "waiting_foreign_count": foreign_wait, "waiting_same_origin_count": same_wait,
            "waiting_note_samples": [note_ref(h) for h in wait_notes],
            "waiting_samples_truncated": sum(wait_keys.values()) > len(wait_notes),
            "midpoint_foreign": midpoint_foreign,
            "launch_positions": sorted(launch_keys, key=int),
            "launch_note_samples": [note_ref(h) for h in launch_notes],
            "same_origin_launch": same_launch, "umiyuri_structure": umiyuri,
            "labels": labels, "base_weight": weight, "continuous_run_id": None,
        }
        units.append(unit)
        head_key = (round(n.source_time, 6), n.position)
        if head_key not in heads:
            heads[head_key] = {"time": n.source_time, "origin": n.position, "wait": n.wait,
                               "start": n.time, "end": n.end, "line": n.line, "tol": tol,
                               "foreign": False, "same_launch": False, "weight": 0.0,
                               "units": [], "in_run": False}
        h = heads[head_key]
        h["wait"] = max(h["wait"], n.wait)
        h["start"] = max(h["start"], n.time)
        h["end"] = max(h["end"], n.end)
        h["foreign"] = h["foreign"] or bool(foreign_wait)
        h["same_launch"] = h["same_launch"] or same_launch
        h["weight"] = max(h["weight"], weight)
        h["units"].append(unit)
        evidence = (f"头 {n.source_time:.3f}s（{n.position} 键）→ 起划 {n.time:.3f}s → 尾 {n.end:.3f}s；"
                    f"等待期 {sum(wait_keys.values())} 次外键（{key_text(wait_keys)}），其中异键 {foreign_wait} 次；"
                    f"启动同刻外键 {key_text(launch_keys)}，同起点 TAP {'有' if same_launch else '无'}。")
        for label in labels:
            if label == "海底捞型错位":
                reason = "头/启动均为双押，中点异键插入，启动含原起点 TAP；仅判定结构，不推断手法。"
            elif label == "同位拍划":
                reason = "TAP 在滑条起点与起划时刻重合；不是在尾判时刻重合。"
            elif label == "同位拍拍划":
                reason = "头与起划之间含原起点的再次击打；按基础结构单独标记。"
            else:
                reason = "异键位于头与起划之间，不要求滑行中段存在 TAP。"
            events.append({"label": label, "start": round(n.source_time, 4), "end": round(n.end, 4),
                           "note_count": 1, "strength": round(weight, 3), "line": n.line,
                           "evidence": f"[{unit['id']}] {evidence} {reason}"})

    # Temporal runs operate on head timestamps, not CSV row order or slide ends.
    # Multiple routes from one head and simultaneous heads occupy one time step.
    frames: list[list[dict[str, Any]]] = []
    for h in sorted(heads.values(), key=lambda h: (h["time"], h["origin"])):
        if frames and abs(frames[-1][0]["time"] - h["time"]) < EPS:
            frames[-1].append(h)
        else:
            frames.append([h])
    runs: list[dict[str, Any]] = []
    chain: list[list[dict[str, Any]]] = []

    def finish_run() -> None:
        if len(chain) < 3:
            return
        members = [h for frame in chain for h in frame if h["foreign"]]
        ids = [u["id"] for h in members for u in h["units"] if u["waiting_foreign_count"]]
        start, end = min(h["time"] for h in members), max(h["end"] for h in members)
        run_id = f"run_{len(runs) + 1:03d}"
        for h in members:
            h["in_run"] = True
            for u in h["units"]:
                if u["waiting_foreign_count"]:
                    u["continuous_run_id"] = run_id
        origins = [sorted({h["origin"] for h in frame if h["foreign"]}, key=int) for frame in chain]
        alternating = (all(len(p) == 1 for p in origins) and origins[0] != origins[1]
                       and all(origins[i] == origins[i - 2] for i in range(2, len(origins))))
        run = {"id": run_id, "start": round(start, 4), "end": round(end, 4),
               "head_steps": len(chain), "unique_heads": len(members),
               "member_slide_ids": ids, "head_positions": origins,
               "alternating_two_origins": alternating, "line": min(h["line"] for h in members)}
        runs.append(run)
        events.append({"label": "连续错位", "start": run["start"], "end": run["end"],
                       "note_count": len(members), "strength": float(len(chain)), "line": run["line"],
                       "evidence": f"[{run_id}] 连续 {len(chain)} 个头时刻均有等待期异键；"
                                   "相邻头间隔不超过相邻最大等待时长的 1.25 倍；"
                                   f"{'两起点交替；' if alternating else ''}同头多路径和同刻双星不重复计步。"})

    for frame in frames:
        active = [h for h in frame if h["foreign"]]
        if not active:
            finish_run()
            chain = []
            continue
        if chain:
            previous = [h for h in chain[-1] if h["foreign"]]
            gap = active[0]["time"] - previous[0]["time"]
            allowed = 1.25 * max(h["wait"] for h in previous + active)
            if gap > allowed + EPS:
                finish_run()
                chain = []
        chain.append(frame)
    finish_run()

    nheads = len(heads)
    weighted = sum(min(1.0, h["weight"] + (.10 if h["in_run"] else 0.0)) for h in heads.values())
    weighted_fraction = weighted / max(1, nheads)
    head_rate = nheads / max(.25, span)
    gate = min(1.0, head_rate / .5)
    score = sat(weighted_fraction * gate, .6)
    summaries = {
        "total_slides": len(slides), "eligible_slides": len(units), "unique_heads": nheads,
        "excluded_headless_or_zero_time_slides": len(slides) - len(units),
        "waiting_foreign_slides": sum(u["waiting_foreign_count"] > 0 for u in units),
        "same_origin_waiting_slides": sum(u["waiting_same_origin_count"] > 0 for u in units),
        "same_origin_launch_slides": sum(u["same_origin_launch"] for u in units),
        "umiyuri_structure_slides": sum(u["umiyuri_structure"] for u in units),
        "matched_unique_heads": sum(h["weight"] > 0 for h in heads.values()),
        "foreign_wait_unique_heads": sum(h["foreign"] for h in heads.values()),
        "continuous_runs": len(runs), "longest_run_head_steps": max((r["head_steps"] for r in runs), default=0),
        "head_fraction_in_runs": sum(h["in_run"] for h in heads.values()) / max(1, nheads),
    }
    return {"version": "delayed-head-structure-v1", "summary": summaries,
            "score": round(score, 1), "score_unrounded": score,
            "weighted_head_fraction": weighted_fraction, "head_rate_gate": gate,
            "waiting_interleave_fraction": sum(h["foreign"] for h in heads.values()) / max(1, nheads),
            "same_origin_launch_fraction": sum(h["same_launch"] for h in heads.values()) / max(1, nheads),
            "events": events, "slides": units, "runs": runs,
            "definition": "头—等待期—启动结构；不以滑行中段异键并行替代错位。按原谱计时，不按曲名、标级或固定键位匹配。",
            "scoring": "每个独立头取各路径最大权重：等待异键并同位起划0.90，仅等待异键0.75，同位等待0.30，仅同位拍划0.25，否则0；连续至少3个头时刻加0.10，上限1。取头均值，乘 min(1,独立头/秒÷0.5)，再作100×(1−exp(−x/0.6))。权重未经曲库校准。",
            "limitations": "这是时序和键位结构证据，不确定左右手/换手/划区碰撞。海底捞型要求等待中点异键及头/启动双押，是保守子集；无头或零等待滑条不参与头错位判断。"}


def analyze(parsed: ParsedChart, source: ChartSource, difficulty: int, declared_override: float | None = None, model: dict[str, Any] | None = None) -> dict[str, Any]:
    notes = parsed.notes
    if not notes:
        raise ValueError(f"{DIFFICULTIES.get(difficulty, str(difficulty))} 没有可分析的 note。")
    warnings = list(parsed.warnings)
    slides = [n for n in notes if n.kind == "slide"]
    heads = [n for n in notes if n.kind != "slide"]
    outer = [n for n in notes if n.outer]
    touch = [n for n in notes if n.kind.startswith("touch")]
    times = [n.time for n in notes]
    weights = [note_effort(n) for n in notes]
    distinct = sorted(set(times))
    gaps = [b - a for a, b in zip(distinct, distinct[1:]) if b - a > .008]
    tail = min(.5, max(.05, statistics.median(gaps) if gaps else .5))
    start = times[0]
    end = max(max(n.end for n in notes), max(times) + tail)
    span = max(.25, end - start)
    avg_effort, avg_nps = sum(weights) / span, len(notes) / span
    peak_effort, peak_time = peak_window(times, weights, 1.0)
    peak_nps, _ = peak_window(times, [1.0] * len(notes), 1.0)
    _, sustain = sampled_rates(times, weights, start, end, 8.0)
    sustained = quantile(sustain, .9)
    timeline_t, timeline_nps = sampled_rates(times, [1.0] * len(notes), start, end, 2.0, .5)
    groups = grouped_outer(notes)
    patterns, covered = detect_runs(groups)
    denom = max(1, len(groups))
    trill_fraction, jack_fraction, sweep_fraction = (len(covered[k]) / denom for k in ("trill", "jack", "sweep"))
    movement, movement_events, overfull = movement_proxy(groups)
    patterns.extend(movement_events)
    if overfull:
        warnings.append(f"发现 {overfull} 组超过两枚外键的同押；可能需要掌押或多人处理，分手估计仅取两端，难度不适用于此类谱面。")
    rhythm_steps = [b[0].beat - a[0].beat for a, b in zip(groups, groups[1:]) if .02 < b[0].beat - a[0].beat <= 2]
    # Evaluate IOIs, NOT absolute beat phase. A shifted constant rhythm is not made harder.
    offgrid = sum(abs(d * 8 - round(d * 8)) > .12 for d in rhythm_steps) / max(1, len(rhythm_steps))
    changes = sum(abs(math.log2(b / a)) > .45 for a, b in zip(rhythm_steps, rhythm_steps[1:])) / max(1, len(rhythm_steps) - 1)
    rhythm = .55 * offgrid + .45 * changes
    union, overlap, slide_peak = interval_metrics(slides)
    overlap_ratio = overlap / max(EPS, union)
    chain_slides = [n for n in slides if len(n.segments) > 1]
    slide_speed = quantile([sum(s.length for s in n.segments) / max(.08, n.duration) for n in slides], .9)
    chain_fraction = len(chain_slides) / max(1, len(slides))
    for n in chain_slides:
        patterns.append(event("连接滑条 / 一笔画", [n], f"Simai 显式连接 {len(n.segments)} 段；不等于手法已验证", len(n.segments)))
    for n in slides:
        if any(s.shape == "w" for s in n.segments):
            patterns.append(event("Wifi", [n], "Simai w 形状；整条计一个 SLIDE，不拆成三轨", 1))
    # Endpoint-compatible headless joins, not an exact slide-judgment simulation.
    by_end: dict[int, list[tuple[float, Note]]] = defaultdict(list)
    for n in slides:
        by_end[n.segments[-1].end].append((n.end, n))
    for entries in by_end.values():
        entries.sort(key=lambda x: x[0])
    joins = 0
    for n in slides:
        if not n.headless:
            continue
        entries = by_end.get(int(n.position), [])
        end_times = [e[0] for e in entries]
        i = bisect.bisect_left(end_times, n.time - .08)
        found = next((other for t, other in entries[i:i + 8] if abs(t - n.time) <= .08 and other is not n), None)
        if found:
            joins += 1
            patterns.append(event("无头滑条接续候选", [found, n], "尾键与起键一致，启动和结束时间相差不超过 80 ms", 1))
    # Interleaving proxy: foreign-key attacks inside a tracing interval, excluding endpoints.
    outer_times = [n.time for n in outer]
    interleaved = []
    for n in slides:
        lo = bisect.bisect_left(outer_times, n.time + .08)
        hi = bisect.bisect_right(outer_times, n.end - .08)
        foreign = [h for h in outer[lo:hi] if int(h.position) not in (int(n.position), n.segments[-1].end)]
        if len(foreign) >= 2:
            interleaved.append(n)
            patterns.append(event("滑行期间异键并行候选", [n], f"滑行中段有 {len(foreign)} 个非起尾键 TAP/HOLD；未判断真实路径遮挡", len(foreign)))
    chord_count = sum(len(g) >= 2 for g in groups)
    active_hold = []
    hold_occupied_hits = 0
    for n in heads:
        active_hold = [h for h in active_hold if h.end > n.time + EPS]
        if any(h.time < n.time - EPS for h in active_hold) and all(h.position != n.position for h in active_hold):
            hold_occupied_hits += 1
        if n.kind in ("hold", "touch_hold") and n.duration > .10:
            active_hold.append(n)
    coordination = min(2.0, chord_count / denom + .7 * overlap_ratio + .5 * hold_occupied_hits / max(1, len(heads)))
    for _, group_iter in itertools.groupby(touch, key=lambda n: round(n.time, 6)):
        ns = list(group_iter)
        if len(ns) >= 3:
            patterns.append(event("触摸簇", ns, f"同一时刻 {len(ns)} 枚 TOUCH；未模拟单掌覆盖", len(ns)))
    # Non-overlapping representative burst segment.
    burst_notes = [n for n in notes if peak_time - 1 + EPS < n.time <= peak_time + EPS]
    if peak_nps >= max(8, avg_nps * 1.5) and burst_notes:
        patterns.append(event("爆发", burst_notes, f"最密 1 秒：{peak_nps:.1f} 个判定对象/秒；计时口径为启动", peak_nps))
    fractions = {"break": sum(n.is_break for n in notes) / len(notes), "ex": sum(n.ex for n in notes) / len(notes), "touch": len(touch) / len(notes)}
    slide_rate = len(slides) / span
    misalignment = detect_misalignment(slides, outer, span)
    patterns.extend(misalignment.pop("events"))
    coverage_gate = min(1, slide_rate / .5)
    radar = [
        sat(.5 * avg_effort + .5 * sustained, 6), sat(peak_effort, 16),
        sat(trill_fraction * min(1.5, peak_effort / 10), .35),
        sat(jack_fraction * min(1.5, peak_effort / 8), .28),
        sat(sweep_fraction * min(1.5, peak_effort / 12), .30), sat(movement, .5),
        sat(rhythm, .6), sat(slide_rate * (1 + min(12, slide_speed) / 10), 1.8),
        misalignment["score_unrounded"], sat((chain_fraction + joins / max(1, len(slides))) * coverage_gate, .5),
        sat(coordination * min(1.5, avg_effort / 5), .7), sat(fractions["touch"] * min(1.5, avg_effort / 4), .3)
    ]
    features = {
        "log_avg_effort": math.log1p(avg_effort), "log_peak_effort": math.log1p(peak_effort),
        "log_sustained_effort": math.log1p(sustained), "trill_fraction": trill_fraction,
        "jack_fraction": jack_fraction, "sweep_fraction": sweep_fraction, "travel_pressure": movement,
        "rhythm_complexity": rhythm, "slide_rate": slide_rate, "slide_speed": min(30, slide_speed),
        "slide_overlap_ratio": overlap_ratio, "chain_fraction": chain_fraction,
        "touch_fraction": fractions["touch"], "coordination": coordination,
        "break_fraction": fractions["break"], "ex_fraction": fractions["ex"],
        "waiting_interleave_fraction": misalignment["waiting_interleave_fraction"],
        "same_origin_launch_fraction": misalignment["same_origin_launch_fraction"],
        "misalign_run_fraction": misalignment["summary"]["head_fraction_in_runs"]
    }
    effective = .4 * avg_effort + .2 * peak_effort + .4 * sustained
    base = ANCHORS[-1][1]
    for (a, x), (b, y) in zip(ANCHORS, ANCHORS[1:]):
        if effective <= b:
            base = x + max(0, effective - a) / (b - a) * (y - x)
            break
    gate = min(1.0, effective / 4)
    components = [("密度映射基线", base), ("纵连", .30 * radar[3] / 100 * gate), ("位移近似", .25 * radar[5] / 100 * gate), ("节奏变化", .25 * radar[6] / 100 * gate), ("滑条处理", .50 * radar[7] / 100 * gate), ("错位结构", .25 * radar[8] / 100 * gate), ("连接滑条", .18 * radar[9] / 100 * gate), ("协同近似", .25 * radar[10] / 100 * gate), ("EX 修正", -.15 * fractions["ex"] * gate)]
    estimate_raw = sum(c for _, c in components)
    prediction: dict[str, Any] = {"method": "handcrafted-heuristic-v1.1", "calibrated": False, "error_estimate": None, "uncertainty": "未校准；没有可用的统计误差或置信区间。", "contributions": [{"feature": k, "contribution": round(v, 5)} for k, v in components], "in_training_set": False}
    if model is not None:
        estimate_raw, model_components = predict_model(model, features)
        in_sample = parsed.fingerprint in model.get("training_fingerprints", [])
        prediction.update(method="ridge-calibrated-v1", calibrated=True, error_estimate=model.get("validation"), uncertainty="误差来自训练语料的按组交叉验证；不是该谱面的置信区间。", contributions=model_components, in_training_set=in_sample)
        if in_sample:
            warnings.append("此谱面出现在模型训练集中；当前数值是样本内拟合，不代表泛化准确率。")
        low, high = model.get("training_level_range", [1, 15.5])
        if not low <= estimate_raw <= high:
            warnings.append("模型预测超出训练标级范围，属于外推。")
    estimate = round(max(1.0, min(15.5, estimate_raw)), 1)
    prediction.update(estimated_level=estimate, unclipped_level=round(estimate_raw, 5), clipped=not (1 <= estimate_raw <= 15.5))
    if parsed.skipped or overfull:
        prediction.update(estimated_level=None, unclipped_level=None, clipped=False, uncertainty="存在跳过语法或超过两枚外键的同押，难度预估已禁用。")
    if span < 20 or len(notes) < 100:
        warnings.append("谱面较短或物量较少，统计特征不稳定；当前预估尤其不适合外推到完整曲目。")
    if slides:
        warnings.append("曲线滑条长度、自动分手、错位和协同均为近似；未模拟判定区、碰撞、掌押、遮挡与真实手序。")
    if any(s.shape in ("p", "q", "pp", "qq", "s", "z", "w") for n in slides for s in n.segments):
        warnings.append("p/q/pp/qq/s/z/w 路径长度使用固定近似；总时长连接滑条的分段时间也按近似长度分配。")
    level_text = source.metadata.get(f"lv_{difficulty}", "")
    declared = declared_override
    declared_source = "--level" if declared_override is not None else None
    if declared is None and re.fullmatch(r"\d+\.\d+", level_text):
        declared, declared_source = float(level_text), "maidata 标注（不保证来自官方）"
    if declared is not None and not 1 <= declared <= 15.5:
        warnings.append("文件标级超出 1–15.5，未计算偏差。")
        declared = None
    delta = round(estimate - declared, 2) if declared is not None and prediction["estimated_level"] is not None else None
    # Do not label water/fake from an unvalidated heuristic or a display-only integer / '+'.
    pattern_summary = []
    for label in sorted(set(p["label"] for p in patterns)):
        rows = [p for p in patterns if p["label"] == label]
        pattern_summary.append({"label": label, "count": len(rows), "max_strength": max(p["strength"] for p in rows)})
    return {
        "schema_version": SCHEMA_VERSION, "analyzer_version": VERSION, "source_file": source.path, "source_encoding": source.encoding,
        "title": source.metadata.get("title", Path(source.path).stem), "artist": source.metadata.get("artist", ""),
        "difficulty": difficulty, "difficulty_name": DIFFICULTIES.get(difficulty, f"SLOT {difficulty}"),
        "declared_level_text": level_text, "declared_constant": declared, "declared_constant_source": declared_source,
        "deviation_prediction_minus_declared": delta, "fingerprint": parsed.fingerprint,
        "note_counts": official_style_counts(notes),
        "statistics": {"judged_objects": len(notes), "types": dict(Counter(n.kind for n in notes)), "break_count": sum(n.is_break for n in notes), "ex_count": sum(n.ex for n in notes), "start_seconds": round(start, 4), "end_seconds": round(end, 4), "effective_seconds": round(span, 4), "mean_onset_nps": round(avg_nps, 4), "peak_1s_onset_nps": round(peak_nps, 4), "mean_effort_per_second": round(avg_effort, 4), "peak_1s_effort": round(peak_effort, 4), "p90_8s_effort": round(sustained, 4), "peak_slide_concurrency": slide_peak, "bpm_min": min(x["bpm"] for x in parsed.tempo), "bpm_max": max(x["bpm"] for x in parsed.tempo)},
        "radar": [{"label": k, "score": round(v, 1)} for k, v in zip(AXES, radar)],
        "radar_scale": "固定公式的 0–100 饱和强度，不是百分位、命中概率或技能准确度；不同轴不得相加。",
        "prediction": prediction, "model_features": features, "misalignment": misalignment,
        "pattern_summary": pattern_summary, "patterns": sorted(patterns, key=lambda p: (p["start"], p["label"])),
        "warnings": list(dict.fromkeys(warnings)), "skipped_tokens": parsed.skipped,
        "timeline": [{"time": round(t, 4), "onset_nps_2s": round(nps, 4)} for t, nps in zip(timeline_t, timeline_nps)],
        "method_notes": ["密度使用 note 启动：SLIDE 在等待结束时计入；星星头单独计 TAP，连接滑条整条计 1，WiFi 整条计 1。", "时长为首个判定对象启动至最后对象结束；末尾 TAP 补 0.05–0.5 秒中位间隔；不包含前后空白。", "所有检测阈值与密度映射锚点均为本 demo 人工定义，未使用 AWMC 私有算法。", "默认预测完全不读取 lv_N；整数与 + 只展示，不擅自推断定数。", misalignment["definition"], misalignment["scoring"], "错位基础事件按滑条条数，连续错位按段数；子型标签可重叠。独立星星头去重后参与雷达计分。"]
    }


def predict_model(model: dict[str, Any], features: dict[str, float]) -> tuple[float, list[dict[str, Any]]]:
    if not isinstance(model, dict):
        raise ValueError("模型必须是 JSON 对象")
    if model.get("format") != "maimai-ridge-v1" or model.get("feature_names") != MODEL_FEATURES or model.get("analyzer_version") != VERSION:
        raise ValueError("模型格式、特征顺序或分析器版本不兼容；请用本版本 calibrate.py 重新训练。")
    p = len(MODEL_FEATURES)
    for k in ("means", "scales", "weights"):
        if not isinstance(model.get(k), list) or len(model[k]) != p or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in model[k]):
            raise ValueError(f"模型 {k} 字段无效")
    if not isinstance(model.get("intercept"), (int, float)) or not math.isfinite(model["intercept"]) or any(s <= 0 for s in model["scales"]):
        raise ValueError("模型截距或标准差无效")
    contributions = [{"feature": "模型截距", "contribution": model["intercept"]}]
    for key, mean, scale, weight in zip(MODEL_FEATURES, model["means"], model["scales"], model["weights"]):
        contributions.append({"feature": key, "contribution": (features[key] - mean) / scale * weight})
    return sum(c["contribution"] for c in contributions), contributions


def analyze_maidata(
    text: str,
    *,
    origin: str = "<uploaded>",
    encoding: str = "utf-8",
    bpm_override: float | None = None,
    strict: bool = True,
    model: dict[str, Any] | None = None,
    catalog: dict[str, Any] | None = None,
    percentiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse every non-empty difficulty and optionally overlay catalog / peer-percentile data."""
    source = load_source_text(text, origin, encoding)
    reports = []
    for difficulty in sorted(source.charts):
        parsed = parse_chart(source, difficulty, bpm_override, strict)
        if not parsed.notes:
            continue
        report = analyze(parsed, source, difficulty, None, model)
        if catalog is not None or percentiles is not None:
            from catalog import enrich_report
            enrich_report(report, catalog, percentiles)
        reports.append(report)
    if not reports:
        raise ValueError("所选谱面全部为空。")
    preferred = next((r["difficulty"] for r in reports if r["difficulty"] in (6, 5)), reports[-1]["difficulty"])
    return {
        "schema_version": SCHEMA_VERSION,
        "analyzer_version": VERSION,
        "title": source.metadata.get("title", Path(origin).stem or "uploaded"),
        "artist": source.metadata.get("artist", ""),
        "encoding": source.encoding,
        "origin": source.path,
        "preferred_difficulty": preferred,
        "reports": reports,
    }


def radar_svg(report: dict[str, Any]) -> str:
    width, height, cx, cy, radius = 820, 790, 410, 374, 236
    def point(i: int, r: float) -> tuple[float, float]:
        angle = -math.pi / 2 + 2 * math.pi * i / len(AXES)
        return cx + r * math.cos(angle), cy + r * math.sin(angle)
    def polygon(r: float) -> str:
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in (point(i, r) for i in range(len(AXES))))
    esc = html.escape
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="rt rd">', f'<title id="rt">{esc(report["title"])} · {esc(report["difficulty_name"])} 雷达</title>', '<desc id="rd">十二个维度，固定 0 到 100 刻度。部分维度是近似估计，不是玩家百分位。</desc>', '<g font-family="system-ui, Microsoft YaHei, PingFang SC, sans-serif" fill="currentColor">', '<text x="28" y="36" font-size="18">配置强度 · 固定刻度 0–100</text>']
    for level in (20, 40, 60, 80, 100):
        parts.append(f'<polygon points="{polygon(radius * level / 100)}" fill="none" stroke="currentColor" stroke-opacity=".16" stroke-width="1"/>')
        parts.append(f'<text x="{cx + 7}" y="{cy - radius * level / 100 + 16:.1f}" font-size="12" opacity=".55">{level}</text>')
    points = []
    for i, axis in enumerate(report["radar"]):
        x, y = point(i, radius)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.2f}" y2="{y:.2f}" stroke="currentColor" stroke-opacity=".14"/>')
        lx, ly = point(i, radius + 57)
        anchor = "middle" if abs(lx - cx) < 30 else "start" if lx > cx else "end"
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="17">{esc(axis["label"])}</text>')
        parts.append(f'<text x="{lx:.1f}" y="{ly + 25:.1f}" text-anchor="{anchor}" font-size="22" font-weight="650">{axis["score"]:.1f}</text>')
        points.append(point(i, radius * axis["score"] / 100))
    poly = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    parts.append(f'<polygon points="{poly}" fill="currentColor" fill-opacity=".12" stroke="currentColor" stroke-width="2.5"/>')
    for (x, y), axis in zip(points, report["radar"]):
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="currentColor"><title>{esc(axis["label"])}：{axis["score"]}</title></circle>')
    estimate = report["prediction"]["estimated_level"]
    caption = f'启发式预估 {estimate:.1f} · 未校准' if estimate is not None and not report["prediction"]["calibrated"] else f'校准模型预估 {estimate:.1f}' if estimate is not None else '难度预估已禁用'
    parts.append(f'<text x="410" y="731" text-anchor="middle" font-size="20" font-weight="650">{esc(caption)}</text>')
    parts.append('<text x="410" y="760" text-anchor="middle" font-size="14" opacity=".7">非 AWMC 算法 · 非官方定数 · 不是玩家百分位</text></g></svg>')
    return "".join(parts)


def density_svg(report: dict[str, Any]) -> str:
    rows = report["timeline"]
    x0, x1, y0, y1 = 60, 1090, 36, 221
    lo, hi = rows[0]["time"], rows[-1]["time"]
    ymax = max(5, math.ceil(max(r["onset_nps_2s"] for r in rows) / 5) * 5)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1120 275" role="img" aria-label="以谱面时间为横轴的两秒窗口启动密度曲线"><g fill="currentColor" font-family="system-ui,Microsoft YaHei,sans-serif">', '<text x="60" y="20" font-size="13">启动密度 · 判定对象 / 秒 · 2 秒窗口</text>']
    for i in range(5):
        y = y1 - (y1 - y0) * i / 4
        parts.append(f'<line x1="{x0}" x2="{x1}" y1="{y:.2f}" y2="{y:.2f}" stroke="currentColor" stroke-opacity=".13"/><text x="48" y="{y + 4:.2f}" text-anchor="end" font-size="12">{ymax * i / 4:g}</text>')
    coords = []
    for r in rows:
        x = x0 + (x1 - x0) * (r["time"] - lo) / max(EPS, hi - lo)
        y = y1 - (y1 - y0) * r["onset_nps_2s"] / ymax
        coords.append(f"{x:.2f},{y:.2f}")
    parts.append(f'<polyline points="{" ".join(coords)}" fill="none" stroke="currentColor" stroke-width="2"/>')
    for i in range(6):
        t = lo + (hi - lo) * i / 5
        x = x0 + (x1 - x0) * i / 5
        parts.append(f'<text x="{x:.2f}" y="245" font-size="13" text-anchor="middle">{t:.1f}s</text>')
    parts.append('</g></svg>')
    return "".join(parts)


def misalignment_html(report: dict[str, Any]) -> str:
    m = report["misalignment"]
    summary = m["summary"]
    esc = html.escape
    stats = [
        (f'{summary["waiting_foreign_slides"]} / {summary["eligible_slides"]}', "等待期异键 / 可检查滑条"),
        (str(summary["same_origin_launch_slides"]), "同位拍划 · 条"),
        (str(summary["umiyuri_structure_slides"]), "海底捞型结构 · 条"),
        (str(summary["continuous_runs"]), "连续错位 · 段"),
    ]
    cards = ''.join(f'<div class="metric"><strong>{value}</strong><small>{label}</small></div>' for value, label in stats)
    runs = ''.join(
        f'<tr><td class="num">{r["start"]:.2f}–{r["end"]:.2f}s</td><td class="num">{r["head_steps"]}</td>'
        f'<td>{esc(" → ".join("/".join(p) for p in r["head_positions"]))}</td><td class="num">{r["line"]}</td></tr>'
        for r in m['runs'])
    if not runs:
        runs = '<tr><td colspan="4">没有达到连续至少 3 个头时刻的规则；不等于没有单个错位单元。</td></tr>'
    units = []
    for u in m['slides']:
        samples = '；'.join(f'{n["position"]}@{n["time"]:.3f}s' for n in u['waiting_note_samples']) or '无'
        if u['waiting_samples_truncated']:
            samples += '；仅展示每键首尾样本，完整数量见 JSON'
        tags = '、'.join(u['labels']) or '未命中错位规则'
        units.append(
            f'<tr id="{u["id"]}"><td>{esc(u["id"])}<br>第 {u["line"]} 行<br><code>{esc(u["token"])}</code></td>'
            f'<td class="num">头 {u["head_time"]:.3f}s<br>启动 {u["slide_start"]:.3f}s<br>尾 {u["slide_end"]:.3f}s</td>'
            f'<td>{esc(samples)}</td><td>{esc("/".join(u["launch_positions"]) or "无")}<br>'
            f'原起点 TAP：{"有" if u["same_origin_launch"] else "无"}</td><td>{esc(tags)}</td></tr>')
    sample_unit = next((u for u in m['slides'] if u['umiyuri_structure']),
                       next((u for u in m['slides'] if u['waiting_foreign_count']), None))
    example = ''
    if sample_unit:
        u = sample_unit
        waiting = '；'.join(f'{n["time"]:.3f}s：{n["position"]} 键' for n in u['waiting_note_samples'])
        example = (f'<div class="sequence"><h3>原谱逐事件示例 · 第 {u["line"]} 行</h3><div class="sequence-grid">'
                   f'<div><small>① 星星头</small><strong>{u["head_time"]:.3f}s</strong>'
                   f'<p>{u["origin"]} 键出头，同刻外键 {esc("/".join(u["head_positions"]))}。</p></div>'
                   f'<div><small>② 等待期间</small><strong>{esc(waiting)}</strong>'
                   '<p>这里的插键发生在起划之前，不是滑行中段。</p></div>'
                   f'<div><small>③ 滑条启动</small><strong>{u["slide_start"]:.3f}s</strong>'
                   f'<p>同刻外键 {esc("/".join(u["launch_positions"]) or "无")}；'
                   f'原起点 TAP：{"有" if u["same_origin_launch"] else "无"}。'
                   f'滑条在 {u["slide_end"]:.3f}s 结束。</p></div></div>'
                   f'<p><code>{esc(u["token"])}</code> · 只描述谱面要求，不确定玩家使用哪只手。</p></div>')
    if not units:
        units.append('<tr><td colspan="5">没有可进行有头等待结构检查的滑条。</td></tr>')
    return (f'<section id="misalignment"><h2>错位结构核对</h2><p>{esc(m["definition"])}</p>'
            f'<div class="metrics misalign-metrics">{cards}</div>'
            '<p class="muted">子型可重叠，不能相加为总数。无头、零等待或零时长滑条不参与此项；'
            '原谱计时包含 first，未提供音频时不保证与录屏同步。</p>'
            f'{example}<h3>连续错位段</h3><div class="table-wrap"><table><thead><tr>'
            '<th class="num">谱面时间</th><th class="num">连续头时刻</th><th>起点顺序</th><th class="num">源码行</th>'
            f'</tr></thead><tbody>{runs}</tbody></table></div>'
            f'<details><summary>逐滑条证据 · {len(m["slides"])} 条，含未命中项</summary><div class="details-body table-wrap">'
            '<table class="evidence-table"><thead><tr><th>滑条 / 源码</th><th class="num">完整时序</th>'
            '<th>等待期外键 · 键位@秒</th><th>启动同刻</th><th>命中规则</th></tr></thead>'
            f'<tbody>{"".join(units)}</tbody></table></div></details>'
            f'<details><summary>错位轴评分公式与限制</summary><div class="details-body"><p>{esc(m["scoring"])}</p>'
            f'<p>本谱去重后的加权头占比 {m["weighted_head_fraction"]:.5f}，频率门控 {m["head_rate_gate"]:.5f}。'
            f'错位轴 {m["score"]:.1f} / 100。</p><p>{esc(m["limitations"])}</p></div></details></section>')


def report_html(report: dict[str, Any], siblings: list[tuple[str, str]]) -> str:
    esc = html.escape
    stats, pred = report["statistics"], report["prediction"]
    estimate = "—" if pred["estimated_level"] is None else f'{pred["estimated_level"]:.1f}'
    title = report["title"]
    decl = report["declared_level_text"] or "未填写"
    nav = " ".join(f'<a href="{esc(path, quote=True)}">{esc(label)}</a>' for label, path in siblings)
    radar_rows = "".join(f'<tr><td>{esc(r["label"])}</td><td class="num">{r["score"]:.1f}</td></tr>' for r in report["radar"])
    warnings = "".join(f'<p>{esc(w)}</p>' for w in report["warnings"])
    patterns = "".join(f'<tr><td>{esc(r["label"])}</td><td class="num">{r["start"]:.2f}–{r["end"]:.2f}s</td><td class="num">{r["line"]}</td><td>{esc(r["evidence"])}</td></tr>' for r in report["patterns"])
    if not patterns:
        patterns = '<tr><td colspan="4">没有触发当前规则的配置段；不等于谱面没有难点。</td></tr>'
    chips = "".join(f'<span class="chip">{esc(p["label"])} × {p["count"]}</span>' for p in report["pattern_summary"])
    contributions = "".join(f'<tr><td>{esc(c["feature"])}</td><td class="num">{c["contribution"]:+.4f}</td></tr>' for c in pred["contributions"])
    notes = "".join(f'<p>{esc(n)}</p>' for n in report["method_notes"])
    delta = report["deviation_prediction_minus_declared"]
    comparison = f'与文件标注 {report["declared_constant"]:.1f} 相差 {delta:+.2f}。' if delta is not None else '整数标级与「+」不反推定数，不输出水谱 / 虚高判断。'
    validation = pred.get("error_estimate")
    validation_text = f'<p>按组交叉验证 MAE：{validation["mae"]:.3f}；RMSE：{validation["rmse"]:.3f}。这不是本谱面误差保证。</p>' if validation else ''
    mode = "已使用本地校准模型" if pred["calibrated"] else "未校准的启发式模型"
    sample = '<p><strong>样本内拟合：当前谱面在训练集中。</strong></p>' if pred["in_training_set"] else ''
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · 舞萌谱面分析</title><style>
*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,-apple-system,"Microsoft YaHei","PingFang SC",sans-serif;line-height:1.65}}main{{max-width:1220px;margin:0 auto;padding:40px 30px 64px}}header{{border-bottom:2px solid;padding-bottom:24px}}.eyebrow{{letter-spacing:.18em;font-size:12px;font-weight:700}}h1{{font-size:clamp(28px,4vw,46px);line-height:1.22;margin:12px 0;overflow-wrap:anywhere}}h2{{font-size:23px;margin:30px 0 15px}}p{{margin:8px 0}}.muted{{opacity:.7}}nav{{display:flex;flex-wrap:wrap;gap:14px;margin-top:14px}}a{{color:inherit;text-underline-offset:4px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;padding:24px 0;border-bottom:1px solid}}.metric strong{{display:block;font-size:38px;line-height:1.2;font-variant-numeric:tabular-nums}}.metric small{{display:block;margin-top:8px}}.estimate-note{{padding:18px 0;border-bottom:1px solid;font-size:14px}}.overview{{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(240px,1fr);gap:35px;align-items:center}}svg{{display:block;width:100%;height:auto}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:10px 8px;border-bottom:1px solid rgba(0,0,0,.13);text-align:left;vertical-align:top}}th{{font-size:12px;letter-spacing:.04em}}.num{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}.table-wrap{{overflow-x:auto}}.chip{{display:inline-block;border:1px solid;padding:3px 9px;border-radius:3px;font-size:13px;margin:3px 6px 3px 0}}details{{border-top:1px solid;padding:15px 0}}summary{{cursor:pointer;font-weight:650}}.details-body{{padding-top:10px;font-size:14px;overflow-wrap:anywhere}}.sequence{{margin:24px 0;padding:18px 0;border-top:1px solid;border-bottom:1px solid}}.sequence-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px}}.sequence strong{{display:block;font-variant-numeric:tabular-nums;font-size:21px;overflow-wrap:anywhere}}.sequence small{{display:block;opacity:.7}}.sequence h3{{margin-top:0}}.misalign-metrics .metric strong{{font-size:32px}}.evidence-table{{min-width:760px}}.evidence-table code{{overflow-wrap:anywhere}}footer{{margin-top:35px;font-size:12px;opacity:.65}}@media(max-width:760px){{main{{padding:24px 16px}}.overview{{grid-template-columns:1fr;gap:0}}.sequence-grid{{grid-template-columns:1fr;gap:14px}}.metrics{{grid-template-columns:repeat(2,1fr)}}.metric strong{{font-size:32px}}}}@media print{{main{{padding:0}}details{{break-inside:avoid}}nav{{display:none}}}}
</style></head><body><main><header><div class="eyebrow">MAIDATA / LOCAL ANALYSIS · V{VERSION}</div><h1>{esc(title)}</h1><p>{esc(report["artist"])} · {esc(report["difficulty_name"])} · 文件标级 {esc(decl)}</p><nav>{nav}</nav></header>
<div class="metrics"><div class="metric"><strong>{estimate}</strong><small>预估定数 · {esc(mode)}</small></div><div class="metric"><strong>{stats["judged_objects"]:,}</strong><small>判定对象 · 星星头与滑条分开计数</small></div><div class="metric"><strong>{stats["mean_onset_nps"]:.2f}</strong><small>平均启动密度 / 秒</small></div><div class="metric"><strong>{stats["peak_1s_onset_nps"]:.1f}</strong><small>最高 1 秒启动密度 / 秒</small></div></div>
<section class="estimate-note"><strong>不是 AWMC 算法，也不是官方定数。</strong><p>{esc(pred["uncertainty"])} {esc(comparison)}</p>{sample}{validation_text}</section>
<section><h2>十二维配置雷达</h2><p class="muted">{esc(report["radar_scale"])}</p><div class="overview"><div>{radar_svg(report)}</div><table><thead><tr><th>维度</th><th class="num">强度 / 100</th></tr></thead><tbody>{radar_rows}</tbody></table></div></section>
{misalignment_html(report)}
<section><h2>密度时间轴</h2><p class="muted">谱面时间 · 含 first 偏移 · 有效区间 {stats["effective_seconds"]:.2f} 秒 · BPM {stats["bpm_min"]:g}–{stats["bpm_max"]:g}</p>{density_svg(report)}</section>
<section><h2>检测到的配置段</h2><p>{chips or '未触发配置规则。'}</p><p class="muted">错位基础事件按滑条条数，连续错位按段数；子型可重叠，不能相加。strength 是各规则内部量，不能跨标签直接比较。</p><details><summary>展开全部 {len(report["patterns"])} 条规则命中</summary><div class="details-body table-wrap"><table><thead><tr><th>配置</th><th class="num">谱面时间</th><th class="num">源码行</th><th>判定依据</th></tr></thead><tbody>{patterns}</tbody></table></div></details></section>
<section><h2>数据与方法</h2><details open><summary>解析警告与适用范围</summary><div class="details-body">{warnings or '<p>未发现解析警告。</p>'}</div></details><details><summary>难度贡献明细</summary><div class="details-body"><p>各项之和为限幅前预测；最终显示限制在 1.0–15.5。特征贡献不是因果结论。</p><table>{contributions}</table></div></details><details><summary>统计口径</summary><div class="details-body">{notes}<p>输入文件 SHA-256（事件规范化）：{esc(report["fingerprint"])}</p></div></details></section>
<footer>完全本地运行，无第三方脚本、无网络请求、无账号依赖。输出包含 JSON、SVG 与可追溯的配置时间段。</footer></main></body></html>'''


def write_report(report: dict[str, Any], out: Path, siblings: list[tuple[str, str]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (out / "radar.svg").write_text(radar_svg(report), encoding="utf-8")
    (out / "density.svg").write_text(density_svg(report), encoding="utf-8")
    (out / "report.html").write_text(report_html(report, siblings), encoding="utf-8")
    with (out / "misalignment.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["id", "line", "token", "origin", "head_time", "slide_start", "slide_end", "wait_seconds", "waiting_foreign_count", "waiting_same_origin_count", "same_origin_launch", "umiyuri_structure", "continuous_run_id", "waiting_positions", "launch_positions", "labels"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for u in report["misalignment"]["slides"]:
            row = {key: u.get(key) for key in fields}
            row.update(waiting_positions="/".join(u["waiting_counts_by_position"]), launch_positions="/".join(u["launch_positions"]), labels=";".join(u["labels"]))
            writer.writerow(row)
    with (out / "patterns.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["label", "start", "end", "note_count", "strength", "evidence", "line"])
        writer.writeheader()
        writer.writerows(report["patterns"])


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="本地 maidata 分析：雷达 SVG + HTML + JSON + 预估定数（默认未校准）。")
    ap.add_argument("input", nargs="?", default="maidata.txt", help="maidata 文件或包含它的文件夹；默认当前目录 maidata.txt")
    ap.add_argument("--difficulty", "-d", default="all", help="all、master、expert、remaster，或 inote 槽位数字；默认分析全部")
    ap.add_argument("--out", "-o", default="analysis_output", help="输出目录")
    ap.add_argument("--open", action="store_true", help="分析后打开本地报告")
    ap.add_argument("--encoding", help="强制输入编码，如 utf-8-sig、cp932、gb18030")
    ap.add_argument("--bpm", type=float, help="仅提供谱面没有声明时的初始 BPM；谱内 (BPM) 仍优先")
    ap.add_argument("--level", type=float, help="仅单难度：提供用于比较的已知定数，不参与预测")
    ap.add_argument("--model", type=Path, help="calibrate.py 生成的本地岭回归模型")
    ap.add_argument("--catalog", type=Path, help="build_catalog.py 生成的曲库快照（国服拟合 / 日服定数）")
    ap.add_argument("--percentiles", type=Path, help="同等级雷达百分位表")
    ap.add_argument("--lenient", action="store_true", help="跳过未知 note，记录警告并禁用预测；时间控制语法仍严格")
    ap.add_argument("--version", action="version", version=VERSION)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        path = Path(args.input).expanduser()
        if path.is_dir():
            found = [p for p in path.iterdir() if p.is_file() and p.name.lower() == "maidata.txt"]
            if len(found) != 1:
                raise ValueError("该目录下没有唯一的 maidata.txt 文件。")
            path = found[0]
        if args.bpm is not None:
            number(str(args.bpm), "--bpm", strict_positive=True)
        if args.level is not None and (not math.isfinite(args.level) or not 1 <= args.level <= 15.5):
            raise ValueError("--level 必须在 1–15.5 内")
        source = load_source(path, args.encoding)
        aliases = {"easy": 1, "basic": 2, "advanced": 3, "expert": 4, "master": 5, "remaster": 6, "re:master": 6, "original": 7}
        selection = args.difficulty.lower()
        if selection == "all":
            selected = sorted(source.charts)
        else:
            try:
                selected = [aliases[selection] if selection in aliases else int(selection)]
            except ValueError:
                raise ValueError("难度应为 all、master、expert、remaster 或 inote 槽位数字") from None
        if args.level is not None and len(selected) != 1:
            raise ValueError("--level 只适用于单难度，请同时指定 --difficulty")
        if any(d not in source.charts for d in selected):
            raise ValueError(f"该文件可用的 inote 槽位：{', '.join(map(str, sorted(source.charts)))}")
        model = json.loads(args.model.read_text(encoding="utf-8-sig")) if args.model else None
        catalog = json.loads(args.catalog.read_text(encoding="utf-8-sig")) if args.catalog else None
        percentiles = json.loads(args.percentiles.read_text(encoding="utf-8-sig")) if args.percentiles else None
        out = Path(args.out).resolve()
        # Parse and analyze all first; a parse failure must not look like a fresh complete report.
        reports = []
        for d in selected:
            chart = parse_chart(source, d, args.bpm, not args.lenient)
            if not chart.notes and selection == "all":
                print(f"跳过空谱面 inote_{d}。")
                continue
            report = analyze(chart, source, d, args.level, model)
            if catalog is not None or percentiles is not None:
                from catalog import enrich_report
                enrich_report(report, catalog, percentiles)
            reports.append(report)
        if not reports:
            raise ValueError("所选谱面全部为空。")
        out.mkdir(parents=True, exist_ok=True)
        links = [(r["difficulty_name"], f'../difficulty_{r["difficulty"]}/report.html') for r in reports]
        for report in reports:
            folder = out / f'difficulty_{report["difficulty"]}'
            write_report(report, folder, links)
            value = report["prediction"]["estimated_level"]
            estimate = f"{value:.1f}" if value is not None else "禁用"
            print(f'{report["difficulty_name"]}: 物量 {report["statistics"]["judged_objects"]} | 预估 {estimate} | 错位 {report["misalignment"]["score"]:.1f}/100 | {folder / "report.html"}')
            ms = report["misalignment"]["summary"]
            if ms["total_slides"]:
                print(f'  错位结构：等待期异键 {ms["waiting_foreign_slides"]} 条；同位拍划 {ms["same_origin_launch_slides"]} 条；海底捞型 {ms["umiyuri_structure_slides"]} 条；连续错位 {ms["continuous_runs"]} 段。')
        esc = html.escape
        items = "".join(f'<li><a href="difficulty_{r["difficulty"]}/report.html">{esc(r["difficulty_name"])}</a> · 文件标级 {esc(r["declared_level_text"] or "未填写")} · 预估 {r["prediction"]["estimated_level"] if r["prediction"]["estimated_level"] is not None else "禁用"}</li>' for r in reports)
        (out / "index.html").write_text(f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>谱面分析</title><body style="font-family:system-ui,Microsoft YaHei,sans-serif;max-width:850px;margin:60px auto;padding:24px;line-height:1.8"><h1>{esc(source.metadata.get("title", path.stem))}</h1><p>选择难度查看雷达、密度曲线、配置时间段和预测。默认是未校准的启发式估计，非官方定数。</p><ul>{items}</ul></body></html>', encoding="utf-8")
        (out / "summary.json").write_text(json.dumps([{k: r[k] for k in ("title", "difficulty", "difficulty_name", "declared_level_text", "prediction", "statistics", "radar")} for r in reports], ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(f"完成：{out / 'index.html'}")
        if args.open:
            target = out / "index.html" if len(reports) > 1 else out / f"difficulty_{reports[0]['difficulty']}" / "report.html"
            if not webbrowser.open(target.as_uri()):
                print("浏览器未自动打开；请手动打开上面的 report.html。")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
