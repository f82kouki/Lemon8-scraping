from pathlib import Path

from Lemon8.poc.lemon8_parser import normalize_numeric, parse_post_metrics

FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_post_metrics_normal_html():
    html = _read_fixture("post_normal.html")
    result = parse_post_metrics(html, "https://www.lemon8-app.com/@example_user/7371784553075343878")
    assert result.parse_ok is True
    assert result.read_count == 129911
    assert result.author_link_name == "yazawakakoki"
    assert result.group_id == "7371784553075343878"


def test_parse_post_metrics_missing_article():
    html = _read_fixture("post_missing_article.html")
    result = parse_post_metrics(html, "https://www.lemon8-app.com/@fallback_user/123")
    assert result.parse_ok is False
    assert result.read_count is None
    assert result.parse_error == "read_count_missing"
    assert result.author_link_name == "fallback_user"


def test_parse_post_metrics_invalid_numeric_as_zero():
    html = _read_fixture("post_invalid_numeric.html")
    result = parse_post_metrics(html, "https://www.lemon8-app.com/@invalid_numeric_user/123")
    assert result.parse_ok is True
    assert result.read_count == 0


def test_parse_post_metrics_negative_as_zero():
    html = _read_fixture("post_negative.html")
    result = parse_post_metrics(html, "https://www.lemon8-app.com/@negative_user/123")
    assert result.parse_ok is True
    assert result.read_count == 0


def test_parse_post_metrics_url_fallback_author():
    html = _read_fixture("post_encoded.html")
    result = parse_post_metrics(html, "https://www.lemon8-app.com/@url_fallback_user/777")
    assert result.read_count == 129911
    # Encoded fixture includes @Encoded_User, so parser should prefer data over URL fallback.
    assert result.author_link_name == "encoded_user"


def test_normalize_numeric_edge_cases():
    assert normalize_numeric(None) == 0
    assert normalize_numeric("") == 0
    assert normalize_numeric("abc") == 0
    assert normalize_numeric("-12") == 0
    assert normalize_numeric("12345") == 12345
