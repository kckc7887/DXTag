#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Faster maidata-only crawler for the public maisquared HTML index."""
from __future__ import annotations

import argparse
import html as htmlmod
import re
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = "https://ftp.nijika.org/maisquared/"
SKIP = {"legacy_maidata (do not download)", "zip", "collections", "..", "../"}
HREF = re.compile(r'href="([^"]+)"', re.I)
CTX = ssl.create_default_context()


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "DXTag-maidata-crawler/1.2"})
    with urllib.request.urlopen(req, context=CTX, timeout=timeout) as resp:
        return resp.read()


def list_dir(url: str) -> list[str]:
    text = fetch(url).decode("utf-8", "replace")
    out = []
    for href in HREF.findall(text):
        name = urllib.parse.unquote(href.split("?")[0])
        if name in (".", "./") or name.lower() in SKIP or name.startswith("?"):
            continue
        out.append(htmlmod.unescape(name))
    return out


def save_maidata(folder_url: str, dest: Path) -> tuple[str, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest.as_posix(), "skip"
    url = folder_url if folder_url.endswith("maidata.txt") else urllib.parse.urljoin(folder_url, "maidata.txt")
    try:
        data = fetch(url)
    except Exception as exc:  # noqa: BLE001
        return url, f"err:{exc}"
    if data[:1] == b"<":
        return url, "html"
    dest.write_bytes(data)
    return dest.as_posix(), "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("corpus/maisquared"))
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    versions = [n for n in list_dir(BASE) if n.endswith("/")]
    jobs = []
    for ver in versions:
        if ver.strip("/").lower() in SKIP:
            continue
        ver_url = urllib.parse.urljoin(BASE, urllib.parse.quote(ver))
        try:
            songs = [n for n in list_dir(ver_url) if n.endswith("/")]
        except Exception as exc:  # noqa: BLE001
            print("skip version", ver, exc)
            continue
        print(ver, len(songs), "songs")
        for song in songs:
            song_url = urllib.parse.urljoin(ver_url, urllib.parse.quote(song))
            dest = args.out / ver.strip("/") / song.strip("/") / "maidata.txt"
            jobs.append((song_url, dest))
    ok = skip = err = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(save_maidata, url, dest) for url, dest in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            _, status = fut.result()
            ok += status == "ok"
            skip += status == "skip"
            err += status not in ("ok", "skip")
            if i % 50 == 0:
                print(f"progress {i}/{len(jobs)} ok={ok} skip={skip} err={err}")
    print(f"done ok={ok} skip={skip} err={err} total_jobs={len(jobs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
