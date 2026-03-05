---
name: Lemon8 Phase1詳細作戦
overview: 既存のLemon8スクレイピング基盤に対して、ArticleDetail抽出を安全に追加し、Firestore保存・既存API互換・運用監視までをPhase1単体で完結させる実行計画です。
todos:
  - id: phase1-analyze-parser
    content: UserDetail抽出ロジックを共通化できる構造に分解する
    status: pending
  - id: phase1-add-article-detail-parser
    content: ArticleDetail抽出関数を追加し6項目を正規化する
    status: pending
  - id: phase1-wire-scrape-flow
    content: スクレイピング本流にArticleDetail抽出結果を組み込む
    status: pending
  - id: phase1-add-observability
    content: 抽出成功/失敗の運用ログを追加する
    status: pending
  - id: phase1-add-tests
    content: パーサーの単体テストと疑似統合テストを追加する
    status: pending
  - id: phase1-regression-check
    content: 一覧/CSV/削除APIの非回帰を確認する
    status: pending
isProject: false
---

# Lemon8 Phase1 詳細作戦書（IG/TikTok方式準拠版）

## 目的

- Lemon8投稿詳細HTMLから `$ArticleDetail+{groupId}` を抽出し、`read_count` を `view_count` としてRDBへ保存する。
- Instagram/TikTokと同じく、**最新値テーブル + 履歴テーブル + VideoEntry集計値** の3層で管理する。
- 既存の再生数集計導線（報酬判定・管理画面表示）へ Lemon8 を同列統合する。

## この作戦書のゴール粒度

- 実装担当が「どの関数に何を足すか」を迷わず着手できること。
- テスト担当が「何を確認すれば完了か」を即時に判定できること。
- 運用担当が「失敗時にどこを見るか」をログ設計で追えること。

## 方針変更（今回の要求反映）

- 旧方針: Firestore `lemon8_influencers` に投稿指標を追加保存
- 新方針: IG/TikTokと同じRDB方式に統一
  - `Lemon8Post` に最新値（`view_count` 等）を保持
  - `Lemon8PostHistory` に更新前スナップショットを保持
  - `VideoEntry.current_view_count` は `IG + TikTok + Lemon8` 合算で更新
- これにより、再生数の保存・履歴・確定ロジックを全SNSで同型にする

## 対象範囲

- 対象実装
  - `[/Users/yazawakoki/develop/vimmy/backend/api/services/lemon8_scraping_service.py](/Users/yazawakoki/develop/vimmy/backend/api/services/lemon8_scraping_service.py)`
  - `[/Users/yazawakoki/develop/vimmy/backend/api/models/video_campaign_model.py](/Users/yazawakoki/develop/vimmy/backend/api/models/video_campaign_model.py)`（`Lemon8Post` / `Lemon8PostHistory`）
  - `[/Users/yazawakoki/develop/vimmy/backend/alembic/versions](/Users/yazawakoki/develop/vimmy/backend/alembic/versions)`（migration）
  - `[/Users/yazawakoki/develop/vimmy/backend/api/jobs/lemon8_metrics_job.py](/Users/yazawakoki/develop/vimmy/backend/api/jobs/lemon8_metrics_job.py)`（新規）
  - `[/Users/yazawakoki/develop/vimmy/backend/api/jobs/video_view_reward_job.py](/Users/yazawakoki/develop/vimmy/backend/api/jobs/video_view_reward_job.py)`（合算反映）
- 影響確認対象（回帰確認）
  - `[/Users/yazawakoki/develop/vimmy/backend/api/controllers/user/entries_controller.py](/Users/yazawakoki/develop/vimmy/backend/api/controllers/user/entries_controller.py)`
  - `[/Users/yazawakoki/develop/vimmy/backend/api/controllers/admin/entries_controller.py](/Users/yazawakoki/develop/vimmy/backend/api/controllers/admin/entries_controller.py)`
  - `[/Users/yazawakoki/develop/vimmy/backend/api/controllers/public/campaigns_controller.py](/Users/yazawakoki/develop/vimmy/backend/api/controllers/public/campaigns_controller.py)`

