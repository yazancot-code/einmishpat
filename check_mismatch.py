import csv
import sys

def count_lines_in_field(field):
    """Count the number of lines in a field (separated by \n)"""
    if not field or field.strip() == '':
        return 0
    return len(field.split('\n'))

def main():
    filename = '/Users/azancoty/azancotycoding/einmishpatnetmitsvah/ein_mishpat_niddah.csv'

    mismatch_count = 0
    total_rows = 0

    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header

        for row_num, row in enumerate(reader, start=2):
            total_rows += 1

            if len(row) < 7:
                # Malformed row
                mismatch_count += 1
                continue

            text_field = row[5]   # text column (0-indexed: 5)
            url_field = row[6]    # url column (0-indexed: 6)

            text_lines = count_lines_in_field(text_field)
            url_lines = count_lines_in_field(url_field)

            if text_lines != url_lines:
                mismatch_count += 1
                # Optional: print details for first few mismatches
                if mismatch_count <= 5:
                    print(f"Row {row_num}: TEXT lines={text_lines}, URL lines={url_lines}")
                    print(f"  TEXT: {repr(text_field[:100])}")
                    print(f"  URL: {repr(url_field[:100])}")
                    print()

    print(f"Total rows processed: {total_rows}")
    print(f"Mismatches (TEXT lines ≠ URL lines): {mismatch_count}")

if __name__ == '__main__':
    main()