# Phase3 報酬系 詳細作戦書（現状調査済み更新版）

> 作成日: 2026-03-12

---

## 非対象（今回スコープ外）

- `backend/api/jobs/video_view_reward_job.py` ← job系は今回対象外

---

## 現状調査サマリー

2026-03-12時点のコード調査による実装状況。

### ✅ 実装済み（変更不要）

| ファイル | 状態 |
|---|---|
| `backend/api/models/video_campaign_model.py` | Lemon8Post・Lemon8PostHistory・VideoCampaign.is_lemon8 完備 |
| `backend/api/schemas/video_entry_schema.py` | Lemon8PostResponse・URL検証スキーマ完備 |
| `backend/api/controllers/public/campaigns_controller.py` | Lemon8用サブクエリ・platform filterも完備 |
| `backend/api/controllers/admin/users_controller.py` | Lemon8アカウント一覧・管理対応済み |
| `backend/api/models/enums.py` | LEMON8_CONNECT/DISCONNECT定義済み |
| `frontend/user-app/src/types/campaign.types.ts` | platform union に "lemon8" 含む |
| `frontend/user-app/src/components/user/types/mypage.types.ts` | 同上 |
| `frontend/user-app/src/pages/my-videos/MyVideosPage.tsx` | タブ・アイコン・フィルター完備 |
| `frontend/user-app/src/pages/featured-videos/FeaturedVideosPage.tsx` | lemon8_count含む集計・タブ完備 |
| `frontend/user-app/src/components/user/sections/SubmittedVideosSection.tsx` | アイコン・色対応済み |
| `frontend/user-app/src/pages/campaigns/video/steps/CompletionStep.tsx` | Lemon8URL表示・InsightsUI済み |
| `frontend/admin-dashboard/src/components/video/ViewHistoryDialog.tsx` | Lemon8タブ表示済み（詳細計測は制限付き） |
| `frontend/packages/apis/` | Lemon8PostResponse・lemon8_count・URL検証APIの型生成済み |

### ❌ 未実装（今回の対象）

| ファイル | 問題 |
|---|---|
| `backend/api/utils/view_count_utils.py` | `update_entry_view_count()` がIG+TikTok+YouTubeのみ。Lemon8Post未加算 |
| `backend/api/controllers/user/entries_controller.py` | `latest_view_count` 算出箇所にLemon8なし |
| `backend/api/controllers/admin/entries_controller.py` | 同上 |
| `backend/api/controllers/public/judge_controller.py` | lemon8_postsのフェッチ自体がない（IG/TikTok/YouTubeのみ） |
| `backend/api/reports/data/campaign_report_data.py` | ①is_lemon8フラグ ②CampaignSummary.lemon8_post_count ③get_campaign_summary()のLemon8集計セクション ④get_creator_performance()のLemon8バッチフェッチ ⑤import — 全て未対応 |
| `backend/api/schemas/campaign_report_schema.py` | PlatformBreakdownResponse にlemon8_*フィールドなし |
| `backend/api/schemas/post_history_schema.py` | Lemon8PostHistoryResponse クラス未定義 |
| `frontend/admin-dashboard/src/pages/campaigns/CampaignReportPage.tsx` | allPostsSorted にlemon8_posts未追加・KPI未集計 |
| `frontend/admin-dashboard/src/components/campaigns/report/ExecutiveSummary.tsx` | totalPosts・platform breakdown にLemon8未追加 |
| `frontend/admin-dashboard/src/components/campaigns/report/reportConstants.ts` | PLATFORM_COLORS にlemon8未定義 |
| `frontend/admin-dashboard/src/pages/submissions/video/VideoCompletedPage.tsx` | platformフィルターがIG/TikTokのみ |
| `frontend/user-app/src/pages/campaigns/posts/CampaignPostsPage.tsx` | Lemon8投稿未対応（仕様確認必要） |

---

## 実装方針

- 集計の単一情報源は `video_entry_id` ごとの「最新SNSメトリクス合算値」
- controllerごとに式を持たず、`view_count_utils.py` の共通関数へ寄せる
- 欠損値は `None` ではなく `0` として扱い、合算は常に `int` で返す
- Lemon8が未登録でも既存IG/TikTokの値は一切変えない（後方互換）
- Lemon8の view_count 相当は `Lemon8Post.read_count` を使用（他と異なるフィールド名に注意）
- 丸めは全SNSで統一（backend側のみ実施、frontend再計算なし）

---

## 実装ステップ

### Step 1: `view_count_utils.py` に Lemon8 を追加【最重要】

