"""Test whether arXiv throttle is per-connection (parallel ranges help) or per-IP."""
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AID = "2306.03314"  # collab_llm (~600 KB)
URL = f"https://arxiv.org/pdf/{AID}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
TMP = Path(".test_ranges")
TMP.mkdir(exist_ok=True)


def fetch_range(start, end, idx):
    cmd = ["curl", "-sS", "-L", "--fail", "--connect-timeout", "20",
           "--max-time", "150", "-A", UA,
           "-H", f"Range: bytes={start}-{end}",
           "-o", str(TMP / f"{idx:02d}.bin"), URL]
    subprocess.run(cmd, capture_output=True, text=True)


# First get the real content-length (we only know partial size ~600KB)
import urllib.request
req = urllib.request.Request(URL, method="HEAD", headers={"User-Agent": UA})
with urllib.request.urlopen(req, timeout=30) as r:
    total = int(r.headers.get("Content-Length") or 0)
print(f"content-length: {total} bytes")

CHUNKS = 6
span = total // CHUNKS
jobs = []
for i in range(CHUNKS):
    start = i * span
    end = total - 1 if i == CHUNKS - 1 else (i + 1) * span - 1
    jobs.append((start, end, i))

import concurrent.futures
t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=CHUNKS) as ex:
    futs = [ex.submit(fetch_range, s, e, i) for s, e, i in jobs]
    concurrent.futures.wait(futs)
elapsed = time.time() - t0
got = sum(p.stat().st_size for p in TMP.glob("*.bin"))
print(f"after {elapsed:.0f}s: {got / 1e6:.2f} MB aggregate "
      f"({got / elapsed / 1024:.1f} KB/s)")

import shutil
shutil.rmtree(TMP, ignore_errors=True)
