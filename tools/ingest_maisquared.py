#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Download only maidata.txt from the public maisquared mirror (no audio/video)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

MIRROR = "https://ftp.nijika.org/maisquared/"
EXCLUDE = [
    "legacy_maidata (DO NOT DOWNLOAD)",
    "zip",
    "collections",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("corpus/maisquared"))
    ap.add_argument("--url", default=MIRROR)
    ap.add_argument("--limit", type=int, default=0, help="optional max files (0 = all)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    wget = [
        "wget",
        "-r",
        "-l",
        "5",
        "-np",
        "-nH",
        "--cut-dirs=1",
        "-A",
        "maidata.txt",
        "-R",
        "*.mp3,*.mp4,*.jpg,*.png,*.jpeg,*.zip,*.webp",
        "--timeout=20",
        "--tries=2",
        "--retry-connrefused",
        "-e",
        "robots=off",
        "-P",
        str(args.out),
    ]
    for name in EXCLUDE:
        wget.extend(["-X", f"/{name}"])
    if args.limit:
        wget.extend(["-Q", f"{max(1, args.limit)}k"])  # not file count; skip
    wget.append(args.url)
    print(" ".join(wget), file=sys.stderr)
    return subprocess.call(wget)


if __name__ == "__main__":
    raise SystemExit(main())
