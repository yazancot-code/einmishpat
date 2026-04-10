"""
Extract עין משפט נר מצוה references from all מסכת נידה PDFs
and write them to ein_mishpat_niddah.csv.

Columns: daf, amud, entry_letter, local_letters, text

Usage:
    python3 extract_ein_mishpat.py

Expects niddah_pdfs/ directory (run download_niddah.py first).
"""

import csv
import os
import re
import fitz
from collections import defaultdict

# ---------------------------------------------------------------------------
# Font-glyph → Hebrew letter mapping for Vilna,Bold AND FrankRuehl_Shas,Bold
# Both fonts share the same glyph-to-letter codes.
#
# Single-char codes (units glyphs):
#   ‡(8225)=א  ·(183)=ב  ‚(8218)=ג  „(8222)=ד  ‰(8240)=ה
#   Â(194)=ו   Ê(202)=ז  Á(193)=ח   Ë(203)=ט
#
# Tens / standalone codes  (second char in compound → tens digit):
#   È(200)=י   Ù(217)=י  (two glyph variants for yod used on different pages)
#   Î(206)=כ   Ï(207)=ל  Ó(211)=מ   \x0e(14)=נ  (tentative)
#
# Compound entries are stored [UNITS][TENS] in visual LTR order;
# decoding reverses the pair to get logical Hebrew:
#   ‡+È → א+י → reversed → יא (11)
#   Ê+Ë → ז+ט → reversed → טז (16)   (special case: 15,16 use Ë as ט tens)
#   „+Ù → ד+י → reversed → יד (14)
#
# Decorative / ignored glyphs:
#   Ú(218) — suffix that appears after some standalone letters; dropped silently.

ENTRY_LETTER_MAP = {
    '\u2021': 'א',  # ‡  8225 — aleph
    '\u00b7': 'ב',  # ·   183 — bet
    '\u201a': 'ג',  # ‚  8218 — gimel
    '\u201e': 'ד',  # „  8222 — dalet
    '\u2030': 'ה',  # ‰  8240 — heh
    '\u00c2': 'ו',  # Â   194 — vav
    '\u00ca': 'ז',  # Ê   202 — zayin
    '\u00c1': 'ח',  # Á   193 — chet
    '\u00cb': 'ט',  # Ë   203 — tet  (units 9, also tens for טו/טז)
    '\u00c8': 'י',  # È   200 — yod  (10)
    '\u00ce': 'כ',  # Î   206 — kaf  (20)
    '\u00cf': 'ל',  # Ï   207 — lamed (30)
    '\u00d3': 'מ',  # Ó   211 — mem  (40)
    '\x0e':   'נ',  # ^N    14 — nun  (50)
    '\u00d2': 'ס',  # Ò   210 — samech (60)
    '\u00da': 'ע',  # Ú   218 — ayin  (70)
    '\u00d9': 'פ',  # Ù   217 — pe    (80)
    '\u02c6': 'צ',  # ˆ   710 — tsadi (90)
    '\u02dc': 'ק',  # ˜   732 — kof   (100)
}

EIN_MISHPAT_GLYPH = 'ÔÈÚ'   # Vilna-font rendering of "עין"
SECTION_HDR_SIZE  = 11.6    # Vilna non-bold section headers in margin
ENTRY_GLOBAL_SIZE = 8.4     # Vilna,Bold global entry markers
ENTRY_LOCAL_SIZE  = 7.4     # FrankRuehl_Shas,Bold local entry markers
SIZE_TOL          = 0.5     # tolerance for size comparisons

PDF_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "niddah_pdfs")
OUT_CSV  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ein_mishpat_niddah.csv")
LAST_DAF = 73


# ---------------------------------------------------------------------------

def decode_letter(text: str) -> str:
    """
    Map Vilna / FrankRuehl_Shas glyph string → Hebrew letter(s).
    Single-char glyphs map directly.
    Two-char compounds are stored [UNITS][TENS]; we reverse for logical Hebrew.
    Unknown / decorative glyphs are dropped.
    """
    mapped = [ENTRY_LETTER_MAP[ch] for ch in text.strip() if ch in ENTRY_LETTER_MAP]
    if not mapped:
        return ''
    return mapped[0] if len(mapped) == 1 else ''.join(reversed(mapped))


