import json
from pathlib import Path

oc_ext = Path('openclaw-main/extensions')
jv_ext = Path('extensions')

oc_list = sorted([p.name for p in oc_ext.iterdir() if p.is_dir()])
jv_list = sorted([p.name for p in jv_ext.iterdir() if p.is_dir()])

print(f"OpenClaw extension count: {len(oc_list)}")
print(f"JARVIS extension count: {len(jv_list)}")

# check all openclaw extensions
missing = []
for name in oc_list:
    # check exact name or underscore vs hyphen
    alt_name = name.replace('-', '_')
    if name not in jv_list and alt_name not in jv_list:
        missing.append(name)

print(f"\nMissing from JARVIS ({len(missing)}):")
for m in missing:
    print(f"  - {m}")
