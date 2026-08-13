from pathlib import Path
import csv

jarvis_run = Path('src/agents/embedded_agent_runner/run')
map_file = Path('parity_reports/embedded_runner_mapping_classified.csv')

rows = []
with map_file.open('r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        if r['status']=='missing' and r['classification']=='runtime':
            rows.append(r)

# pick top 10
selected = rows[:10]
created = []
for r in selected:
    cand = r['candidate_variants'].split(',')[0]
    cand = cand.strip()
    if not cand.startswith('run/'):
        cand_path = jarvis_run / cand
    else:
        cand_path = Path('src/agents/embedded_agent_runner') / cand
    cand_path.parent.mkdir(parents=True, exist_ok=True)
    if not cand_path.exists():
        content = f"\"\"\"Stub for {r['openclaw_rel']}\nGenerated to unblock parity work.\n\"\"\"\n\n# TODO: implement parity from OpenClaw\n\ndef _not_implemented():\n    raise NotImplementedError('Stub created for parity work: {r['openclaw_rel']}')\n"
        cand_path.write_text(content, encoding='utf-8')
        created.append(str(cand_path))

print('created', len(created), 'stubs')
for c in created:
    print(c)
