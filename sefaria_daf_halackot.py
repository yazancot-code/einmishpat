import json
import urllib.request
import re
from collections import defaultdict


def normalize(s):
    """Normalize string for comparison"""
    return str(s).lower()


def clean_hebrew(text):
    """Remove HTML tags from Sefaria text"""
    if not text:
        return text
    return re.sub(r'<[^>]+>', '', text).strip()


TREF = "Pesachim.2b"
TARGET_DAF = normalize(TREF.replace(".", " "))

TEXT_URL = f"https://www.sefaria.org/api/v3/texts/{TREF}?version=source&return_format=text_only"
LINKS_URL = f"https://www.sefaria.org/api/links/{TREF}?category=Halakhah"


BOOK_PATTERNS = {
    "Rambam": ["mishneh torah", "rambam"],        # was "Mishneh Torah"
    "Tur": ["tur", "arbaah turim"],
    "SMaG": ["sefer mitzvot gadol", "smag"],       # was "Sefer Mitzvot Gadol"
    "Shulchan Aruch": ["shulchan aruch", "shulchan arukh", "orach chayim"]
}

def fetch_json(url):
    """Fetch JSON data from a URL using urllib"""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def fetch_text():
    """Fetch the main Talmud text"""
    print("Fetching Talmud text...")
    data = fetch_json(TEXT_URL)
    if "versions" in data and len(data["versions"]) > 0:
        text = data["versions"][0].get("text", [])
        print(f"Found {len(text)} text segments")
        return text
    else:
        print("Warning: No text versions found")
        return []

def fetch_links():
    """Fetch Halacha links for the text"""
    print("Fetching Halacha links...")
    try:
        return fetch_json(LINKS_URL)
    except Exception as e:
        print(f"Warning: Failed to fetch links: {e}")
        return []

def normalize(s):
    """Normalize string for comparison"""
    return str(s).lower()

def identify_book(ref):
    """Identify which book a reference belongs to"""
    ref_l = normalize(ref)
    for book, patterns in BOOK_PATTERNS.items():
        for p in patterns:
            if p in ref_l:
                return book
                print("book found")
    return None

def extract_segment(ref):
    """Extract segment/page number from a reference"""
    try:
        return int(ref.split(":")[-1])
    except:
        return None


def build_mapping(links):
    """Build mapping of segments to their Halacha references"""
    mapping = defaultdict(lambda: defaultdict(list))

    for link in links:
        if link.get("category") != "Halakhah":
            continue

        anchor_ref = link.get("anchorRef", "")
        source_ref = link.get("sourceRef", "")
        source_he_ref = link.get("sourceHeRef", source_ref)
        book_part = source_ref.split(",")[0] if source_ref else source_ref

        if TARGET_DAF not in normalize(anchor_ref):
            continue

        seg = extract_segment(anchor_ref)
        if seg is None:
            continue

        book = identify_book(book_part)
        if not book:
            continue

        # Extract Hebrew text from "he" field only and clean HTML tags
        he = link.get("he")
        if isinstance(he, list):
            halacha_text = clean_hebrew(" ".join(he))
        elif isinstance(he, str):
            halacha_text = clean_hebrew(he)
        else:
            halacha_text = None

        mapping[seg][book].append({
            "ref": source_he_ref,
            "text": halacha_text
        })

    return mapping

def main():
    print("Starting extraction...")
    text = fetch_text()
    links = fetch_links()
    mapping = build_mapping(links)

    print(f"Total links fetched: {len(links)}")
    print(f"Halakhah links processed: {sum(len(v) for d in mapping.values() for v in d.values())}")

    for i, segment_text in enumerate(text, start=1):
        print(f"\n--- Segment {i} ---")
        print(segment_text)

        if i in mapping:
            for book, items in mapping[i].items():
                print(f"\n  {book}:")
                for item in items:
                    print(f"    - {item['ref']}")
                    if item["text"]:
                        print(f"      TEXT: {item['text'][:2000]}...")

if __name__ == "__main__":
    main()