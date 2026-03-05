# lemon8.api

Lemon8投稿URLに対して、Seleniumを使わずに取得・解析し、投稿者と連携アカウントの整合性を検証するためのPoCです。

## できること

- 投稿URLを取得して `read_count` や投稿者の `link_name` を抽出
- 投稿URLの投稿者と、想定している連携アカウント名の一致判定
- 単一ユーザー検証（`single_user`）と複数ユーザー検証（`multi_user`）に対応
- 検証結果を JSONL で保存し、標準出力にサマリを表示

## 前提

- Python 3.10+（`python3` が使える環境）
- macOS / Linux 想定

## セットアップ

```bash
make install
```

`pytest`, `httpx`, `beautifulsoup4` をインストールします。

## 検証実行（単一ユーザー）

デフォルト設定のまま実行:

```bash
make validate
```

詳細ログを表示・保存して実行:

```bash
make validate-verbose
```

主な入力/出力（デフォルト）:

- 入力URL: `Lemon8/tests/runtime/urls.txt`
- 連携アカウント: `Lemon8/tests/runtime/linked_accounts.json`
- 結果JSONL: `Lemon8/tests/runtime/validation_result.jsonl`
- 詳細ログ: `Lemon8/tests/runtime/validation_debug.log`（`validate-verbose` 時）

## 検証実行（複数ユーザー）

`url_user_mapping.csv`（`url,user_id,region` ヘッダ）を用意して実行します。

```bash
make validate-multi \
  URL_USER_MAPPING_FILE=path/to/url_user_mapping.csv \
  LINKED_ACCOUNTS_FILE=path/to/linked_accounts_multi.json
```

既定の runtime ファイルを使う短縮実行:

```bash
make vm
```

出力先は `OUTPUT_JSONL_MULTI`（デフォルト: `Lemon8/tests/runtime/validation_result_multi.jsonl`）です。

## ファイル形式

### `urls.txt`

- 1行1URL
- 空行と `#` で始まる行は無視

例:

```txt
# Lemon8検証用URL
https://s.lemon8-app.com/al/GgbccrUvTc
```

### `linked_accounts.json`（単一ユーザー）

```json
{
  "user_id": "demo_user",
  "lemon8_link_names": ["f82_bmw4"]
}
```

### `linked_accounts_multi.json`（複数ユーザー）

```json
{
  "users": [
    {
      "user_id": "user_a",
      "lemon8_link_names": ["name_a1", "name_a2"]
    },
    {
      "user_id": "user_b",
      "lemon8_link_names": ["name_b1"]
    }
  ]
}
```

## 出力仕様

結果JSONLは1行1レコードで、主に以下を含みます。

- `user_id`, `url`, `final_url`
- `fetch_ok`, `http_status`, `error_type`
- `read_count`, `author_link_name`, `effective_author_link_name`
- `ownership_status`（`matched` / `mismatched` / `unknown`）
- `failure_reason`, `stop_triggered`, `elapsed_ms`

標準出力には、成功率や一致率をまとめたサマリJSONが表示されます。

## 補足

- 地域判定は `REGION`, `ALLOWED_REGIONS` で制御できます（例: `jp,us`）。
- CLIを直接使う場合は `python -m Lemon8.poc.run_validation --help` を参照してください。