## 現状整理（コード起点）

- 既存サービスは `parse_user_detail_from_html()` で `$UserDetail` のみ抽出しており、投稿指標は未保存。
- IG/TikTok は `InstagramPost` / `TikTokPost` の `view_count` を更新し、更新前を `*PostHistory` に退避する方式。
- `VideoEntry.current_view_count` はメトリクスジョブで合算更新され、報酬確定ジョブが確定処理を担う。
- Lemon8も同方式へ揃えることで、再生数ロジックの分岐を最小化できる。

## Phase1の成果物（Deliverables）

- コード変更
  - `Lemon8ScrapingService` に ArticleDetail 抽出・正規化処理を追加。
  - Lemon8投稿の最新値を `Lemon8Post` に保存する更新処理を追加。
  - 更新前レコードを `Lemon8PostHistory` へ保存する履歴処理を追加。
  - `VideoEntry.current_view_count` 合算に Lemon8 を含める。
- テスト追加
  - パーサー単体テスト（正常系/異常系/境界値）。
  - Lemon8Post upsert + 履歴生成のテスト。
  - `VideoEntry.current_view_count` の3SNS合算テスト。
- 運用ドキュメント反映
  - 成功率低下時の暫定運用手順（切り分け順）を記述。

## 実装方針

### 1) HTMLブロック抽出処理を共通化

- `lemon8_scraping_service.py` に、キー名（`$UserDetail` / `$ArticleDetail`）を受け取る内部ヘルパーを追加する。
- URLデコード後の文字列から対象JSONブロックを抽出し、波括弧カウントで終端を決定する（現行のUserDetail抽出ロジックを再利用/一般化）。
- パース失敗時は例外送出せず `None` を返し、warningログへ集約する（fail-soft）。

#### 実装詳細（関数設計）

- 追加候補関数
  - `_extract_json_block_by_key(decoded_html: str, key_prefix: str) -> Optional[str]`
    - 役割: `"$UserDetail+"` / `"$ArticleDetail+"` のJSON文字列を切り出す。
    - 失敗時: `None` を返す（例外は握りつぶさず warning で記録）。
  - `_parse_json_block(decoded_html: str, key_prefix: str) -> Optional[dict]`
    - 役割: 上記抽出 + `json.loads` を一体化。
    - 失敗時: `json.JSONDecodeError`/`ValueError` を捕捉して `None`。
- 既存関数の改修
  - `parse_user_detail_from_html()` は内部で共通ヘルパーを呼ぶ形へ置換。

### 2) ArticleDetail専用パーサーを追加

- `parse_article_detail_from_html(html: str) -> Optional[dict]` を追加。
- 取得対象（Phase1固定）
  - `read_count`
  - `digg_count`
  - `favorite_count`
  - `comment_count`
  - `article_class`
  - `publish_time`
- 数値項目は `int` 変換（欠損/不正値は0）、文字列項目は `None` 許容で正規化する。

#### 正規化仕様（固定）

- 数値フィールド
  - 対象: `read_count`, `digg_count`, `favorite_count`, `comment_count`
  - 変換規則:
    - `None` / 未定義 / 空文字 / 数値変換不能 => `0`
    - 文字列数値（例: `"12345"`） => `int`
    - 負値が来た場合 => `0` に丸める（防御的対応）
- 文字列フィールド
  - 対象: `article_class`, `publish_time`
  - 変換規則:
    - 未定義/空文字は `None`
    - それ以外は `str` 化して保存

#### 想定されるLemon8側キー揺れ対策

- `digg_count` が存在しない場合に備え、`like_count` 等の代替キー候補を fallback として吸収する実装余地を残す。
- ただし Phase1 では過剰実装せず、まずは `digg_count` 直読み + ログ観測で判断する。

