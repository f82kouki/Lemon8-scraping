---
name: Phase2詳細作戦
overview: Lemon8統合のPhase2（アカウント連携・URL提出・ownership検証・admin審査表示）を、既存Instagram/TikTok実装パターンに沿って破壊的変更なく実装するための詳細実行計画です。バックエンド契約→OpenAPI生成→フロント導線→検証/受け入れの順で進める具体手順を定義します。
todos:
  - id: backend-contract-phase2
    content: Backendでis_lemon8・lemon8_accounts・lemon8_url・validate-lemon8-url契約を実装する
    status: pending
  - id: openapi-regenerate
    content: OpenAPI再生成とfrontend/packages/apis更新で型契約を同期する
    status: pending
  - id: user-app-flow-phase2
    content: user-appにLemon8連携UIとURL提出/validate導線を追加する
    status: pending
  - id: admin-review-phase2
    content: admin-dashboardのURL審査一覧/詳細にLemon8投稿表示を追加する
    status: pending
  - id: admin-user-social-phase2
    content: adminユーザー詳細のSNS連携状況/パフォーマンス表示にLemon8を追加する
    status: pending
  - id: phase2-qa-regression
    content: Phase2受け入れテストと既存IG/TikTok回帰確認を実施する
    status: pending
isProject: false
---

# Phase2 詳細作戦書（Lemon8 アカウント連携 + URL提出 + ownership検証）

## ゴール

- `is_lemon8` がキャンペーン作成/編集/取得に一貫反映される。
- user social連携に `lemon8_accounts` が追加される。
- `submit_url` に `lemon8_url` を追加し、`validate-lemon8-url` で ownership 必須検証を行う。
- admin の URL審査一覧/詳細で Lemon8投稿を確認できる。
- OpenAPI 再生成後、`frontend/packages/apis` と各画面が型エラーなく追従する。

## 実装方針（順序固定）

1. Backend domain/API契約の追加（DB・schema・route/controller）
2. OpenAPI再生成と `frontend/packages/apis` 更新
3. user-app 導線（SNS連携・URL提出・未連携制御）
4. admin-dashboard 審査導線（一覧・詳細・投稿情報表示）
5. 結合テスト・回帰確認・受け入れ判定

## 作業分解

### A. Backend: キャンペーン・SNS連携・URL検証契約

- **キャンペーン可否フラグ**
  - `VideoCampaign` に `is_lemon8` を追加し、作成/更新/取得スキーマに反映。
  - 対象: [vimmy/backend/api/models/video_campaign_model.py](vimmy/backend/api/models/video_campaign_model.py), [vimmy/backend/api/schemas/video_campaign_schema.py](vimmy/backend/api/schemas/video_campaign_schema.py)
- **SNS連携レスポンス拡張**
  - social accountsレスポンスへ `lemon8_accounts` を追加。
  - Lemon8連携・解除APIを既存IG/TikTokと同等の責務で追加。
  - 対象: [vimmy/backend/api/models/user_model.py](vimmy/backend/api/models/user_model.py), [vimmy/backend/api/controllers/user/social_controller.py](vimmy/backend/api/controllers/user/social_controller.py), [vimmy/backend/api/routes/user/social_route.py](vimmy/backend/api/routes/user/social_route.py), [vimmy/backend/api/schemas/auth_schema.py](vimmy/backend/api/schemas/auth_schema.py), [vimmy/backend/api/schemas/user_schema.py](vimmy/backend/api/schemas/user_schema.py)
- **URL提出契約拡張**
  - `UrlSubmissionCreate` に `lemon8_url` を追加。
  - `POST /validate-lemon8-url` を新設し、ownership判定は validate側で完結。
  - submit側は保存責務に限定し、validate済みURLのみ受け付ける既存方針に合わせる。
  - 対象: [vimmy/backend/api/schemas/video_entry_schema.py](vimmy/backend/api/schemas/video_entry_schema.py), [vimmy/backend/api/routes/user/entries_route.py](vimmy/backend/api/routes/user/entries_route.py), [vimmy/backend/api/controllers/user/entries_controller.py](vimmy/backend/api/controllers/user/entries_controller.py)
- **ownership検証仕様の実装固定**
  - `link_name` 正規化（`@`除去・lowercase・末尾`/`除去・URL decode・全角空白除去）を共通関数化。
  - URL抽出 `linkName` と `Lemon8Account.link_name` の一致必須、不一致時は理由付き4xx。
  - エラーメッセージは user-app でそのまま表示可能な文面に統一。

### B. OpenAPI/型生成同期

- Backend変更後に OpenAPI を再生成し、`frontend/packages/apis` を更新。
- `videoEntry*Response` と `urlSubmissionCreate` の Lemon8項目が生成されることを確認。
- 対象: [vimmy/frontend/packages/apis](vimmy/frontend/packages/apis)

### C. user-app: 連携UI + URL提出導線

- **SNS連携UI追加**
  - Lemon8を `SnsAccountSection` に追加し、連携/解除アクションを `MyPage` へ配線。
  - 対象: [vimmy/frontend/user-app/src/components/user/sections/SnsAccountSection.tsx](vimmy/frontend/user-app/src/components/user/sections/SnsAccountSection.tsx), [vimmy/frontend/user-app/src/pages/mypage/MyPage.tsx](vimmy/frontend/user-app/src/pages/mypage/MyPage.tsx)
