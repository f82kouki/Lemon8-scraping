# Phase2 Scraping可否検証結果

## 実行日時

- 2026-03-05

## 実行コマンド

```bash
python3 -m Lemon8.poc.run_validation \
  --mode single_user \
  --urls-file Lemon8/tests/runtime/urls.txt \
  --linked-accounts-file Lemon8/tests/runtime/linked_accounts.json \
  --output-jsonl Lemon8/tests/runtime/validation_result.jsonl \
  --region jp \
  --allowed-regions jp
```

## 実行結果サマリ

- `total`: 1
- `fetch_success_rate`: 0.0%
- `read_count_extraction_rate`: 0.0%
- `ownership_decidable_rate`: 0.0%
- `auto_stopped`: false

## 詳細（JSONL抜粋）

- `error_type`: `challenge_detected`
- `http_status`: `200`
- `failure_reason`: `fetch_failed`
- `read_count`: `null`
- `ownership_status`: `unknown`

## 判定（Go/No-Go）

- 結論: **No-Go（現時点）**
- 判定根拠:
  - `fetch_success_rate >= 90%` を満たさない
  - `read_count_extraction_rate >= 85%` を満たさない
  - `ownership_decidable_rate >= 85%` を満たさない
  - 初回実行で `challenge_detected` が発生し、HTML取得の安定性が確認できない

## 実装面で確認できたこと

- URLエンコード断片をデコードして `readCount` を抽出するパーサー自体は unit test で成立。
- ownership 判定ロジック（`matched` / `mismatched` / `unknown`）は unit test で成立。
- 自動停止ガード（403/429連続・比率）は CLI 実装済み。

## 次アクション

1. URLサンプルを増やし（最低10件）時間帯を分けて再試行。
2. `challenge_detected` の再現率を計測し、回避不能なら非ブラウザ方針の制約として仕様へ明記。
3. `error_type` 分布をもとに、Phase2本実装の `validate-lemon8-url` で返す失敗理由を確定。
