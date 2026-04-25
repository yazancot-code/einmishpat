import fitz

EIN_MISHPAT_GLYPH = 'ÔÈÚ'
SECTION_HDR_SIZE = 11.6
SIZE_TOL = 0.5

path = 'tractate_pdfs/niddah/niddah_02a.pdf'
doc = fitz.open(path)
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
for s in sorted(all_spans, key=lambda s: s['y']):
    font, sz, text = s['font'], s['size'], s['text']
    if 'Vilna' in font and 'Bold' not in font and abs(sz - SECTION_HDR_SIZE) < SIZE_TOL and EIN_MISHPAT_GLYPH in text:
        cx = (s['x0'] + s['x1']) / 2
        print(f'Found: font={font}, size={sz:.2f}, text={text!r}')
        print(f'  center x={cx:.2f}, page_width/2={page_width/2:.2f}')
        if cx < page_width / 2:
            print('  -> left margin (0, 90)')
        else:
            print('  -> right margin (510, 600)')
        break