**ファイル**: `backend/api/utils/view_count_utils.py`

現在の `update_entry_view_count()` は IG + TikTok + YouTube のみ合算（L38）。

**変更内容:**
1. `Lemon8Post` の import を追加
2. `read_count` の SUM 集計クエリを追加
3. 合計式を `ig + tk + yt + l8` に修正
4. ログ出力行にも `L8: {l8_views}` を追加

```python
# 追加するクエリ
l8_stmt = select(func.sum(Lemon8Post.read_count)).where(
    Lemon8Post.video_entry_id == entry.id,
    col(Lemon8Post.deleted_at).is_(None),
)
l8_views = await session.scalar(l8_stmt) or 0

total_views = ig_views + tk_views + yt_views + l8_views  # L38修正
```

> この修正が `VideoEntry.current_view_count` に反映されるため、
> `admin/entries_controller.py` の `confirmed_view_count` も自動的に解決する。

---

### Step 2: `entries_controller` (user/admin) の `latest_view_count` 修正

**ファイル:**
- `backend/api/controllers/user/entries_controller.py`（L355-365付近）
- `backend/api/controllers/admin/entries_controller.py`（L498-504付近）

両ファイルとも `latest_view_count` 算出箇所にLemon8を追加:

```python
# admin/entries_controller.py では campaign_is_lemon8 フラグでガードする
if campaign_is_lemon8 and lemon8_posts:
    latest_view_count += sum(post.read_count or 0 for post in lemon8_posts)
```

---

### Step 3: `public/judge_controller.py` に `lemon8_posts` フェッチを追加

**ファイル**: `backend/api/controllers/public/judge_controller.py`（L60-63付近）

現在 IG/TikTok/YouTube のみフェッチしている箇所に追加:

```python
lemon8_posts = await self._get_lemon8_posts(entry.id)
```

レスポンスへの組み込みも追加する。

---

### Step 4: `campaign_report_data.py` の Lemon8 対応（変更箇所5点）

**ファイル**: `backend/api/reports/data/campaign_report_data.py`

1. **import追加**: `Lemon8Post` を import
2. **CampaignInfo dataclass**: `is_lemon8: bool` フィールド追加
3. **CampaignSummary dataclass**: `lemon8_post_count: int = 0` フィールド追加
4. **`get_campaign_info()`**: `is_lemon8=campaign.is_lemon8` を追加
5. **`get_campaign_summary()`**: IG/TikTok/YouTube の集計セクション（各~15行）に倣い、Lemon8セクションを追加
6. **`get_creator_performance()`**: IG/TikTok/YouTube のバッチフェッチ（各~9行）に倣い、Lemon8バッチフェッチを追加

---

### Step 5: `campaign_report_schema.py` の `PlatformBreakdownResponse` 拡張

**ファイル**: `backend/api/schemas/campaign_report_schema.py`（L171-185付近）

```python
# Lemon8メトリクス（追加）
lemon8_post_count: int = 0
lemon8_total_reads: int = 0    # read_count ≒ view_count
lemon8_total_diggs: int = 0    # like相当
lemon8_total_comments: int = 0
lemon8_avg_reads: float = 0.0
lemon8_cpv: float | None = None
```

---

### Step 6: `post_history_schema.py` に `Lemon8PostHistoryResponse` 追加

**ファイル**: `backend/api/schemas/post_history_schema.py`

既存の `InstagramPostHistoryResponse` / `TikTokPostHistoryResponse` / `YouTubePostHistoryResponse` に倣って追加:

```python
class Lemon8PostHistoryResponse(SQLModel):
    id: UUID
    lemon8_post_id: UUID
    read_count: int = 0
    digg_count: int = 0
    favorite_count: int = 0
    comment_count: int = 0
    recorded_at: datetime
    created_at: datetime
```

---

### Step 7: admin フロントエンド Report 修正

**`reportConstants.ts`** に Lemon8カラー追加:

```ts
lemon8: "#FFD700",
```

**`ExecutiveSummary.tsx`**:
- `totalPosts` 計算に `lemon8_post_count` 追加
- platform breakdown表示にLemon8行追加

**`CampaignReportPage.tsx`**:
- `allPostsSorted` の `useMemo` に `report?.lemon8_posts ?? []` を追加
- KPI計算にLemon8を含める

---

### Step 8: `VideoCompletedPage.tsx` の platform フィルター拡張

**ファイル**: `frontend/admin-dashboard/src/pages/submissions/video/VideoCompletedPage.tsx`

