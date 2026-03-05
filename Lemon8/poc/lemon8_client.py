from __future__ import annotations

from collections import deque
import re
import time
from urllib.parse import urlparse

import httpx

from Lemon8.poc.models import FetchResult, StopExecutionError

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

_CHALLENGE_KEYWORDS = ("captcha", "challenge", "verify you are human")
_CONSENT_KEYWORDS = ("consent", "cookie settings", "accept all")
_POST_PATH_PATTERN = re.compile(r"^/@[^/]+/\d+/?$")


def _detect_content_issue(html: str | None) -> str | None:
    if not html:
        return None
    lowered = html.lower()
    if any(keyword in lowered for keyword in _CHALLENGE_KEYWORDS):
        return "challenge_detected"
    if any(keyword in lowered for keyword in _CONSENT_KEYWORDS):
        return "consent_required"
    return None


def _is_allowed_host(host: str | None) -> bool:
    if not host:
        return False
    return host == "lemon8-app.com" or host.endswith(".lemon8-app.com")


def _is_post_path(path: str) -> bool:
    return _POST_PATH_PATTERN.match(path) is not None


def _is_safe_redirect_target(response: httpx.Response) -> bool:
    parsed = urlparse(str(response.url))
    return (
        200 <= response.status_code < 300
        and _is_allowed_host(parsed.hostname)
        and _is_post_path(parsed.path)
    )


def _classify_response(response: httpx.Response, content_issue: str | None) -> str | None:
    status = response.status_code
    if content_issue is not None:
        return content_issue
    if response.history and not _is_safe_redirect_target(response):
        return "redirected"
    if status == 403:
        return "forbidden"
    if status == 429:
        return "rate_limited"
    if 500 <= status < 600:
        return "network"
    return None


def fetch_post_html(url: str, timeout_sec: float = 10.0) -> FetchResult:
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
            response = client.get(url)
    except httpx.TimeoutException:
        return FetchResult(url=url, final_url=None, http_status=None, ok=False, error_type="timeout", raw_html=None)
    except httpx.NetworkError:
        return FetchResult(url=url, final_url=None, http_status=None, ok=False, error_type="network", raw_html=None)
    except Exception:
        return FetchResult(url=url, final_url=None, http_status=None, ok=False, error_type="unknown", raw_html=None)

    content_issue = _detect_content_issue(response.text)
    error_type = _classify_response(response, content_issue=content_issue)
    if response.status_code >= 400 or error_type in {"challenge_detected", "consent_required", "redirected"}:
        return FetchResult(
            url=url,
            final_url=str(response.url),
            http_status=response.status_code,
            ok=False,
            error_type=error_type or "unknown",
            raw_html=response.text,
        )

    return FetchResult(
        url=url,
        final_url=str(response.url),
        http_status=response.status_code,
        ok=True,
        error_type=None,
        raw_html=response.text,
    )


def fetch_with_retry(url: str, retry_count: int = 3, base_delay_sec: float = 0.7) -> FetchResult:
    retryable = {"timeout", "rate_limited", "network"}
    latest: FetchResult | None = None

    for attempt in range(retry_count + 1):
        latest = fetch_post_html(url)
        if latest.ok:
            return latest
        if latest.error_type not in retryable or attempt == retry_count:
            return latest
        sleep_for = base_delay_sec * (2**attempt)
        time.sleep(sleep_for)

    # Unreachable in normal flow.
    return latest or FetchResult(
        url=url,
        final_url=None,
        http_status=None,
        ok=False,
        error_type="unknown",
        raw_html=None,
    )


def enforce_stop_guard(
    recent_statuses: deque[int],
    consecutive_forbidden_or_limited: int,
    current_status: int | None,
) -> int:
    if current_status in {403, 429}:
        consecutive_forbidden_or_limited += 1
        recent_statuses.append(current_status)
    else:
        consecutive_forbidden_or_limited = 0
        if current_status is not None:
            recent_statuses.append(current_status)

    if consecutive_forbidden_or_limited >= 3:
        raise StopExecutionError("403/429 が3回連続したため停止しました。")

    if len(recent_statuses) == recent_statuses.maxlen:
        throttled = sum(1 for status in recent_statuses if status in {403, 429})
        if throttled / len(recent_statuses) >= 0.5:
            raise StopExecutionError("直近20件の403/429比率が50%以上のため停止しました。")

    return consecutive_forbidden_or_limited
