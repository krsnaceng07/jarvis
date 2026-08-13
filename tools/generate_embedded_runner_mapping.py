from pathlib import Path
import csv

root = Path('e:/jarvis')
open_dir = root / 'openclaw-main' / 'src' / 'agents' / 'embedded-agent-runner'
jarvis_dir = root / 'src' / 'agents' / 'embedded_agent_runner'

open_files = sorted(p for p in open_dir.rglob('*.ts') if p.is_file())
jarvis_files = {str(p.relative_to(jarvis_dir)).replace('\\','/') for p in jarvis_dir.rglob('*.py') if p.is_file()}

def variants_for(rel_path: str):
    # return possible python candidate relative paths
    v = set()
    p = Path(rel_path)
    parts = p.parts
    fname = parts[-1]
    base = fname[:-3] if fname.endswith('.ts') else fname
    # variant 1: replace - with _ and append .py
    v.add('/'.join(parts[:-1] + (base.replace('-', '_') + '.py',)))
    # variant 2: replace - with _ and . with _
    v.add('/'.join(parts[:-1] + (base.replace('-', '_').replace('.', '_') + '.py',)))
    # variant 3: if top-level file like 'run.something.ts' map to 'run/something.py'
    if '.' in base:
        maybe = base.split('.', 1)[1]
        v.add('run/' + maybe.replace('-', '_') + '.py')
        v.add('run/' + maybe.replace('-', '_').replace('.', '_') + '.py')
    # variant 4: original path with dots replaced
    v.add(rel_path.replace('.ts', '.py').replace('-', '_'))
    # variant 5: just filename in run/ folder
    v.add('run/' + base.replace('-', '_').replace('.', '_') + '.py')
    # variant 6: fallback - the basename only
    v.add(base.replace('-', '_').replace('.', '_') + '.py')
    return v

rows = []
missing = []
for p in open_files:
    rel = str(p.relative_to(open_dir)).replace('\\','/')
    cand = variants_for(rel)
    matched = None
    for c in cand:
        if c in jarvis_files:
            matched = c
            break
    rows.append((rel, ','.join(sorted(cand)), matched or '', 'matched' if matched else 'missing'))
    if not matched:
        missing.append(rel)

# write CSV
out = Path('parity_reports/embedded_runner_mapping.csv')
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['openclaw_rel', 'candidate_variants', 'jarvis_match', 'status'])
    for r in rows:
        writer.writerow(r)

# also write missing list
with open('parity_reports/embedded_runner_missing.txt', 'w', encoding='utf-8') as f:
    for m in missing:
        f.write(m + '\n')

print('wrote', out, 'missing', len(missing))
