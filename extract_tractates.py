"""
Extract עין משפט נר מצוה references from 2 pages (daf 2a, 2b) of each tractate
and write them to extract_ein_ Mishpat.csv.

Columns: tractate, daf, amud, entry_letter, local_letters, raw_text, text, url

Usage:
    python3 extract_ractates.py
"""

import csv
import os
import re
import fitz
from collections import defaultdict

# Reuse the extraction logic from extract_ ein_mishpat.py
# Font-glyph → Hebrew letter mapping for Vilna, Bold AND FrankRuehl_Shas, Bold
ENTRY_LETTER_MAP = {
    '\u2021': 'א',  # ‡  8225 — aleph
    '\u00b7': 'ב',  # ·   183 — bet
    '\u201a': 'ג',  # ‚  8218 — gimel
    '\u201e': 'ד',  # „  8222 — dalet
    '\u2030': 'ה',  # ‰  8240 — heh
    '\u00c2': 'ו',  # Â   194 — vav
    '\u00ca': 'ז',  # Ê   202 — zayin
    '\u00c1': 'ח',  # Á   193 — chet
    '\u00cb': 'ט',  # Ë   203 — tet
    '\u00c8': 'י',  # È   200 — yod (10)
    '\u00ce': 'כ',  # Î   206 — kaf (20)
    '\u00cf': 'ל',  # Ï   207 — lamed (30)
    '\u00d3': 'מ',  # Ó   211 — mem (40)
    '\x0e':   'נ',  # ^N    14 — nun (50)
    '\u00d2': 'ס',  # Ò   210 — samech (60)
    '\u00da': 'ע',  # Ú   218 — ayin (70)
    '\u00d9': 'פ',  # Ù   217 — pe (80)
    '\u02c6': 'צ',  # ˆ   710 — tsadi (90)
    '\u02dc': 'ק',  # ˜   732 — kof (100)
}

EIN_MISHPAT_GLYPH = 'ÔÈÚ'   # Vilna- font rendering of "עין"
SECTION_HDR_SIZE  = 11.6    # Vilna non-bold section headers in margin
ENTRY_GLOBAL_SIZE = 8.4     # Vilna,Bold global entry markers
ENTRY_LOCAL_SIZE  = 7.4     # FrankRuehl_Shas,Bold local entry markers
SIZE_TOL          = 0.5     # tolerance for size comparisons

PDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tractate_pdfs")
OUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract_ein_mishpat.csv")


# List of all tractates (from download_ Tractates.py)
TRACTATES = [
    'berachos', 'shabbos', 'eruvin', 'pesachim', 'shekalim', 'yoma', 'sukkah',
    'beitzah', 'rosh-hashanah', 'taanis', 'megillah', 'moed-katan', 'chagigah',
    'yevamos', 'kesubos', 'nedarim', 'nazir', 'sotah', 'gittin', 'kiddushin',
    'bava-kamma', 'bava-metzia', 'bava-basra', 'sanhedrin', 'makkos', 'shevuos',
    'avodah-zarah', 'horayos', 'zevachim', 'menachos', 'chullin', 'bechoros',
    'arachin', 'temurah', 'kereisos', 'meilah', 'tamid', 'niddah',
]


def decode_letter(text: str) -> str:
    """Map Vilna / FrankRuehl_Shas glyph string → Hebrew letter(s)."""
    mapped = [ENTRY_LETTER_MAP[ch] for ch in text.strip() if ch in ENTRY_LETTER_MAP]
    if not mapped:
        return ''
    return mapped[0] if len(mapped) == 1 else ''.join(reversed(mapped))


def is_entry_marker_glyph(text: str) -> bool:
    """Check if text consists only of entry letter glyphs (should not be in reference text)."""
    stripped = text.strip()
    if not stripped:
        return False
    return all(ch in ENTRY_LETTER_MAP or ch.isspace() for ch in stripped)


def to_hebrew(raw_visual: str) -> str:
    """Convert Rashi_rc_Fix_Shas visual-order text → logical Hebrew Unicode."""
    try:
        converted = raw_visual. encode('latin-1').decode('cp1255')
    except (UnicodeEncodeError, UnicodeDecodeError):
        converted = raw_visual
    words = converted.split(' ')
    return ' '.join(w[::-1] for w in reversed(words))


