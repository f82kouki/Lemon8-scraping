from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ErrorType = Literal[
    "timeout",
    "forbidden",
    "rate_limited",
    "network",
    "challenge_detected",
    "redirected",
    "consent_required",
    "html_schema_changed",
    "unknown",
]

OwnershipStatus = Literal["matched", "mismatched", "unknown"]
OwnershipReason = Literal["author_missing", "author_mismatch", "fetch_failed", "parse_failed"]


@dataclass
class FetchResult:
    url: str
    final_url: str | None
    http_status: int | None
    ok: bool
    error_type: ErrorType | None
    raw_html: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParseResult:
    url: str
    read_count: int | None
    author_link_name: str | None
    group_id: str | None
    parse_ok: bool
    parse_error: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OwnershipResult:
    url: str
    expected_link_names: list[str]
    actual_link_name: str | None
    ownership_status: OwnershipStatus
    reason: OwnershipReason | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationTarget:
    user_id: str
    url: str
    region: str
    expected_link_names: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class StopExecutionError(RuntimeError):
    pass