- **URL提出ステップ拡張**
  - `is_lemon8` 判定、`lemon8Url` 入力、validate呼び出し、submit payload追加。
  - 未連携時disable、連携導線、inlineエラー表示をIG/TikTokと同等に統一。
  - 対象: [vimmy/frontend/user-app/src/pages/campaigns/video/steps/UrlSubmissionStep.tsx](vimmy/frontend/user-app/src/pages/campaigns/video/steps/UrlSubmissionStep.tsx)
- **型波及修正（最小）**
  - platform unionの固定箇所に `lemon8` を追加し、ビルドエラーを解消。
  - 対象: [vimmy/frontend/user-app/src/types/campaign.types.ts](vimmy/frontend/user-app/src/types/campaign.types.ts), [vimmy/frontend/user-app/src/components/user/types/mypage.types.ts](vimmy/frontend/user-app/src/components/user/types/mypage.types.ts)

### D. admin-dashboard: URL審査一覧/詳細追従

- **一覧（URL審査）**
  - `UrlCheckTable` のマッピングに Lemon8投稿URL抽出を追加し、列表示へ反映。
  - 全体審査一覧でも同一ロジックがあるため、`VideoUrlPendingPage` も同時に追従する。
  - 対象: [vimmy/frontend/admin-dashboard/src/pages/campaigns/components/UrlCheckTable.tsx](vimmy/frontend/admin-dashboard/src/pages/campaigns/components/UrlCheckTable.tsx), [vimmy/frontend/admin-dashboard/src/pages/submissions/video/VideoUrlPendingPage.tsx](vimmy/frontend/admin-dashboard/src/pages/submissions/video/VideoUrlPendingPage.tsx)
- **詳細（投稿情報）**
  - `VideoEntryDetailPage` の `hasPost` 判定へ Lemon8を追加。
  - `VideoPostInfo` の `InstagramPostCard`/`TikTokPostCard` 構成に合わせて Lemon8投稿カードを追加する。
  - URL承認/却下ダイアログにも Lemon8投稿情報（投稿URL・ユーザー名・説明）を追加する。
  - `VideoEntryDetailPage` から URL承認/却下ダイアログへ投稿配列を渡す配線（IG/TT/LEMON8）を明示して、表示欠落を防ぐ。
  - 対象: [vimmy/frontend/admin-dashboard/src/pages/video/VideoEntryDetailPage.tsx](vimmy/frontend/admin-dashboard/src/pages/video/VideoEntryDetailPage.tsx), [vimmy/frontend/admin-dashboard/src/components/video-detail/VideoPostInfo.tsx](vimmy/frontend/admin-dashboard/src/components/video-detail/VideoPostInfo.tsx), [vimmy/frontend/admin-dashboard/src/components/video-detail/UrlApprovalDialog.tsx](vimmy/frontend/admin-dashboard/src/components/video-detail/UrlApprovalDialog.tsx), [vimmy/frontend/admin-dashboard/src/components/video-detail/UrlRejectionDialog.tsx](vimmy/frontend/admin-dashboard/src/components/video-detail/UrlRejectionDialog.tsx)

### D-2. admin-dashboard: ユーザー詳細（SNS連携状況/パフォーマンス）追従

- `UserDetailPage` の SNSアカウント情報セクションで利用している `SocialAccountsSection` に Lemon8連携表示を追加する。
- `SNS連携状況` に Lemon8行（連携済み/未連携、link_name/URL表示）を追加する。
- `Instagram パフォーマンス` / `TikTok パフォーマンス` と同等に Lemon8 パフォーマンスカードと投稿URL一覧を追加する。
- `getUserSocialPosts` レスポンスと `user` 型（`lemon8_accounts`）の追従を合わせて実施する。
- 対象: [vimmy/frontend/admin-dashboard/src/pages/users/UserDetailPage.tsx](vimmy/frontend/admin-dashboard/src/pages/users/UserDetailPage.tsx), [vimmy/frontend/admin-dashboard/src/components/users/SocialAccountsSection.tsx](vimmy/frontend/admin-dashboard/src/components/users/SocialAccountsSection.tsx), [vimmy/frontend/packages/apis](vimmy/frontend/packages/apis)

### E. 検証・受け入れ

- **API検証**
  - `submit_url` が `lemon8_url` を受け取る。
  - `validate-lemon8-url` が ownership一致時成功/不一致時理由付き失敗。
- **UI検証（user-app）**
  - Lemon8有効キャンペーンのみ入力欄表示。
  - 未連携時は提出不可、連携後にvalidate→submit成功。
- **UI検証（admin）**
  - URL審査一覧（キャンペーン別・全体）で Lemon8投稿URLが表示される。
  - 動画エントリー詳細の投稿情報カード（Instagram/TikTok/Lemon8）と URL承認/却下ダイアログで Lemon8投稿情報が表示される。
  - ユーザー詳細の `SNS連携状況` と `Lemon8 パフォーマンス` が連携有無に応じて表示される。
- **回帰確認**
  - IGのみ、TikTokのみ、IG+TikTok の既存フローが非回帰。

## 実装上の注意点

- `UrlCheckTable` と類似ロジックのある画面（URL審査の別一覧）で修正漏れを起こさない。
- OpenAPI更新前にフロント改修を進めると型不整合が増えるため、契約更新を先行する。
- ownership判定の正規化処理を散在させず、共通ユーティリティへ集約する。

## 完了条件（Phase2）

- Backend: `is_lemon8` / `lemon8_accounts` / `lemon8_url` / `validate-lemon8-url` が契約として成立。
- user-app: Lemon8連携状態に応じたURL提出導線が動作。
- admin-dashboard: Lemon8投稿が審査導線で可視化。
- OpenAPI生成後に user-app/admin-dashboard の型エラーがない。

