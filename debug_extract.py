import fitz
import os

PDF_DIR = 'tractate_pdfs'
TRACTATE = 'niddah'
DAF = 2
AMUD = 'a'

EIN_MISHPAT_GLYPH = 'ÔÈÚ'
SECTION_HDR_SIZE = 11.6
SIZE_TOL = 0.5

fname = f'{TRACTATE}_{DAF:02d}{AMUD}.pdf'
fpath = os.path.join(PDF_DIR, TRACTATE, fname)
print(f'Checking: {fpath}')
print(f'Exists: {os.path.exists(fpath)}')

doc = fitz.open(fpath)
page = doc[0]
page_width = page.rect.width

d = page.get_text('dict')
all_spans = []
for block in d['blocks']:
    if block.get('type') != 0: continue
    for line in block['lines']:
        for span in line['spans']:
            x0, y0, x1, y1 = span['bbox']
            all_spans.append({'y': y0, 'x0': x0, 'x1': x1, 'font': span['font'], 'size': span['size'], 'text': span['text']})

# Find עין משפט
found = False
for s in sorted(all_spans, key=lambda s: s['y']):
    font, sz, text = s['font'], s['size'], s['text']
    if ('Vilna' in font and 'Bold' not in font
            and abs(sz - SECTION_HDR_SIZE) < SIZE_TOL
            and EIN_MISHPAT_GLYPH in text):
        print(f'MATCH: font={font}, size={sz:.2f}, text={text!r}')
        found = True
        break
if not found:
    vilna_fonts = set(s['font'] for s in all_spans if 'Vilna' in s['font'])
    print(f'Vilna fonts on page: {vilna_fonts}')
    vilna_sizes = sorted(set(round(s['size'],1) for s in all_spans if 'Vilna' in s['font']))
    print(f'Vilna sizes on page: {vilna_sizes}')
    # Show first few Vilna spans
    for s in all_spans[:10]:
        if 'Vilna' in s['font']:
            print(f"  Vilna: size={s['size']:.2f}, text={s['text'][:20]!r}")
