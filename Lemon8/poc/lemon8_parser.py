from __future__ import annotations

import json
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

from Lemon8.poc.models import ParseResult

_URL_USER_PATTERN = re.compile(r"/@([^/?#]+)")
_URL_GROUP_PATTERN = re.compile(r"/@[^/]+/(\d+)")


def extract_script_texts(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [script.get_text() for script in soup.find_all("script") if script.get_text()]


def decode_url_encoded_blob(text: str) -> str:
    decoded = text
    for _ in range(2):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    return decoded


def _extract_json_object_from(text: str, start_index: int) -> dict | None:
    brace_start = text.find("{", start_index)
    if brace_start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for idx in range(brace_start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[brace_start : idx + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


def extract_json_block(script_text: str, key_prefix: str) -> dict | None:
    for candidate in (script_text, decode_url_encoded_blob(script_text)):
        start = candidate.find(key_prefix)
        if start < 0:
            continue
        parsed = _extract_json_object_from(candidate, start)
        if parsed is not None:
            return parsed
    return None


def _find_first_key(data: object, keys: tuple[str, ...]) -> object | None:
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                return data[key]
        for value in data.values():
            found = _find_first_key(value, keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_first_key(item, keys)
            if found is not None:
                return found
    return None


def normalize_numeric(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return 0
        try:
            return max(int(float(stripped)), 0)
        except ValueError:
            return 0
    return 0


def normalize_link_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = decode_url_encoded_blob(value).strip().lower()
    if normalized.startswith("@"):
        normalized = normalized[1:]
    normalized = normalized.rstrip("/")
    return normalized or None


def _extract_author_from_url(source_url: str) -> str | None:
    match = _URL_USER_PATTERN.search(source_url)
    if not match:
        return None
    return normalize_link_name(match.group(1))


def _extract_group_id(source_url: str) -> str | None:
    match = _URL_GROUP_PATTERN.search(source_url)
    if not match:
        return None
    return match.group(1)


def parse_post_metrics(html: str, source_url: str) -> ParseResult:
    scripts = extract_script_texts(html)
    article_data = None
    user_data = None

    for script_text in scripts:
        if article_data is None:
            article_data = extract_json_block(script_text, "$ArticleDetail")
        if user_data is None:
            user_data = extract_json_block(script_text, "$UserDetail")
        if article_data and user_data:
            break

    read_raw = _find_first_key(article_data, ("readCount", "read_count"))
    author_raw = _find_first_key(user_data, ("linkName", "link_name", "authorName"))

    read_count = normalize_numeric(read_raw) if read_raw is not None else None
    author = normalize_link_name(str(author_raw) if author_raw is not None else None)
    if author is None:
        author = _extract_author_from_url(source_url)

    parse_error = None
    parse_ok = True

    if article_data is None and user_data is None:
        parse_ok = False
        parse_error = "html_schema_changed"
    elif read_count is None:
        parse_ok = False
        parse_error = "read_count_missing"

    return ParseResult(
        url=source_url,
        read_count=read_count,
        author_link_name=author,
        group_id=_extract_group_id(source_url),
        parse_ok=parse_ok,
        parse_error=parse_error,
    )
