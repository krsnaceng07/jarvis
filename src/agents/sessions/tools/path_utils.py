"""jarvis.agents.sessions.tools.path_utils — session tool path normalization helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/path-utils.ts``.

Phase 6.10a — path normalization.

Expands user / file URL inputs and resolves
read/write paths against the active cwd with
macOS filename variants. The variants exist
because macOS uses NFD-decomposed filenames
+ U+2019 right-single-quote in screenshot
names — the helpers try multiple normalisations
so a user-typed path still resolves to a real
file on disk.

Adaptations
-----------
- The OpenClaw source uses Node ``fs.accessSync``
  + ``path.isAbsolute`` + ``path.resolve``.
  The Python port uses :func:`os.path.isabs` +
  :func:`os.path.realpath` (or :func:`os.path.join`
  + resolve) + :func:`os.access`.
- The OpenClaw source's
  ``fileURLToPath`` is replaced with
  :func:`urllib.parse.urlparse` +
  :func:`urllib.request.url2pathname` (the
  Python stdlib equivalent).
- The OpenClaw source's NFD normalisation
  via ``str.normalize("NFD")`` is preserved
  — :mod:`unicodedata`` provides the same
  on the Python side (``unicodedata.normalize("NFD", s)``).
- The OpenClaw source's
  ``fileExists`` becomes a thin
  :func:`os.path.isfile` + :func:`os.path.isdir`
  combo (the OpenClaw source's ``accessSync``
  with ``F_OK`` only checks existence, not
  type).
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request


#: Unicode whitespace variants that should be
#: normalised to ASCII space. Mirrors
#: ``UNICODE_SPACES``
#: (``path-utils.ts:11``).
_UNICODE_SPACES = re.compile("[\u00a0\u2000-\u200a\u202f\u205f\u3000]")

#: Narrow no-break space (used by macOS in
#: screenshot filenames). Mirrors
#: ``NARROW_NO_BREAK_SPACE`` (``path-utils.ts:12``).
_NARROW_NO_BREAK_SPACE = "\u202f"


def _normalize_unicode_spaces(value: str) -> str:
    return _UNICODE_SPACES.sub(" ", value)


def _try_macos_screenshot_path(file_path: str) -> str:
    """Replace the ASCII space in `` AM`` / `` PM``
    with the narrow no-break space macOS uses.
    Mirrors ``tryMacOSScreenshotPath``
    (``path-utils.ts:17-19``)."""
    # The replacement is built via raw-string
    # concatenation so ``\\1`` is preserved
    # literally (Python's :func:`re.sub`
    # expansion of ``\\1`` gives the captured
    # group; an f-string ``\\1`` collapses to
    # a single ``\1`` which :func:`re.sub`
    # reads as a backreference but is brittle
    # when the captured group is followed by
    # other content). Use raw concatenation
    # to keep the regex semantics exact.
    return re.sub(r" (AM|PM)\.", _NARROW_NO_BREAK_SPACE + r"\1.", file_path)


def _try_nfd_variant(file_path: str) -> str:
    """Return the NFD-decomposed form of the
    path. macOS stores filenames in NFD form.
    Mirrors ``tryNFDVariant`` (``path-utils.ts:21-24``)."""
    return unicodedata.normalize("NFD", file_path)


def _try_curly_quote_variant(file_path: str) -> str:
    """Replace ASCII apostrophes with U+2019
    right-single-quote (used in French macOS
    screenshot names like "Capture d'écran").
    Mirrors ``tryCurlyQuoteVariant``
    (``path-utils.ts:26-30``)."""
    return file_path.replace("'", "\u2019")


def _file_exists(file_path: str) -> bool:
    return os.path.isfile(file_path) or os.path.isdir(file_path)


def _normalize_at_prefix(file_path: str) -> str:
    """Strip the leading ``@`` that the
    OpenClaw source strips. Some users wrap
    paths in ``@`` to escape terminal
    autocompletion; the tool layer should
    treat ``@/foo`` the same as ``/foo``.
    Mirrors ``normalizeAtPrefix``
    (``path-utils.ts:41-43``)."""
    if file_path.startswith("@"):
        return file_path[1:]
    return file_path


def normalize_user_home_path(file_path: str) -> str:
    """Normalize hallucinated or foreign user profile paths to current user's home.

    LLMs frequently hallucinate usernames (e.g. 'rsnac', 'user', 'username', 'admin', 'john')
    when constructing paths like 'C:\\Users\\rsnac\\Downloads\\...'. On Windows, creating
    directories in C:\\Users\\ requires elevated administrator privileges and fails with
    [WinError 5] Access is denied. Furthermore, Python's os.path.expanduser('~foo') unconditionally
    constructs 'C:\\Users\\foo' on Windows even when 'foo' does not exist.

    If a path references a user profile directory (e.g. 'C:\\Users\\<user>\\...' or
    '/Users/<user>/...' or '/home/<user>/...') that does NOT exist on the host, but the current
    user's home directory is valid, redirect the path to the current user's profile.
    """
    if not file_path:
        return file_path

    clean_path = str(file_path).strip().strip("'\"`")
    current_home = os.path.expanduser("~")

    # 1. Tilde with specific username: ~rsnac or ~rsnac/Downloads
    tilde_user_match = re.match(r"^~([a-zA-Z0-9_\-\.]+)(?:[/\\](.*))?$", clean_path)
    if tilde_user_match:
        target_user = tilde_user_match.group(1)
        subpath = tilde_user_match.group(2) or ""
        expanded = os.path.expanduser(f"~{target_user}")
        if not os.path.isdir(expanded):
            return os.path.normpath(os.path.join(current_home, subpath)) if subpath else current_home

    # 2. Windows drive or UNC: [C:][/\]Users[/\<user>[/\][<subpath>]
    win_match = re.match(
        r"^([a-zA-Z]:)?[/\\]Users[/\\]([^/\\]+)(?:[/\\](.*))?$",
        clean_path,
        re.IGNORECASE,
    )
    if win_match:
        drive_prefix = win_match.group(1) or ("C:" if sys.platform == "win32" else "")
        target_user = win_match.group(2)
        subpath = win_match.group(3) or ""

        # Profile directory candidate
        profile_candidate = (
            f"{drive_prefix}\\Users\\{target_user}"
            if drive_prefix
            else f"\\Users\\{target_user}"
        )
        if not os.path.isdir(profile_candidate):
            # Target user profile doesn't exist on disk -> redirect to current user's profile
            return os.path.normpath(os.path.join(current_home, subpath)) if subpath else current_home
        return clean_path

    # 3. POSIX: /(Users|home)/<user>[/<subpath>]
    posix_match = re.match(r"^/(Users|home)/([^/]+)(?:/(.*))?$", clean_path)
    if posix_match:
        base_kind = posix_match.group(1)
        target_user = posix_match.group(2)
        subpath = posix_match.group(3) or ""
        profile_candidate = f"/{base_kind}/{target_user}"
        if not os.path.isdir(profile_candidate):
            return os.path.normpath(os.path.join(current_home, subpath)) if subpath else current_home
        return clean_path

    return clean_path


def _expand_path(file_path: str) -> str:
    """Expand ``~`` / ``file://`` / ``@`` prefix and normalize user home directories.
    Mirrors ``expandPath`` (``path-utils.ts:45-61``)."""
    normalized = _normalize_unicode_spaces(_normalize_at_prefix(file_path))
    normalized = normalize_user_home_path(normalized)
    if normalized.startswith("file://"):
        try:
            parsed = urllib.parse.urlparse(normalized)
            path = urllib.request.url2pathname(parsed.path)
            if parsed.netloc:
                # UNC path on Windows: file://server/share
                return f"//{parsed.netloc}{path}"
            return path
        except (ValueError, OSError):
            return normalized
    if normalized == "~":
        return os.path.expanduser("~")
    if normalized.startswith("~/") or normalized.startswith("~\\"):
        return os.path.expanduser("~") + normalized[1:]
    return normalized


def discover_system_drives() -> list[str]:
    """Discover active logical drives on the host PC.

    On Windows, uses GetLogicalDrives to return active drive roots (e.g. ['C:\\', 'E:\\']).
    On POSIX systems, returns ['/'].
    """
    if sys.platform == "win32":
        try:
            import ctypes
            import string

            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            return [
                f"{d}:\\" for d in string.ascii_uppercase if (bitmask & (1 << (ord(d) - ord("A"))))
            ]
        except Exception:
            # Fallback: scan common drive letters
            import string

            return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    return ["/"]


def is_drive_available(drive_or_path: str) -> bool:
    """Check if the drive referenced by the path exists on this PC."""
    if sys.platform != "win32":
        return True
    path_str = str(drive_or_path).strip()
    match = re.match(r"^([a-zA-Z]):", path_str)
    if not match:
        return True
    drive_letter = match.group(1).upper() + ":\\"
    return drive_letter in discover_system_drives()


def resolve_to_cwd(file_path: str, cwd: str) -> str:
    """Resolve a path relative to ``cwd``,
    expanding ``~``, normalizing Windows drive letters,
    normalizing user home paths, and accepting absolute paths as-is. Mirrors ``resolveToCwd``
    (``path-utils.ts:67-73``)."""
    expanded = _expand_path(file_path)
    expanded = normalize_user_home_path(expanded)

    if sys.platform == "win32":
        # Handle bare drive letters like "D:" or "c:" -> "D:\" or "C:\"
        if re.match(r"^[a-zA-Z]:$", expanded):
            return expanded.upper() + "\\"
        # Handle forward slashes in drive roots like "D:/path" -> "D:\path"
        if re.match(r"^[a-zA-Z]:[/\\]", expanded) and not file_path.startswith("~"):
            return os.path.normpath(expanded)

    if os.path.isabs(expanded):
        return expanded

    return os.path.realpath(os.path.join(cwd, expanded))


def resolve_read_path(file_path: str, cwd: str) -> str:
    """Resolve a read-target path. Tries the
    expanded path + the macOS variants
    (NFD, curly-quote, AM/PM) so a
    user-typed path still resolves to a real
    file on disk. Mirrors ``resolveReadPath``
    (``path-utils.ts:75-106``)."""
    resolved = resolve_to_cwd(file_path, cwd)
    if _file_exists(resolved):
        return resolved

    am_pm = _try_macos_screenshot_path(resolved)
    if am_pm != resolved and _file_exists(am_pm):
        return am_pm

    nfd = _try_nfd_variant(resolved)
    if nfd != resolved and _file_exists(nfd):
        return nfd

    curly = _try_curly_quote_variant(resolved)
    if curly != resolved and _file_exists(curly):
        return curly

    nfd_curly = _try_curly_quote_variant(nfd)
    if nfd_curly != resolved and _file_exists(nfd_curly):
        return nfd_curly

    if sys.platform == "win32":
        # Windows drive root fallback: e.g. cwd is 'E:\jarvis', file_path is 'stonic' -> check 'E:\stonic'
        drive, _ = os.path.splitdrive(cwd or os.getcwd())
        if drive:
            clean_rel = file_path.lstrip("/\\")
            drive_candidate = os.path.normpath(f"{drive}\\{clean_rel}")
            if _file_exists(drive_candidate):
                return drive_candidate

        # Strip redundant repo/project folder from path if present:
        cwd_base = os.path.basename(cwd or os.getcwd())
        if cwd_base and f"\\{cwd_base}\\" in resolved:
            stripped = resolved.replace(f"\\{cwd_base}\\", "\\", 1)
            if _file_exists(stripped):
                return stripped

    return resolved


def resolve_unicode_path(file_path: str, cwd: str = "") -> str:
    """Resolve a filesystem path with Unicode normalization (NFC/NFD) and slash hygiene.

    Ensures non-ASCII/Nepali filenames (e.g. 'परिचय.txt'), user home paths, and mixed-slash Windows paths
    resolve accurately against the local filesystem, matching JARVIS's getReadPathVariants.
    """
    if not file_path:
        return file_path

    # 1. Normalize hallucinated/foreign user home paths (e.g. C:\Users\rsnac -> C:\Users\kcs23)
    file_path = normalize_user_home_path(file_path)

    # 2. Unicode NFC normalization and slash clean
    norm_text = unicodedata.normalize("NFC", str(file_path).strip().strip("'\"`"))
    norm_text = re.sub(r"[/\\]+", "/", norm_text)
    norm_text = re.sub(r"^([a-zA-Z]):/+", r"\1:/", norm_text)

    # 3. Resolve against cwd
    resolved = resolve_to_cwd(norm_text, cwd or os.getcwd())

    # 4. Direct existence check
    if os.path.exists(resolved) or os.path.islink(resolved):
        return resolved

    # 5. Try NFD variant
    nfd = unicodedata.normalize("NFD", resolved)
    if os.path.exists(nfd) or os.path.islink(nfd):
        return nfd

    # 6. Try macOS / screenshot variants
    read_variant = resolve_read_path(norm_text, cwd or os.getcwd())
    if os.path.exists(read_variant) or os.path.islink(read_variant):
        return read_variant

    # 7. NTFS Parent Directory Scan fallback
    # If the file was written with a slight encoding/combining mark divergence,
    # match against actual entries in the parent directory.
    parent_dir = os.path.dirname(resolved)
    target_name = os.path.basename(resolved)
    if parent_dir and os.path.isdir(parent_dir):
        try:
            target_nfc = unicodedata.normalize("NFC", target_name)
            target_nfd = unicodedata.normalize("NFD", target_name)
            for entry in os.listdir(parent_dir):
                entry_nfc = unicodedata.normalize("NFC", entry)
                entry_nfd = unicodedata.normalize("NFD", entry)
                if (
                    entry_nfc == target_nfc
                    or entry_nfd == target_nfd
                    or entry.casefold() == target_name.casefold()
                ):
                    candidate = os.path.join(parent_dir, entry)
                    if os.path.exists(candidate):
                        return candidate
        except Exception:
            pass

    # 8. Windows Drive Root and Subpath Recovery
    if sys.platform == "win32":
        drive, _ = os.path.splitdrive(cwd or os.getcwd())
        if drive:
            clean_rel = norm_text.lstrip("/\\")
            drive_candidate = os.path.normpath(f"{drive}\\{clean_rel}")
            if os.path.exists(drive_candidate) or os.path.islink(drive_candidate):
                return drive_candidate

        cwd_base = os.path.basename(cwd or os.getcwd())
        if cwd_base and f"\\{cwd_base}\\" in resolved:
            stripped = resolved.replace(f"\\{cwd_base}\\", "\\", 1)
            if os.path.exists(stripped) or os.path.islink(stripped):
                return stripped

    return resolved


def open_web_url_unified(url: str) -> bool:
    """Open a web URL in the unified JARVIS Playwright browser to prevent duplicate browser windows."""
    try:
        import asyncio
        from extensions.browser.src.browser_runtime import get_browser_runtime

        async def _open():
            rt = await get_browser_runtime()
            await rt.open_tab(url=url)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            asyncio.create_task(_open())
            return True
        else:
            asyncio.run(_open())
            return True
    except Exception:
        pass
    import webbrowser
    webbrowser.open(url)
    return True


def launch_windows_app(target: str) -> tuple[bool, str]:
    """Launch a Windows application reliably across Win32, UWP/Store apps, URI protocols, and Web fallbacks.

    Prevents WinError 2 file not found errors when opening applications like WhatsApp, Spotify,
    Telegram, Calculator, etc.
    """
    import shutil
    import subprocess

    t_raw = str(target or "").strip().strip("'\"`")
    if not t_raw:
        return False, "Target application or path is empty"

    # 1. URL or URI scheme (e.g. http://, https://, whatsapp:, tg:, spotify:, calc:, ms-settings:)
    if "://" in t_raw or (
        ":" in t_raw
        and not os.path.exists(t_raw)
        and not (len(t_raw) >= 3 and t_raw[1:3] in (":\\", ":/"))
    ):
        try:
            if t_raw.startswith(("http://", "https://")):
                open_web_url_unified(t_raw)
                return True, f"Opened web URL '{t_raw}' in browser"
            else:
                os.startfile(t_raw)
                return True, f"Launched protocol '{t_raw}'"
        except Exception:
            pass

    t_clean = t_raw.lower().replace(".exe", "").strip()

    # 2. Known Windows application aliases to URI schemes & web fallbacks
    PROTOCOL_MAP: dict[str, tuple[str, str | None]] = {
        "whatsapp": ("whatsapp:", "https://web.whatsapp.com"),
        "whatsappdesktop": ("whatsapp:", "https://web.whatsapp.com"),
        "telegram": ("tg:", "https://web.telegram.org"),
        "telegramdesktop": ("tg:", "https://web.telegram.org"),
        "spotify": ("spotify:", "https://open.spotify.com"),
        "calculator": ("calculator:", None),
        "calc": ("calculator:", None),
        "settings": ("ms-settings:", None),
        "camera": ("microsoft.windows.camera:", None),
        "photos": ("ms-photos:", None),
        "store": ("ms-windows-store:", None),
        "microsoftstore": ("ms-windows-store:", None),
        "youtube": ("https://www.youtube.com", "https://www.youtube.com"),
        "chatgpt": ("https://chatgpt.com", "https://chatgpt.com"),
        "openai": ("https://chatgpt.com", "https://chatgpt.com"),
        "facebook": ("https://www.facebook.com", "https://www.facebook.com"),
        "fb": ("https://www.facebook.com", "https://www.facebook.com"),
        "twitter": ("https://x.com", "https://x.com"),
        "x": ("https://x.com", "https://x.com"),
        "instagram": ("https://www.instagram.com", "https://www.instagram.com"),
        "google": ("https://www.google.com", "https://www.google.com"),
        "reddit": ("https://www.reddit.com", "https://www.reddit.com"),
        "linkedin": ("https://www.linkedin.com", "https://www.linkedin.com"),
        "github": ("https://github.com", "https://github.com"),
        "gmail": ("https://mail.google.com", "https://mail.google.com"),
        "notepad": ("notepad", None),
        "paint": ("mspaint.exe", None),
        "mspaint": ("mspaint.exe", None),
        "explorer": ("explorer.exe", None),
    }

    if t_clean in PROTOCOL_MAP:
        uri, web_fallback = PROTOCOL_MAP[t_clean]
        try:
            if uri.startswith("http"):
                open_web_url_unified(uri)
                return True, f"Opened {t_raw} via browser ({uri})"
            elif uri.endswith(".exe"):
                subprocess.Popen([uri], shell=False)
                return True, f"Launched {t_raw} executable ({uri})"
            else:
                os.startfile(uri)
                return True, f"Launched {t_raw} via protocol URI '{uri}'"
        except Exception:
            if web_fallback:
                try:
                    open_web_url_unified(web_fallback)
                    return True, f"Launched {t_raw} via web fallback ({web_fallback})"
                except Exception:
                    pass

    # 3. Direct file/path exists on disk
    norm_path = normalize_user_home_path(t_raw)
    if os.path.exists(norm_path):
        try:
            os.startfile(norm_path)
            return True, f"Launched file '{norm_path}'"
        except Exception:
            pass

    # 4. Standard executable found in system PATH
    exe_path = shutil.which(t_raw) or shutil.which(f"{t_raw}.exe")
    if exe_path:
        try:
            subprocess.Popen([exe_path], shell=False)
            return True, f"Launched executable '{exe_path}'"
        except Exception:
            pass

    # 5. PowerShell Get-StartApps lookup (for any Windows Store / UWP installed app)
    try:
        ps_cmd = f"Get-StartApps | Where-Object {{ $_.Name -like '*{t_raw}*' }} | Select-Object -ExpandProperty AppID -First 1"
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=3.0,
        )
        app_id = res.stdout.strip()
        if app_id:
            subprocess.Popen(f'explorer.exe shell:AppsFolder\\{app_id}', shell=True)
            return True, f"Launched Store App '{t_raw}' (AppID: {app_id})"
    except Exception:
        pass

    # 6. Fallback: cmd.exe /c start "" "<target>"
    try:
        subprocess.Popen(f'cmd.exe /c start "" "{t_raw}"', shell=True)
        return True, f"Attempted launch via cmd start for '{t_raw}'"
    except Exception as exc:
        return False, f"Failed to launch '{t_raw}': {exc}"


__all__ = [
    "discover_system_drives",
    "is_drive_available",
    "launch_windows_app",
    "normalize_user_home_path",
    "resolve_read_path",
    "resolve_to_cwd",
    "resolve_unicode_path",
]

