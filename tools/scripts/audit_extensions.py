import glob
import os

extensions = [
    d
    for d in os.listdir("extensions")
    if os.path.isdir(os.path.join("extensions", d)) and not d.startswith(".")
]
print(f"Total extensions: {len(extensions)}")

no_tests = []
stub_plugins = []
no_plugin_file = []

for ext in sorted(extensions):
    ext_dir = os.path.join("extensions", ext)

    # Check tests
    tests_dir = os.path.join(ext_dir, "tests")
    test_files = glob.glob(os.path.join(ext_dir, "**/test_*.py"), recursive=True)
    if not os.path.exists(tests_dir) and not test_files:
        no_tests.append(ext)

    # Check plugin.py
    plugin_py = os.path.join(ext_dir, "plugin.py")
    if os.path.exists(plugin_py):
        content = open(plugin_py, "r", encoding="utf-8").read().strip()
        lines = [
            line_str
            for line_str in content.split("\n")
            if line_str.strip()
            and not line_str.strip().startswith("#")
            and not line_str.strip().startswith('"""')
        ]
        if len(lines) < 5 or "Stub in Phase" in content:
            stub_plugins.append((ext, len(lines)))
    else:
        if not os.path.exists(os.path.join(ext_dir, "__init__.py")) and not os.path.exists(
            os.path.join(ext_dir, "src")
        ):
            no_plugin_file.append(ext)

print(f"\n=== Extensions without colocated tests ({len(no_tests)}) ===")
for e in no_tests:
    print(" ", e)

print(f"\n=== Stub / minimal plugins ({len(stub_plugins)}) ===")
for ext_name, line_count in stub_plugins:
    print(f"  {ext_name} ({line_count} lines)")

print(f"\n=== Extensions without plugin.py / __init__.py / src/ ({len(no_plugin_file)}) ===")
for e in no_plugin_file:
    print(" ", e)
