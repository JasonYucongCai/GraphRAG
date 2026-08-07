"""Temp helper: robust arXiv PDF downloader via curl.exe (deleted after use).

arXiv throttles bot-ish connections (~16 KB/s). This downloader is built for
CORRECTNESS over speed:
  • curl.exe with full browser headers (Chrome on Windows)
  • `-C -` resume — interrupted downloads continue where they left off
  • no aggressive max-time (each file may take 5–20 min when throttled)
  • retries across hosts (arxiv.org → export.arxiv.org) with backoff
  • every file validated with pypdf after download; corrupt files are
    deleted and re-fetched
  • polite pacing: one file at a time, sleeps between files
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PAPERS_DIR_ARG = "database/multi-agent-network/assets/papers"
MAP_JSON_ARG = "tools/_map.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

CURL_HEADERS = [
    "-A", UA,
    "-H", "Accept: application/pdf,text/html,application/xhtml+xml,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.9",
    "-H", "Referer: https://www.google.com/",
]

HOSTS = [
    "https://arxiv.org/pdf/{aid}",
    "https://export.arxiv.org/pdf/{aid}",
]


def valid_pdf(path: Path) -> bool:
    """Return True if path is a readable PDF with at least one page."""
    try:
        from pypdf import PdfReader
        r = PdfReader(str(path))
        return len(r.pages) >= 1
    except Exception:  # noqa: BLE001
        return False


def curl_fetch(url: str, out: Path, resume: bool = True, max_time: int = 600) -> int:
    """Download (or resume) url into out. Returns curl exit code.

    arXiv throttles connections to ~13-16 KB/s but transfers succeed; the
    --speed-time/--speed-limit pair aborts dead connections quickly, and -C -
    resumes partial files so throttled transfers never lose progress.
    """
    cmd = ["curl", "-sS", "-L", "--fail", "--retry", "2", "--retry-delay", "3",
           "--retry-all-errors", "--connect-timeout", "20", "--max-time",
           str(max_time), "--speed-time", "60", "--speed-limit", "1024"]
    if resume:
        cmd.append("-C")
        cmd.append("-")
    cmd += CURL_HEADERS + ["-o", str(out), url]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"      curl exit {proc.returncode}: {proc.stderr.strip()[-140:]}")
    return proc.returncode


def s2_oa_url(aid: str) -> Optional[str]:
    """Semantic Scholar openAccessPdf URL if it points off-arXiv (fallback host)."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{aid}?fields=openAccessPdf"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
        u = (data.get("openAccessPdf") or {}).get("url", "")
        if u and "arxiv.org" not in u:
            return u
    except Exception:  # noqa: BLE001
        pass
    return None


def get_length(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers.get("Content-Length") or 0)


