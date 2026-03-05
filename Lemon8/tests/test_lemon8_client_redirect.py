import httpx

from Lemon8.poc.lemon8_client import fetch_post_html


class _FakeClient:
    def __init__(self, response: httpx.Response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str) -> httpx.Response:
        return self._response


def _build_redirect_response(final_url: str, html: str = "<html>ok</html>") -> httpx.Response:
    short_request = httpx.Request("GET", "https://s.lemon8-app.com/al/abc")
    redirect_response = httpx.Response(
        302,
        headers={"location": final_url},
        request=short_request,
    )
    final_request = httpx.Request("GET", final_url)
    return httpx.Response(
        200,
        text=html,
        request=final_request,
        history=[redirect_response],
    )


def test_short_url_redirect_success(monkeypatch):
    response = _build_redirect_response("https://www.lemon8-app.com/@owner_1/111")
    monkeypatch.setattr("Lemon8.poc.lemon8_client.httpx.Client", lambda **kwargs: _FakeClient(response))

    result = fetch_post_html("https://s.lemon8-app.com/al/abc")
    assert result.ok is True
    assert result.error_type is None
    assert result.final_url == "https://www.lemon8-app.com/@owner_1/111"


def test_short_url_redirect_non_post_failed(monkeypatch):
    response = _build_redirect_response("https://www.lemon8-app.com/discover/trending")
    monkeypatch.setattr("Lemon8.poc.lemon8_client.httpx.Client", lambda **kwargs: _FakeClient(response))

    result = fetch_post_html("https://s.lemon8-app.com/al/abc")
    assert result.ok is False
    assert result.error_type == "redirected"
    assert result.final_url == "https://www.lemon8-app.com/discover/trending"


def test_short_url_redirect_challenge_failed(monkeypatch):
    response = _build_redirect_response(
        "https://www.lemon8-app.com/@owner_1/111",
        html="<html>captcha challenge required</html>",
    )
    monkeypatch.setattr("Lemon8.poc.lemon8_client.httpx.Client", lambda **kwargs: _FakeClient(response))

    result = fetch_post_html("https://s.lemon8-app.com/al/abc")
    assert result.ok is False
    assert result.error_type == "challenge_detected"
