"""
Download all tractate Gemara pages as PDFs from shas.org.

Usage:
    python3 download_tractates.py --all          # Download all tractates
    python3 download_tractates.py -t niddah      # Download specific tractate
    python3 download_tractates.py --list         # List available tractates
    python3 download_tractates.py -t shabbos yevamos  # Multiple tractates

No third-party dependencies — uses only stdlib urllib.

PDFs are saved to ./tractate_pdfs/<tractate>/<tractate>_<daf><amud>.pdf
e.g. niddah_02a.pdf, shabbos_17b.pdf, ...

Re-running the script skips already-downloaded files.
"""

import os
import sys
import time
import argparse
import urllib.request
import urllib.error

BASE_URL = "https://www.shas.org/daf-pdf/api/"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tractate_pdfs")
DELAY = 0.5  # seconds between requests
HEADERS = {"User-Agent": "einmishpat-niddah-downloader/1.0"}

# Tractate data: transliterated name -> max daf
# Based on shas.org Daf PDF Viewer API
# https://www.shas.org/daf-pdf/api/api-documentation.html
TRACTATES = {
    'berachos': 64,
    'shabbos': 157,
    'eruvin': 105,
    'pesachim': 121,
    'shekalim': 22,
    'yoma': 88,
    'sukkah': 56,
    'beitzah': 40,
    'rosh-hashanah': 35,
    'taanis': 31,
    'megillah': 32,
    'moed-katan': 29,
    'chagigah': 27,
    'yevamos': 122,
    'kesubos': 112,
    'nedarim': 91,
    'nazir': 66,
    'sotah': 49,
    'gittin': 90,
    'kiddushin': 82,
    'bava-kamma': 119,
    'bava-metzia': 119,
    'bava-basra': 176,
    'sanhedrin': 113,
    'makkos': 24,
    'shevuos': 49,
    'avodah-zarah': 76,
    'horayos': 14,
    'zevachim': 120,
    'menachos': 110,
    'chullin': 142,
    'bechoros': 61,
    'arachin': 34,
    'temurah': 34,
    'kereisos': 28,
    'meilah': 22,
    'tamid': 33,
    'niddah': 73,
}

# Hebrew names for display
TRACTATE_HEBREW = {
    'berachos': 'ברכות',
    'shabbos': 'שבת',
    'eruvin': 'עירובין',
    'pesachim': 'פסחים',
    'shekalim': 'שקלים',
    'yoma': 'יומא',
    'sukkah': 'סוכה',
    'beitzah': 'ביצה',
    'rosh-hashanah': 'ראש השנה',
    'taanis': 'תענית',
    'megillah': 'מגילה',
    'moed-katan': 'מועד קטן',
    'chagigah': 'חגיגה',
    'yevamos': 'יבמות',
    'kesubos': 'כתובות',
    'nedarim': 'נדרים',
    'nazir': 'נזיר',
    'sotah': 'סוטה',
    'gittin': 'גיטין',
    'kiddushin': 'קידושין',
    'bava-kama': 'בבא קמא',
    'bava-metzia': 'בבא מציעא',
    'bava-basra': 'בבא בתרא',
    'sanhedrin': 'סנהדרין',
    'makkos': 'מכות',
    'shevuos': 'שבועות',
    'avodah-zarah': 'עבודה זרה',
    'horayos': 'הוריות',
    'zevachim': 'זבחים',
    'menachos': 'מנחות',
    'chullin': 'חולין',
    'bechoros': 'בכורות',
    'arachin': 'ערכין',
    'temurah': 'תמורה',
    'kereisos': 'כריתות',
    'meilah': 'מעילה',
    'tamid': 'תמיד',
    'niddah': 'נדה',
}


def list_tractates():
    """List all available tractates."""
    print("Available tractates:")
    for name, max_daf in sorted(TRACTATES.items()):
        hebrew = TRACTATE_HEBREW.get(name, '')
        print(f"  {name:20} ({hebrew}) - {max_daf} daf")


def build_pages(tractate):
    """Build list of (daf, amud) for a tractate."""
    max_daf = TRACTATES.get(tractate)
    if not max_daf:
        return []

    pages = []
    for daf in range(2, max_daf + 1):
        for amud in ("a", "b"):
            # Skip last amud if tractate ends on a
            if daf == max_daf and tractate in ('niddah',) and amud == "b":
                continue
            pages.append((daf, amud))
    return pages


def fetch_url(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read()


def download_page(tractate, daf, amud, index, total):
    filename = f"{tractate}_{daf:02d}{amud}.pdf"
    tractate_dir = os.path.join(OUTPUT_DIR, tractate)
    filepath = os.path.join(tractate_dir, filename)

    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        print(f"[{index}/{total}] {filename}  (skipped, already exists)")
        return "skipped"

    url = f"{BASE_URL}?masechta={tractate}&daf={daf}&amud={amud}"
    for attempt in (1, 2):
        try:
            status, data = fetch_url(url)
            if status == 200:
                os.makedirs(tractate_dir, exist_ok=True)
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


def download_tractate(tractate):
    """Download all pages for a single tractate."""
    if tractate not in TRACTATES:
        print(f"Error: Unknown tractate '{tractate}'")
        print(f"Use --list to see available tractates")
        return None

    pages = build_pages(tractate)
    total = len(pages)
    hebrew = TRACTATE_HEBREW.get(tractate, tractate)

    print(f"\n{hebrew} ({tractate}) — {total} pages → {OUTPUT_DIR}/{tractate}/")

    counts = {"ok": 0, "skipped": 0, "failed": 0}

    for i, (daf, amud) in enumerate(pages, start=1):
        result = download_page(tractate, daf, amud, i, total)
        counts[result] += 1
        if result == "ok":
            time.sleep(DELAY)

    print(f"  Done: {counts['ok']} downloaded, {counts['skipped']} skipped, {counts['failed']} failed")
    return counts


def download_all(tractates):
    """Download all specified tractates."""
    total_tractates = len(tractates)
    grand_counts = {"ok": 0, "skipped": 0, "failed": 0}

    for i, tractate in enumerate(tractates, start=1):
        print(f"\n=== [{i}/{total_tractates}] Downloading {tractate} ===")
        counts = download_tractate(tractate)
        if counts:
            for k in grand_counts:
                grand_counts[k] += counts[k]

    print(f"\n{'='*50}")
    print(f"TOTAL: {grand_counts['ok']} downloaded, {grand_counts['skipped']} skipped, {grand_counts['failed']} failed")


def main():
    global OUTPUT_DIR

    parser = argparse.ArgumentParser(
        description="Download Gemara pages as PDFs from shas.org",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '-t', '--tractate',
        nargs='+',
        help="Tractate(s) to download (default: all)"
    )
    parser.add_argument(
        '--list', '--list-tractates',
        action='store_true',
        help="List available tractates and exit"
    )
    parser.add_argument(
        '-o', '--output',
        default=OUTPUT_DIR,
        help=f"Output directory (default: {OUTPUT_DIR})"
    )

    args = parser.parse_args()

    OUTPUT_DIR = args.output

    if args.list:
        list_tractates()
        return

    tractates = args.tractate
    if not tractates:
        # Download all tractates
        tractates = list(TRACTATES.keys())

    print(f"Downloading {len(tractates)} tractate(s): {', '.join(tractates)}")
    download_all(tractates)


if __name__ == "__main__":
    main()
