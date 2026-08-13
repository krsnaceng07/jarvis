import csv
from pathlib import Path

infile = Path('parity_reports/embedded_runner_mapping.csv')
outfile = Path('parity_reports/embedded_runner_mapping_classified.csv')

with infile.open('r', encoding='utf-8') as f_in, outfile.open('w', encoding='utf-8', newline='') as f_out:
    reader = csv.DictReader(f_in)
    fieldnames = reader.fieldnames + ['classification']
    writer = csv.DictWriter(f_out, fieldnames=fieldnames)
    writer.writeheader()
    for row in reader:
        oc = row['openclaw_rel']
        if oc.endswith('.test.ts'):
            cls = 'test'
        else:
            cls = 'runtime'
        row['classification'] = cls
        writer.writerow(row)

print('wrote', outfile)
