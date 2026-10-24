"""Tests for Browser CLI subcommands."""

import argparse
from extensions.browser.src.cli.browser_cli import register_cli
from extensions.browser.src.cli.cli_lifecycle import browser_doctor, browser_status
from extensions.browser.src.cli.cli_profiles import browser_profiles
from extensions.browser.src.cli.cli_tabs import browser_tabs


def test_cli_registration():
    """Verify that browser CLI registers its subcommands with argparse."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    ctx = {"program": subparsers}

    register_cli(ctx)

    # Test parser recognizes 'browser'
    args = parser.parse_args(["browser", "status"])
    assert args.command == "browser"
    assert args.browser_command == "status"
    assert callable(args.func)


def test_cli_doctor(capsys):
    """Verify browser_doctor CLI prints diagnostic report."""
    args = argparse.Namespace()
    browser_doctor(args)

    captured = capsys.readouterr()
    assert "Browser Doctor:" in captured.out
    assert "playwright_installed" in captured.out
    assert "storage_disk_space" in captured.out


def test_cli_status(capsys):
    """Verify browser_status CLI outputs runtime status."""
    args = argparse.Namespace()
    browser_status(args)

    captured = capsys.readouterr()
    assert "Browser Status:" in captured.out
    assert "Profile: openclaw" in captured.out or "Profile: jarvis" in captured.out


def test_cli_profiles(capsys):
    """Verify browser_profiles CLI outputs configured profiles."""
    args = argparse.Namespace()
    browser_profiles(args)

    captured = capsys.readouterr()
    assert "Configured Browser Profiles:" in captured.out
    assert "openclaw" in captured.out


def test_cli_tabs_empty(capsys):
    """Verify browser_tabs outputs message when no tabs are open."""
    args = argparse.Namespace()
    browser_tabs(args)

    captured = capsys.readouterr()
    assert "No open tabs." in captured.out or "Open Tabs:" in captured.out
