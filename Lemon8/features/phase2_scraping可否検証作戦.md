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

## 実行コマンド（Makefile）

```bash
make install
make test
make validate
make validate-verbose
```

- 変数上書き例:

```bash
make validate URLS_FILE=Lemon8/features/practice-url.txt
make validate-verbose LOG_FILE=Lemon8/tests/runtime/validation_debug.log
```

- 複数ユーザー実行:

```bash
make validate-multi \
  LINKED_ACCOUNTS_FILE=Lemon8/tests/runtime/linked_accounts_multi.json \
  URL_USER_MAPPING_FILE=Lemon8/tests/runtime/url_user_mapping.csv
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
  - `https://s.lemon8-app.com/...` の短縮URLも入力可
  - ただし最終到達先が `https://*.lemon8-app.com/@<user>/<post_id>` 形式であること
- `linked_accounts.json`
  - `{ "user_id": "u1", "lemon8_link_names": ["owner_name"] }`

## 判定閾値

- `fetch_success_rate >= 90`
- `read_count_extraction_rate >= 85`
- `ownership_decidable_rate >= 85`

## 自動停止

- `403/429` 3連続で停止
- 直近20件の `403/429` 比率が50%以上で停止

## 短縮URLの成功条件

- 短縮URLからのリダイレクトでも、次を満たせば `fetch_ok=true` 扱い
  - 最終URLホストが `*.lemon8-app.com`
  - 最終URLパスが `/@<user>/<post_id>` 形式
  - 最終レスポンスが `2xx`
  - 本文が `challenge/captcha/consent` ではない
- 上記を満たさない場合は `error_type=redirected` で失敗扱い
