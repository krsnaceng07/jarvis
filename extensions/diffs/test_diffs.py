import pytest
from .tool import normalize_diff_input


def test_normalize_diff_input_before_after():
    params = {
        "before": "old code",
        "after": "new code",
        "path": "test.txt",
        "title": "A diff title",
    }
    result = normalize_diff_input(params)
    assert result["kind"] == "before_after"
    assert result["before"] == "old code"
    assert result["after"] == "new code"
    assert result["path"] == "test.txt"
    assert result["title"] == "A diff title"


def test_normalize_diff_input_patch():
    params = {"patch": "--- a/test.txt\n+++ b/test.txt\n@@ -1 +1 @@\n-old code\n+new code"}
    result = normalize_diff_input(params)
    assert result["kind"] == "patch"
    assert "patch" in result


def test_normalize_diff_input_validation():
    # Both patch and before/after should raise
    with pytest.raises(ValueError):
        normalize_diff_input({"patch": "---", "before": "old", "after": "new"})

    # Neither patch nor before/after should raise
    with pytest.raises(ValueError):
        normalize_diff_input({})
