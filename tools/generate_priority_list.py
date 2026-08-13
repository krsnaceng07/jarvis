import csv
from pathlib import Path

infile = Path('parity_reports/embedded_runner_mapping_classified.csv')
out = Path('parity_reports/embedded_runner_priority.md')

rows = []
with infile.open('r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

# Filter missing runtime files
missing_runtime = [r for r in rows if r['status']=='missing' and r['classification']=='runtime']

# Prioritization rules (ordered)
priority_keywords = [
    'attempt-prompt',
    'attempt-execution',
    'attempt-session',
    'attempt-stream',
    'attempt-system-prompt',
    'attempt-result',
    'attempt',
    'model',
    'run/',
]

def score(r):
    name = r['openclaw_rel']
    for i,k in enumerate(priority_keywords):
        if k in name:
            return i
    return len(priority_keywords)

sorted_missing = sorted(missing_runtime, key=lambda r: (score(r), r['openclaw_rel']))

out.parent.mkdir(parents=True, exist_ok=True)
with out.open('w', encoding='utf-8') as f:
    f.write('# Prioritized Embedded Runner Parity Gaps (runtime)\n')
    f.write('Generated: 2026-08-08\\n\\n')
    f.write('Focus: prompt lifecycle, execution, session, model-harness\\n\\n')
    f.write('## Top priority files\\n\\n')
    for r in sorted_missing[:200]:
        f.write(f"- {r['openclaw_rel']}  (candidates: {r['candidate_variants']})\n")
    f.write('\n## All missing runtime files\n\n')
    for r in sorted_missing:
        f.write(f"- {r['openclaw_rel']}, status={r['status']}, candidates={r['candidate_variants']}\n")

print('wrote', out)