### 3) 保存データへ投稿指標を組み込む

- `read_count` は Lemon8の再生指標として `view_count` にマッピングする。
- `Lemon8Post` の更新時は、更新前データを `Lemon8PostHistory` に退避してから最新値を反映する。
- `VideoEntry.current_view_count` 更新関数で `IG + TikTok + Lemon8` の合算を保存する。
- ArticleDetail抽出失敗時はジョブ継続し、該当投稿はスキップまたはデフォルト更新（要件に従い統一）する。

#### RDB保存スキーマ（Phase1追加分）

- 追加キーと型
  - `view_count: int`（`read_count` 由来）
  - `digg_count: int`
  - `favorite_count: int`
  - `comment_count: int`
  - `article_class: Optional[str]`
  - `publish_time: Optional[str]`
- 既存互換
  - `Lemon8Post` は最新値のみ保持、更新前は `Lemon8PostHistory` へ移送。
  - 既存集計APIは3SNS合算でもレスポンス契約を維持することを確認対象に含める。

### 4) ログ/運用観測を最小追加

- 抽出結果の件数を把握できるよう、カテゴリ/ページ単位で「ArticleDetail成功数・失敗数」をログに出す。
- ジョブ側は戻り値変更なし（`scraped_count/saved_count/error_count` を維持）とし、運用面の後方互換を保つ。

#### ログ出力要件（最低限）

- ページ単位
  - `article_detail_success_count`
  - `article_detail_failed_count`
  - `article_detail_success_rate`
- 実行全体単位
  - 総成功数/総失敗数
  - 失敗率（%）
- warningログに含める文脈
  - `category`
  - `page`
  - `link_name`
  - `group_id`
  - 失敗原因（missing key / json parse error など）

## 実装タスク分解（担当者向け）

### Task A: パーサー基盤整理

- `parse_user_detail_from_html()` の内部処理を分割し、共通ヘルパーを先に実装。
- 既存挙動との差分が無いことをローカルで確認。

### Task B: ArticleDetail抽出追加

- `parse_article_detail_from_html()` を追加。
- 正規化関数（数値/文字列）をローカル関数化して再利用。

### Task C: 収集フロー配線

- Lemon8メトリクス更新ジョブ（新規）で対象 `Lemon8Post` を順次処理。
- 更新前履歴（`Lemon8PostHistory`）保存 -> 最新値更新 -> `VideoEntry.current_view_count` 再計算の順で実装。

### Task D: ログ補強

- ページごとの成功/失敗カウンタを追加。
- 既存ログ粒度を維持しつつ、追加ログは `info`/`warning` に限定。

### Task E: テスト

- パーサー単体 + 疑似統合 + 回帰観点の最低セットを実装。

## テスト計画

- 単体テストを新規追加
  - `tests` 配下に `lemon8_scraping_service` のパーサーテストを追加し、以下を検証:
    - 正常HTMLから6項目を抽出できる
    - `$ArticleDetail` 欠落時に `None` で復帰する
    - 数値変換不能時に0フォールバックする
- 疑似統合テスト（サービス関数）
  - `Lemon8Post` 更新時に `Lemon8PostHistory` が生成されることを確認。
  - `VideoEntry.current_view_count` が3SNS合算になることを確認。
- 回帰確認
  - user/admin/public の再生数表示APIが Lemon8 追加後も契約を壊さないことを確認。

### テストケース詳細（最小必須）

- Case 1: 正常HTML
  - 入力: `$UserDetail` + `$ArticleDetail` を含むHTML
  - 期待: 6項目が型通りに抽出される
- Case 2: ArticleDetail欠落
  - 入力: `$UserDetail` のみ
  - 期待: 投稿更新処理は落ちず、対象レコードはスキップまたはデフォルト反映
- Case 3: 数値不正
  - 入力: `read_count: "abc"` 等
  - 期待: `0` にフォールバック