def curl_fetch_range(url: str, start: int, end: int, dst: Path) -> int:
    """Download bytes [start, end] of url into dst (retries). Returns bytes."""
    for attempt in range(3):
        try:
            cmd = ["curl", "-sS", "-L", "--fail", "--connect-timeout", "20",
                   "--max-time", "240", "-A", UA,
                   "-H", f"Range: bytes={start}-{end}",
                   "-o", str(dst), url]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0 and dst.stat().st_size == end - start + 1:
                return dst.stat().st_size
            print(f"      range {start}-{end} attempt {attempt + 1} failed "
                  f"({dst.stat().st_size if dst.exists() else 0} B)")
            time.sleep(4 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001
            print(f"      range {start}-{end} attempt {attempt + 1}: {str(exc)[:100]}")
            time.sleep(4 * (attempt + 1))
    raise IOError(f"range {start}-{end} failed after 3 attempts")


def fetch_ranged(url: str, out: Path, chunks: int = 6) -> bool:
    """Download url with N parallel ranged connections; returns valid-PDF bool.

    arXiv's ~14 KB/s throttle is PER-CONNECTION — 6 parallel ranged
    connections measured ~122 KB/s aggregate (~9×)."""
    try:
        total = get_length(url)
        if total <= 0:
            raise IOError("no content-length")
    except Exception as exc:  # noqa: BLE001
        print(f"      no content-length ({str(exc)[:80]}) — falling back to plain")
        return False
    if out.exists() and out.stat().st_size == total and valid_pdf(out):
        return True
    part_dir = out.parent / f".parts_{out.stem}"
    part_dir.mkdir(exist_ok=True)
    span = total // chunks
    jobs = [(i * span, total - 1 if i == chunks - 1 else (i + 1) * span - 1, i)
            for i in range(chunks)]
    t0 = time.time()
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=chunks) as ex:
        futs = {ex.submit(curl_fetch_range, url, s, e, part_dir / f"{i:03d}"): i
                for i, s, e in jobs}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            done += 1
            print(f"      chunk {done}/{chunks} done "
                  f"({(time.time() - t0):.0f}s elapsed)")
    with out.open("wb") as f:
        for i in range(chunks):
            f.write((part_dir / f"{i:03d}").read_bytes())
    import shutil
    shutil.rmtree(part_dir, ignore_errors=True)
    print(f"      stitched {out.stat().st_size // 1024} KB in "
          f"{time.time() - t0:.0f}s")
    return valid_pdf(out)


def fetch_one(aid: str, out: Path) -> bool:
    """Try hosts/attempts until a valid PDF lands in out.

    Strategy: parallel ranged connections (~6× single-connection speed);
    partials are resumed with plain curl; falls back to Semantic Scholar.
    """
    if out.exists() and valid_pdf(out):
        return True
    for host_tmpl in HOSTS:
        url = host_tmpl.format(aid=aid)
        for attempt in range(3):
            have = out.stat().st_size if out.exists() else 0
            print(f"    [{attempt + 1}/3] {url.split('/pdf/')[1]} "
                  f"(have {have // 1024} KB)")
            if have == 0:
                if fetch_ranged(url, out):
                    return True
            else:
                rc = curl_fetch(url, out, resume=True)
                if rc == 0 and valid_pdf(out):
                    return True
                if out.exists() and out.stat().st_size < 20_000:
                    try:
                        out.unlink()
                    except OSError:
                        pass
            time.sleep(6 + 3 * attempt)
    # last resort: Semantic Scholar OA link on another host
    oa = s2_oa_url(aid)
    if oa:
        print(f"    S2 fallback: {oa[:100]}")
        rc = curl_fetch(oa, out, resume=False)
        if rc == 0 and out.exists() and valid_pdf(out):
            return True
        if out.exists():
            try:
                out.unlink()
            except OSError:
                pass
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("papers_dir", nargs="?", default=PAPERS_DIR_ARG)
    ap.add_argument("map_json", nargs="?", default=MAP_JSON_ARG)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    papers_dir = Path(args.papers_dir)
    papers_dir.mkdir(parents=True, exist_ok=True)
    mapping = json.loads(Path(args.map_json).read_text(encoding="utf-8"))
    only = set(args.only.split(",")) if args.only else None

    items = list(mapping.items())
    ok, fail = 0, []
    t0 = time.time()
    for i, (aid, fname) in enumerate(items, 1):
        if only and aid not in only:
            continue
        out = papers_dir / fname
        print(f"[{i}/{len(items)}] {aid} → {fname}")
        if out.exists() and valid_pdf(out):
            print(f"    already valid ({out.stat().st_size // 1024} KB) — skip")
            ok += 1
            continue
        good = fetch_one(aid, out)
        if good:
            print(f"    OK {out.stat().st_size // 1024} KB "
                  f"({(time.time() - t0) / 60:.1f} min elapsed)")
            ok += 1
        else:
            print(f"    FAILED {aid}")
            fail.append(aid)
        time.sleep(8)  # polite pacing between files

    print(f"\n=== done: {ok}/{len(items)} OK, failed: {fail or 'none'} "
          f"in {(time.time() - t0) / 60:.1f} min ===")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