def to_hebrew(raw_visual: str) -> str:
    """
    Convert Rashi_rc_Fix_Shas visual-order text → logical Hebrew Unicode.
    The font stores cp1255 bytes as Latin-1 chars, in visual LTR order.
    Steps: re-decode as cp1255 → reverse word order → reverse each word.
    """
    try:
        converted = raw_visual.encode('latin-1').decode('cp1255')
    except (UnicodeEncodeError, UnicodeDecodeError):
        converted = raw_visual
    words = converted.split(' ')
    return ' '.join(w[::-1] for w in reversed(words))


# ---------------------------------------------------------------------------

def find_ein_mishpat_column(all_spans, page_width):
    """
    Locate the עין משפט נר מצוה section on the page.
    Returns (header_y, col_x0, col_x1) or None if not found.

    Strategy: find a Vilna non-bold span at section-header size that contains
    the characteristic 'ÔÈÚ' glyph sequence, then use its x-position to
    decide which margin column (left ≈ 0–90, right ≈ 510–600) this is in.
    """
    for s in sorted(all_spans, key=lambda s: s['y']):
        font, sz, text = s['font'], s['size'], s['text']
        if ('Vilna' in font and 'Bold' not in font
                and abs(sz - SECTION_HDR_SIZE) < SIZE_TOL
                and EIN_MISHPAT_GLYPH in text):
            cx = (s['x0'] + s['x1']) / 2
            if cx < page_width / 2:
                return s['y'], 0, 90          # left margin ('a' pages)
            else:
                return s['y'], 510, 600       # right margin ('b' pages)
    return None


def find_section_end(all_spans, header_y, col_x0, col_x1):
    """
    Find the y-coordinate where the עין משפט section ends.
    Looks for the NEXT Vilna non-bold section-header-sized span in the same
    margin column that appears more than 20pt below the header.
    """
    for s in sorted(all_spans, key=lambda s: s['y']):
        if s['y'] <= header_y + 20:
            continue
        font, sz, text = s['font'], s['size'], s['text']
        if (s['x0'] >= col_x0 and s['x1'] <= col_x1          # contained in column
                and 'Vilna' in font and 'Bold' not in font
                and abs(sz - SECTION_HDR_SIZE) < SIZE_TOL
                and text.strip()):
            return s['y']
    return float('inf')


