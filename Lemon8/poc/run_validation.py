from __future__ import annotations

import argparse
from collections import deque
import csv
import json
import logging
from pathlib import Path
import time

from Lemon8.poc.lemon8_client import enforce_stop_guard, fetch_with_retry
from Lemon8.poc.lemon8_parser import extract_author_from_post_url, parse_post_metrics
from Lemon8.poc.models import StopExecutionError, ValidationTarget
from Lemon8.poc.ownership_validator import validate_ownership


def setup_logger(verbose: bool = False, log_file: str | None = None) -> logging.Logger:
    logger = logging.getLogger("lemon8_validation")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO if verbose else logging.WARNING)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def load_urls(path: str) -> list[str]:
    urls: list[str] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def load_linked_accounts(path: str) -> dict[str, list[str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if "users" in payload:
        result: dict[str, list[str]] = {}
        for row in payload["users"]:
            result[row["user_id"]] = row.get("lemon8_link_names", [])
        return result
    return {payload["user_id"]: payload.get("lemon8_link_names", [])}


def build_validation_targets(
    urls: list[str],
    linked_accounts: dict[str, list[str]],
    mapping_path: str | None = None,
    mode: str = "single_user",
    region: str = "jp",
) -> list[ValidationTarget]:
    if mode == "single_user":
        if len(linked_accounts) != 1:
            raise ValueError("single_userモードではlinked_accountsは1ユーザーのみ許容します。")
        user_id = next(iter(linked_accounts))
        expected_names = linked_accounts[user_id]
        return [
            ValidationTarget(
                user_id=user_id,
                url=url,
                region=region,
                expected_link_names=expected_names,
            )
            for url in urls
        ]

    if mode != "multi_user":
        raise ValueError(f"未対応モードです: {mode}")

    if not mapping_path:
        raise ValueError("multi_userモードでは--url-user-mapping-fileが必須です。")

    mapped: list[ValidationTarget] = []
    with Path(mapping_path).open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            user_id = row["user_id"].strip()
            url = row["url"].strip()
            target_region = (row.get("region") or region).strip()
            if user_id not in linked_accounts:
                raise ValueError(f"user_id={user_id} の連携アカウントがlinked_accountsに存在しません。")
            mapped.append(
                ValidationTarget(
                    user_id=user_id,
                    url=url,
                    region=target_region,
                    expected_link_names=linked_accounts[user_id],
                )
            )
    return mapped


def run_batch_validation(
    targets: list[ValidationTarget],
    allowed_regions: set[str] | None = None,
    logger: logging.Logger | None = None,
) -> list[dict]:
    log = logger or logging.getLogger("lemon8_validation")
    results: list[dict] = []
    recent_statuses: deque[int] = deque(maxlen=20)
    consecutive_blocked = 0
    stop_triggered = False
    allow_regions = allowed_regions or {"jp"}

    for target in targets:
        started = time.perf_counter()
        log.info("start user_id=%s region=%s url=%s", target.user_id, target.region, target.url)

        if target.region not in allow_regions:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            row = {
                "user_id": target.user_id,
                "url": target.url,
                "final_url": None,
                "effective_author_link_name": None,
                "author_source": "missing",
                "region": target.region,
                "fetch_ok": False,
                "http_status": None,
                "error_type": "unknown",
                "read_count": None,
                "author_link_name": None,
                "ownership_status": "unknown",
                "failure_reason": "region_not_allowed",
                "stop_triggered": False,
                "elapsed_ms": elapsed_ms,
            }
            results.append(row)
            log.warning(
                "skip region_not_allowed user_id=%s region=%s allowed_regions=%s",
                target.user_id,
                target.region,
                ",".join(sorted(allow_regions)),
            )
            log.info("final row=%s", json.dumps(row, ensure_ascii=False))
            continue

        try:
            fetch_result = fetch_with_retry(target.url)
            log.info(
                "fetch status=%s ok=%s error_type=%s",
                fetch_result.http_status,
                fetch_result.ok,
                fetch_result.error_type,
            )
            consecutive_blocked = enforce_stop_guard(
                recent_statuses=recent_statuses,
                consecutive_forbidden_or_limited=consecutive_blocked,
                current_status=fetch_result.http_status,
            )
        except StopExecutionError as exc:
            stop_triggered = True
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            row = {
                "user_id": target.user_id,
                "url": target.url,
                "final_url": None,
                "effective_author_link_name": None,
                "author_source": "missing",
                "region": target.region,
                "fetch_ok": False,
                "http_status": 429,
                "error_type": "rate_limited",
                "read_count": None,
                "author_link_name": None,
                "ownership_status": "unknown",
                "failure_reason": "auto_stop_triggered",
                "stop_triggered": True,
                "elapsed_ms": elapsed_ms,
            }
            results.append(row)
            log.error("stop_guard triggered url=%s reason=%s", target.url, str(exc))
            log.info("final row=%s", json.dumps(row, ensure_ascii=False))
            break

        if not fetch_result.ok:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            row = {
                "user_id": target.user_id,
                "url": target.url,
                "final_url": fetch_result.final_url,
                "effective_author_link_name": None,
                "author_source": "missing",
                "region": target.region,
                "fetch_ok": False,
                "http_status": fetch_result.http_status,
                "error_type": fetch_result.error_type,
                "read_count": None,
                "author_link_name": None,
                "ownership_status": "unknown",
                "failure_reason": "fetch_failed",
                "stop_triggered": False,
                "elapsed_ms": elapsed_ms,
            }
            results.append(row)
            log.warning(
                "fetch failed url=%s status=%s error_type=%s",
                target.url,
                fetch_result.http_status,
                fetch_result.error_type,
            )
            log.info("final row=%s", json.dumps(row, ensure_ascii=False))
            continue

        parse_result = parse_post_metrics(fetch_result.raw_html or "", target.url)
        log.info(
            "parse read_count=%s author=%s parse_error=%s",
            parse_result.read_count,
            parse_result.author_link_name,
            parse_result.parse_error,
        )
        error_type = "html_schema_changed" if parse_result.parse_error == "html_schema_changed" else None

        effective_author_link_name = parse_result.author_link_name
        author_source = "html"
        if effective_author_link_name is None:
            effective_author_link_name = extract_author_from_post_url(fetch_result.final_url or "")
            author_source = "final_url" if effective_author_link_name is not None else "missing"

        ownership = validate_ownership(
            actual_link_name=effective_author_link_name,
            linked_names=target.expected_link_names,
            url=target.url,
        )
        log.info(
            "ownership status=%s reason=%s actual=%s expected=%s author_source=%s",
            ownership.ownership_status,
            ownership.reason,
            ownership.actual_link_name,
            ",".join(ownership.expected_link_names),
            author_source,
        )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        row = {
            "user_id": target.user_id,
            "url": target.url,
            "final_url": fetch_result.final_url,
            "effective_author_link_name": effective_author_link_name,
            "author_source": author_source,
            "region": target.region,
            "fetch_ok": True,
            "http_status": fetch_result.http_status,
            "error_type": error_type,
            "read_count": parse_result.read_count,
            "author_link_name": parse_result.author_link_name,
            "ownership_status": ownership.ownership_status,
            "failure_reason": parse_result.parse_error or ownership.reason,
            "stop_triggered": False,
            "elapsed_ms": elapsed_ms,
        }
        results.append(row)
        log.info("final row=%s", json.dumps(row, ensure_ascii=False))

    if stop_triggered and results:
        # Traceability: mark all returned rows with final stop state.
        results[-1]["stop_triggered"] = True
    return results


def summarize_results(rows: list[dict]) -> dict:
    total = len(rows)
    if total == 0:
        return {
            "total": 0,
            "fetch_success_rate": 0.0,
            "read_count_extraction_rate": 0.0,
            "read_count": None,
            "read_count_sum": 0,
            "ownership_status": None,
            "ownership_status_counts": {"matched": 0, "mismatched": 0, "unknown": 0},
            "ownership_decidable_rate": 0.0,
            "auto_stopped": False,
        }

    fetch_ok = sum(1 for row in rows if row["fetch_ok"])
    read_count_ok = sum(1 for row in rows if row["read_count"] is not None)
    read_counts = [row["read_count"] for row in rows if row["read_count"] is not None]
    ownership_status_counts = {
        "matched": sum(1 for row in rows if row["ownership_status"] == "matched"),
        "mismatched": sum(1 for row in rows if row["ownership_status"] == "mismatched"),
        "unknown": sum(1 for row in rows if row["ownership_status"] == "unknown"),
    }
    ownership_decidable = sum(1 for row in rows if row["ownership_status"] in {"matched", "mismatched"})
    auto_stopped = any(row["stop_triggered"] for row in rows)

    single_read_count = read_counts[0] if total == 1 and read_counts else None
    single_ownership_status = rows[0]["ownership_status"] if total == 1 else None
    return {
        "total": total,
        "fetch_success_rate": round((fetch_ok / total) * 100, 2),
        "read_count_extraction_rate": round((read_count_ok / total) * 100, 2),
        "read_count": single_read_count,
        "read_count_sum": sum(read_counts),
        "ownership_status": single_ownership_status,
        "ownership_status_counts": ownership_status_counts,
        "ownership_decidable_rate": round((ownership_decidable / total) * 100, 2),
        "auto_stopped": auto_stopped,
    }


def write_jsonl(path: str, rows: list[dict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lemon8 Seleniumなし検証CLI")
    parser.add_argument("--urls-file", required=True)
    parser.add_argument("--linked-accounts-file", required=True)
    parser.add_argument("--url-user-mapping-file", default=None)
    parser.add_argument("--mode", choices=["single_user", "multi_user"], default="single_user")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--region", default="jp")
    parser.add_argument("--allowed-regions", default="jp", help="Comma-separated allowed regions, e.g. jp,us")
    parser.add_argument("--verbose", action="store_true", help="URL単位の処理ログを標準出力に表示する")
    parser.add_argument("--log-file", default=None, help="詳細ログ出力先ファイル")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logger = setup_logger(verbose=args.verbose, log_file=args.log_file)
    urls = load_urls(args.urls_file)
    linked_accounts = load_linked_accounts(args.linked_accounts_file)
    targets = build_validation_targets(
        urls=urls,
        linked_accounts=linked_accounts,
        mapping_path=args.url_user_mapping_file,
        mode=args.mode,
        region=args.region,
    )
    allowed_regions = {item.strip() for item in args.allowed_regions.split(",") if item.strip()}
    rows = run_batch_validation(targets=targets, allowed_regions=allowed_regions, logger=logger)
    write_jsonl(args.output_jsonl, rows)

    summary = summarize_results(rows)
    logger.info("summary=%s", json.dumps(summary, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
