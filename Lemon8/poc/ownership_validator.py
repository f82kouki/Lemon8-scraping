from __future__ import annotations

from Lemon8.poc.lemon8_parser import normalize_link_name
from Lemon8.poc.models import OwnershipResult


def normalize_link_names(names: list[str]) -> list[str]:
    normalized: list[str] = []
    for name in names:
        fixed = normalize_link_name(name)
        if fixed:
            normalized.append(fixed)
    return sorted(set(normalized))


def validate_ownership(
    actual_link_name: str | None,
    linked_names: list[str],
    url: str = "",
) -> OwnershipResult:
    expected = normalize_link_names(linked_names)
    actual = normalize_link_name(actual_link_name)

    if actual is None:
        return OwnershipResult(
            url=url,
            expected_link_names=expected,
            actual_link_name=None,
            ownership_status="unknown",
            reason="author_missing",
        )

    if actual in expected:
        return OwnershipResult(
            url=url,
            expected_link_names=expected,
            actual_link_name=actual,
            ownership_status="matched",
            reason=None,
        )

    return OwnershipResult(
        url=url,
        expected_link_names=expected,
        actual_link_name=actual,
        ownership_status="mismatched",
        reason="author_mismatch",
    )