def find_ein_mishpat_header(all_spans, page_width):
    """
    Locate the עין משפט נר מצוה header on the page.
    Works with both named fonts (Vilna) and generic TrueType fonts (TTxxxxx).
    Detection is based on: size ~11.6pt, position in margin, contains 'ÔÈÚ' glyph.
    """
    margin_boundary = page_width * 0.20  # margins are ~15% of page width

    for s in sorted(all_spans, key=lambda s: s['y']):
        sz, text = s['size'], s['text']
        # Check size matches header size
        if not abs(sz - SECTION_HDR_SIZE) < SIZE_TOL:
            continue
        # Check for characteristic glyph
        if EIN_MISHPAT_GLYPH not in text:
            continue
        # Check span is in margin (left or right)
        if s['x0'] < margin_boundary:
            return s['y'], s['x0'], True  # left side
        elif s['x0'] > page_width - margin_boundary:
            return s['y'], s['x0'], False  # right side
    return None


def detect_column_bounds(header_x, page_width, is_left_side):
    """
    Define column boundaries based on header position.
    Returns (col_x0, col_x1, marker_x_threshold).
    marker_x_threshold is for distinguishing entry markers from reference text.
    """
    if is_left_side:
        # Left margin: content from page edge to past the header
        col_x0 = 0
        col_x1 = header_x + 35
        # Entry markers are typically at the right edge of the margin column
        # They are ~15-20pt to the right of the header x position
        marker_x_threshold = header_x + 10
    else:
        # Right margin: content from before header to page edge
        # Use wider bounds (50pt) to capture all content
        col_x0 = header_x - 50
        col_x1 = page_width
        marker_x_threshold = header_x - 10

    return col_x0, col_x1, marker_x_threshold


def find_section_end(all_spans, header_y, header_x, is_left_side):
    """
    Find the y-coordinate where the עין משפט section ends.
    Looks for the next section header (size ~11.6pt) in the same margin column.
    Works with any font name.
    """
    # Use more restrictive bounds based on header position
    # Section headers should be within the same x-range as the Ein Mishpat header
    if is_left_side:
        section_x_max = header_x + 20  # headers should be close to original header
    else:
        section_x_min = header_x - 20

    for s in sorted(all_spans, key=lambda s: s['y']):
        # Skip spans too close to header
        if s['y'] <= header_y + 25:
            continue
        sz, text = s['size'], s['text']
        # Must be header-sized and non-empty
        if not (abs(sz - SECTION_HDR_SIZE) < SIZE_TOL and text.strip()):
            continue
        # Check if span is in the actual margin column (not Tosafot/Rashi area)
        if is_left_side:
            if s['x0'] < section_x_max:
                return s['y']
        else:
            if s['x0'] > section_x_min:
                return s['y']
    return float('inf')