def extract_ein_mishpat(pdf_path: str):
    """
    Extract all עין משפט entries from one daf-side PDF.
    Returns a list of {'entry_letter', 'local_letters', 'text'} dicts.
    """
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
                x0, y0, x1, y1 = span["bbox"]
                all_spans.append({
                    'y': y0, 'x0': x0, 'x1': x1,
                    'font': span['font'],
                    'size': span['size'],
                    'text': span['text'],
                })

    all_spans.sort(key=lambda s: (round(s['y']), s['x0']))

    # Find the Ein Mishpat section location
    loc = find_ein_mishpat_column(all_spans, page_width)
    if loc is None:
        doc.close()
        return []

    header_y, col_x0, col_x1 = loc
    end_y = find_section_end(all_spans, header_y, col_x0, col_x1)

    # Collect content spans inside the column, between header and next section.
    # Require BOTH edges within the column (not just overlapping) to exclude
    # main-body text spans that start at the column boundary but extend far right.
    content = [
        s for s in all_spans
        if (s['y'] > header_y + 15 and s['y'] < end_y
            and s['x0'] >= col_x0 and s['x1'] <= col_x1)
    ]

    # Group spans into lines by rounded y
    line_map = defaultdict(list)
    for s in content:
        line_map[round(s['y'])].append(s)

    # -----------------------------------------------------------------------
    # Parse entries.
    # Each global marker (Vilna,Bold ~8.4) starts a new entry.
    # Local markers (FrankRuehl_Shas,Bold ~7.4) belong to the current entry.
    # Rashi_rc_Fix_Shas text is the reference, accumulated until a ':' is found.
    # -----------------------------------------------------------------------
    entries = []
    cur_global = ''
    cur_locals = []
    cur_text_lines = []   # one converted Hebrew string per visual line
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

        # --- Pass 1: global marker (Vilna,Bold ~8.4) -----------------------
        # Collect ALL Vilna,Bold spans at this y before combining.
        # Most compound letters (כ,מ tens) are a single span e.g. '‡Î' → כא.
        # But נ (nun=50) tens is stored as two separate spans at the same y:
        # units span (lower x) + nun span (higher x). Collect, sort by x0,
        # decode each, reverse the list → logical Hebrew [tens, units].
        if y_key not in seen_global_ys:
            global_parts = []
            for s in line_spans:
                font, text = s['font'], s['text'].strip()
                if not text:
                    continue
                if ('Vilna' in font and 'Bold' in font
                        and abs(s['size'] - ENTRY_GLOBAL_SIZE) < SIZE_TOL):
                    letter = decode_letter(text)
                    if letter:
                        global_parts.append((s['x0'], letter))
            if global_parts:
                global_parts.sort(key=lambda p: p[0])
                if len(global_parts) == 1:
                    # Single span: decode_letter already reversed internally
                    combined = global_parts[0][1]
                else:
                    # Multi-span: each decoded letter is a single char;
                    # visual LTR order is [units, tens], reverse → [tens, units]
                    combined = ''.join(reversed([p[1] for p in global_parts]))
                flush_entry()
                cur_global = combined
                seen_global_ys.add(y_key)

        # --- Pass 2: local markers (FrankRuehl_Shas,Bold ~7.4) ------------
        # Allow multiple locals on the same y-line (no y-dedup here).
        for s in line_spans:
            font, text = s['font'], s['text'].strip()
            if not text:
                continue
            if ('FrankRuehl_Shas' in font and 'Bold' in font
                    and abs(s['size'] - ENTRY_LOCAL_SIZE) < SIZE_TOL):
                letter = decode_letter(text)
                if letter:
                    cur_locals.append(letter)

        # --- Pass 3: reference text (Rashi_rc_Fix_Shas) --------------------
        # Collect all Rashi spans on this line in visual (LTR) x-order,
        # join them, then call to_hebrew ONCE so the whole line is correctly
        # reversed from visual order to logical Hebrew order.
        rashi_raw = [s['text'].strip() for s in line_spans
                     if 'Rashi_rc_Fix_Shas' in s['font'] and s['text'].strip()]
        if rashi_raw:
            heb_line = to_hebrew(' '.join(rashi_raw))
            if heb_line.strip():
                cur_text_lines.append(heb_line)

    flush_entry()
    doc.close()
    return entries


# ---------------------------------------------------------------------------
# Post-processing: normalize abbreviations, split sources, resolve שם
# ---------------------------------------------------------------------------

# Split on whitespace immediately before a source marker
_SOURCE_SPLIT_RE = re.compile(r'\s+(?=(?:סמג|טוש"ע|שו"ע)\b)')

# Capture the last מהלכות/מהל' phrase in a Rambam segment.
# Char class includes " and ' so abbreviated masechet names (ק"ש, ת"ת, הטומא') are consumed.
# Lookahead stops before:
#   הל…  (הלכה, הל', הל"X etc.)
#   ה + 0-2 Hebrew letters + gershayim/geresh  (ה"ד, הל"ג, הט"ז, הלכ' …)
#   ו + anything with gershayim/geresh  (וע"ש, ובמ"מ, ופ"ג …)
#   any non-Hebrew, non-quote, non-space  (. : etc.)
#   end of string, or ופ (next chapter)
_MASECHET_RE = re.compile(
    r"""(מהל(?:כות|')\s+[\u05d0-\u05ea "']+?)"""
    r"""(?=\s+(?:הל|ה[\u05d0-\u05ea]{0,2}["']|ו\S*["']|[^\u05d0-\u05ea"' \t\n])|\s*$|\s+ופ)""",
    re.UNICODE,
)
# Capture the last chapter reference immediately before מהל.
# Handles both abbreviated (פ"ג, פט"ו) and full-word (פרק ט"ז) forms.
_CHAPTER_RE = re.compile(r'(פ(?:רק\s+\S+|\S+))(?=\s+מהל)', re.UNICODE)

