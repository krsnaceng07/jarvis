"""Tests for src.infra.exec_safe_bin_policy_validator."""


from src.infra.exec_safe_bin_policy_profiles import SAFE_BIN_PROFILES, SafeBinProfile
from src.infra.exec_safe_bin_policy_validator import validate_safe_bin_argv


def test_validate_safe_bin_argv_wc():
    profile = SAFE_BIN_PROFILES["wc"]
    
    # Valid wc usage
    assert validate_safe_bin_argv(["-l"], profile) is True
    assert validate_safe_bin_argv(["-c"], profile) is True
    assert validate_safe_bin_argv(["--lines"], profile) is True
    assert validate_safe_bin_argv(["-l", "-c"], profile) is True
    assert validate_safe_bin_argv(["-lc"], profile) is True
    
    # Invalid wc usage (files0-from is denied)
    assert validate_safe_bin_argv(["--files0-from", "file.txt"], profile) is False
    
    # Invalid wc usage (positional files)
    assert validate_safe_bin_argv(["file.txt"], profile) is False
    
    # Invalid wc usage (unrecognized flag)
    assert validate_safe_bin_argv(["-x"], profile) is False
    assert validate_safe_bin_argv(["--unrecognized"], profile) is False


def test_validate_safe_bin_argv_grep():
    profile = SAFE_BIN_PROFILES["grep"]
    
    # Valid grep usage
    assert validate_safe_bin_argv(["-e", "pattern"], profile) is True
    assert validate_safe_bin_argv(["--regexp", "pattern"], profile) is True
    assert validate_safe_bin_argv(["--regexp=pattern"], profile) is True
    
    # Invalid grep usage (positional pattern)
    assert validate_safe_bin_argv(["pattern"], profile) is False
    
    # Invalid grep usage (path-like value)
    assert validate_safe_bin_argv(["-e", "/tmp/pattern"], profile) is False
    
    # Invalid grep usage (shell expansion value)
    assert validate_safe_bin_argv(["-e", "$PATTERN"], profile) is False


def test_validate_safe_bin_argv_head():
    profile = SAFE_BIN_PROFILES["head"]
    
    # Valid head usage
    assert validate_safe_bin_argv(["-n", "10"], profile) is True
    assert validate_safe_bin_argv(["-n10"], profile) is True
    assert validate_safe_bin_argv(["--lines", "10"], profile) is True
    assert validate_safe_bin_argv(["--lines=10"], profile) is True
    
    # GNU Abbreviation works
    assert validate_safe_bin_argv(["--lin", "10"], profile) is True
    
    # Invalid positional
    assert validate_safe_bin_argv(["-n", "10", "file.txt"], profile) is False


def test_validate_safe_bin_argv_jq():
    profile = SAFE_BIN_PROFILES["jq"]
    
    # Even if flags are valid, jq is denied by semantics
    assert validate_safe_bin_argv(["--arg", "a", "b"], profile, bin_name="jq") is False


def test_validate_safe_bin_argv_awk():
    # Semantics deny awk even without a profile
    assert validate_safe_bin_argv(["-F", ","], SAFE_BIN_PROFILES.get("awk", SafeBinProfile()), bin_name="awk") is False


if __name__ == '__main__':
    test_validate_safe_bin_argv_wc()
    test_validate_safe_bin_argv_grep()
    test_validate_safe_bin_argv_head()
    test_validate_safe_bin_argv_jq()
    test_validate_safe_bin_argv_awk()
    print("All tests passed.")
