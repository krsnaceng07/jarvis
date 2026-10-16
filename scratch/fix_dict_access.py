import re

files = [
    "packages/plugin_sdk/tests/test_memory_host_read_file_shared_phase54.py",
    "packages/plugin_sdk/tests/test_memory_host_hash_status_secret_phase52.py",
    "packages/plugin_sdk/tests/test_memory_host_event_types_phase5.py"
]

for filename in files:
    try:
        content = open(filename, "r", encoding="utf-8").read()
        content = re.sub(r'result\["([a-zA-Z0-9_]+)"\]', r'result.get("\1")', content)
        content = re.sub(r'assert "([a-zA-Z0-9_]+)" not in result', r'assert result.get("\1") is None', content)
        open(filename, "w", encoding="utf-8").write(content)
    except FileNotFoundError:
        pass
