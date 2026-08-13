from pathlib import Path
import csv

root = Path('e:/jarvis')
jarvis_run = root / 'src' / 'agents' / 'embedded_agent_runner' / 'run'
map_file = root / 'parity_reports' / 'embedded_runner_mapping_classified.csv'

if not map_file.exists():
    print('mapping file not found:', map_file)
    raise SystemExit(1)

rows = []
with map_file.open('r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        if r.get('status') == 'missing' and r.get('classification') == 'runtime':
            rows.append(r)

created = []
for r in rows:
    candidates = r.get('candidate_variants','').split(',')
    if not candidates:
        continue
    cand = candidates[0].strip()
    # normalize candidate into a safe relative path
    if cand.startswith('run/'):
        rel = cand[4:]
    else:
        rel = cand
    # sanitize to replace dots in names (except .py extension)
    if rel.count('.') > 1:
        parts = rel.split('.')
        ext = parts[-1]
        name = '_'.join(parts[:-1]) + '.' + ext
        rel = name
    # ensure .py extension
    if not rel.endswith('.py'):
        rel = rel + '.py'
    file_path = jarvis_run / rel
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if file_path.exists():
        continue
    content = f"\"\"\"Stub for {r['openclaw_rel']}\nGenerated to unblock parity work.\n\"\"\"\n\n# TODO: implement parity from OpenClaw\n\ndef _not_implemented():\n    raise NotImplementedError('Stub created for parity work: {r['openclaw_rel']}')\n"
    file_path.write_text(content, encoding='utf-8')
    created.append(str(file_path))

print('created', len(created), 'stubs')
for c in created:
    print(c)
