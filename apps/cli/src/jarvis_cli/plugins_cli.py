"""jarvis_cli.plugins_cli -- ``jarvis plugins`` subcommand tree.

Mirrors OpenClaw's ``src/cli/plugins-cli.ts`` and
``src/cli/plugins-cli.runtime.ts``.  Implements the management
subcommands users interact with day-to-day.  Authoring commands
(build/validate/pack/init) and hosted-marketplace commands are stubbed
until the extension registry is live.

Subcommands
-----------
  list          List discovered extensions (table or JSON).
  search        Local search over loaded extension manifests.
  inspect       Detailed single-plugin or all-plugin view.
  enable        Set plugins.entries.<id>.enabled = true in config.
  disable       Set plugins.entries.<id>.enabled = false in config.
  install       Copy or link a local-path extension into extensions/.
  uninstall     Remove an extension from extensions/ and config.
  update        Rescan and report extension state changes.
  registry      Show extension discovery state.
  doctor        Surface plugin load issues.
  marketplace   Stub subcommands (entries / refresh / list).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "openclaw.plugin.json"
_JARVIS_CONFIG_PATH = Path.home() / ".jarvis" / "config.json"


# ── manifest scanning ─────────────────────────────────────────────────


def _scan_manifests(extensions_root: Path) -> list[dict[str, Any]]:
    """Scan ``extensions/*/openclaw.plugin.json`` and return parsed manifests.

    Adds synthetic ``_ext_name`` and ``_manifest_path`` keys.
    Never raises; bad manifests are skipped with a stderr warning.
    """
    results: list[dict[str, Any]] = []
    if not extensions_root.is_dir():
        return results
    for child in sorted(extensions_root.iterdir()):
        if not child.is_dir():
            continue
        mp = child / MANIFEST_FILENAME
        if not mp.exists():
            continue
        try:
            raw = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[WARN] plugins: cannot read {mp}: {exc}", file=sys.stderr)
            continue
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        raw["_ext_name"] = child.name
        raw["_manifest_path"] = str(mp)
        results.append(raw)
    return results


def _scan_bundles(extensions_root: Path) -> list[dict[str, Any]]:
    """Detect and return bundle metadata rows for non-native extension dirs.

    Mirrors OpenClaw bundle detection; each returned dict has the same shape
    as native manifest rows (with extra ``_bundle_format`` key).
    Never raises.
    """
    results: list[dict[str, Any]] = []
    if not extensions_root.is_dir():
        return results

    native_dirs: set[str] = set()
    for child in extensions_root.iterdir():
        if child.is_dir() and (child / MANIFEST_FILENAME).exists():
            native_dirs.add(child.name)

    try:
        from jarvis_sdk.bundle_manifest import detect_bundle_format, load_bundle_manifest  # noqa: PLC0415
    except ImportError:
        return results

    for child in sorted(extensions_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name in native_dirs:
            continue
        bundle_fmt = detect_bundle_format(child)
        if bundle_fmt is None:
            continue
        bm = load_bundle_manifest(child, bundle_fmt)
        if bm is None:
            continue
        results.append(
            {
                "id": bm.id,
                "name": bm.name or bm.id,
                "version": f"{bm.version or ''} b".strip(),
                "description": bm.description or "",
                "activation": bm.activation or "on_demand",
                "kind": "bundle",
                "format": "bundle",
                "status": "enabled",
                "source": str(child),
                "_bundle_format": bundle_fmt,
                "_ext_name": child.name,
                "_capabilities": list(bm.capabilities),
            }
        )
    return results


# ── config raw-JSON helpers ───────────────────────────────────────────


def _find_config_path(workspace: Path) -> Path:
    """Resolve the config path to write (workspace-local takes priority)."""
    for candidate in (
        workspace / "config" / "jarvis.json",
        workspace / "config.json",
        _JARVIS_CONFIG_PATH,
    ):
        if candidate.exists():
            return candidate
    return _JARVIS_CONFIG_PATH


def _load_raw_config(workspace: Path) -> dict[str, Any]:
    path = _find_config_path(workspace)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_raw_config(workspace: Path, raw: dict[str, Any]) -> None:
    path = _find_config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


def _set_plugin_enabled(workspace: Path, plugin_id: str, enabled: bool) -> None:
    """Toggle ``plugins.entries.<plugin_id>.enabled`` in the raw config.

    Mirrors OpenClaw's ``setPluginEnabled`` in config-state helpers:
    writes only what it owns; leaves all other config keys intact.
    """
    raw = _load_raw_config(workspace)
    raw.setdefault("plugins", {}).setdefault("entries", {}).setdefault(plugin_id, {})["enabled"] = (
        enabled
    )
    _save_raw_config(workspace, raw)


def _get_plugin_enabled_map(workspace: Path) -> dict[str, bool]:
    """Return plugin_id -> enabled override from config (missing = default enabled)."""
    raw = _load_raw_config(workspace)
    plugins_raw = raw.get("plugins", {})
    if not isinstance(plugins_raw, dict):
        return {}
    entries = plugins_raw.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    result: dict[str, bool] = {}
    for pid, entry in entries.items():
        if isinstance(entry, dict) and "enabled" in entry:
            result[str(pid)] = bool(entry["enabled"])
    return result


# ── status resolution ─────────────────────────────────────────────────


def _resolve_status(
    manifest: dict[str, Any],
    enabled_map: dict[str, bool],
    skipped: list[str],
) -> str:
    """Return 'enabled' | 'disabled' | 'error'."""
    plugin_id = str(manifest.get("id", manifest.get("_ext_name", "?")))
    ext_name = str(manifest.get("_ext_name", plugin_id))
    if ext_name in skipped:
        return "error"
    if enabled_map.get(plugin_id) is False:
        return "disabled"
    return "enabled"


# ── subcommand: list ──────────────────────────────────────────────────


def _cmd_plugins_list(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins list`` -- mirrors ``openclaw plugins list``.

    Shows native extensions and bundles (Agent Plugins / Codex / Claude /
    Cursor) in a unified table.  Bundle rows carry a ``b`` badge in the
    version column so they are visually distinct.
    """
    extensions_root = workspace / "extensions"
    manifests = _scan_manifests(extensions_root)
    enabled_map = _get_plugin_enabled_map(workspace)
    skipped: list[str] = load_result.get("_skipped", [])

    rows: list[dict[str, Any]] = []
    for m in manifests:
        plugin_id = str(m.get("id", m.get("_ext_name", "?")))
        status = _resolve_status(m, enabled_map, skipped)
        if args.enabled and status != "enabled":
            continue
        rows.append(
            {
                "id": plugin_id,
                "name": str(m.get("name", plugin_id)),
                "version": str(m.get("version", "")),
                "description": str(m.get("description", "")),
                "activation": str(m.get("activation", "on_demand")),
                "kind": str(m.get("kind", "")),
                "format": str(m.get("format", "jarvis")),
                "status": status,
                "source": str(m.get("_manifest_path", "")),
            }
        )

    # Include bundles (Agent Plugins / Codex / Claude / Cursor).
    bundle_rows = _scan_bundles(extensions_root)
    for br in bundle_rows:
        if not args.enabled or br["status"] == "enabled":
            rows.append(
                {
                    "id": br["id"],
                    "name": br["name"],
                    "version": br["version"],
                    "description": br["description"],
                    "activation": br["activation"],
                    "kind": f"bundle/{br['_bundle_format']}",
                    "format": "bundle",
                    "status": br["status"],
                    "source": br["source"],
                }
            )

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "workspace": str(workspace),
                    "extensionsRoot": str(extensions_root),
                    "pluginCount": len(rows),
                    "plugins": rows,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if not rows:
        if args.enabled:
            print("No enabled extensions found. Run 'jarvis plugins list' to inspect all.")
        else:
            print("No extensions found. Run 'jarvis plugins install <path>' to add one.")
        return 0

    enabled_count = sum(1 for r in rows if r["status"] == "enabled")
    native_count = sum(1 for r in rows if r["format"] != "bundle")
    bundle_count = len(rows) - native_count
    extra = f" + {bundle_count} bundle{'s' if bundle_count != 1 else ''}" if bundle_count else ""
    print(f"Extensions ({enabled_count}/{native_count} enabled{extra})\n")

    if getattr(args, "verbose", False):
        for r in rows:
            _print_plugin_verbose(r)
    else:
        _print_plugin_table(rows)
    return 0


def _print_plugin_table(rows: list[dict[str, Any]]) -> None:
    id_w = max(max(len(r["id"]) for r in rows), 2)
    ver_w = max(max(len(r["version"]) for r in rows), 7)
    kind_w = max((max(len(r["kind"]) for r in rows)), 4)
    hdr = f"{'ID':<{id_w}}  {'Version':<{ver_w}}  {'Status':<10}  {'Kind':<{kind_w}}  Description"
    print(hdr)
    print("-" * (len(hdr) + 10))
    for r in rows:
        sym = "v" if r["status"] == "enabled" else ("x" if r["status"] == "disabled" else "!")
        status_str = f"{sym} {r['status']}"
        desc = r["description"][:60] if r["description"] else ""
        print(
            f"{r['id']:<{id_w}}  {r['version']:<{ver_w}}  "
            f"{status_str:<10}  {r['kind']:<{kind_w}}  {desc}"
        )


def _print_plugin_verbose(r: dict[str, Any]) -> None:
    print(f"-- {r['name']} ({r['id']}) --")
    print(f"  Version:     {r['version'] or '(none)'}")
    print(f"  Status:      {r['status']}")
    print(f"  Kind:        {r['kind'] or '(none)'}")
    print(f"  Activation:  {r['activation']}")
    print(f"  Format:      {r['format']}")
    if r.get("format") == "bundle" and r.get("_bundle_format"):
        print(f"  Bundle format: {r['_bundle_format']}")
    if r.get("_capabilities"):
        print(f"  Capabilities: {', '.join(r['_capabilities'])}")
    if r["description"]:
        print(f"  Description: {r['description']}")
    print(f"  Source:      {r['source']}")
    print()


# ── subcommand: search ────────────────────────────────────────────────


def _cmd_plugins_search(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins search`` -- local search over installed manifests."""
    query = " ".join(args.query).lower().strip() if args.query else ""
    manifests = _scan_manifests(workspace / "extensions")
    matches = [
        m
        for m in manifests
        if not query
        or query in f"{m.get('id', '')} {m.get('name', '')} {m.get('description', '')}".lower()
    ]
    if getattr(args, "limit", None) and isinstance(args.limit, int):
        matches = matches[: args.limit]

    if getattr(args, "json", False):
        print(
            json.dumps(
                [
                    {
                        "id": str(m.get("id", "")),
                        "name": str(m.get("name", "")),
                        "version": str(m.get("version", "")),
                        "description": str(m.get("description", "")),
                    }
                    for m in matches
                ],
                indent=2,
            )
        )
        return 0

    if not matches:
        print(f"No extensions match {query!r}." if query else "No extensions found.")
        return 0

    label = f" matching {query!r}" if query else ""
    print(f"Found {len(matches)} extension(s){label}:\n")
    for m in matches:
        pid = str(m.get("id", "?"))
        name = str(m.get("name", pid))
        desc = str(m.get("description", ""))
        ver = str(m.get("version", ""))
        ver_str = f"  v{ver}" if ver else ""
        print(f"  {name} ({pid}){ver_str}")
        if desc:
            print(f"    {desc}")
    print(
        "\nNote: Search covers locally installed extensions only. "
        "Hosted search coming once the JARVIS extension registry is available."
    )
    return 0


# ── subcommand: inspect ───────────────────────────────────────────────


def _cmd_plugins_inspect(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins inspect`` -- mirrors ``openclaw plugins inspect``."""
    plugin_id: str | None = getattr(args, "id", None)
    inspect_all: bool = getattr(args, "all", False)
    as_json: bool = getattr(args, "json", False)

    if not inspect_all and not plugin_id:
        print(
            "Specify a plugin id or --all.\n"
            "Run 'jarvis plugins list' to see discovered extensions.",
            file=sys.stderr,
        )
        return 1

    manifests = _scan_manifests(workspace / "extensions")
    enabled_map = _get_plugin_enabled_map(workspace)
    skipped: list[str] = load_result.get("_skipped", [])
    tool_decls: list[dict[str, Any]] = load_result.get("tool_decls", [])

    target_manifests = (
        manifests
        if inspect_all
        else [m for m in manifests if m.get("id") == plugin_id or m.get("_ext_name") == plugin_id]
    )

    if not target_manifests:
        id_str = plugin_id or "(all)"
        print(f"Extension {id_str!r} not found. Run 'jarvis plugins list'.", file=sys.stderr)
        return 1

    def _build(m: dict[str, Any]) -> dict[str, Any]:
        pid = str(m.get("id", m.get("_ext_name", "?")))
        status = _resolve_status(m, enabled_map, skipped)
        plugin_tools = [
            d["name"]
            for d in tool_decls
            if isinstance(d, dict) and d.get("name", "").startswith(pid)
        ]
        return {
            "id": pid,
            "name": str(m.get("name", pid)),
            "version": str(m.get("version", "")),
            "description": str(m.get("description", "")),
            "activation": str(m.get("activation", "on_demand")),
            "kind": str(m.get("kind", "")),
            "format": str(m.get("format", "jarvis")),
            "status": status,
            "source": str(m.get("_manifest_path", "")),
            "entrypoint": str(m.get("entrypoint", "")),
            "capabilities": m.get("capabilities", {}),
            "contracts": m.get("contracts", {}),
            "tools": plugin_tools,
            "diagnostics": (
                [{"level": "error", "message": "failed to load"}] if status == "error" else []
            ),
        }

    records = [_build(m) for m in target_manifests]

    if as_json:
        payload: Any = records[0] if (not inspect_all and len(records) == 1) else records
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    for rec in records:
        print(f"\n-- {rec['name']} ({rec['id']}) --")
        print(f"  Status:      {rec['status']}")
        print(f"  Version:     {rec['version'] or '(none)'}")
        print(f"  Kind:        {rec['kind'] or '(none)'}")
        print(f"  Activation:  {rec['activation']}")
        if rec["description"]:
            print(f"  Description: {rec['description']}")
        print(f"  Entrypoint:  {rec['entrypoint'] or '(none)'}")
        print(f"  Source:      {rec['source']}")
        if rec["tools"]:
            print(f"  Tools:       {', '.join(rec['tools'])}")
        for d in rec["diagnostics"]:
            print(f"  [{d.get('level', 'warn').upper()}] {d.get('message', '')}")
    print()
    return 0


# ── subcommands: enable / disable ─────────────────────────────────────


def _cmd_plugins_enable(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins enable <id>``."""
    _set_plugin_enabled(workspace, args.id, True)
    print(f"Extension '{args.id}' enabled. Restart the gateway to apply.")
    return 0


def _cmd_plugins_disable(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins disable <id>``."""
    _set_plugin_enabled(workspace, args.id, False)
    print(f"Extension '{args.id}' disabled. Restart the gateway to apply.")
    return 0


# ── subcommand: install ───────────────────────────────────────────────


def _install_local_path(
    source: Path,
    workspace: Path,
    *,
    link: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """Copy or link a local extension directory into ``extensions/``.

    Extracted so that marketplace install can reuse it for local-path entries.
    """
    manifest_path = source / MANIFEST_FILENAME
    if not manifest_path.exists():
        print(f"Error: '{source}' has no '{MANIFEST_FILENAME}'.", file=sys.stderr)
        return 1

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: cannot read manifest: {exc}", file=sys.stderr)
        return 1

    plugin_id = str(manifest.get("id", source.name))
    ext_name = source.name
    dest = workspace / "extensions" / ext_name

    if dest.exists() and not force:
        print(
            f"Error: extensions/{ext_name} already exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        action = "link" if link else "copy"
        print(f"[dry-run] Would {action} {source} -> extensions/{ext_name}")
        print(f"[dry-run] Would register '{plugin_id}' as enabled.")
        return 0

    if link:
        if dest.is_symlink():
            dest.unlink()
        elif dest.exists():
            shutil.rmtree(dest)
        dest.symlink_to(source, target_is_directory=True)
        print(f"Linked extensions/{ext_name} -> {source}")
    else:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        print(f"Installed extensions/{ext_name} (copied from {source})")

    _set_plugin_enabled(workspace, plugin_id, True)
    print(f"Extension '{plugin_id}' registered. Restart the gateway to activate.")
    return 0


def _install_from_git(
    url: str,
    workspace: Path,
    *,
    ref: str | None = None,
    subdir: str | None = None,
    link: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """Clone a git repository and install the extension it contains.

    Mirrors OpenClaw's ``git-install.ts`` clone + checkout + copy/link logic.
    """
    import shutil as _shutil
    import subprocess
    import tempfile

    if not shutil.which("git"):
        print(
            "Error: 'git' not found on PATH. Install git to use git/GitHub sources.",
            file=sys.stderr,
        )
        return 1

    label = url
    _is_commit_sha = bool(
        ref and len(ref) == 40 and all(c in "0123456789abcdefABCDEF" for c in ref)
    )

    if dry_run:
        ref_str = f"#{ref}" if ref else ""
        sub_str = f" (subdir: {subdir})" if subdir else ""
        print(f"[dry-run] Would clone {url}{ref_str}{sub_str} -> extensions/")
        return 0

    tmp_dir = tempfile.mkdtemp(prefix="jarvis-git-install-")
    repo_dir = Path(tmp_dir) / "repo"
    try:
        argv = ["git", "clone"]
        if not ref or not _is_commit_sha:
            argv += ["--depth", "1"]
        if ref and not _is_commit_sha:
            argv += ["--branch", ref]
        argv += [url, str(repo_dir)]

        result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "git clone failed"
            print(f"Error: failed to clone {label}: {detail}", file=sys.stderr)
            return 1

        if _is_commit_sha and ref:
            checkout = subprocess.run(
                ["git", "switch", "--detach", "--", ref],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if checkout.returncode != 0:
                detail = checkout.stderr.strip() or "git checkout failed"
                print(f"Error: failed to checkout {ref} in {label}: {detail}", file=sys.stderr)
                return 1

        # Resolve subdirectory.
        ext_source = repo_dir / subdir if subdir else repo_dir
        if not ext_source.exists():
            print(f"Error: subdir '{subdir}' not found in cloned repo.", file=sys.stderr)
            return 1

        return _install_local_path(
            ext_source.resolve(), workspace, link=link, force=force, dry_run=False
        )
    except subprocess.TimeoutExpired:
        print(f"Error: git operation timed out cloning {label}.", file=sys.stderr)
        return 1
    finally:
        _shutil.rmtree(tmp_dir, ignore_errors=True)


def _cmd_plugins_install(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins install <spec>``.

    Supported sources (mirrors OpenClaw's ``management-mutations.ts`` dispatch):

    - Local path:        ``./my-ext`` or ``/absolute/path``
    - GitHub shorthand:  ``owner/repo[#ref]``
    - Git URL:           ``git+https://...`` or ``git+ssh://...``
    - Marketplace entry: ``marketplace:<source>:<plugin-name>``
    - clawhub / npm:     not yet available (clear error)
    """
    from jarvis_sdk.install_source import (
        parse_install_spec,
        GitSource,
        GitHubSource,
        MarketplaceSource,
        ClawHubSource,
        NpmSource,
        normalize_git_clone_source,
    )

    spec: str = args.spec
    link: bool = getattr(args, "link", False)
    force: bool = getattr(args, "force", False)
    dry_run: bool = getattr(args, "dry_run", False)

    source = parse_install_spec(spec, link=link)

    if isinstance(source, ClawHubSource):
        print(
            f"Error: ClawHub registry install ('{spec}') is not yet available.\n"
            "ClawHub support requires the JARVIS extension registry service.\n"
            "To install a local extension: jarvis plugins install ./my-ext",
            file=sys.stderr,
        )
        return 1

    if isinstance(source, NpmSource):
        print(
            f"Error: npm remote install ('{spec}') is not yet available.\n"
            "To install a local extension: jarvis plugins install ./my-ext",
            file=sys.stderr,
        )
        return 1

    if isinstance(source, GitHubSource):
        normalized = normalize_git_clone_source(source.repo)
        if normalized is None:
            print(f"Error: cannot resolve GitHub spec '{source.repo}'.", file=sys.stderr)
            return 1
        url, _ref, _label = normalized
        ref = source.ref or _ref
        return _install_from_git(
            url,
            workspace,
            ref=ref,
            subdir=source.subdir,
            link=link,
            force=force,
            dry_run=dry_run,
        )

    if isinstance(source, GitSource):
        return _install_from_git(
            source.url,
            workspace,
            ref=source.ref,
            subdir=source.subdir,
            link=link,
            force=force,
            dry_run=dry_run,
        )

    if isinstance(source, MarketplaceSource):
        return _marketplace_install_plugin(
            marketplace_source=source.marketplace,
            plugin_name=source.plugin,
            workspace=workspace,
            link=link,
            force=force,
            dry_run=dry_run,
        )

    # LocalPathSource
    local_path = Path(source.path).resolve()
    if not local_path.exists():
        print(f"Error: '{local_path}' does not exist.", file=sys.stderr)
        return 1
    return _install_local_path(local_path, workspace, link=link, force=force, dry_run=dry_run)


# ── subcommand: uninstall ─────────────────────────────────────────────


def _cmd_plugins_uninstall(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins uninstall <id>``."""
    plugin_id: str = args.id
    keep_files: bool = getattr(args, "keep_files", False)
    force: bool = getattr(args, "force", False)
    dry_run: bool = getattr(args, "dry_run", False)

    manifests = _scan_manifests(workspace / "extensions")
    target = next(
        (m for m in manifests if m.get("id") == plugin_id or m.get("_ext_name") == plugin_id),
        None,
    )
    if target is None:
        print(f"Error: extension '{plugin_id}' not found.", file=sys.stderr)
        return 1

    ext_name = str(target["_ext_name"])
    ext_dir = workspace / "extensions" / ext_name

    if dry_run:
        print(f"[dry-run] Would remove config entry for '{plugin_id}'.")
        if not keep_files:
            print(f"[dry-run] Would delete extensions/{ext_name}/")
        return 0

    if not force:
        try:
            confirm = (
                input(f"Uninstall '{plugin_id}' (extensions/{ext_name})? [y/N] ").strip().lower()
            )
        except (EOFError, KeyboardInterrupt):
            confirm = ""
        if confirm not in ("y", "yes"):
            print("Aborted.")
            return 0

    # Remove config entry.
    raw = _load_raw_config(workspace)
    plugins_raw = raw.get("plugins", {})
    if isinstance(plugins_raw, dict):
        entries = plugins_raw.get("entries", {})
        if isinstance(entries, dict) and plugin_id in entries:
            del entries[plugin_id]
            _save_raw_config(workspace, raw)

    if not keep_files and ext_dir.exists():
        if ext_dir.is_symlink():
            ext_dir.unlink()
        else:
            shutil.rmtree(ext_dir)
        print(f"Removed extensions/{ext_name}/")
    elif keep_files:
        print(f"Kept extensions/{ext_name}/ (--keep-files).")

    print(f"Extension '{plugin_id}' uninstalled. Restart the gateway to apply.")
    return 0


# ── subcommand: update ────────────────────────────────────────────────


def _cmd_plugins_update(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins update`` -- stub (no hosted registry yet)."""
    plugin_id: str | None = getattr(args, "id", None)
    update_all: bool = getattr(args, "all", False)

    if not plugin_id and not update_all:
        print(
            "Specify a plugin id or --all.\n"
            "Example: jarvis plugins update memory_core\n"
            "         jarvis plugins update --all",
            file=sys.stderr,
        )
        return 1

    print(
        "Note: Automatic updates from a hosted registry are not yet available.\n"
        "To update a locally installed extension, run:\n"
        "  jarvis plugins install <new-path> --force\n\n"
        "Current versions:"
    )
    manifests = _scan_manifests(workspace / "extensions")
    targets = (
        manifests
        if update_all
        else [m for m in manifests if m.get("id") == plugin_id or m.get("_ext_name") == plugin_id]
    )
    if not targets:
        print(f"  No extensions found matching '{plugin_id or 'all'}'.")
        return 0
    for m in targets:
        pid = str(m.get("id", m.get("_ext_name", "?")))
        print(f"  {pid}  {m.get('version', '(no version)')}")
    return 0


# ── subcommand: registry ──────────────────────────────────────────────


def _cmd_plugins_registry(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins registry`` -- mirrors ``openclaw plugins registry``."""
    as_json: bool = getattr(args, "json", False)
    extensions_root = workspace / "extensions"
    manifests = _scan_manifests(extensions_root)
    enabled_map = _get_plugin_enabled_map(workspace)
    skipped: list[str] = load_result.get("_skipped", [])
    loaded_count: int = int(load_result.get("_plugin_count", 0))

    plugin_records = [
        {
            "id": str(m.get("id", m.get("_ext_name", "?"))),
            "ext_name": str(m.get("_ext_name", "")),
            "version": str(m.get("version", "")),
            "status": _resolve_status(m, enabled_map, skipped),
            "activation": str(m.get("activation", "on_demand")),
        }
        for m in manifests
    ]

    diagnostics = [
        {"level": "error", "message": f"Extension '{ext}' failed to load."} for ext in skipped
    ]

    payload: dict[str, Any] = {
        "workspaceDir": str(workspace),
        "extensionsRoot": str(extensions_root),
        "registrySource": "manifest-scan",
        "registryState": "fresh",
        "manifestCount": len(manifests),
        "loadedCount": loaded_count,
        "skippedCount": len(skipped),
        "plugins": plugin_records,
        "diagnostics": diagnostics,
    }

    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("Extension Registry\n")
    print(f"  Workspace:  {workspace}")
    print(f"  Source:     {extensions_root}")
    print(
        f"  Manifests:  {payload['manifestCount']}  "
        f"({payload['loadedCount']} loaded, {payload['skippedCount']} skipped)"
    )
    print(f"  State:      {payload['registryState']}\n")

    if not plugin_records:
        print("  (no extensions discovered)")
        return 0

    print(f"  {'ID':<30} {'Version':<12} Status")
    print(f"  {'-' * 30} {'-' * 12} ------")
    for rec in plugin_records:
        sym = "v" if rec["status"] == "enabled" else ("x" if rec["status"] == "disabled" else "!")
        print(f"  {rec['id']:<30} {rec['version']:<12} {sym} {rec['status']}")

    if diagnostics:
        print("\n  Diagnostics:")
        for d in diagnostics:
            print(f"    [{d['level'].upper()}] {d['message']}")
    return 0


# ── subcommand: doctor ────────────────────────────────────────────────


def _cmd_plugins_doctor(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins doctor`` -- mirrors ``openclaw plugins doctor``."""
    as_json: bool = getattr(args, "json", False)
    skipped: list[str] = load_result.get("_skipped", [])
    doctor_contracts: list[dict[str, Any]] = load_result.get("doctor_contracts", [])

    issues: list[dict[str, Any]] = [
        {
            "pluginId": ext,
            "level": "error",
            "message": (
                f"Extension '{ext}' failed to load. "
                "Check the entry point and dependencies. "
                "Run 'jarvis doctor' for repair guidance."
            ),
        }
        for ext in skipped
    ] + [
        {
            "pluginId": str(c.get("plugin_id", "?")),
            "level": "info",
            "message": (
                f"Doctor contract: {c.get('name', c.get('plugin_id', '?'))} -- "
                "run 'jarvis doctor' for details."
            ),
        }
        for c in doctor_contracts
    ]

    if as_json:
        print(
            json.dumps(
                {
                    "pluginCount": int(load_result.get("_plugin_count", 0)),
                    "skippedCount": len(skipped),
                    "issues": issues,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if not issues and not skipped:
        print("No extension load issues detected. All extensions loaded successfully.")
        return 0

    if skipped:
        print(f"Load failures ({len(skipped)}):")
        for ext in skipped:
            print(f"  ! {ext}")
        print("\nRun 'jarvis doctor' for detailed repair contracts.\n")

    if issues:
        print("Issues:")
        for issue in issues:
            level = issue.get("level", "info")
            sym = {"error": "!", "warn": "?", "info": "i"}.get(level, "i")
            print(f"  [{sym}] [{issue['pluginId']}] {issue['message']}")

    return 1 if skipped else 0


# ── marketplace helpers ───────────────────────────────────────────────


def _marketplace_install_plugin(
    marketplace_source: str,
    plugin_name: str,
    workspace: Path,
    *,
    link: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """Load a marketplace and install one plugin by name.

    Mirrors OpenClaw's ``installPluginFromMarketplace``.
    """
    from jarvis_sdk.marketplace import load_marketplace, resolve_marketplace_install_path

    if not plugin_name:
        print("Error: specify a plugin name. Example: marketplace list <source>", file=sys.stderr)
        return 1

    try:
        manifest = load_marketplace(marketplace_source)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: could not load marketplace '{marketplace_source}': {exc}", file=sys.stderr)
        return 1

    entry = next((p for p in manifest.plugins if p.name == plugin_name), None)
    if entry is None:
        names = ", ".join(p.name for p in manifest.plugins)
        print(
            f"Error: plugin '{plugin_name}' not found in marketplace.\n"
            f"Available: {names or '(none)'}.",
            file=sys.stderr,
        )
        return 1

    install_path = resolve_marketplace_install_path(entry, manifest.root_dir)
    if install_path is None:
        print(
            f"Error: plugin '{plugin_name}' has a remote source ({entry.source.kind}) "
            "that requires git/URL install — not yet supported via marketplace.",
            file=sys.stderr,
        )
        return 1

    source_path = Path(install_path)
    if not source_path.exists():
        print(f"Error: marketplace plugin path does not exist: {install_path}", file=sys.stderr)
        return 1

    return _install_local_path(source_path, workspace, link=link, force=force, dry_run=dry_run)


# ── subcommand: marketplace ───────────────────────────────────────────


def _cmd_plugins_marketplace(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """``jarvis plugins marketplace`` -- mirrors OpenClaw marketplace commands.

    Subcommands:
      list <source>            Load and list plugins from a marketplace.
      install <source> <name>  Install one plugin from a marketplace.
      add <name> <source>      Register a marketplace shortcut.
      remove <name>            Remove a marketplace shortcut.
      known                    Print the known-marketplace registry.
    """
    from jarvis_sdk.marketplace import (
        load_marketplace,
        read_known_marketplaces,
        write_known_marketplaces,
    )

    sub = getattr(args, "marketplace_command", None)

    # ── marketplace list <source> ──
    if sub == "list":
        source: str | None = getattr(args, "source", None)
        as_json: bool = getattr(args, "json", False)
        if not source:
            print(
                "Usage: jarvis plugins marketplace list <source>\n"
                "  <source> can be a local path, GitHub shorthand, or git URL.",
                file=sys.stderr,
            )
            return 1
        try:
            manifest = load_marketplace(source)
        except Exception as exc:  # noqa: BLE001
            print(f"Error: could not load marketplace '{source}': {exc}", file=sys.stderr)
            return 1

        if as_json:
            records = [
                {
                    "name": p.name,
                    "version": p.version,
                    "description": p.description,
                    "source": {"kind": p.source.kind},
                }
                for p in manifest.plugins
            ]
            print(
                json.dumps(
                    {"name": manifest.name, "version": manifest.version, "plugins": records},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        title = manifest.name or source
        print(f"Marketplace: {title}")
        if manifest.version:
            print(f"Version:     {manifest.version}")
        print(f"Source:      {manifest.source_label}\n")
        if not manifest.plugins:
            print("  (no plugins)")
            return 0
        print(f"  {'Name':<30} {'Version':<12} Description")
        print(f"  {'-' * 30} {'-' * 12} -----------")
        for p in manifest.plugins:
            ver = p.version or ""
            desc = (p.description or "")[:60]
            print(f"  {p.name:<30} {ver:<12} {desc}")
        return 0

    # ── marketplace install <source> <plugin> ──
    if sub == "install":
        source = getattr(args, "source", None)
        plugin_name: str = getattr(args, "plugin", "") or ""
        link: bool = getattr(args, "link", False)
        force: bool = getattr(args, "force", False)
        dry_run: bool = getattr(args, "dry_run", False)
        if not source or not plugin_name:
            print(
                "Usage: jarvis plugins marketplace install <source> <plugin-name>",
                file=sys.stderr,
            )
            return 1
        return _marketplace_install_plugin(
            source,
            plugin_name,
            workspace,
            link=link,
            force=force,
            dry_run=dry_run,
        )

    # ── marketplace add <name> <source> ──
    if sub == "add":
        name: str = getattr(args, "name", "") or ""
        mkt_source: str = getattr(args, "source", "") or ""
        if not name or not mkt_source:
            print(
                "Usage: jarvis plugins marketplace add <name> <source>",
                file=sys.stderr,
            )
            return 1
        known = read_known_marketplaces()
        known[name] = mkt_source
        write_known_marketplaces(known)
        print(f"Registered marketplace '{name}' -> {mkt_source}")
        return 0

    # ── marketplace remove <name> ──
    if sub == "remove":
        name = getattr(args, "name", "") or ""
        if not name:
            print("Usage: jarvis plugins marketplace remove <name>", file=sys.stderr)
            return 1
        known = read_known_marketplaces()
        if name not in known:
            print(f"Error: marketplace '{name}' not in registry.", file=sys.stderr)
            return 1
        del known[name]
        write_known_marketplaces(known)
        print(f"Removed marketplace '{name}' from registry.")
        return 0

    # ── marketplace known ──
    if sub == "known":
        as_json = getattr(args, "json", False)
        known = read_known_marketplaces()
        if as_json:
            print(json.dumps(known, indent=2, ensure_ascii=False))
            return 0
        if not known:
            print("No known marketplaces registered.")
            print("Use: jarvis plugins marketplace add <name> <source>")
            return 0
        print("Known marketplaces:\n")
        for n, s in known.items():
            print(f"  {n:<20} {s}")
        return 0

    # No subcommand or unrecognised.
    print(
        "JARVIS Marketplace Commands:\n\n"
        "  list <source>              List plugins in a marketplace\n"
        "  install <source> <plugin>  Install a plugin from a marketplace\n"
        "  add <name> <source>        Register a marketplace shortcut\n"
        "  remove <name>              Remove a marketplace shortcut\n"
        "  known                      Print the known-marketplace registry\n\n"
        "Examples:\n"
        "  jarvis plugins marketplace list ./my_marketplace\n"
        "  jarvis plugins marketplace list owner/repo-marketplace\n"
        "  jarvis plugins marketplace install ./my_marketplace my-plugin\n"
        "  jarvis plugins marketplace add mymarket ./my_marketplace\n"
    )
    return 0


# ── parser registration ───────────────────────────────────────────────


def register_plugins_subparser(
    sp: "argparse._SubParsersAction[argparse.ArgumentParser]",
) -> None:
    """Register the ``plugins`` subcommand tree on ``sp``.

    Mirrors ``registerPluginsCli(program)`` in OpenClaw's
    ``src/cli/plugins-cli.ts``.
    """
    plugins_p = sp.add_parser(
        "plugins",
        help="Manage JARVIS extensions.",
        description=(
            "Discover, install, enable, disable, update, and inspect JARVIS extensions.\n\n"
            "Typical workflow:\n"
            "  jarvis plugins list                    # see what is loaded\n"
            "  jarvis plugins install ./my-ext        # local-path install\n"
            "  jarvis plugins install owner/repo      # GitHub shorthand\n"
            "  jarvis plugins install git+https://... # git URL\n"
            "  jarvis plugins enable <id>             # enable a disabled extension\n"
            "  jarvis plugins doctor                  # diagnose load failures\n"
            "  jarvis plugins marketplace list ./mkt  # browse a marketplace"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = plugins_p.add_subparsers(dest="plugins_command", metavar="<action>")

    # list
    p_list = sub.add_parser("list", help="List discovered extensions.")
    p_list.add_argument("--json", action="store_true", help="Print JSON.")
    p_list.add_argument(
        "--enabled", action="store_true", default=False, help="Only show enabled extensions."
    )
    p_list.add_argument(
        "--verbose", action="store_true", default=False, help="Show detailed entries."
    )

    # search
    p_search = sub.add_parser("search", help="Search extensions by keyword.")
    p_search.add_argument("query", nargs="*", help="Search query.")
    p_search.add_argument("--limit", type=int, default=None, metavar="N", help="Max results.")
    p_search.add_argument("--json", action="store_true", help="Print JSON.")

    # inspect / info (alias)
    p_inspect = sub.add_parser("inspect", aliases=["info"], help="Inspect extension details.")
    p_inspect.add_argument("id", nargs="?", default=None, help="Extension id.")
    p_inspect.add_argument("--all", action="store_true", help="Inspect all extensions.")
    p_inspect.add_argument("--json", action="store_true", help="Print JSON.")

    # enable
    p_enable = sub.add_parser("enable", help="Enable an extension in config.")
    p_enable.add_argument("id", help="Extension id.")

    # disable
    p_disable = sub.add_parser("disable", help="Disable an extension in config.")
    p_disable.add_argument("id", help="Extension id.")

    # install
    p_install = sub.add_parser(
        "install",
        help="Install an extension from a local path, GitHub repo, or git URL.",
        description=(
            "Install an extension.\n\n"
            "Sources:\n"
            "  ./my-ext              Local path\n"
            "  owner/repo[#ref]      GitHub shorthand\n"
            "  git+https://...[#ref] Git URL\n"
            "  marketplace:<src>:<name>  From a marketplace manifest\n\n"
            "Examples:\n"
            "  jarvis plugins install ./my_ext\n"
            "  jarvis plugins install owner/repo --link\n"
            "  jarvis plugins install git+https://github.com/x/y.git#main --force\n"
            "  jarvis plugins install ./ext --dry-run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_install.add_argument(
        "spec",
        metavar="<spec>",
        help="Local path, GitHub shorthand (owner/repo), git+ URL, or marketplace:<src>:<name>.",
    )
    p_install.add_argument(
        "-l", "--link", action="store_true", default=False, help="Symlink instead of copy."
    )
    p_install.add_argument(
        "--force", action="store_true", default=False, help="Overwrite existing extension."
    )
    p_install.add_argument(
        "--dry-run", action="store_true", default=False, dest="dry_run", help="Preview only."
    )

    # uninstall
    p_uninstall = sub.add_parser("uninstall", help="Uninstall an extension.")
    p_uninstall.add_argument("id", help="Extension id.")
    p_uninstall.add_argument(
        "--keep-files",
        action="store_true",
        default=False,
        dest="keep_files",
        help="Keep files on disk.",
    )
    p_uninstall.add_argument(
        "--force", action="store_true", default=False, help="Skip confirmation prompt."
    )
    p_uninstall.add_argument(
        "--dry-run", action="store_true", default=False, dest="dry_run", help="Preview only."
    )

    # update
    p_update = sub.add_parser("update", help="Update installed extensions.")
    p_update.add_argument("id", nargs="?", default=None, help="Extension id (omit with --all).")
    p_update.add_argument(
        "--all", action="store_true", default=False, help="Update all extensions."
    )
    p_update.add_argument(
        "--dry-run", action="store_true", default=False, dest="dry_run", help="Preview only."
    )

    # registry
    p_registry = sub.add_parser("registry", help="Inspect the extension discovery state.")
    p_registry.add_argument("--json", action="store_true", help="Print JSON.")
    p_registry.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Re-run discovery scan (always fresh; flag is a no-op until a persistent index is added).",
    )

    # doctor
    p_doctor = sub.add_parser("doctor", help="Report extension load issues.")
    p_doctor.add_argument("--json", action="store_true", help="Print JSON.")

    # marketplace (full)
    marketplace_p = sub.add_parser(
        "marketplace",
        help="Browse and install extensions from marketplace manifests.",
    )
    mkt_sub = marketplace_p.add_subparsers(dest="marketplace_command", metavar="<action>")

    # marketplace list
    mkt_list = mkt_sub.add_parser("list", help="List plugins in a marketplace.")
    mkt_list.add_argument("source", help="Local path or git URL / GitHub shorthand.")
    mkt_list.add_argument("--json", action="store_true")

    # marketplace install
    mkt_install = mkt_sub.add_parser("install", help="Install a plugin from a marketplace.")
    mkt_install.add_argument("source", help="Marketplace source (local path or git URL).")
    mkt_install.add_argument("plugin", help="Plugin name within the marketplace.")
    mkt_install.add_argument("-l", "--link", action="store_true", default=False)
    mkt_install.add_argument("--force", action="store_true", default=False)
    mkt_install.add_argument("--dry-run", action="store_true", default=False, dest="dry_run")

    # marketplace add
    mkt_add = mkt_sub.add_parser("add", help="Register a named marketplace shortcut.")
    mkt_add.add_argument("name", help="Shortcut name.")
    mkt_add.add_argument("source", help="Marketplace source.")

    # marketplace remove
    mkt_remove = mkt_sub.add_parser("remove", help="Remove a named marketplace shortcut.")
    mkt_remove.add_argument("name", help="Shortcut name.")

    # marketplace known
    mkt_known = mkt_sub.add_parser("known", help="Print the known-marketplace registry.")
    mkt_known.add_argument("--json", action="store_true")


# ── dispatcher ────────────────────────────────────────────────────────


def handle_plugins_command(
    args: argparse.Namespace,
    workspace: Path,
    load_result: dict[str, Any],
) -> int:
    """Dispatch ``args.plugins_command`` to the appropriate handler.

    ``load_result`` is the dict produced by ``_load_cli_plugins(workspace)``
    in ``main.py``, extended with ``_skipped`` and ``_plugin_count`` keys
    from the SDK ``LoadResult``.
    """
    cmd = getattr(args, "plugins_command", None)

    _dispatch: dict[str, Any] = {
        "list": _cmd_plugins_list,
        "search": _cmd_plugins_search,
        "inspect": _cmd_plugins_inspect,
        "info": _cmd_plugins_inspect,
        "enable": _cmd_plugins_enable,
        "disable": _cmd_plugins_disable,
        "install": _cmd_plugins_install,
        "uninstall": _cmd_plugins_uninstall,
        "update": _cmd_plugins_update,
        "registry": _cmd_plugins_registry,
        "doctor": _cmd_plugins_doctor,
        "marketplace": _cmd_plugins_marketplace,
    }

    handler = _dispatch.get(cmd)  # type: ignore[arg-type]
    if handler is not None:
        return handler(args, workspace, load_result)

    # No subcommand -- print summary help.
    print(
        "JARVIS Extension Manager\n\n"
        "Commands:\n"
        "  list        List discovered extensions\n"
        "  search      Search extensions by keyword\n"
        "  inspect     Inspect extension details\n"
        "  enable      Enable an extension in config\n"
        "  disable     Disable an extension in config\n"
        "  install     Install from local path, GitHub, or git URL\n"
        "  uninstall   Remove an extension\n"
        "  update      Update installed extensions\n"
        "  registry    Show discovery state\n"
        "  doctor      Report load issues\n"
        "  marketplace Browse and install from marketplace manifests\n\n"
        "Run 'jarvis plugins <command> --help' for details."
    )
    return 0


__all__ = [
    "handle_plugins_command",
    "register_plugins_subparser",
]
