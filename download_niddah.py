"""
Download all מסכת נידה (Tractate Niddah) Gemara pages as PDFs from shas.org.

Usage:
    python3 download_niddah.py

No third-party dependencies — uses only stdlib urllib.

PDFs are saved to ./niddah_pdfs/niddah_<daf><amud>.pdf
e.g. niddah_02a.pdf, niddah_17b.pdf, ...

Niddah spans daf 2a through 73a (143 pages total).
Re-running the script skips already-downloaded files.
"""

import os
import time
import urllib.request
import urllib.error

BASE_URL = "https://www.shas.org/daf-pdf/api/"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "niddah_pdfs")
DELAY = 0.5  # seconds between requests
HEADERS = {"User-Agent": "einmishpat-niddah-downloader/1.0"}

# Niddah: daf 2–73; tractate ends at 73a so 73b is skipped
LAST_DAF = 73


def build_pages():
    pages = []
    for daf in range(2, LAST_DAF + 1):
        for amud in ("a", "b"):
            if daf == LAST_DAF and amud == "b":
                continue
            pages.append((daf, amud))
    return pages


def fetch_url(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read()


def download_page(daf, amud, index, total):
    filename = f"niddah_{daf:02d}{amud}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        print(f"[{index}/{total}] {filename}  (skipped, already exists)")
        return "skipped"

    url = f"{BASE_URL}?masechta=niddah&daf={daf}&amud={amud}"
    for attempt in (1, 2):
        try:
            status, data = fetch_url(url)
            if status == 200:
                with open(filepath, "wb") as f:
                    f.write(data)
                size_kb = len(data) // 1024
                print(f"[{index}/{total}] {filename}  ({size_kb} KB)")
                return "ok"
            else:
                print(f"[{index}/{total}] {filename}  WARNING: HTTP {status}")
                return "failed"
        except urllib.error.HTTPError as e:
            print(f"[{index}/{total}] {filename}  WARNING: HTTP {e.code}")
            return "failed"
        except (urllib.error.URLError, OSError) as e:
            if attempt == 1:
                print(f"[{index}/{total}] {filename}  retrying after error: {e}")
                time.sleep(1)
            else:
                print(f"[{index}/{total}] {filename}  FAILED: {e}")
                return "failed"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pages = build_pages()
    total = len(pages)
    print(f"מסכת נידה — {total} pages to download → {OUTPUT_DIR}\n")

    counts = {"ok": 0, "skipped": 0, "failed": 0}

    for i, (daf, amud) in enumerate(pages, start=1):
        result = download_page(daf, amud, i, total)
        counts[result] += 1
        if result == "ok":
            time.sleep(DELAY)

    print(f"\nDone.  Downloaded: {counts['ok']}  |  Skipped: {counts['skipped']}  |  Failed: {counts['failed']}")


if __name__ == "__main__":
    main()
