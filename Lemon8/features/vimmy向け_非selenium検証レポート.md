# vimmy向け Lemon8非Selenium検証レポート

## レポート目的

- 本プロジェクトで実施した Lemon8 スクレイピング検証結果を、`vimmy` 側の Phase1/Phase2 実装へそのまま移植できる形で整理する。
- 検証対象は次の3点。
  - Lemon8アカウント連携名との照合（ownership）
  - 投稿URLからの再生数相当（`read_count`）取得
  - 短縮URLを含むURL入力時の安定判定

## 結論（実装可否）

- **非Selenium（`httpx + BeautifulSoup + JSONパース`）で実装可能**。
- 実装済み PoC で、`read_count` 抽出・ownership 判定・短縮URLリダイレクト対応を確認済み。
- ただし実運用では、`404` や `challenge/consent` 系を前提に fail-soft 運用（エラー分類と継続処理）が必須。

## 最新検証結果（multi_user / verbose）

- 実行コマンド: `make vmv`
- サマリ（直近実行）
  - `total`: 11
  - `fetch_success_rate`: 90.91
  - `read_count_extraction_rate`: 90.91
  - `read_count_sum`: 21516
  - `ownership_status_counts`: `matched=3`, `mismatched=7`, `unknown=1`
  - `ownership_decidable_rate`: 90.91
  - `auto_stopped`: false
- `unknown=1` の理由
  - デフォルトの runtime データに **404になる無効URLを1件意図的に含めている**ため（検証用）。

## 本プロジェクトで実装済みの要点

- 取得層（`Lemon8/poc/lemon8_client.py`）
  - HTTP取得、リトライ、エラー分類、停止ガード（403/429）
  - 短縮URLの安全なリダイレクト成功判定
- パース層（`Lemon8/poc/lemon8_parser.py`）
  - `BeautifulSoup` で script 抽出
  - URLエンコード断片（`%22` など）を decode して JSON 抽出
  - `readCount` 優先抽出、正規化
  - `final_url` 由来の `@username` fallback 対応
- 判定層（`Lemon8/poc/ownership_validator.py`）
  - `matched / mismatched / unknown` 判定
  - `@` 除去、lowercase、末尾 `/` 除去などの正規化
- 実行層（`Lemon8/poc/run_validation.py`）
  - single/multi_user 実行
  - JSONL 出力、見やすい段階ログ（`[START] [FETCH] [PARSE] [OWNERSHIP] [RESULT]`）
  - サマリ出力に `ownership_status_counts` などを集約

## vimmyへの移植マッピング

- Phase1（スクレイピング保存系）へ移植
  - 移植対象関数
    - `normalize_numeric`: `readCount` 等を `int` に正規化（`None`/不正値/負値は `0`）
    - `decode_url_encoded_blob`: `%22` などを含む script 文字列を decode
    - `extract_json_block`: `$ArticleDetail` / `$UserDetail` の JSON ブロック抽出
    - `parse_post_metrics`: HTML から `read_count`, `author_link_name`, `group_id` を返す集約関数
  - vimmy側での配置イメージ
    - `services/lemon8_scraping_service.py` に「抽出ユーティリティ層」として分離配置
    - 既存の UserDetail 抽出は残し、ArticleDetail 抽出を追加して統合
  - 保存マッピング（固定推奨）
    - `read_count -> Lemon8Post.view_count`
    - 既存の `VideoEntry.current_view_count` は `IG + TikTok + Lemon8` 合算に反映
  - fail-soft実装ルール
    - 抽出失敗時は `None`/reason を返し、例外でジョブ全体を停止しない
    - 投稿単位で `skip` して処理継続（ジョブ最終サマリで失敗件数を集計）
    - ログには `group_id`, `url`, `reason` を必須出力

- Phase2（連携/検証系）へ移植
  - 移植対象関数
    - `normalize_link_name`: `@` 除去、lowercase、decode、末尾 `/` 除去
    - `validate_ownership`: `matched/mismatched/unknown` を reason 付きで判定
    - `extract_author_from_post_url`（`final_url` fallback 用）: `/@<user>/<post_id>` 形式から所有者を抽出
  - ownership 判定優先順位（固定推奨）
    1. HTML由来 `author_link_name`
    2. `final_url` 由来 `@username`（1が欠損時のみ）
    3. どちらも取れなければ `unknown(author_missing)`
  - `validate-lemon8-url` のレスポンス設計
    - 成功: `ok=true`, `ownership_status=matched`, `read_count`, `final_url`, `author_source`
    - 失敗: `ok=false` かつ reason を機械可読で返す
      - `author_mismatch`
      - `author_missing`
      - `fetch_failed`
      - `challenge_detected` / `consent_required` / `redirected` / `html_schema_changed`
  - フロント接続時の最小契約
    - user-app は reason をそのまま表示可能な文言マップを持つ
    - submit API は validate 成功済み URL のみ受け付ける（責務分離）

## 推奨API挙動（vimmy実装時）

- `validate-lemon8-url` 成功条件
  - URL取得成功
  - `read_count` 抽出成功（もしくは仕様で許容する最小要件を明確化）
  - ownership が `matched`
- 失敗レスポンスは機械可読な理由を返す
  - `fetch_failed`
  - `author_missing`
  - `author_mismatch`
  - `challenge_detected` / `consent_required` / `redirected` / `html_schema_changed`

## 運用ガード（移植必須）

- 403/429 3連続で自動停止
- 直近20件の403/429比率が50%以上で停止
- 許可リージョンのみ実行（allowlist）
- ログに `user_id`, `url`, `final_url`, `error_type`, `failure_reason`, `elapsed_ms` を残す

## 受け入れ基準（vimmy側の最終チェック）

- `fetch_success_rate >= 90%`
- `read_count_extraction_rate >= 85%`
- `ownership_decidable_rate >= 85%`
- `unknown` の主要因が一時エラー/404に限定され、構文起因の `author_missing` が支配的でないこと

## 引き継ぎ時の注意

- 現在の runtime サンプルには意図的な無効URLが含まれるため、数値評価時は除外または置換する。
- ownership 精度は URL と連携アカウントの正しい紐付け（multi_user の mapping）に強く依存する。
- `make test` は実装妥当性、`make validate*` は実データでの成立性評価。両方を分けて運用する。