def extract_ein_mishpat(pdf_path: str):
    """Extract all עין משפט entries from one daf-side PDF."""
    doc = fitz.open(pdf_path)
    page = doc[0]
    page_width = page.rect.width
    d = page.get_text("dict")

    # Collect ALL spans on page
    all_spans = []
    for block in d["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                x0, y0, x1, _ = span["bbox"]
                all_spans.append({
                    'y': y0, 'x0': x0, 'x1': x1,
                    'font': span['font'],
                    'size': span['size'],
                    'text': span['text'],
                })

    all_spans.sort(key=lambda s: (round(s['y']), s['x0']))

    # Find the Ein Mishpat header
    header_info = find_ein_mishpat_header(all_spans, page_width)
    if header_info is None:
        doc.close()
        return []

    header_y, header_x, is_left_side = header_info

    # Define column bounds based on header position
    col_x0, col_x1, marker_x_threshold = detect_column_bounds(header_x, page_width, is_left_side)

    # Find section end
    end_y = find_section_end(all_spans, header_y, header_x, is_left_side)

    # Collect content spans inside the column.
    content = [
        s for s in all_spans
        if (s['y'] > header_y + 15 and s['y'] < end_y
            and s['x0'] >= col_x0 and s['x0'] <= col_x1)
    ]

    # Group spans into lines by rounded y
    line_map = defaultdict(list)
    for s in content:
        line_map[round(s['y'])].append(s)

    # Check if page uses named fonts (Vilna, FrankRuehl) or generic TT fonts
    has_named_fonts = any(
        s['font'] in ('Vilna,Bold', 'FrankRuehl_Shas,Bold') or 'Rashi' in s['font']
        for s in content
    )

    # Detect marker sizes dynamically from this page's content
    # Global markers use Vilna,Bold (or larger size with TT fonts)
    # Local markers use FrankRuehl_Shas,Bold (or smaller size with TT fonts)
    global_marker_sizes = set()
    local_marker_sizes = set()
    all_marker_sizes = []

    for s in content:
        if not is_entry_marker_glyph(s['text']):
            continue
        sz = round(s['size'], 1)
        if has_named_fonts:
            if s['font'] == 'Vilna,Bold' and s['size'] < 12:
                global_marker_sizes.add(sz)
            elif s['font'] == 'FrankRuehl_Shas,Bold':
                local_marker_sizes.add(sz)
        else:
            # For TT fonts, collect all marker sizes to determine threshold
            if 7.0 < s['size'] < 10.0 and s['x0'] > marker_x_threshold - 15:
                all_marker_sizes.append((sz, s['x0']))

    # For TT fonts, distinguish global vs local by position (global is further right)
    if not has_named_fonts and all_marker_sizes:
        # Global markers are positioned further right than local markers
        # Find the size that appears at the rightmost positions
        sizes_by_max_x = {}
        for sz, x in all_marker_sizes:
            if sz not in sizes_by_max_x or x > sizes_by_max_x[sz]:
                sizes_by_max_x[sz] = x
        # The size with highest x position is likely global markers
        if sizes_by_max_x:
            sorted_sizes = sorted(sizes_by_max_x.items(), key=lambda p: p[1], reverse=True)
            global_marker_sizes.add(sorted_sizes[0][0])
            for sz, _ in sorted_sizes[1:]:
                local_marker_sizes.add(sz)

    # Determine size thresholds based on detected markers
    if global_marker_sizes:
        global_size_min = min(global_marker_sizes) - 0.3
        global_size_max = max(global_marker_sizes) + 0.3
    else:
        global_size_min, global_size_max = 7.8, 10.0  # fallback

    if local_marker_sizes:
        local_size_min = min(local_marker_sizes) - 0.3
        local_size_max = max(local_marker_sizes) + 0.3
    else:
        local_size_min, local_size_max = 7.0, 8.5  # fallback

    # Reference text size: use Rashi font sizes or small TT font sizes
    ref_text_sizes = set()
    for s in content:
        if not is_entry_marker_glyph(s['text']) and s['x0'] < marker_x_threshold - 5:
            if has_named_fonts:
                if 'Rashi' in s['font']:
                    ref_text_sizes.add(round(s['size'], 1))
            else:
                # For TT fonts, reference text is typically 7.0-7.8pt
                if 6.5 < s['size'] < 8.0:
                    ref_text_sizes.add(round(s['size'], 1))
    if ref_text_sizes:
        ref_size_min = min(ref_text_sizes) - 0.2
        ref_size_max = max(ref_text_sizes) + 0.2
    else:
        ref_size_min, ref_size_max = 6.9, 7.9  # fallback

    # Parse entries
    entries = []
    cur_global = ''
    cur_locals = []
    cur_text_lines = []
    seen_global_ys = set()

    def flush_entry():
        nonlocal cur_global, cur_locals, cur_text_lines
        raw_text = ' '.join(cur_text_lines).strip()
        if ':' in raw_text:
            raw_text = raw_text[:raw_text.index(':') + 1]
        if cur_global or cur_locals or raw_text:
            entries.append({
                'entry_letter':  cur_global,
                'local_letters': ' '.join(cur_locals),
                'text':          raw_text,
            })
        cur_global     = ''
        cur_locals     = []
        cur_text_lines = []

    for y_key in sorted(line_map.keys()):
        line_spans = sorted(line_map[y_key], key=lambda s: s['x0'])

        # Pass 1: global marker (Vilna,Bold font or size-based for TT fonts)
        if y_key not in seen_global_ys:
            global_parts = []
            for s in line_spans:
                text = s['text'].strip()
                if not text or not is_entry_marker_glyph(text):
                    continue
                # Detect by font name OR by size range for TT fonts
                is_global = False
                if has_named_fonts:
                    is_global = (s['font'] == 'Vilna,Bold'
                                 and global_size_min < s['size'] < global_size_max)
                else:
                    # For TT fonts: size in global range and positioned far right
                    is_global = (global_size_min < s['size'] < global_size_max
                                 and s['x0'] > marker_x_threshold)
                if is_global:
                    letter = decode_letter(text)
                    if letter:
                        global_parts.append((s['x0'], letter))
            if global_parts:
                global_parts.sort(key=lambda p: p[0])
                if len(global_parts) == 1:
                    combined = global_parts[0][1]
                else:
                    combined = ''.join(reversed([p[1] for p in global_parts]))
                flush_entry()
                cur_global = combined
                seen_global_ys.add(y_key)

        # Pass 2: local markers (FrankRuehl_Shas,Bold font or size-based for TT fonts)
        for s in line_spans:
            text = s['text'].strip()
            if not text or not is_entry_marker_glyph(text):
                continue
            # Detect by font name OR by size range for TT fonts
            is_local = False
            if has_named_fonts:
                is_local = (s['font'] == 'FrankRuehl_Shas,Bold'
                            and local_size_min < s['size'] < local_size_max)
            else:
                # For TT fonts: size in local range
                is_local = (local_size_min < s['size'] < local_size_max
                            and s['x0'] > marker_x_threshold - 10)
            if is_local:
                letter = decode_letter(text)
                if letter:
                    cur_locals.append(letter)

        # Pass 3: reference text (Rashi font or small TT fonts, left side of margin)
        # Exclude spans that are only entry marker glyphs
        if has_named_fonts:
            rashi_raw = [s['text'].strip() for s in line_spans
                         if 'Rashi' in s['font'] and ref_size_min < s['size'] < ref_size_max
                         and s['x0'] < marker_x_threshold - 5
                         and s['text'].strip() and not is_entry_marker_glyph(s['text'])]
        else:
            rashi_raw = [s['text'].strip() for s in line_spans
                         if ref_size_min < s['size'] < ref_size_max
                         and s['x0'] < marker_x_threshold - 5
                         and s['text'].strip() and not is_entry_marker_glyph(s['text'])]
        if rashi_raw:
            heb_line = to_hebrew(' '.join(rashi_raw))
            if heb_line.strip():
                cur_text_lines.append(heb_line)

    flush_entry()
    doc.close()
    return entries


# Post-processing functions (abbreviated for brevity - same as extract_ ein_mishpat.py)
_SOURCE_SPLIT_RE = re.compile(r'\s+(?=(?:סמג|טוש"ע|שו"ע)\b)')
_BRACKET_RE = re.compile(r'\s*[\]\[]\s*')

def post_process_rows(rows):
    """Post-process rows - simplified version."""
    for row in rows:
        # Remove brackets
        text = _BRACKET_RE.sub(' ', row['text'])
        text = re.sub(r'\s+', ' ', text).strip()

        # Split sources
        parts = _SOURCE_SPLIT_RE.split(text)
        lines = []

        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part.startswith('סמג'):
                lines.append(part)
            elif part.startswith('טוש"ע') or part.startswith('שו"ע'):
                content = re.sub(r'^(?:טוש"ע|שו"ע)\s*', '', part)
                lines.append('טור שולחן ערוך ' + content)
            else:
                content = re.sub(r"^מיי'\s*", '', part)
                lines.append('רמב"ם ' + content)

        row['text'] = '\n'.join(lines)

    return rows


def build_wikisource_urls() -> str:
    """Build placeholder URLs (simplified)."""
    return ''


def get_all_pdfs(tractate: str) -> list:
    """Get all PDF files for a tractate, sorted by daf number and amud."""
    tractate_dir = os.path.join(PDF_DIR, tractate)
    if not os.path.isdir(tractate_dir):
        return []

    pdfs = []
    for fname in os.listdir(tractate_dir):
        if not fname.endswith('.pdf'):
            continue
        # Parse filename: tractate_XXy.pdf where XX is daf number, y is amud (a/b)
        base = fname[:-4]  # remove .pdf
        parts = base.rsplit('_', 1)
        if len(parts) != 2:
            continue
        daf_str = parts[1]
        if len(daf_str) < 2:
            continue
        try:
            daf = int(daf_str[:-1])
            amud = daf_str[-1]
            if amud in ('a', 'b'):
                pdfs.append((daf, amud, fname))
        except ValueError:
            continue

    # Sort by daf number, then amud (a before b)
    pdfs.sort(key=lambda x: (x[0], x[1]))
    return pdfs


def main():
    all_rows = []
    total_tractates = len(TRACTATES)

    for i, tractate in enumerate(TRACTATES, start=1):
        # Get all PDF files for this tractate
        pdfs = get_all_pdfs(tractate)
        if not pdfs:
            print(f"[{i}/{total_tractates}] {tractate}: no PDFs found")
            continue

        tractate_entries = 0
        for daf, amud, fname in pdfs:
            fpath = os.path.join(PDF_DIR, tractate, fname)

            entries = extract_ein_mishpat(fpath)
            if entries:
                tractate_entries += len(entries)
                for e in entries:
                    all_rows.append({
                        'tractate':       tractate,
                        'daf':           daf,
                        'amud':          amud,
                        'entry_letter':  e['entry_letter'],
                        'local_letters': e['local_letters'],
                        'raw_text':      e['text'],
                        'text':          e['text'],
                        'url':           '',
                    })

        print(f"[{i}/{total_tractates}] {tractate}: {len(pdfs)} pages, {tractate_entries} entries")

    all_rows = post_process_rows(all_rows)

    # Write CSV
    with open(OUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(
            f, fieldnames=['tractate', 'daf', 'amud', 'entry_letter', 'local_letters', 'raw_text', 'text', 'url'])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} entries → {OUT_CSV}")


if __name__ == '__main__':
    main()
