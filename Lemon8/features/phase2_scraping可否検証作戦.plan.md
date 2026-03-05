# Phase2 Scraping可否検証 実行メモ

## 目的

- Seleniumなしで Lemon8 投稿URLの `readCount` 抽出と ownership 判定が成立するかを確認する。

## 実行コマンド（single_user）

```bash
python3 -m Lemon8.poc.run_validation \
  --mode single_user \
  --urls-file Lemon8/tests/runtime/urls.txt \
  --linked-accounts-file Lemon8/tests/runtime/linked_accounts.json \
  --output-jsonl Lemon8/tests/runtime/validation_result.jsonl \
  --region jp \
  --allowed-regions jp
```

## 実行コマンド（ログ詳細あり）

```bash
python3 -m Lemon8.poc.run_validation \
  --mode single_user \
  --urls-file Lemon8/tests/runtime/urls.txt \
  --linked-accounts-file Lemon8/tests/runtime/linked_accounts.json \
  --output-jsonl Lemon8/tests/runtime/validation_result.jsonl \
  --region jp \
  --allowed-regions jp \
  --verbose \
  --log-file Lemon8/tests/runtime/validation_debug.log
```

- `--verbose`: URLごとの処理段階ログを標準出力に表示
- `--log-file`: 同じ詳細ログをファイルへ保存

## 入力ファイル例

- `urls.txt`
  - 1行1URL
- `linked_accounts.json`
  - `{ "user_id": "u1", "lemon8_link_names": ["owner_name"] }`

## 判定閾値

- `fetch_success_rate >= 90`
- `read_count_extraction_rate >= 85`
- `ownership_decidable_rate >= 85`

## 自動停止

- `403/429` 3連続で停止
- 直近20件の `403/429` 比率が50%以上で停止
