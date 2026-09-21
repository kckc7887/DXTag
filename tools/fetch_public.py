#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Download public CN/JP catalog JSON into corpus/ (gitignored)."""
from __future__ import annotations

import argparse
import json
import ssl
import urllib.request
from pathlib import Path

URLS = {
    "music_data.json": "https://www.diving-fish.com/api/maimaidxprober/music_data",
    "chart_stats.json": "https://www.diving-fish.com/api/maimaidxprober/chart_stats",
    "dxdata.json": "https://raw.githubusercontent.com/gekichumai/dxrating/main/packages/dxdata/dxdata.json",
}


def fetch(url: str, dest: Path, timeout: int = 120) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "DXTag-catalog-builder/1.2"})
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        data = resp.read()
    dest.write_bytes(data)
    # sanity: json
    json.loads(data.decode("utf-8"))
    print(f"wrote {dest} ({len(data)} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("corpus/raw"))
    args = ap.parse_args()
    for name, url in URLS.items():
        try:
            fetch(url, args.out / name)
        except Exception as exc:  # noqa: BLE001 — CLI
            print(f"WARN {name}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