# Tur section codes
_TUR_CODE_RE = re.compile(r'(?:י"ד|יו"ד|אה"ע|ח"מ|או"ח)')
# Siman references (סי', סימן, or ס י' with optional space)
_SIMAN_RE = re.compile(r'(?:סי\'|סימן|ס\s*י\')\s*\S+')

# Remove ] and [ brackets (including surrounding whitespace)
_BRACKET_RE = re.compile(r'\s*[\]\[]\s*')

# Split Rambam content on ו before a chapter marker (new sub-reference)
_RAMBAM_SUB_SPLIT_RE = re.compile(r'\s+ו(?=פ)')

_ABBREV_MAP: dict | None = None  # module-level cache


def _load_abbreviations() -> dict:
    """Load and cache the abbreviation map from abbreviations.csv."""
    global _ABBREV_MAP
    if _ABBREV_MAP is not None:
        return _ABBREV_MAP
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'abbreviations.csv')
    _ABBREV_MAP = {}
    if not os.path.exists(csv_path):
        return _ABBREV_MAP
    with open(csv_path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            abbrev = row.get('קיצור', '').strip()
            full   = row.get('פירוש מלא', '').strip()
            if not abbrev or not full:
                continue
            # Normalize Hebrew geresh ׳→' and gershayim ״→"
            abbrev = abbrev.replace('\u05f3', "'").replace('\u05f4', '"')
            full   = full.replace('\u05f3', "'").replace('\u05f4', '"')
            _ABBREV_MAP[abbrev] = full
    return _ABBREV_MAP


def _expand_abbreviations(text: str, abbrev_map: dict) -> str:
    """
    Expand all abbreviations in *text* using *abbrev_map*.
    Longer entries are processed first so that e.g. מהל' is expanded before הל'.
    """
    text = text.replace('\u05f3', "'").replace('\u05f4', '"')
    for abbrev, full in sorted(abbrev_map.items(), key=lambda x: -len(x[0])):
        pattern = r'(?:(?<=\s)|^)' + re.escape(abbrev) + r'(?=\s|$)'
        text = re.sub(pattern, full, text, flags=re.MULTILINE)
    return text




def _split_sources(text):
    """
    Split a raw text entry into [(label, content), ...] per halakhic source.
    Labels: 'רמב"ם', 'סמג', 'טור שולחן ערוך'.
    """
    text = text.strip().rstrip(':')
    parts = _SOURCE_SPLIT_RE.split(text)
    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith('סמג'):
            result.append(('סמג', part[3:].strip()))
        elif part.startswith('טוש"ע') or part.startswith('שו"ע'):
            content = re.sub(r'^(?:טוש"ע|שו"ע)\s*', '', part)
            result.append(('טור שולחן ערוך', content))
        else:
            content = re.sub(r"^מיי'\s*", '', part)
            result.append(('רמב"ם', content))
    return result


def _resolve_rambam_shem(content, last_masechet, last_chapter):
    """Replace שם in a Rambam segment with the tracked reference."""
    if 'שם' not in content or not last_masechet:
        return content

    base = (last_chapter + ' ' + last_masechet).strip()

    # פX שם הל… → פX [masechet] הל…  (chapter given before שם)
    content = re.sub(
        r'(פ\S+)\s+שם(?=\s+הל)',
        lambda m: m.group(1) + ' ' + last_masechet,
        content,
    )
    # שם פרק X → פרק X [masechet]  (chapter written out as two tokens: "פרק" + numeral)
    content = re.sub(
        r'שם\s+פרק\s+(\S+)',
        lambda m: 'פרק ' + m.group(1) + ' ' + last_masechet,
        content,
    )
    # שם פX → פX [masechet]  (new chapter follows שם, abbreviated form)
    content = re.sub(
        r'שם\s+(פ\S+)',
        lambda m: m.group(1) + ' ' + last_masechet,
        content,
    )
    # שם הל… → [chapter masechet] הל…
    content = re.sub(r'שם(?=\s+הל)', base, content)
    # שם ו → [base] ו  (addl ref follows with vav)
    content = re.sub(r'שם(?=\s+ו)', base, content)
    # שם at end of segment
    content = re.sub(r'שם$', base, content.strip())

    return content


def _resolve_tur_shem(content, last_tur_code, last_tur_siman):
    """Replace שם in a Tur/SA segment with the tracked reference."""
    if 'שם' not in content or not last_tur_siman:
        return content

    code_siman = (last_tur_code + ' ' + last_tur_siman).strip()

    # [code] שם סעיף → [code] [siman] סעיף
    content = re.sub(
        r'((?:י"ד|יו"ד|אה"ע|ח"מ|או"ח)\s+)שם(?=\s+סעיף)',
        lambda m: m.group(1) + last_tur_siman,
        content,
    )
    # [code] שם (before ו or end) → [code] [siman]
    content = re.sub(
        r'((?:י"ד|יו"ד|אה"ע|ח"מ|או"ח)\s+)שם(?=\s+ו|\s*$)',
        lambda m: m.group(1) + last_tur_siman,
        content,
    )
    # שם וסימן → [code_siman] וסימן
    content = re.sub(r'שם(?=\s+וסימן)', code_siman, content)
    # שם at end
    content = re.sub(r'שם$', code_siman, content.strip())

    return content


def post_process_rows(rows):
    """
    For every row:
      1. Removes ] [ brackets from the raw text.
      2. Replaces מיי' with רמב"ם; expands טוש"ע/שו"ע to טור שולחן ערוך.
      3. Splits sources onto separate lines within the text cell.
      4. Resolves שם references using the last tracked reference per source.
      5. Splits each Rambam segment on ו+chapter into individual lines.
      6. Expands all abbreviations from abbreviations.csv.
    """
    abbrev_map     = _load_abbreviations()
    last_masechet  = ''
    last_chapter   = ''
    last_smag      = ''
    last_tur_code  = ''
    last_tur_siman = ''

    for row in rows:
        # Step 1: remove brackets and collapse extra whitespace
        text = _BRACKET_RE.sub(' ', row['text'])
        text = re.sub(r'\s+', ' ', text).strip()

        parts = _split_sources(text)
        lines = []

        for label, content in parts:
            if label == 'רמב"ם':
                # Split on ו+chapter connectors; resolve שם and inject masechet
                # per-segment so within-entry references resolve correctly.
                seg_masechet = last_masechet
                seg_chapter  = last_chapter
                for seg in _RAMBAM_SUB_SPLIT_RE.split(content):
                    seg = seg.strip()
                    if 'שם' in seg and re.match(r'[פשו]', seg):
                        seg = _resolve_rambam_shem(seg, seg_masechet, seg_chapter)
                    m = _MASECHET_RE.search(seg)
                    if m:
                        seg_masechet = m.group(1)
                    elif seg_masechet and 'מהל' not in seg:
                        # Only inject tracked masechet when the segment has no masechet of its own
                        c = re.match(r'(פ\S+)(.*)', seg, re.DOTALL)
                        if c:
                            seg = f'{c.group(1)} {seg_masechet}{c.group(2)}'
                    cs = _CHAPTER_RE.findall(seg)
                    if cs:
                        seg_chapter = cs[-1]
                    lines.append('רמב"ם ' + _expand_abbreviations(seg, abbrev_map))
                last_masechet = seg_masechet
                last_chapter  = seg_chapter

            elif label == 'סמג':
                if 'שם' in content and last_smag:
                    content = content.replace('שם', last_smag, 1)
                last_smag = content
                lines.append('סמג ' + _expand_abbreviations(content, abbrev_map))

            elif label == 'טור שולחן ערוך':
                content = _resolve_tur_shem(content, last_tur_code, last_tur_siman)
                code_m = _TUR_CODE_RE.search(content)
                if code_m:
                    last_tur_code = code_m.group(0)
                siman_m = _SIMAN_RE.search(content)
                if siman_m:
                    last_tur_siman = siman_m.group(0)
                lines.append('טור שולחן ערוך ' + _expand_abbreviations(content, abbrev_map))

        row['text'] = '\n'.join(lines)
        row['url']  = _build_wikisource_urls(lines)

    return rows


# ---------------------------------------------------------------------------
# Wikisource URL builder
# URL pattern: https://he.wikisource.org/wiki/רמב"ם_הלכות_{masechet}_{chapter}_{halacha}
# Chapter and halacha are bare Hebrew numerals (ג, יז, …) — not the words פרק/הלכה.
# ---------------------------------------------------------------------------

from urllib.parse import quote as _url_quote


def _rambam_to_wikisource(line: str) -> str:
    """
    Convert a fully-expanded Rambam reference line to a he.wikisource.org URL.
    e.g. 'רמב"ם פרק ג מהלכות מטמאי משכב ומושב הלכה ד'
      → 'https://he.wikisource.org/wiki/רמב"ם_הלכות_מטמאי_משכב_ומושב_ג_ד' (encoded)
    """
    if not line.startswith('רמב"ם '):
        return ''
    content = line[6:]  # strip label

    # Chapter numeral (the Hebrew letter(s) after the word פרק)
    ch_m = re.search(r'פרק\s+(\S+)', content)
    if not ch_m:
        return ''
    chapter = ch_m.group(1)

    # Masechet name (the words after מהלכות, stopping before הלכה or end)
    mas_m = re.search(
        r'מהל(?:כות|\')\s+([\u05d0-\u05ea\s]+?)(?=\s+הלכה|\s*$)',
        content, re.UNICODE,
    )
    if not mas_m:
        return ''
    masechet = mas_m.group(1).strip()

    # First halacha numeral (the Hebrew letter(s) after the word הלכה)
    hal_m = re.search(r'הלכה\s+(\S+)', content)
    halacha = hal_m.group(1) if hal_m else ''

    # Build wiki page title:  רמב"ם הלכות {masechet} {chapter} {halacha}
    title = 'רמב"ם הלכות ' + masechet + ' ' + chapter
    if halacha:
        title += ' ' + halacha

    encoded = _url_quote(title.replace(' ', '_'), safe='_')
    return 'https://he.wikisource.org/wiki/' + encoded


# ---------------------------------------------------------------------------
# Wikisource URL builder — סמג
# URL pattern: סמ"ג_לאו_{number}  /  סמ"ג_עשה_{number}
# (singular לאו/עשה, not the plural לאוין/עשין that appears in our text)
# ---------------------------------------------------------------------------

_SMAG_REF_RE = re.compile(r'(לאוין|עשין)\s+(\S+)')
_SMAG_TYPE_MAP = {'לאוין': 'לאו', 'עשין': 'עשה'}


def _smag_to_wikisource(line: str) -> list:
    """
    Convert a סמג reference line to Wikisource URL(s).
    Handles multiple refs on one line (e.g. לאוין קיא ועשין רמג → 2 URLs).
    Embedded Tur/SA text after the commandment numbers is ignored automatically
    because the regex only matches לאוין/עשין patterns.
    """
    if not line.startswith('סמג '):
        return []
    content = line[4:]
    # Fix PDF split artefact: ע שין → עשין
    content = re.sub(r'ע\s+שין', 'עשין', content)

    urls = []
    for m in _SMAG_REF_RE.finditer(content):
        type_s = _SMAG_TYPE_MAP[m.group(1)]
        number = m.group(2)
        title   = f'סמ"ג {type_s} {number}'
        encoded = _url_quote(title.replace(' ', '_'), safe='_')
        urls.append('https://he.wikisource.org/wiki/' + encoded)
    return urls


# ---------------------------------------------------------------------------
# Wikisource URL builder — Tur / Shulchan Aruch
# URL pattern: שולחן_ערוך_{section}_{siman}_{seif}
# ---------------------------------------------------------------------------

# Map any form (expanded or abbreviated) → canonical section name
_TUR_SECTION_MAP = {
    'יורה דעה':  'יורה דעה',
    'אבן העזר':  'אבן העזר',
    'חושן משפט': 'חושן משפט',
    'אורח חיים': 'אורח חיים',
    'י"ד':  'יורה דעה',
    'יו"ד': 'יורה דעה',
    'אה"ע': 'אבן העזר',
    'ח"מ':  'חושן משפט',
    'חו"מ': 'חושן משפט',
    'א"ח':  'אורח חיים',
    'או"ח': 'אורח חיים',
}
_TUR_SECTION_RE = re.compile(
    r'(יורה דעה|אבן העזר|חושן משפט|אורח חיים|י"ד|יו"ד|אה"ע|ח"מ|חו"מ|א"ח|או"ח)'
)


def _parse_tur_refs(text: str) -> list:
    """
    Extract [(siman, seif), …] pairs from Tur content (the part after the section name).
    Handles: single siman, multiple simanim with ו, ranges (עד), missing seif.
    """
    # Normalise ס י' / סי' → סימן so the tokeniser can find them uniformly
    text = re.sub(r"ס\s*י'", 'סימן', text)
    tokens = text.split()
    refs = []
    cur_siman = None
    cur_seif  = None
    i = 0
    while i < len(tokens):
        clean = tokens[i].lstrip('ו')
        if clean == 'סימן' and i + 1 < len(tokens):
            if cur_siman is not None:
                refs.append((cur_siman, cur_seif or ''))
            cur_siman = tokens[i + 1]
            cur_seif  = None
            i += 2
        elif clean == 'סעיף' and i + 1 < len(tokens) and cur_seif is None:
            cur_seif = tokens[i + 1]
            i += 2
        else:
            i += 1
    if cur_siman is not None:
        refs.append((cur_siman, cur_seif or ''))
    return refs


def _tur_to_wikisource(line: str) -> list:
    """
    Convert a טור שולחן ערוך reference line to Wikisource URL(s).
    Returns a list (one URL per siman referenced in the line).
    """
    if not line.startswith('טור שולחן ערוך '):
        return []
    content = line[len('טור שולחן ערוך '):].strip()

    sec_m = _TUR_SECTION_RE.search(content)
    if not sec_m:
        return []
    section      = _TUR_SECTION_MAP[sec_m.group(1)]
    content_rest = content[sec_m.end():].strip()

    urls = []
    for siman, seif in _parse_tur_refs(content_rest):
        title = f'שולחן ערוך {section} {siman}'
        if seif:
            title += f' {seif}'
        encoded = _url_quote(title.replace(' ', '_'), safe='_')
        urls.append('https://he.wikisource.org/wiki/' + encoded)
    return urls


def _build_wikisource_urls(lines: list) -> str:
    """
    Return newline-separated Wikisource URLs for רמב"ם, סמג, and
    טור שולחן ערוך lines in the entry.
    """
    urls = []
    for line in lines:
        if line.startswith('רמב"ם '):
            u = _rambam_to_wikisource(line)
            if u:
                urls.append(u)
        elif line.startswith('סמג '):
            urls.extend(_smag_to_wikisource(line))
        elif line.startswith('טור שולחן ערוך '):
            urls.extend(_tur_to_wikisource(line))
    return '\n'.join(urls)


# ---------------------------------------------------------------------------

def build_page_list():
    pages = []
    for daf in range(2, LAST_DAF + 1):
        for amud in ('a', 'b'):
            if daf == LAST_DAF and amud == 'b':
                continue
            pages.append((daf, amud))
    return pages


def main():
    pages    = build_page_list()
    total    = len(pages)
    all_rows = []

    for i, (daf, amud) in enumerate(pages, start=1):
        fname = f"niddah_{daf:02d}{amud}.pdf"
        fpath = os.path.join(PDF_DIR, fname)
        if not os.path.exists(fpath):
            print(f"[{i}/{total}] {fname}  MISSING")
            continue

        entries = extract_ein_mishpat(fpath)
        marker  = f"{len(entries)} entries" if entries else "no עין משפט"
        print(f"[{i}/{total}] {fname}  {marker}")

        for e in entries:
            all_rows.append({
                'daf':           daf,
                'amud':          amud,
                'entry_letter':  e['entry_letter'],
                'local_letters': e['local_letters'],
                'raw_text':      e['text'],
                'text':          e['text'],
            })

    all_rows = post_process_rows(all_rows)

    with open(OUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(
            f, fieldnames=['daf', 'amud', 'entry_letter', 'local_letters', 'raw_text', 'text', 'url'])
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} entries → {OUT_CSV}")


if __name__ == '__main__':
    main()
