import os
from collections import Counter
skip_dirs = {'.venv','openclaw-main','.git','build','dist'}
matches = Counter()
for root, dirs, files in os.walk('.'):
    # skip unwanted dirs
    parts = set(root.split(os.sep))
    if parts & skip_dirs:
        continue
    for fn in files:
        if fn.endswith('.py'):
            path = os.path.join(root, fn)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    txt = f.read()
            except Exception:
                continue
            cnt = txt.count('NotImplementedError(')
            if cnt > 0:
                matches[path] = cnt
for p, c in matches.most_common(50):
    print(f"{c:3d}  {p}")
print('\nTotal files with NotImplementedError:', len(matches))
