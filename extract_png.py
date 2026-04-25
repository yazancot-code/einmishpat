"""
Extract עין משפט נר מצוה references from a PNG image using OCR.

This script uses pytesseract for Hebrew OCR, then applies similar
parsing logic to extract_tractates.py to identify entry markers
and reference text.

IMPORTANT: Standard tesseract Hebrew OCR does NOT recognize Rashi script well.
Rashi is a semi-cursive font used in Talmudic commentaries that differs from
standard Hebrew block letters. For better Rashi OCR, consider:
  1. Using Google Cloud Vision API (better Hebrew/Rashi support)
  2. Using a trained Rashi-specific model (e.g., from DICTA or similar projects)
  3. Using eScriptorium with a Rashi-trained model

Usage:
    python3 extract_png.py [image_path] [options]

    Options:
      --preprocess    Apply image preprocessing to improve OCR quality
      --debug         Show detailed debug output including bounding boxes
      --legacy        Use tesseract legacy engine (sometimes better for unusual fonts)
      --yiddish       Try Yiddish language model (closer to Rashi letterforms)
      --google        Use Google Cloud Vision API (RECOMMENDED for Rashi script)
                      Requires: pip install google-cloud-vision
                      And: export GOOGLE_APPLICATION_CREDENTIALS=/path/to/creds.json

    If no image_path is provided, defaults to ein_mishpat_section.png

Requirements:
    pip install pytesseract pillow opencv-python numpy
    brew install tesseract tesseract-lang  # for Hebrew support on macOS
"""

import sys
import os
import re
import csv
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

try:
    import pytesseract
except ImportError:
    print("Error: pytesseract not installed. Run: pip install pytesseract")
    print("Also install tesseract: brew install tesseract tesseract-lang")
    sys.exit(1)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from google.cloud import vision
    HAS_GOOGLE_VISION = True
except ImportError:
    HAS_GOOGLE_VISION = False

# Hebrew letter values for parsing entry markers
HEBREW_LETTERS = 'אבגדהוזחטיכלמנסעפצקרשת'
HEBREW_LETTER_VALUES = {
    'א': 1, 'ב': 2, 'ג': 3, 'ד': 4, 'ה': 5, 'ו': 6, 'ז': 7, 'ח': 8, 'ט': 9,
    'י': 10, 'כ': 20, 'ל': 30, 'מ': 40, 'נ': 50, 'ס': 60, 'ע': 70, 'פ': 80,
    'צ': 90, 'ק': 100, 'ר': 200, 'ש': 300, 'ת': 400,
}

# Patterns for identifying entry markers vs reference text
ENTRY_MARKER_PATTERN = re.compile(r'^[אבגדהוזחטיכלמנסעפצקרשת]{1,3}\s')
GLOBAL_MARKER_PATTERN = re.compile(r'^([אבגדהוזחטיכלמנסעפצקרשת]{1,2})\s+([אבגדהוזחטיכלמנסעפצקרשת])\s')

# Source patterns (same as extract_tractates.py)
_SOURCE_SPLIT_RE = re.compile(r'\s+(?=(?:סמג|טוש"ע|שו"ע)\b)')
_BRACKET_RE = re.compile(r'\s*[\]\[]\s*')

# Pattern to identify reference lines (start with entry marker like "יח א")
REFERENCE_LINE_PATTERN = re.compile(
    r'^([אבגדהוזחטיכלמנסעפצקרשת]{1,3})\s+([אבגדהוזחטיכלמנסעפצקרשת])\s+(.+)$'
)

# Pattern for continuation lines (no entry marker)
CONTINUATION_PATTERN = re.compile(r'^[^אבגדהוזחטיכלמנסעפצקרשת]|^[א-ת]{4,}')


