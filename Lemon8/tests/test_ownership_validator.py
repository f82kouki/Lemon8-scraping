from Lemon8.poc.ownership_validator import validate_ownership


def test_validate_ownership_matched():
    result = validate_ownership("@User_A", ["user_a", "user_b"], "https://example.com/post")
    assert result.ownership_status == "matched"
    assert result.reason is None


def test_validate_ownership_case_insensitive():
    result = validate_ownership("MiXeDName", ["mixedname"], "https://example.com/post")
    assert result.ownership_status == "matched"


def test_validate_ownership_with_at_prefix():
    result = validate_ownership("@owner", ["owner"], "https://example.com/post")
    assert result.ownership_status == "matched"


def test_validate_ownership_mismatched():
    result = validate_ownership("another_user", ["owner"], "https://example.com/post")
    assert result.ownership_status == "mismatched"
    assert result.reason == "author_mismatch"


def test_validate_ownership_unknown():
    result = validate_ownership(None, ["owner"], "https://example.com/post")
    assert result.ownership_status == "unknown"
    assert result.reason == "author_missing"
