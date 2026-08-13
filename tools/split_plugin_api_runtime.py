from pathlib import Path

root = Path('packages/plugin_sdk/src/jarvis_sdk')
api_path = root / 'api.py'
api_text = api_path.read_text(encoding='utf-8')
lines = api_text.splitlines(keepends=True)

class_start = None
class_end = None
for idx, line in enumerate(lines):
    if line.startswith('class PluginApi:'):
        class_start = idx
        break

if class_start is None:
    raise SystemExit('Unable to find PluginApi class start')

for idx in range(class_start, len(lines)):
    if lines[idx].startswith('__all__ = ['):
        class_end = idx
        break

if class_end is None:
    raise SystemExit('Unable to find PluginApi class end / __all__ boundary')

plugin_api_lines = lines[class_start:class_end]
plugin_api_header = (
    '"""Runtime implementation for PluginApi — split from api.py to keep the public SDK facade compact.\n\n'
    'Mirrors the OpenClaw host contract: plugin registration methods accumulate a plugin\'s\n'
    'capabilities, and the host consumes the public properties after registration.\n"""\n\n'
    'from __future__ import annotations\n\n'
)

plugin_api = plugin_api_header + ''.join(plugin_api_lines)
(root / 'plugin_api.py').write_text(plugin_api, encoding='utf-8')

replacement = [
    '# PluginApi runtime implementation moved to plugin_api.py.\n',
    'from .plugin_api import PluginApi\n',
]
updated = lines[:class_start] + replacement + lines[class_end:]
api_path.write_text(''.join(updated), encoding='utf-8')

print('split_API_OK', len(lines), 'class_start', class_start + 1, 'class_end', class_end + 1)