def preprocess_image(image_path: str) -> Image.Image:
    """
    Preprocess image to improve OCR quality.
    - Convert to grayscale
    - Increase contrast
    - Apply thresholding
    - Remove noise
    """
    img = Image.open(image_path)

    # Convert to grayscale
    img = img.convert('L')

    # Increase contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)

    # Sharpen
    img = img.filter(ImageFilter.SHARPEN)

    if HAS_CV2:
        # Use OpenCV for better preprocessing
        img_array = np.array(img)

        # Apply adaptive thresholding
        img_array = cv2.adaptiveThreshold(
            img_array, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Denoise
        img_array = cv2.fastNlMeansDenoising(img_array, h=10)

        img = Image.fromarray(img_array)

    return img


def ocr_google_vision(image_path: str) -> str:
    """
    Perform OCR using Google Cloud Vision API.
    Has much better support for Hebrew and Rashi script.

    Requires:
        pip install google-cloud-vision
        export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
    """
    if not HAS_GOOGLE_VISION:
        raise ImportError("google-cloud-vision not installed. Run: pip install google-cloud-vision")

    client = vision.ImageAnnotatorClient()

    with open(image_path, 'rb') as f:
        content = f.read()

    image = vision.Image(content=content)

    # Use document_text_detection for better structured text recognition
    response = client.document_text_detection(
        image=image,
        image_context={'language_hints': ['he']}  # Hebrew hint
    )

    if response.error.message:
        raise Exception(f"Google Vision API error: {response.error.message}")

    return response.full_text_annotation.text


def ocr_image(image_path: str, preprocess: bool = False, legacy: bool = False,
              lang: str = 'heb', use_google: bool = False) -> str:
    """
    Perform OCR on image to extract Hebrew text.
    Returns the raw OCR text.

    Args:
        image_path: Path to image file
        preprocess: Apply image preprocessing
        legacy: Use tesseract legacy engine (OEM 0) instead of LSTM (OEM 3)
        lang: Language model to use ('heb', 'yid', 'heb+yid')
        use_google: Use Google Cloud Vision API instead of tesseract
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Google Cloud Vision - much better for Rashi script
    if use_google:
        return ocr_google_vision(image_path)

    if preprocess:
        img = preprocess_image(image_path)
    else:
        img = Image.open(image_path)

    # Configure tesseract for Hebrew
    # PSM modes:
    #   3 = Fully automatic page segmentation
    #   4 = Assume a single column of text of variable sizes
    #   6 = Assume a single uniform block of text
    #  11 = Sparse text - find as much text as possible
    #  12 = Sparse text with OSD
    # OEM modes:
    #   0 = Legacy engine only (sometimes better for unusual fonts)
    #   1 = Neural nets LSTM engine only
    #   3 = Default, based on what is available

    oem = 0 if legacy else 3
    custom_config = f'--oem {oem} --psm 4 -l {lang}'

    try:
        text = pytesseract.image_to_string(img, config=custom_config)
    except pytesseract.TesseractError as e:
        if legacy and 'legacy' in str(e).lower():
            print(f"Warning: Legacy engine not available for {lang}, falling back to LSTM...")
            custom_config = f'--oem 3 --psm 4 -l {lang}'
            text = pytesseract.image_to_string(img, config=custom_config)
        else:
            raise
    return text


def ocr_image_with_boxes(image_path: str) -> list:
    """
    Perform OCR and get bounding box data for each text element.
    Returns list of dicts with text, position, and confidence.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    img = Image.open(image_path)

    # Get detailed OCR data
    custom_config = r'--oem 3 --psm 4 -l heb'
    data = pytesseract.image_to_data(img, config=custom_config, output_type=pytesseract.Output.DICT)

    results = []
    n_boxes = len(data['text'])

    for i in range(n_boxes):
        text = data['text'][i].strip()
        if text:
            results.append({
                'text': text,
                'x': data['left'][i],
                'y': data['top'][i],
                'width': data['width'][i],
                'height': data['height'][i],
                'conf': data['conf'][i],
                'line_num': data['line_num'][i],
                'block_num': data['block_num'][i],
            })

    return results


def parse_entry_line(line: str) -> dict | None:
    """
    Parse a line that starts with an entry marker.
    Returns dict with entry_letter, local_letters, and text.
    """
    line = line.strip()
    if not line:
        return None

    # Try to match pattern like "יח א מיי' פ"ח מהלכות..."
    match = REFERENCE_LINE_PATTERN.match(line)
    if match:
        return {
            'entry_letter': match.group(1),
            'local_letters': match.group(2),
            'text': match.group(3).strip(),
        }

    # Try simpler pattern - just entry letter at start
    simple_match = re.match(r'^([אבגדהוזחטיכלמנסעפצקרשת]{1,3})\s+(.+)$', line)
    if simple_match:
        rest = simple_match.group(2)
        # Check if next char is also a single letter (local marker)
        local_match = re.match(r'^([אבגדהוזחטיכלמנסעפצקרשת])\s+(.+)$', rest)
        if local_match:
            return {
                'entry_letter': simple_match.group(1),
                'local_letters': local_match.group(1),
                'text': local_match.group(2).strip(),
            }
        else:
            return {
                'entry_letter': simple_match.group(1),
                'local_letters': '',
                'text': rest.strip(),
            }

    return None


def is_header_line(line: str) -> bool:
    """Check if line is a header like 'עין משפט נר מצוה'."""
    return 'עין משפט' in line or 'נר מצוה' in line


def parse_ocr_text(raw_text: str) -> list:
    """
    Parse raw OCR text into structured entries.
    Returns list of dicts with entry_letter, local_letters, raw_text, text.
    """
    lines = raw_text.strip().split('\n')
    entries = []
    current_entry = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip header lines
        if is_header_line(line):
            continue

        # Try to parse as new entry
        parsed = parse_entry_line(line)
        if parsed:
            # Save previous entry
            if current_entry:
                entries.append(current_entry)
            current_entry = {
                'entry_letter': parsed['entry_letter'],
                'local_letters': parsed['local_letters'],
                'raw_text': parsed['text'],
                'text': parsed['text'],
            }
        elif current_entry:
            # Continuation of previous entry
            current_entry['raw_text'] += ' ' + line
            current_entry['text'] += ' ' + line

    # Don't forget last entry
    if current_entry:
        entries.append(current_entry)

    return entries


def post_process_entries(entries: list) -> list:
    """
    Post-process entries - same logic as extract_tractates.py.
    Normalizes source references.
    """
    for entry in entries:
        # Remove brackets
        text = _BRACKET_RE.sub(' ', entry['text'])
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

        entry['text'] = '\n'.join(lines) if lines else text

    return entries


def extract_from_png(image_path: str, verbose: bool = True, preprocess: bool = False,
                      debug: bool = False, legacy: bool = False, lang: str = 'heb',
                      use_google: bool = False) -> list:
    """
    Main extraction function.
    Returns list of entries extracted from the image.
    """
    if verbose:
        print(f"Processing: {image_path}")
        if use_google:
            print("OCR engine: Google Cloud Vision (recommended for Rashi)")
        else:
            print(f"OCR engine: Tesseract (lang={lang}, legacy={legacy}, preprocess={preprocess})")
            print("\nNOTE: Rashi script may not be recognized well by standard tesseract.")
            print("      Use --google for better results (requires Google Cloud credentials).\n")

    # Perform OCR
    raw_text = ocr_image(image_path, preprocess=preprocess, legacy=legacy, lang=lang, use_google=use_google)

    if verbose:
        print("\n--- Raw OCR Output ---")
        print(raw_text)
        print("--- End OCR Output ---\n")

    if debug:
        # Also get bounding box data
        boxes = ocr_image_with_boxes(image_path)
        print("\n--- OCR Bounding Boxes ---")
        for box in boxes:
            print(f"  Line {box['line_num']}: '{box['text']}' at ({box['x']}, {box['y']}) conf={box['conf']}")
        print("--- End Bounding Boxes ---\n")

    # Parse into entries
    entries = parse_ocr_text(raw_text)

    if verbose:
        print(f"Found {len(entries)} raw entries")

    # Post-process
    entries = post_process_entries(entries)

    return entries


def save_to_csv(entries: list, output_path: str):
    """Save entries to CSV file."""
    fieldnames = ['entry_letter', 'local_letters', 'raw_text', 'text']

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(entries)

    print(f"Wrote {len(entries)} entries to {output_path}")


def main():
    # Default image path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_image = os.path.join(script_dir, 'ein_mishpat_section.png')

    # Parse command line arguments
    args = sys.argv[1:]
    preprocess = '--preprocess' in args
    debug = '--debug' in args
    legacy = '--legacy' in args
    use_yiddish = '--yiddish' in args
    use_google = '--google' in args

    # Determine language
    lang = 'yid' if use_yiddish else 'heb'

    # Remove flags from args
    args = [a for a in args if not a.startswith('--')]

    # Get image path from command line or use default
    if args:
        image_path = args[0]
    else:
        image_path = default_image

    # Extract entries
    entries = extract_from_png(
        image_path,
        verbose=True,
        preprocess=preprocess,
        debug=debug,
        legacy=legacy,
        lang=lang,
        use_google=use_google
    )

    # Print results
    print("\n=== Extracted Entries ===")
    for i, entry in enumerate(entries, 1):
        print(f"\n--- Entry {i} ---")
        print(f"Entry letter: {entry['entry_letter']}")
        print(f"Local letters: {entry['local_letters']}")
        print(f"Text: {entry['text']}")

    # Save to CSV
    output_csv = os.path.splitext(image_path)[0] + '_extracted.csv'
    save_to_csv(entries, output_csv)


if __name__ == '__main__':
    main()