- `Platform` 型を `"instagram" | "tiktok" | "youtube" | "lemon8"` に拡張
- `<SelectItem value="lemon8">Lemon8</SelectItem>` 追加

---

### Step 9: OpenAPI 再生成と SDK 更新

反映順序:

1. backend schema更新マージ・deploy
2. `make api-dev` を実行（OpenAPI再生成 + `frontend/packages/apis/` のorval更新）
3. user-app/admin-dashboard双方で型エラー0確認後 frontend deploy

---

## 対象ファイル一覧

### Backend（変更あり）

| ファイル | 変更内容 | 優先度 |
|---|---|:---:|
| `backend/api/utils/view_count_utils.py` | Lemon8Post.read_count を加算 | 最高 |
| `backend/api/controllers/user/entries_controller.py` | latest_view_count にLemon8追加 | 高 |
| `backend/api/controllers/admin/entries_controller.py` | latest_view_count にLemon8追加 | 高 |
| `backend/api/controllers/public/judge_controller.py` | lemon8_postsフェッチ追加 | 高 |
| `backend/api/reports/data/campaign_report_data.py` | is_lemon8・lemon8_post_count・get_campaign_summary・get_creator_performance | 高 |
| `backend/api/schemas/campaign_report_schema.py` | lemon8_*フィールド追加 | 高 |
| `backend/api/schemas/post_history_schema.py` | Lemon8PostHistoryResponse追加 | 中 |

### Frontend（変更あり）

| ファイル | 変更内容 | 優先度 |
|---|---|:---:|
| `frontend/admin-dashboard/src/components/campaigns/report/reportConstants.ts` | Lemon8カラー定義 | 高 |
| `frontend/admin-dashboard/src/components/campaigns/report/ExecutiveSummary.tsx` | totalPosts・breakdown | 高 |
| `frontend/admin-dashboard/src/pages/campaigns/CampaignReportPage.tsx` | allPostsSorted・KPI | 高 |
| `frontend/admin-dashboard/src/pages/submissions/video/VideoCompletedPage.tsx` | platformフィルター拡張 | 中 |
| `frontend/user-app/src/pages/campaigns/posts/CampaignPostsPage.tsx` | Lemon8投稿追加（要仕様確認） | 低 |

### 変更不要（調査済み）

| ファイル | 理由 |
|---|---|
| `backend/api/jobs/video_view_reward_job.py` | 今回スコープ外 |
| `backend/api/models/video_campaign_model.py` | Lemon8Post/History/is_lemon8 完備 |
| `backend/api/schemas/video_entry_schema.py` | Lemon8PostResponse・URL検証完備 |
| `backend/api/controllers/public/campaigns_controller.py` | Lemon8サブクエリ・filter完備 |
| `backend/api/controllers/admin/users_controller.py` | アカウント管理完備 |
| `backend/api/controllers/user/campaigns_controller.py` | platform filter完備 |
| `backend/api/controllers/admin/companies_controller.py` | view集計に非関与 |
| `frontend/user-app/**`（ユーザー側ページ） | 大半実装済み |
| `frontend/admin-dashboard/src/components/video/ViewHistoryDialog.tsx` | Lemon8タブ実装済み |
| `frontend/packages/apis/` | OpenAPI更新後に自動生成 |

---

## テスト計画

### 単体テスト（`view_count_utils.py`）

| ケース | 入力 | 期待値 |
|---|---|---|
| A | ig=100, tt=200, l8=300 | total=600 |
| B | ig=None, tt=200, l8=None | total=200（0埋め確認） |
| C | read_count=-1 | 0（負数処理） |

### 結合テスト

- 同一entryを user/public/admin APIで取得し、view count 3指標が一致
- `campaign_report_data` の lemon8_views と admin画面の同値を比較
- `judge_controller` でLemon8投稿が正しく返ることを確認

### 回帰テスト

- IG/TikTokのみデータで従来値が不変
- Lemon8未連携キャンペーンで既存導線に影響なし

---

## 完了判定（DoD）

- [ ] `view_count_utils.py` でLemon8を含む合算が正しく動く
- [ ] user/public/admin APIで同一entryのview count 3指標が一致する
- [ ] `judge_controller` でLemon8投稿が返る
- [ ] campaign report APIとadmin表示値が一致する（Lemon8列含む）
- [ ] 通知にLemon8 URLが表示される
- [ ] OpenAPI再生成後にfrontend型エラー0
- [ ] IG/TikTokのみデータで従来値が不変（回帰確認）
