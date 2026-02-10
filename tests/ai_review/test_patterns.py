from codingutils.ai_review.utils import expand_braces


def test_expand_braces_no_group():
    assert expand_braces("*.py") == ["*.py"]


def test_expand_braces_basic():
    assert expand_braces("*.{js,ts,tsx}") == ["*.js", "*.ts", "*.tsx"]


def test_expand_braces_invalid():
    assert expand_braces("*.{py") == ["*.{py"]
    assert expand_braces("*.py}") == ["*.py}"]


def test_expand_braces_empty_group():
    assert expand_braces("*.{}") == ["*.{}"]
