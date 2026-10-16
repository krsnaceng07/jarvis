"""Tests for src.infra.exec_approvals_allowlist."""

import sys

from src.infra.exec_approvals_allowlist import matches_exec_allowlist_pattern


def test_matches_exec_allowlist_pattern_exact():
    # Exact matches
    assert matches_exec_allowlist_pattern("/usr/bin/rg", "/usr/bin/rg") is True
    assert matches_exec_allowlist_pattern("rg", "rg") is True


def test_matches_exec_allowlist_pattern_wildcards():
    # Basic wildcards
    assert matches_exec_allowlist_pattern("/usr/bin/*", "/usr/bin/rg") is True
    assert matches_exec_allowlist_pattern("/usr/bin/*", "/usr/bin/python3") is True
    # * should not cross directory boundaries
    assert matches_exec_allowlist_pattern("/usr/*", "/usr/bin/rg") is False
    
    # ** can cross directory boundaries
    assert matches_exec_allowlist_pattern("/usr/**/rg", "/usr/bin/rg") is True
    assert matches_exec_allowlist_pattern("/usr/**/rg", "/usr/local/bin/rg") is True
    
    # ? matches single character
    assert matches_exec_allowlist_pattern("/usr/bin/python?", "/usr/bin/python3") is True
    assert matches_exec_allowlist_pattern("/usr/bin/python?", "/usr/bin/python39") is False


def test_matches_exec_allowlist_pattern_normalization():
    # Case insensitivity and slash normalization on windows
    if sys.platform == "win32":
        assert matches_exec_allowlist_pattern("C:\\Program Files\\rg.exe", "c:/program files/rg.exe") is True
        assert matches_exec_allowlist_pattern("C:/Program Files/*", "C:\\Program Files\\rg.exe") is True


def test_matches_exec_allowlist_pattern_home_expansion():
    # ~ expands to home directory
    import os
    home = os.path.expanduser("~")
    assert matches_exec_allowlist_pattern("~/bin/rg", f"{home}/bin/rg") is True


def test_matches_exec_allowlist_pattern_dot_segments():
    # Testing how it handles dot segments in the target if pattern has wildcards
    # Using posix path behavior
    assert matches_exec_allowlist_pattern("/usr/**/rg", "/usr/local/../bin/rg") is True
    
    # But if no wildcard, it only does realpath fallback if available (tested implicitly)
    # The normal exact match does exact match unless Windows realpath kicks in
    if sys.platform != "win32":
        assert matches_exec_allowlist_pattern("/usr/bin/rg", "/usr/local/../bin/rg") is False