- Case 4: JSON壊れ
  - 入力: 括弧不整合のJSON断片
  - 期待: 例外で落ちず `None` 返却 + warningログ
- Case 5: 既存互換
  - 入力: IG/TikTok既存エントリーに Lemon8 投稿を追加
  - 期待: `current_view_count` が `IG + TikTok + Lemon8` で計算される

### 実行チェック（想定コマンド）

- 単体テスト: `pytest` で対象モジュールのみ実行
- 静的チェック: 既存の lint/typecheck 手順に従う
- 疑似本番: ステージング相当パラメータ（件数制限）でジョブを1回実行しログ確認

## 受け入れ条件（Phase1 DoD）

- `Lemon8Post` に `view_count`（`read_count`由来）を含む投稿指標が保存される。
- 更新時に `Lemon8PostHistory` へ履歴が作成される。
- `VideoEntry.current_view_count` が3SNS合算で更新される。
- ArticleDetail抽出に失敗してもジョブは停止せず、既存メトリクス更新フローを継続する。
- user/admin/public の再生数表示APIに回帰がない。

## 検証観点チェックリスト（レビュー用）

- コード品質
  - 共通化で `parse_user_detail_from_html()` の責務が明確になっている。
  - 例外制御が fail-soft 方針に沿っている。
- データ品質
  - `Lemon8Post` / `Lemon8PostHistory` の保存型が固定されている。
  - 欠損時デフォルトが仕様通り（数値0 / 文字列None）。
- 運用品質
  - 成功率と更新件数（更新/スキップ/失敗）の可観測性がログから担保される。
  - 失敗時に対象投稿を追跡できる文脈情報が出る。

## 実行順

1. サービス内の共通抽出ヘルパー実装
2. ArticleDetailパーサー実装
3. Lemon8Post/Lemon8PostHistory モデル + migration 実装
4. Lemon8メトリクスジョブ実装（履歴保存 -> 最新値更新）
5. `VideoEntry.current_view_count` の3SNS合算化
6. ログ追加
7. テスト追加
8. 回帰確認

### 推奨スケジュール（1〜1.5日）

- 0.5日: Task A/B（パーサー共通化 + ArticleDetail追加）
- 0.5日: Task C/D（配線 + ログ）
- 0.5日: Task E（テスト + 回帰確認 + 微修正）

## リスクと事前対策

- HTML構造変化で抽出不能になるリスク
  - 対策: パーサー失敗をwarning化し、ジョブ継続。成功率ログで劣化検知。
- フィールド型揺れ（文字列数値、null）
  - 対策: パーサーで型正規化して保存形式を固定。
- 合算ロジックの取りこぼしリスク（Lemon8未加算）
  - 対策: `current_view_count` 算出関数を共通化し、3SNS合算のユニットテストを追加。

## 障害時オペレーション（Phase1暫定）

- 症状: 保存件数はあるが Lemon8 `view_count` が急減/0偏重
  - 確認順:
    1. ジョブログで `article_detail_success_rate` と `post_update_success_rate` を確認
    2. warningログから失敗パターン（missing key / parse error）を集計
    3. `Lemon8PostHistory` と `Lemon8Post` の差分で更新停止ポイントを確認
    4. 直近HTMLサンプルを保存してキー差分を確認
- 暫定対応:
  - fail-soft継続でジョブ停止は回避
  - しきい値超過（例: 成功率50%未満）が連続する場合は運用通知を検討（Phase3で自動化）

## 完了定義（この作戦書に対するDone）

- 実装PRに、以下が全て含まれる
  - サービス改修（共通化 + ArticleDetail）
  - `Lemon8Post` / `Lemon8PostHistory` + migration
  - Lemon8メトリクス更新配線
  - `VideoEntry.current_view_count` 3SNS合算反映
  - ログ補強
  - テスト追加
  - 回帰確認結果（user/admin/public の再生数表示）

