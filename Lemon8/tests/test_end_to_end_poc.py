from Lemon8.poc.models import FetchResult, ValidationTarget
from Lemon8.poc.run_validation import run_batch_validation, summarize_results


def test_end_to_end_success(monkeypatch):
    def fake_fetch(url: str, retry_count: int = 3, base_delay_sec: float = 0.7):
        return FetchResult(
            url=url,
            http_status=200,
            ok=True,
            error_type=None,
            raw_html="""
            <script>
            window.__STATE__ = {
              "$ArticleDetail+abc": {"readCount": 100},
              "$UserDetail+abc": {"linkName": "@owner_1"}
            };
            </script>
            """,
        )

    monkeypatch.setattr("Lemon8.poc.run_validation.fetch_with_retry", fake_fetch)

    targets = [
        ValidationTarget(
            user_id="u1",
            url="https://www.lemon8-app.com/@owner_1/111",
            region="jp",
            expected_link_names=["owner_1"],
        )
    ]
    rows = run_batch_validation(targets, allowed_regions={"jp"})
    assert rows[0]["fetch_ok"] is True
    assert rows[0]["read_count"] == 100
    assert rows[0]["ownership_status"] == "matched"


def test_end_to_end_parse_partial_failure(monkeypatch):
    def fake_fetch(url: str, retry_count: int = 3, base_delay_sec: float = 0.7):
        return FetchResult(
            url=url,
            http_status=200,
            ok=True,
            error_type=None,
            raw_html="""
            <script>
            window.__STATE__ = {
              "$UserDetail+abc": {"linkName": "@owner_1"}
            };
            </script>
            """,
        )

    monkeypatch.setattr("Lemon8.poc.run_validation.fetch_with_retry", fake_fetch)
    targets = [
        ValidationTarget(
            user_id="u1",
            url="https://www.lemon8-app.com/@owner_1/111",
            region="jp",
            expected_link_names=["owner_1"],
        )
    ]
    rows = run_batch_validation(targets, allowed_regions={"jp"})
    assert rows[0]["fetch_ok"] is True
    assert rows[0]["read_count"] is None
    assert rows[0]["failure_reason"] == "read_count_missing"


def test_end_to_end_fetch_failure_classified(monkeypatch):
    def fake_fetch(url: str, retry_count: int = 3, base_delay_sec: float = 0.7):
        return FetchResult(url=url, http_status=429, ok=False, error_type="rate_limited", raw_html="")

    monkeypatch.setattr("Lemon8.poc.run_validation.fetch_with_retry", fake_fetch)
    targets = [
        ValidationTarget(
            user_id="u1",
            url="https://www.lemon8-app.com/@owner_1/111",
            region="jp",
            expected_link_names=["owner_1"],
        )
    ]
    rows = run_batch_validation(targets, allowed_regions={"jp"})
    assert rows[0]["fetch_ok"] is False
    assert rows[0]["error_type"] == "rate_limited"
    assert rows[0]["failure_reason"] == "fetch_failed"


def test_end_to_end_challenge_and_consent_and_redirect(monkeypatch):
    statuses = [
        FetchResult(url="u1", http_status=200, ok=False, error_type="challenge_detected", raw_html=""),
        FetchResult(url="u2", http_status=200, ok=False, error_type="consent_required", raw_html=""),
        FetchResult(url="u3", http_status=302, ok=False, error_type="redirected", raw_html=""),
    ]
    call_index = {"idx": 0}

    def fake_fetch(url: str, retry_count: int = 3, base_delay_sec: float = 0.7):
        result = statuses[call_index["idx"]]
        call_index["idx"] += 1
        return result

    monkeypatch.setattr("Lemon8.poc.run_validation.fetch_with_retry", fake_fetch)

    targets = [
        ValidationTarget(user_id="u1", url="https://example.com/1", region="jp", expected_link_names=["a"]),
        ValidationTarget(user_id="u1", url="https://example.com/2", region="jp", expected_link_names=["a"]),
        ValidationTarget(user_id="u1", url="https://example.com/3", region="jp", expected_link_names=["a"]),
    ]
    rows = run_batch_validation(targets, allowed_regions={"jp"})
    assert rows[0]["error_type"] == "challenge_detected"
    assert rows[1]["error_type"] == "consent_required"
    assert rows[2]["error_type"] == "redirected"


def test_summarize_results_mixed():
    rows = [
        {
            "fetch_ok": True,
            "read_count": 10,
            "ownership_status": "matched",
            "stop_triggered": False,
        },
        {
            "fetch_ok": True,
            "read_count": None,
            "ownership_status": "unknown",
            "stop_triggered": False,
        },
        {
            "fetch_ok": False,
            "read_count": None,
            "ownership_status": "unknown",
            "stop_triggered": True,
        },
    ]
    summary = summarize_results(rows)
    assert summary["total"] == 3
    assert summary["fetch_success_rate"] == 66.67
    assert summary["read_count_extraction_rate"] == 33.33
    assert summary["ownership_decidable_rate"] == 33.33
    assert summary["auto_stopped"] is True
