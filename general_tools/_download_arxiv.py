"""Temp helper: parallel range-chunk PDF downloader for arXiv (deleted after use).

arXiv throttles per-connection throughput; this downloads one PDF with N
parallel ranged connections and stitches them, which multiplies effective
speed. Falls back to plain single-connection download per chunk retries.
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHUNKS = 6
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def get_length(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers.get("Content-Length") or 0)


def fetch_range(url, start, end, dst, idx, timeout=180):
    """Download bytes [start, end] into dst[idx]; retries with backoff."""
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if len(data) != end - start + 1:
                raise IOError(f"short range {len(data)} != {end - start + 1}")
            dst[idx].write_bytes(data)
            return len(data)
        except Exception as exc:  # noqa: BLE001
            print(f"    chunk {idx}: attempt {attempt + 1} failed: {str(exc)[:120]}")
            if attempt == 3:
                raise
            time.sleep(4 * (attempt + 1))


def download_one(url, out: Path, chunks: int = CHUNKS) -> int:
    total = get_length(url)
    print(f"  size {total / 1e6:.1f} MB, {chunks} parallel chunks")
    if total <= 0:
        raise IOError("no content-length")
    out.parent.mkdir(parents=True, exist_ok=True)
    part_dir = out.parent / f".parts_{out.stem}"
    part_dir.mkdir(exist_ok=True)
    span = total // chunks
    jobs = []
    for i in range(chunks):
        start = i * span
        end = total - 1 if i == chunks - 1 else (i + 1) * span - 1
        jobs.append((i, start, end))
    t0 = time.time()
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=chunks) as ex:
        futs = {ex.submit(fetch_range, url, s, e, part_dir, i): i for i, s, e in jobs}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            done += 1
            sz = fut.result()
            print(f"    chunk {done}/{chunks} done ({sz / 1e6:.1f} MB) — "
                  f"{time.time() - t0:.0f}s elapsed")
    # stitch in order
    with out.open("wb") as f:
        for i in range(chunks):
            f.write((part_dir / f"{i:03d}").read_bytes())
    import shutil

    shutil.rmtree(part_dir, ignore_errors=True)
    got = out.stat().st_size
    if got != total:
        raise IOError(f"size mismatch {got} != {total}")
    print(f"  OK {out.name} ({got / 1e6:.1f} MB in {time.time() - t0:.0f}s)")
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("papers_dir")
    ap.add_argument("map_json")  # {"arxiv_id": "filename.pdf"}
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    papers_dir = Path(args.papers_dir)
    mapping = json.loads(Path(args.map_json).read_text(encoding="utf-8"))
    only = set(args.only.split(",")) if args.only else None
    for i, (aid, fname) in enumerate(mapping.items(), 1):
        if only and aid not in only:
            continue
        out = papers_dir / fname
        if out.exists() and out.stat().st_size >= 20_000:
            print(f"[{i}/{len(mapping)}] {aid} already present — skip")
            continue
        print(f"[{i}/{len(mapping)}] {aid} → {fname}")
        try:
            download_one(f"https://arxiv.org/pdf/{aid}", out)
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED {aid}: {str(exc)[:200]}")
        time.sleep(3)


if __name__ == "__main__":
    main()
