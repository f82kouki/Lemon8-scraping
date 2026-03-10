# Lemon8 Phase2 詳細作戦書
## アカウント連携 + URL提出 + ownership必須検証

> 作成日: 2026-03-09
> ベース: `lemon8統合作戦v3_審査反映版.md`
> 現状調査に基づいた実装差分・コード例・実装順を固定

---

## 0. 現状確認（実装済み vs 未実装）

### 実装済み（Phase1相当）
| ファイル | 内容 |
|---|---|
| `backend/api/services/lemon8_scraping_service.py` | フィード取得・投稿詳細解析・インフルエンサーデータ構築（`build_influencer_data`）。アバターURLは現在 `$UserDetail` JSON のみから取得 |
| `backend/api/services/lemon8_client.py` | HTTPクライアント（リトライ・停止ガード付き） |
| `backend/api/services/lemon8_parser.py` | HTML解析・投稿メトリクス抽出・著者アバターURL抽出（`extract_author_avatar_from_html`）。CSSセレクター優先→`$UserDetail` JSON フォールバックの2段階取得 |

> **⚠️ 接続待ち**: `extract_author_avatar_from_html` はまだ `build_influencer_data` から呼び出されていない。
> `build_influencer_data` に `html: str | None = None` パラメータを追加し、以下のように修正が必要:
>
> ```python
> from api.services.lemon8_parser import extract_author_avatar_from_html
>
> def build_influencer_data(
>     self, user_data: dict, category: str, post_id: str, html: str | None = None
> ) -> Optional[dict]:
>     # アバター: html があれば extract_author_avatar_from_html（CSS→JSONフォールバック済み）
>     #           なければ $UserDetail JSON から直接取得
>     avatar_url = extract_author_avatar_from_html(html) if html else None
>     if not avatar_url:
>         avatar = user_data.get("avatar")
>         if isinstance(avatar, dict):
>             url_list = avatar.get("urlList", [])
>             if url_list:
>                 avatar_url = url_list[0]
>         elif isinstance(avatar, str):
>             avatar_url = avatar
> ```
>
> `scrape_influencers_stream` / `scrape_influencers` 内の `build_influencer_data` 呼び出しにも `html=html` を渡す。

### Phase2 スコープ外（既存のLemon8インフルエンサー管理機能）
> 以下はキャンペーン参加者の投稿管理とは別の機能。Phase2 では変更不要。
| ファイル | 内容 |
|---|---|
| `backend/api/jobs/lemon8_scraping_job.py` | インフルエンサー情報をFirestoreへ収集するバッチ（Cloud Run Jobs） |
| `backend/api/routes/admin/lemon8_influencers_route.py` | インフルエンサー一覧・CSVエクスポート・削除 admin API |
| `backend/api/controllers/admin/lemon8_influencers_controller.py` | 上記ルートのコントローラー |

### Phase2 で追加が必要なもの（全て未実装）
| 対象 | 追加内容 |
|---|---|
| `VideoCampaignModel` | `is_lemon8: bool` フラグ |
| `user_model.py` | `Lemon8Account` モデル |
| `video_campaign_model.py` | `Lemon8Post`, `Lemon8PostHistory` モデル |
| `user_model.py > User` | `lemon8_accounts` リレーション |
| `auth_schema.py` | `Lemon8AccountResponse`, `Lemon8ConnectRequest/Response` |
| `auth_schema.py > ConnectedAccountsResponse` | `lemon8_accounts` フィールド |
| `user_schema.py` | （波及確認要） |
| `video_campaign_schema.py` | `is_lemon8` フラグ追加 |
| `video_entry_schema.py` | `lemon8_posts`, `Lemon8PostResponse` |
| `social_route.py` | `/lemon8/connect`, `/lemon8/{id}` DELETE |
| `social_controller.py` | connect_lemon8 / disconnect_lemon8 |
| `entries_route.py` | `validate-lemon8-url` エンドポイント |
| `entries_controller.py` | validate_lemon8_url ownership検証 |
| `alembic/versions/` | migration ファイル |
| Frontend: user-app | SnsAccountSection Lemon8セクション |
| Frontend: user-app | UrlSubmissionStep Lemon8 URL入力 |
| Frontend: admin-dashboard | UrlCheckTable / VideoPostInfo |

---

## 1. タスク一覧と実装順序

```
[STEP 1] DB: Lemon8Account / Lemon8Post / Lemon8PostHistory モデル追加
[STEP 2] DB: migration 作成・適用
[STEP 3] VideoCampaignModel に is_lemon8 追加
[STEP 4] スキーマ拡張: auth_schema / video_campaign_schema / video_entry_schema
[STEP 5] Social API: connect / disconnect エンドポイント
[STEP 6] Entries API: submit_url に lemon8_url 追加 + validate-lemon8-url 新設
[STEP 7] OpenAPI 再生成 + frontend/packages/apis 更新
[STEP 8] Frontend: user-app（SnsAccountSection / UrlSubmissionStep）
[STEP 9] Frontend: admin-dashboard（UrlCheckTable / VideoPostInfo）
```

---

## 2. STEP 1: DB モデル追加

### 2-1. `Lemon8Account` を `user_model.py` に追加

#### 追加場所
`YouTubeAccount` クラスの直後（235行目以降）

#### 追加コード
```python
class Lemon8Account(SQLModel, table=True):
    """
    Lemon8アカウントテーブル

    ユーザーのLemon8アカウント連携情報を管理します。
    OAuth非対応のため、ユーザー名（link_name）を手動入力で連携します。
    """

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)  # 連携ユーザーID

    # Lemon8アカウント識別子
    link_name: str = Field(index=True)  # Lemon8の @username 部分（@除去・lowercase化済み）
    display_name: str | None = None     # 表示名（スクレイピング取得時に補完）
    profile_url: str | None = None      # Lemon8プロフィールURL
    avatar_url: str | None = None       # アバター画像URL（validate-lemon8-url 時にスクレイピングで補完）

    # タイムスタンプ
    created_at: datetime = Field(default_factory=now_jst_as_utc)
    updated_at: datetime = Field(
        default_factory=now_jst_as_utc,
        sa_column=Column(
            "updated_at",
            DateTime,
            default=now_jst_as_utc,
            onupdate=now_jst_as_utc,
        ),
    )
    deleted_at: datetime | None = Field(default=None, index=True)

    # リレーション
    user: "User" = Relationship(back_populates="lemon8_accounts")
    posts: list["Lemon8Post"] = Relationship(
        back_populates="lemon8_account",
        sa_relationship_kwargs={"foreign_keys": "Lemon8Post.lemon8_account_id"},
    )
```

#### `User` クラスのリレーション追記（64〜67行目付近）

```python
    lemon8_accounts: list["Lemon8Account"] = Relationship(back_populates="user")
```

#### `TYPE_CHECKING` の import 追記（19行目付近）

```python
    from .video_campaign_model import VideoEntry, InstagramPost, TikTokPost, YouTubePost, Lemon8Post
```

---

### 2-2. `Lemon8Post` / `Lemon8PostHistory` を `video_campaign_model.py` に追加

#### 追加場所
`YouTubePost` クラスの直後（555行目付近）

#### `Lemon8Post` 追加コード
```python
class Lemon8Post(SQLModel, table=True):
    """
    Lemon8投稿テーブル

    スクレイピングで取得したLemon8投稿データを管理。
    Lemon8Account と VideoEntry の両方に紐づく。
    """

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)

    # 外部キー
    video_entry_id: UUID = Field(foreign_key="videoentry.id", index=True)
    lemon8_account_id: UUID = Field(foreign_key="lemon8account.id", index=True)

    # Lemon8投稿識別子（スクレイピング取得）
    group_id: str = Field(index=True)   # $ArticleDetail+{groupId} から抽出したID
    post_url: str | None = None         # 投稿URL（ユーザー提出値）
    article_class: str | None = None    # 投稿カテゴリクラス（Lemon8内部分類）
    publish_time: datetime | None = None  # 投稿日時（UTC）

    # エンゲージメント統計（スクレイピング更新）
    read_count: int = Field(default=0)   # 閲覧数（= view_count 相当）
    digg_count: int = Field(default=0)   # いいね数
    favorite_count: int = Field(default=0)  # お気に入り数
    comment_count: int = Field(default=0)   # コメント数

    # 審査状態
    approval_status: str | None = Field(default=None, index=True)  # "pending" | "approved" | "rejected"
    rejection_reason: str | None = None
    review_comment: str | None = None
    reviewed_at: datetime | None = None

    # タイムスタンプ
    created_at: datetime = Field(default_factory=now_jst_as_utc)
    updated_at: datetime = Field(
        default_factory=now_jst_as_utc,
        sa_column=Column(
            "updated_at",
            DateTime,
            default=now_jst_as_utc,
            onupdate=now_jst_as_utc,
        ),
    )
    deleted_at: datetime | None = Field(default=None, index=True)

    # リレーション
    video_entry: "VideoEntry" = Relationship(
        back_populates="lemon8_posts",
        sa_relationship_kwargs={"foreign_keys": "Lemon8Post.video_entry_id"},
    )
    lemon8_account: "Lemon8Account" = Relationship(
        back_populates="posts",
        sa_relationship_kwargs={"foreign_keys": "Lemon8Post.lemon8_account_id"},
    )

    # テーブル制約（候補A: group_id 単体ユニーク）
    __table_args__ = (
        UniqueConstraint("group_id", name="uq_lemon8_post_group_id"),
    )
```

> ⚠️ `group_id` のユニーク制約は作戦書v3の「候補A」を採用。
> `(video_entry_id, group_id)` 複合ユニーク（候補B）が必要な場合は `__table_args__` を変更する。

#### `Lemon8PostHistory` 追加コード
```python
class Lemon8PostHistory(SQLModel, table=True):
    """
    Lemon8投稿履歴テーブル

    定期更新ジョブによって記録される時系列の閲覧数履歴。
    """

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    lemon8_post_id: UUID = Field(foreign_key="lemon8post.id", index=True)

    # スナップショット値
    read_count: int = Field(default=0)
    digg_count: int = Field(default=0)
    favorite_count: int = Field(default=0)
    comment_count: int = Field(default=0)
    recorded_at: datetime = Field(default_factory=now_jst_as_utc, index=True)

    created_at: datetime = Field(default_factory=now_jst_as_utc)
```

#### `VideoEntry` クラスへのリレーション追記

`VideoEntry` クラス内の `youtube_posts` リレーション直後に追加:
```python
    lemon8_posts: list["Lemon8Post"] = Relationship(
        back_populates="video_entry",
        sa_relationship_kwargs={"foreign_keys": "Lemon8Post.video_entry_id"},
    )
```

#### `TYPE_CHECKING` の import 追記（user_model 側）
`video_campaign_model.py` の先頭 TYPE_CHECKING ブロックに `Lemon8Account` を追加済みであれば不要。
`user_model.py` 側も同様に `Lemon8Post` を追加する。

---

### 2-3. `models/__init__.py` への登録

```python
from .user_model import ..., Lemon8Account
from .video_campaign_model import ..., Lemon8Post, Lemon8PostHistory
```

---

## 3. STEP 2: Alembic migration

```bash
cd backend
alembic revision --autogenerate -m "add_lemon8_account_post_history"
```

生成後に必ず確認すること:
- `lemon8account` テーブル作成
- `lemon8post` テーブル作成（`uq_lemon8_post_group_id` 制約付き）
- `lemon8posthistory` テーブル作成
- `videocampaign.is_lemon8` カラム追加（STEP 3 と合わせて1回の migration でまとめるのが望ましい）

---

## 4. STEP 3: `VideoCampaignModel` に `is_lemon8` 追加

### 変更ファイル: `backend/api/models/video_campaign_model.py`

#### 変更箇所（67〜70行目）

```python
    # プラットフォーム設定
    is_instagram: bool = Field(default=False)  # Instagram投稿可能
    is_tiktok: bool = Field(default=False)     # TikTok投稿可能
    is_youtube: bool = Field(default=False)    # YouTube投稿可能
    is_lemon8: bool = Field(default=False)     # Lemon8投稿可能  ← 追加
```

---

## 5. STEP 4: スキーマ拡張

### 5-1. `auth_schema.py` — Lemon8 アカウントスキーマ追加

#### 追加クラス群

```python
class Lemon8AccountResponse(BaseModel):
    """Lemon8アカウント詳細レスポンス"""
    id: UUID = Field(..., description="アカウントID")
    user_id: UUID = Field(..., description="ユーザーID")
    link_name: str = Field(..., description="Lemon8ユーザー名（正規化済み）")
    display_name: str | None = Field(None, description="表示名")
    profile_url: str | None = Field(None, description="プロフィールURL")
    avatar_url: str | None = Field(None, description="アバター画像URL")
    created_at: datetime = Field(..., description="作成日時")
    updated_at: datetime = Field(..., description="更新日時")


class Lemon8ConnectRequest(BaseModel):
    """Lemon8アカウント連携リクエスト"""
    username_or_url: str = Field(
        ...,
        description="Lemon8ユーザー名（@あり/なし）またはプロフィールURL"
    )


class Lemon8ConnectResponse(BaseModel):
    """Lemon8アカウント連携レスポンス"""
    success: bool = Field(..., description="連携成功フラグ")
    account: Lemon8AccountResponse = Field(..., description="連携アカウント情報")
    message: str = Field(..., description="メッセージ")
```

#### `ConnectedAccountsResponse` の拡張（101行目付近）

```python
class ConnectedAccountsResponse(BaseModel):
    instagram_accounts: list[InstagramAccountResponse] = Field(default_factory=list)
    tiktok_accounts: list[TikTokAccountResponse] = Field(default_factory=list)
    youtube_accounts: list[YouTubeAccountResponse] = Field(default_factory=list)
    lemon8_accounts: list[Lemon8AccountResponse] = Field(default_factory=list)  # ← 追加
```

---

### 5-2. `video_campaign_schema.py` — `is_lemon8` 追加

#### `VideoCampaignCreate` (41〜43行目)

```python
    is_instagram: bool = False
    is_tiktok: bool = False
    is_youtube: bool = False
    is_lemon8: bool = False  # ← 追加
```

#### `VideoCampaignUpdate` (87〜89行目)

```python
    is_instagram: bool | None = None
    is_tiktok: bool | None = None
    is_youtube: bool | None = None
    is_lemon8: bool | None = None  # ← 追加
```

#### `VideoCampaignResponse` にも `is_lemon8` を追加（Response クラスを確認して追記）

---

### 5-3. `video_entry_schema.py` — `Lemon8PostResponse` + `VideoEntryResponse` 拡張

#### 追加クラス

```python
class Lemon8PostResponse(SQLModel):
    """Lemon8投稿レスポンス"""
    id: UUID
    video_entry_id: UUID
    lemon8_account_id: UUID
    group_id: str
    post_url: str | None = None
    article_class: str | None = None
    publish_time: datetime | None = None
    # エンゲージメント統計
    read_count: int = 0
    digg_count: int = 0
    favorite_count: int = 0
    comment_count: int = 0
    approval_status: str | None = None
    rejection_reason: str | None = None
    review_comment: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
```

#### `VideoEntryResponse` への追記（183〜184行目付近）

```python
    instagram_posts: list[InstagramPostResponse] = []
    tiktok_posts: list[TikTokPostResponse] = []
    youtube_posts: list[YouTubePostResponse] = []
    lemon8_posts: list[Lemon8PostResponse] = []  # ← 追加
```

---

### 5-4. URL提出スキーマ — `lemon8_url` 追加

`video_entry_schema.py` 内に URL提出 Request スキーマが存在する場合（確認して追記）:

```python
class SubmitUrlRequest(SQLModel):
    instagram_url: str | None = None
    tiktok_url: str | None = None
    lemon8_url: str | None = None    # ← 追加
    # バリデーション: 3つのうち1つ以上必須
```

---

## 6. STEP 5: Social API — Lemon8 connect / disconnect

### 6-1. `social_route.py` への追加

#### import に追加
```python
from api.schemas.auth_schema import (
    ...,
    Lemon8ConnectRequest,
    Lemon8ConnectResponse,
)
```

#### エンドポイント追加（265行目以降）

```python
@router.post(
    "/lemon8/connect",
    response_model=Lemon8ConnectResponse,
    responses={
        400: {"model": SocialConnectErrorResponse, "description": "入力エラー"},
        500: {"model": SocialConnectErrorResponse, "description": "サーバーエラー"},
    },
)
async def connect_lemon8_account(
    request: Lemon8ConnectRequest,
    user: User = Depends(line_auth),
    session: AsyncSession = Depends(get_session),
):
    """Lemon8アカウントを連携（ユーザー名 / プロフィールURL）"""
    controller = UserSocialController(session, user)
    try:
        result = await controller.connect_lemon8_account(request.username_or_url)
        return {"success": True, "account": result, "message": "Lemon8アカウントの連携が完了しました"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        logger.error(f"Error connecting Lemon8 account: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="サーバーエラーが発生しました") from None


@router.delete("/lemon8/{account_id}")
async def disconnect_lemon8_account(
    account_id: UUID,
    user: User = Depends(line_auth),
    session: AsyncSession = Depends(get_session),
):
    """Lemon8アカウントの連携を解除"""
    controller = UserSocialController(session, user)
    try:
        success = await controller.disconnect_lemon8_account(account_id)
        if success:
            return {"message": "Lemon8 account disconnected successfully"}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lemon8 account not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
```

---

### 6-2. `social_controller.py` — Lemon8 connect / disconnect 実装

#### 正規化ユーティリティ（クラス外に定義）

```python
import re
from urllib.parse import unquote, urlparse

def normalize_lemon8_link_name(username_or_url: str) -> str:
    """
    Lemon8 ユーザー名を正規化する
    - @除去
    - lowercase化
    - URL末尾 / 除去
    - URL decode
    - 全角空白除去

    例:
        "@JohnDoe"           -> "johndoe"
        "https://www.lemon8-app.com/@johndoe/" -> "johndoe"
        "　JohnDoe　"         -> "johndoe"
    """
    s = unquote(username_or_url).strip()
    s = s.replace("\u3000", "").replace(" ", "")  # 全角・半角空白除去

    # URL形式の場合はパス部分からユーザー名を抽出
    if s.startswith("http"):
        parsed = urlparse(s)
        path = parsed.path.rstrip("/")
        # /@username または /username の形式
        s = re.sub(r"^/@?", "", path.split("/")[-1])
    else:
        s = s.lstrip("@")

    return s.lower()
```

#### `connect_lemon8_account` メソッド

```python
async def connect_lemon8_account(self, username_or_url: str) -> dict:
    """Lemon8アカウントを連携"""
    link_name = normalize_lemon8_link_name(username_or_url)

    if not link_name:
        raise ValueError("有効なLemon8ユーザー名またはURLを入力してください")

    # 重複チェック（同ユーザーの同 link_name 連携を防ぐ）
    existing = await self.session.exec(
        select(Lemon8Account).where(
            Lemon8Account.user_id == self.user.id,
            Lemon8Account.link_name == link_name,
            Lemon8Account.deleted_at.is_(None),
        )
    )
    if existing.first():
        raise ValueError("このLemon8アカウントはすでに連携されています")

    account = Lemon8Account(
        user_id=self.user.id,
        link_name=link_name,
        profile_url=f"https://www.lemon8-app.com/@{link_name}",
    )
    self.session.add(account)
    await self.session.commit()
    await self.session.refresh(account)

    # Activity Log 記録
    await log_activity(self.session, self.user.id, ActionType.LEMON8_CONNECT)

    return {
        "id": str(account.id),
        "user_id": str(account.user_id),
        "link_name": account.link_name,
        "display_name": account.display_name,
        "profile_url": account.profile_url,
        "avatar_url": account.avatar_url,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
    }
```

#### `disconnect_lemon8_account` メソッド

```python
async def disconnect_lemon8_account(self, account_id: UUID) -> bool:
    """Lemon8アカウントの連携を解除（ソフトデリート）"""
    result = await self.session.exec(
        select(Lemon8Account).where(
            Lemon8Account.id == account_id,
            Lemon8Account.user_id == self.user.id,
            Lemon8Account.deleted_at.is_(None),
        )
    )
    account = result.first()
    if not account:
        return False

    account.deleted_at = now_jst_as_utc()
    self.session.add(account)
    await self.session.commit()

    # Activity Log 記録
    await log_activity(self.session, self.user.id, ActionType.LEMON8_DISCONNECT)

    return True
```

> **注意**: Instagram の disconnect では UNIQUE 制約回避のため `instagram_user_id` を `deleted_{id}_{timestamp}` に書き換えているが、
> `Lemon8Account.link_name` にはグローバルな UNIQUE 制約がないため、ソフトデリートのみで問題なし。
> ただし、同一ユーザーが同じ `link_name` を再連携するケースは connect 時の重複チェック（`deleted_at.is_(None)` 条件）で自然に許可される。

#### `ActionType` enum への追加

`backend/api/models/activity_log_model.py`（または `ActionType` が定義されているファイル）に以下を追加:

```python
class ActionType(str, Enum):
    # ... 既存の値 ...
    LEMON8_CONNECT = "lemon8_connect"       # ← 追加
    LEMON8_DISCONNECT = "lemon8_disconnect" # ← 追加
```

> `connect_lemon8_account` / `disconnect_lemon8_account` メソッド内で `ActionType.LEMON8_CONNECT` / `ActionType.LEMON8_DISCONNECT` を参照するため、
> この追加がないとサーバー起動時または実行時に `AttributeError` が発生する。

#### `get_connected_accounts` の拡張

```python
async def get_connected_accounts(self) -> dict:
    # ... 既存の instagram / tiktok / youtube 取得処理 ...

    # Lemon8 追加
    lemon8_result = await self.session.exec(
        select(Lemon8Account).where(
            Lemon8Account.user_id == self.user.id,
            Lemon8Account.deleted_at.is_(None),
        )
    )
    lemon8_accounts = lemon8_result.all()

    return {
        # ... 既存フィールド ...
        "lemon8_accounts": [
            {
                "id": str(a.id),
                "user_id": str(a.user_id),
                "link_name": a.link_name,
                "display_name": a.display_name,
                "profile_url": a.profile_url,
                "avatar_url": a.avatar_url,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            }
            for a in lemon8_accounts
        ],
    }
```

---

## 7. STEP 6: Entries API — `lemon8_url` submit + `validate-lemon8-url` 新設

### 7-1. `entries_route.py` — validate エンドポイント追加

既存の `validate-tiktok-url` / `validate-instagram-url` と同じパターンで追加:

```python
@router.post("/video/{entry_id}/validate-lemon8-url")
async def validate_lemon8_url(
    entry_id: UUID,
    request: ValidateLemon8UrlRequest,   # スキーマで定義
    user: User = Depends(line_auth),
    session: AsyncSession = Depends(get_session),
):
    """Lemon8 URL の ownership 検証（submit 前に呼び出す）"""
    controller = UserEntriesController(session, user)
    try:
        result = await controller.validate_lemon8_url(entry_id, request.lemon8_url)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
```

スキーマ追加（`video_entry_schema.py`）:
```python
class ValidateLemon8UrlRequest(SQLModel):
    lemon8_url: str = Field(..., description="検証するLemon8投稿URL")

class ValidateLemon8UrlResponse(SQLModel):
    is_valid: bool
    group_id: str | None = None
    link_name: str | None = None
    message: str
```

---

### 7-2. `entries_controller.py` — `validate_lemon8_url` 実装

#### ownership 検証ロジック

```python
async def validate_lemon8_url(self, entry_id: UUID, lemon8_url: str) -> dict:
    """
    Lemon8 URL の ownership を検証する

    検証手順:
    1. entry に紐づく campaign が is_lemon8=True か確認
    2. URL から link_name を抽出・正規化
    3. ユーザーの Lemon8Account.link_name と一致するか確認
    4. 投稿 HTML をスクレイピングして group_id を抽出
    5. アバター画像を抽出して Lemon8Account.avatar_url を補完（未設定の場合のみ）
    """
    # 1. エントリー取得
    entry = await self._get_entry(entry_id)
    campaign = entry.video_campaign

    if not campaign.is_lemon8:
        raise ValueError("このキャンペーンはLemon8投稿に対応していません")

    # 2. URLから link_name を抽出
    # Lemon8 URL 形式: https://www.lemon8-app.com/@username/post/GROUP_ID
    url_link_name = _extract_link_name_from_lemon8_url(lemon8_url)
    group_id = _extract_group_id_from_lemon8_url(lemon8_url)

    if not url_link_name:
        raise ValueError("有効なLemon8投稿URLを入力してください")

    # 3. ownership チェック: ユーザーの連携アカウントと比較
    lemon8_accounts = await self.session.exec(
        select(Lemon8Account).where(
            Lemon8Account.user_id == self.user.id,
            Lemon8Account.deleted_at.is_(None),
        )
    )
    accounts = lemon8_accounts.all()

    if not accounts:
        raise ValueError("Lemon8アカウントを先に連携してください")

    normalized_url_link_name = normalize_lemon8_link_name(url_link_name)
    matched_account = next(
        (a for a in accounts if a.link_name == normalized_url_link_name), None
    )

    if not matched_account:
        raise ValueError(
            f"URLのLemon8ユーザー名（@{normalized_url_link_name}）が"
            "連携アカウントと一致しません"
        )

    # 4 & 5. 投稿 HTML を取得 → group_id 確定 + アバター補完
    from api.services.lemon8_client import Lemon8Client
    from api.services.lemon8_parser import extract_author_avatar_from_html

    client = Lemon8Client()
    fetch_result = await client.fetch_with_retry(lemon8_url)

    if fetch_result.status == "success" and fetch_result.html:
        html = fetch_result.html

        # アバター未設定の場合のみ補完
        # extract_author_avatar_from_html は CSS セレクター優先 → $UserDetail JSON フォールバックの2段階で取得
        if not matched_account.avatar_url:
            avatar_url = extract_author_avatar_from_html(html)
            if avatar_url:
                matched_account.avatar_url = avatar_url
                self.session.add(matched_account)
                await self.session.commit()
                logger.info(
                    f"Lemon8アバターを補完: link_name={matched_account.link_name}"
                )

    return {
        "is_valid": True,
        "group_id": group_id,
        "link_name": normalized_url_link_name,
        "message": "Lemon8 URLの検証が完了しました",
    }
```

#### URL 解析ユーティリティ関数

```python
def _extract_link_name_from_lemon8_url(url: str) -> str | None:
    """
    https://www.lemon8-app.com/@username/post/GROUP_ID
    → "username"
    """
    import re
    match = re.search(r"lemon8-app\.com/@([^/]+)", url)
    return match.group(1) if match else None


def _extract_group_id_from_lemon8_url(url: str) -> str | None:
    """
    https://www.lemon8-app.com/@username/post/GROUP_ID
    → "GROUP_ID"
    """
    import re
    match = re.search(r"/post/(\d+)", url)
    return match.group(1) if match else None
```

---

### 7-3. `submit_url` へ `lemon8_url` 追加

既存の submit_url エンドポイントのリクエストスキーマに `lemon8_url` を追加。
保存ロジック（entries_controller.py の `submit_url`）でも `lemon8_post` レコード作成処理を追加:

```python
if lemon8_url and campaign.is_lemon8:
    group_id = _extract_group_id_from_lemon8_url(lemon8_url)
    link_name_from_url = _extract_link_name_from_lemon8_url(lemon8_url)

    # 連携アカウント取得
    lemon8_account = await self._get_lemon8_account_by_link_name(
        self.user.id, normalize_lemon8_link_name(link_name_from_url)
    )

    # Lemon8Post 作成（group_id ユニーク制約によって重複は DB 側で弾く）
    lemon8_post = Lemon8Post(
        video_entry_id=entry.id,
        lemon8_account_id=lemon8_account.id,
        group_id=group_id,
        post_url=lemon8_url,
        approval_status="pending",
    )
    self.session.add(lemon8_post)
```

#### `_get_lemon8_account_by_link_name` ヘルパーメソッド

上記 `submit_url` 内で呼び出す private メソッドを `entries_controller.py` に追加:

```python
async def _get_lemon8_account_by_link_name(self, user_id: UUID, link_name: str) -> "Lemon8Account":
    """
    連携済み Lemon8Account を link_name で取得する。
    見つからない場合は ValueError を送出（submit_url で ownership チェック済みのためここでは基本的に発生しない）。
    """
    result = await self.session.exec(
        select(Lemon8Account).where(
            Lemon8Account.user_id == user_id,
            Lemon8Account.link_name == link_name,
            Lemon8Account.deleted_at.is_(None),
        )
    )
    account = result.first()
    if not account:
        raise ValueError(
            f"連携されたLemon8アカウント（@{link_name}）が見つかりません。"
            "先にSNS設定でLemon8アカウントを連携してください。"
        )
    return account
```

> `validate_lemon8_url` で ownership チェック済みなので通常は見つかるはずだが、
> アカウント削除・連携解除のタイムラグ等に備えてエラーハンドリングを入れておく。

---

## 8. STEP 7: OpenAPI 再生成

```bash
cd backend
# FastAPI サーバー起動 or generate コマンドで openapi.json 出力
# 例:
python -c "
from main import app
import json
from fastapi.openapi.utils import get_openapi
spec = get_openapi(title=app.title, version=app.version, routes=app.routes)
json.dump(spec, open('../openapi.json', 'w'), ensure_ascii=False, indent=2)
"

# frontend の api クライアント再生成
cd frontend/packages/apis
# orval / openapi-generator 等のコマンドを実行
```

> 既存の再生成手順に従う（Makefile 等を確認）

---

## 9. STEP 8: Frontend — user-app

### 9-1. `user.types.ts` — `SnsAccountSectionProps` に Lemon8 action を追加

#### 変更ファイル: `frontend/user-app/src/types/user.types.ts`

```typescript
export interface SnsAccountSectionProps {
  accountsData?: ConnectedAccountsResponse;
  loading?: boolean;
  onInstagramAction: (action: "connect" | "disconnect" | "view_media") => void;
  onTikTokAction: (action: "connect" | "disconnect" | "view_videos" | "reconnect") => void;
  onYouTubeAction: (action: "connect" | "disconnect" | "view_videos") => void;
  onLemon8Action: (action: "connect" | "disconnect") => void;  // ← 追加
}
```

---

### 9-2. `SnsAccountSection.tsx` — Lemon8 セクション追加

#### 変更ファイル: `frontend/user-app/src/components/user/sections/SnsAccountSection.tsx`

**① props 追加（4行目付近）**

```tsx
export const SnsAccountSection = ({
  accountsData,
  loading,
  onInstagramAction,
  onTikTokAction,
  onYouTubeAction,
  onLemon8Action,         // ← 追加
}: SnsAccountSectionProps) => {
```

**② skeleton ブロックに Lemon8 用の `<SectionSkeleton />` を追加（loading ブロック内）**

```tsx
if (loading) {
  return (
    <>
      <section className="mt-3 px-4 py-4 bg-white"><SectionSkeleton /></section>
      <section className="mt-3 px-4 py-4 bg-white"><SectionSkeleton /></section>
      <section className="mt-3 px-4 py-4 bg-white"><SectionSkeleton /></section>
      <section className="mt-3 px-4 py-4 bg-white"><SectionSkeleton /></section>  {/* ← 追加 */}
    </>
  );
}
```

**③ アカウント変数を追加（27〜29行目付近）**

```tsx
const instagramAccount = accountsData?.instagram_accounts?.[0];
const tiktokAccount = accountsData?.tiktok_accounts?.[0];
const youtubeAccount = accountsData?.youtube_accounts?.[0];
const lemon8Account = accountsData?.lemon8_accounts?.[0];  // ← 追加
```

**④ Lemon8 セクションを YouTube セクションの直後（365行目以降）に追加**

```tsx
{/* Lemon8 Section */}
<section className="mt-3 px-4 py-4 bg-white">
  <div className="flex items-center justify-between mb-3">
    <h3 className="text-base font-medium">Lemon8連携</h3>
    {lemon8Account && (
      <button
        type="button"
        onClick={() => onLemon8Action("disconnect")}
        className="text-xs text-red-500 flex items-center"
      >
        <i className="ri-link-unlink ri-sm mr-0.5" />
        連携解除
      </button>
    )}
  </div>

  {lemon8Account ? (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center">
          {/* アバター: スクレイピング取得済みなら img、未取得なら固定アイコン */}
          {lemon8Account.avatar_url ? (
            <img
              src={lemon8Account.avatar_url}
              alt={lemon8Account.link_name}
              className="w-10 h-10 rounded-full object-cover flex-shrink-0"
            />
          ) : (
            <div className="w-10 h-10 flex items-center justify-center bg-yellow-400 rounded-lg flex-shrink-0">
              <span className="text-white text-xs font-bold">L8</span>
            </div>
          )}

          <div className="ml-3 pr-1">
            {lemon8Account.profile_url ? (
              <a
                href={lemon8Account.profile_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium hover:text-app-primary transition-colors flex items-center gap-1"
              >
                @{lemon8Account.link_name}
                <i className="ri-external-link-line text-xs" />
              </a>
            ) : (
              <p className="text-sm font-medium">@{lemon8Account.link_name}</p>
            )}
            {lemon8Account.display_name && (
              <p className="text-xs text-app-text-gray">{lemon8Account.display_name}</p>
            )}
          </div>
        </div>
        <span className="text-xs px-2 py-1 bg-app-primary/10 text-app-primary rounded-full flex-shrink-0">
          連携済み
        </span>
      </div>
    </div>
  ) : (
    <EmptyState
      icon="ri-emotion-line"
      message="Lemon8アカウントが連携されていません"
      actionText="連携する"
      onAction={() => onLemon8Action("connect")}
    />
  )}
</section>
```

---

### 9-3. Lemon8 連携モーダルの実装場所

`SnsAccountSection.tsx` を呼び出している親コンポーネント（Mypage 系）で `onLemon8Action` ハンドラを実装する。
YouTube の `onYouTubeAction("connect")` が URL 入力ダイアログを開くのと同じパターン:

```tsx
// 親コンポーネント（例: MySnsPage.tsx 相当）での実装
const [isLemon8ConnectDialogOpen, setIsLemon8ConnectDialogOpen] = useState(false);
const [lemon8Input, setLemon8Input] = useState("");
const [isConnectingLemon8, setIsConnectingLemon8] = useState(false);

const handleLemon8Action = async (action: "connect" | "disconnect") => {
  if (action === "connect") {
    setIsLemon8ConnectDialogOpen(true);
  } else if (action === "disconnect" && lemon8Account) {
    await connectLemon8Mutation.mutateAsync({ /* DELETE */ });
    await refetchAccounts();
  }
};

const handleLemon8Connect = async () => {
  if (!lemon8Input.trim()) return;
  setIsConnectingLemon8(true);
  try {
    await connectLemon8AccountMutation.mutateAsync({
      data: { username_or_url: lemon8Input.trim() }
    });
    toast({ title: "連携完了", description: "Lemon8アカウントを連携しました" });
    setIsLemon8ConnectDialogOpen(false);
    setLemon8Input("");
    await refetchAccounts();
  } catch (error) {
    toast({ title: "エラー", description: getApiErrorMessage(error, "連携に失敗しました"), variant: "destructive" });
  } finally {
    setIsConnectingLemon8(false);
  }
};
```

**連携ダイアログ JSX（YouTube `connect_youtube_channel` と同じ Dialog パターン）:**

```tsx
<Dialog open={isLemon8ConnectDialogOpen} onOpenChange={setIsLemon8ConnectDialogOpen}>
  <DialogContent className="sm:max-w-[400px]">
    <DialogHeader>
      <DialogTitle>Lemon8アカウントを連携</DialogTitle>
      <DialogDescription>
        Lemon8のユーザー名またはプロフィールURLを入力してください
      </DialogDescription>
    </DialogHeader>
    <div className="space-y-4 py-4">
      <div className="space-y-2">
        <Label>ユーザー名 / プロフィールURL</Label>
        <Input
          placeholder="@username または https://www.lemon8-app.com/@username"
          value={lemon8Input}
          onChange={(e) => setLemon8Input(e.target.value)}
        />
        <p className="text-xs text-gray-500">
          例: @johndoe / johndoe / https://www.lemon8-app.com/@johndoe
        </p>
      </div>
    </div>
    <DialogFooter>
      <Button variant="outline" onClick={() => setIsLemon8ConnectDialogOpen(false)}>
        キャンセル
      </Button>
      <Button onClick={handleLemon8Connect} disabled={isConnectingLemon8 || !lemon8Input.trim()}>
        {isConnectingLemon8 ? "連携中..." : "連携する"}
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

---

### 9-4. `UrlSubmissionStep.tsx` — Lemon8 全対応

#### 変更ファイル: `frontend/user-app/src/pages/campaigns/video/steps/UrlSubmissionStep.tsx`

**① import 追加（30〜39行目付近）**

```tsx
import {
  type VideoEntryResponse,
  type VideoCampaignResponse,
  useSubmitUrlApiUserEntriesVideoEntryIdUrlPost,
  useGetConnectedAccountsApiUserSocialAccountsGet,
  useValidateInstagramUrlApiUserEntriesVideoEntryIdValidateInstagramUrlPost,
  useValidateTiktokUrlApiUserEntriesVideoEntryIdValidateTiktokUrlPost,
  useValidateYoutubeUrlApiUserEntriesVideoEntryIdValidateYoutubeUrlPost,
  useValidateLemon8UrlApiUserEntriesVideoEntryIdValidateLemon8UrlPost,  // ← 追加（OpenAPI再生成後）
  useGetBankAccountsApiUserBankAccountsGet
} from "@vimmy/apis";
```

**② バリデーションレスポンス型を追加（117行目付近）**

```typescript
interface Lemon8UrlValidationResponse {
  is_valid: boolean;
  message: string;
  link_name: string;      // 正規化済みユーザー名
  group_id: string | null; // 投稿ID
}
```

**③ State 追加（211〜235行目付近）**

```tsx
const [lemon8Url, setLemon8Url] = useState("");
const [isValidatingLemon8, setIsValidatingLemon8] = useState(false);
const [lemon8ValidationError, setLemon8ValidationError] = useState<string | null>(null);
const [lemon8PostData, setLemon8PostData] = useState<{ link_name: string; group_id: string | null } | null>(null);
```

**④ `confirmedPlatforms` の型に `'lemon8'` を追加（238〜239行目付近）**

```tsx
const [currentConfirmPlatform, setCurrentConfirmPlatform] = useState<
  'instagram' | 'tiktok' | 'youtube' | 'lemon8' | null
>(null);
const [confirmedPlatforms, setConfirmedPlatforms] = useState<
  Set<'instagram' | 'tiktok' | 'youtube' | 'lemon8'>
>(new Set());
// 確認ダイアログ用 lemon8 URL state
const [validatedLemon8Url, setValidatedLemon8Url] = useState("");
```

**⑤ キャンペーン対応フラグ追加（244〜247行目付近）**

```tsx
const isInstagramEnabled = entry.video_campaign?.is_instagram || false;
const isTikTokEnabled = entry.video_campaign?.is_tiktok || false;
const isYouTubeEnabled = entry.video_campaign?.is_youtube || false;
const isLemon8Enabled = entry.video_campaign?.is_lemon8 || false;  // ← 追加
```

**⑥ `connectedAccounts` に lemon8 を追加（291〜296行目付近）**

```tsx
const connectedAccounts = {
  instagram: connectedAccountsData?.instagram_accounts?.[0],
  tiktok: connectedAccountsData?.tiktok_accounts?.[0],
  youtube: connectedAccountsData?.youtube_accounts?.[0],
  lemon8: connectedAccountsData?.lemon8_accounts?.[0],  // ← 追加
};
```

**⑦ クライアントサイド URL フォーマット検証関数 `validateUrl` に lemon8 を追加（307〜336行目付近）**

```typescript
} else if (platform === "lemon8") {
  // https://www.lemon8-app.com/@username/post/1234567890
  const lemon8Pattern = /lemon8-app\.com\/@[^/]+\/post\/\d+/;
  if (!lemon8Pattern.test(url)) {
    return "正しいLemon8の投稿URLを入力してください（例: https://www.lemon8-app.com/@ユーザー名/post/投稿ID）";
  }
}
```

**⑧ `handleValidate` 関数に Lemon8 バリデーションブロックを追加**

```tsx
// Lemon8 URLのバリデーション（YouTube ブロックの直後）
let cleanedLemon8Url = "";
if (lemon8Url && isLemon8Enabled) {
  cleanedLemon8Url = cleanUrl(lemon8Url);

  // 未連携チェック
  if (!connectedAccounts.lemon8) {
    toast({
      title: "エラー",
      description: "Lemon8アカウントを先に連携してください",
      variant: "destructive"
    });
    return;
  }

  const lemon8Error = validateUrl(cleanedLemon8Url, "lemon8");
  if (lemon8Error) {
    toast({ title: "エラー", description: lemon8Error, variant: "destructive" });
    return;
  }

  setIsValidatingLemon8(true);
  setLemon8ValidationError(null);
  try {
    const rawValidationResult = await validateLemon8UrlMutation.mutateAsync({
      entryId: entryId,
      data: { lemon8_url: cleanedLemon8Url }
    });
    const validationResult = parseValidationResponse<Lemon8UrlValidationResponse>(
      rawValidationResult,
      "link_name" as "account_username"  // parseValidationResponse の accountKey 引数
    );
    if (!validationResult || !validationResult.is_valid) {
      toast({
        title: "エラー",
        description: validationResult?.message || "このLemon8投稿URLは連携されているアカウントの投稿ではありません。",
        variant: "destructive"
      });
      setLemon8ValidationError(validationResult?.message || "連携アカウントと一致しません");
      return;
    }
    setLemon8PostData({ link_name: validationResult.link_name as string, group_id: validationResult.group_id as string | null });
    toast({ title: "確認完了", description: `Lemon8投稿URLが確認されました (@${validationResult.link_name})` });
  } catch (error: unknown) {
    const errorMessage = getApiErrorMessage(error, "Lemon8 URLの検証に失敗しました。もう一度お試しください。");
    toast({ title: "エラー", description: errorMessage, variant: "destructive" });
    return;
  } finally {
    setIsValidatingLemon8(false);
  }
}
```

**⑨ バリデーション成功後の確認ダイアログ制御に lemon8 を追加**

```tsx
setValidatedLemon8Url(cleanedLemon8Url);

// 確認する順番（Instagram → TikTok → YouTube → Lemon8）
if (cleanedInstagramUrl) {
  setCurrentConfirmPlatform('instagram');
} else if (cleanedTiktokUrl) {
  setCurrentConfirmPlatform('tiktok');
} else if (cleanedYoutubeUrl) {
  setCurrentConfirmPlatform('youtube');
} else if (cleanedLemon8Url) {
  setCurrentConfirmPlatform('lemon8');
}
```

**⑩ `handleConfirmSubmit` 内の次プラットフォーム判定に lemon8 を追加**

```tsx
// youtube の後、もしくは instagram/tiktok の後に lemon8 がある場合
if (currentConfirmPlatform === 'youtube' && validatedLemon8Url && !newConfirmed.has('lemon8')) {
  setCurrentConfirmPlatform('lemon8');
  return;
}
// ... 他の組み合わせも同様に追加
```

**⑪ `submitUrlMutation.mutateAsync` の data に `lemon8_url` を追加**

```tsx
await submitUrlMutation.mutateAsync({
  entryId: entryId,
  data: {
    instagram_url: validatedInstagramUrl || undefined,
    tiktok_url: validatedTiktokUrl || undefined,
    youtube_url: validatedYoutubeUrl || undefined,
    lemon8_url: validatedLemon8Url || undefined,  // ← 追加
  }
});
```

**⑫ URL 提出済み表示に lemon8 を追加（788〜890行目の `提出済みURL` ブロック）**

```tsx
{/* Lemon8 */}
{(entry.lemon8_posts?.length ?? 0) > 0 && (
  <div>
    <div className="text-xs text-gray-600 mb-1">Lemon8</div>
    <div className="space-y-1">
      {entry.lemon8_posts?.map((post) => (
        <div key={post.id} className="flex items-start gap-2">
          {post.post_url && (
            <a
              href={post.post_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline text-xs inline-flex items-start gap-1"
            >
              <span className="break-all">{post.post_url}</span>
              <ExternalLink className="h-3 w-3 flex-shrink-0 mt-0.5" />
            </a>
          )}
        </div>
      ))}
    </div>
  </div>
)}
```

> **同じブロックが `isResubmission` の場合にも存在する（910〜994行目付近）ので同様に追加すること。**

**⑬ 提出済み詳細インサイトに `Lemon8PostInsights` を追加（1032〜1054行目付近）**

Lemon8 は Phase2 時点でスクレイピング後の metrics が入っていないので、
`Lemon8PostInsights` コンポーネント（`read_count` 表示のみ）を作成して追加する。

```tsx
{entry.lemon8_posts && entry.lemon8_posts.length > 0 && (
  <Lemon8PostInsights
    posts={entry.lemon8_posts}
    showHistory={false}
  />
)}
```

`Lemon8PostInsights` コンポーネントの実装（`UrlSubmissionStep.tsx` 内またはコンポーネントファイルに追加）:

```tsx
interface Lemon8PostInsightsProps {
  posts: Lemon8PostResponse[];
  showHistory: boolean;
}

function Lemon8PostInsights({ posts }: Lemon8PostInsightsProps) {
  if (posts.length === 0) return null;

  const post = posts[0]; // Phase2 では1エントリー1投稿を想定

  return (
    <div className="bg-gray-50 rounded-lg p-4 space-y-2">
      <p className="text-sm font-medium text-gray-700">Lemon8 投稿インサイト</p>
      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="bg-white rounded p-2 border">
          <div className="text-xs text-gray-500">閲覧数</div>
          <div className="font-semibold text-sm">{(post.read_count ?? 0).toLocaleString()}</div>
        </div>
        <div className="bg-white rounded p-2 border">
          <div className="text-xs text-gray-500">いいね</div>
          <div className="font-semibold text-sm">{(post.digg_count ?? 0).toLocaleString()}</div>
        </div>
        <div className="bg-white rounded p-2 border">
          <div className="text-xs text-gray-500">コメント</div>
          <div className="font-semibold text-sm">{(post.comment_count ?? 0).toLocaleString()}</div>
        </div>
        <div className="bg-white rounded p-2 border">
          <div className="text-xs text-gray-500">ブックマーク</div>
          <div className="font-semibold text-sm">{(post.favorite_count ?? 0).toLocaleString()}</div>
        </div>
      </div>
      <p className="text-xs text-gray-400 text-center">
        ※ 数値は定期更新ジョブ実行後に反映されます（Phase3）
      </p>
    </div>
  );
}
```

**⑭ URL 入力フィールドのレンダリングに Lemon8 入力欄を追加**

既存の YouTube URL 入力セクション（`isYouTubeEnabled` フラグで表示制御）の直後に追加:

```tsx
{/* Lemon8 URL入力 */}
{isLemon8Enabled && (
  <div className="bg-white rounded-lg p-4 space-y-3">
    <Label className="text-base font-semibold flex items-center gap-2">
      <span className="w-5 h-5 bg-yellow-400 rounded text-white text-xs font-bold flex items-center justify-center">L8</span>
      Lemon8投稿URL
    </Label>

    {/* 未連携の場合の警告 */}
    {!connectedAccounts.lemon8 && (
      <Alert className="bg-amber-50 border-amber-200">
        <AlertCircle className="h-4 w-4 text-amber-600" />
        <AlertDescription className="text-sm text-amber-800">
          Lemon8アカウントが連携されていません。
          <Link to="/mypage/sns" className="text-blue-600 hover:underline ml-1">
            SNS設定から連携してください
          </Link>
        </AlertDescription>
      </Alert>
    )}

    <Input
      type="url"
      placeholder="https://www.lemon8-app.com/@ユーザー名/post/投稿ID"
      value={lemon8Url}
      onChange={(e) => {
        setLemon8Url(e.target.value);
        setLemon8ValidationError(null);
        setLemon8PostData(null);
      }}
      disabled={!connectedAccounts.lemon8 || !canSubmitUrl}
      className={lemon8ValidationError ? "border-red-500" : lemon8PostData ? "border-green-500" : ""}
    />

    {/* バリデーション状態表示 */}
    {lemon8ValidationError && (
      <p className="text-xs text-red-600 flex items-center gap-1">
        <AlertCircle className="h-3 w-3" />
        {lemon8ValidationError}
      </p>
    )}
    {lemon8PostData && (
      <p className="text-xs text-green-600 flex items-center gap-1">
        <CheckCircle className="h-3 w-3" />
        @{lemon8PostData.link_name} の投稿が確認されました
      </p>
    )}
  </div>
)}
```

---

## 10. STEP 9: Frontend — admin-dashboard

### 10-1. `UrlCheckTable.tsx` — Lemon8 列追加

#### 変更ファイル: `frontend/admin-dashboard/src/pages/campaigns/components/UrlCheckTable.tsx`

**① `VideoEntry` インターフェースに `lemon8Url` を追加（74〜87行目付近）**

```typescript
interface VideoEntry {
  // ... 既存フィールド ...
  instagramUrl?: string;
  tiktokUrl?: string;
  youtubeUrl?: string;
  lemon8Url?: string;     // ← 追加
  // ...
}
```

**② `mapVideoEntryToUI` に Lemon8 URL を追加（89〜143行目）**

```typescript
const mapVideoEntryToUI = (entry: VideoEntryListItemResponse): VideoEntry => {
  // ... 既存の instagram/tiktok/youtube 処理 ...

  // Lemon8 posts から最新の post_url を取得
  const lemon8Posts = (entry as any).lemon8_posts || [];  // OpenAPI再生成後は正式な型を使う
  const latestLemon8Post = [...lemon8Posts].sort(
    (a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )[0];

  return {
    // ... 既存フィールド ...
    instagramUrl: latestInstagramPost?.permalink || undefined,
    tiktokUrl: latestTikTokPost?.share_url || undefined,
    youtubeUrl: latestYouTubePost?.share_url || undefined,
    lemon8Url: latestLemon8Post?.post_url || undefined,   // ← 追加
    // ...
  };
};
```

**③ 投稿URL セルに Lemon8 リンクを追加（553〜613行目、TableCell「投稿URL」内）**

```tsx
{/* 既存の instagram/tiktok/youtube の後に追加 */}
{entry.lemon8Url && (
  <div className="flex items-center gap-1">
    <span className="w-4 h-4 bg-yellow-400 rounded text-white text-[9px] font-bold flex items-center justify-center flex-shrink-0">
      L8
    </span>
    <a
      href={entry.lemon8Url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 hover:text-blue-800 text-sm"
    >
      Lemon8
    </a>
  </div>
)}
```

**④ 承認ダイアログ・却下ダイアログの投稿URL表示に Lemon8 を追加**

承認ダイアログ（762〜793行目付近）の `border rounded-lg p-2` ブロック内:

```tsx
{selectedEntry.lemon8Url && (
  <div className="flex items-center gap-2">
    <span className="w-4 h-4 bg-yellow-400 rounded text-white text-[9px] font-bold flex items-center justify-center flex-shrink-0">
      L8
    </span>
    <a
      href={selectedEntry.lemon8Url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 hover:text-blue-800 text-xs break-all"
    >
      Lemon8投稿
    </a>
  </div>
)}
```

> 却下ダイアログ（846〜876行目付近）も同様に追加。
> `!selectedEntry.instagramUrl && !selectedEntry.tiktokUrl` の判定も `&& !selectedEntry.lemon8Url` を追加する。

---

### 10-2. `VideoPostInfo.tsx` — Lemon8 投稿カード追加

#### 変更ファイル: `frontend/admin-dashboard/src/components/video-detail/VideoPostInfo.tsx`

**① import 追加（30〜35行目付近）**

```typescript
import type {
  VideoEntryDetailResponse,
  InstagramPostDetailResponse,
  TikTokPostDetailResponse,
  YouTubePostResponse,
  // Lemon8PostResponse は OpenAPI 再生成後に追加
} from "@vimmy/apis";
```

**② フラグと投稿配列を追加（43〜51行目付近）**

```typescript
const isInstagram = entryDetail?.video_campaign?.is_instagram ?? true;
const isTiktok = entryDetail?.video_campaign?.is_tiktok ?? true;
const isYoutube = entryDetail?.video_campaign?.is_youtube ?? false;
const isLemon8 = entryDetail?.video_campaign?.is_lemon8 ?? false;  // ← 追加

const instagramPosts = isInstagram ? (entryDetail?.instagram_posts || []) : [];
const tiktokPosts = isTiktok ? (entryDetail?.tiktok_posts || []) : [];
const youtubePosts = isYoutube ? (entryDetail?.youtube_posts || []) : [];
const lemon8Posts = isLemon8 ? ((entryDetail as any)?.lemon8_posts || []) : [];  // ← 追加（再生成後に型修正）
```

**③ `getPostStatusBadges()` に Lemon8 バッジを追加（107〜114行目付近）**

```typescript
// Lemon8投稿あり
if (lemon8Posts.length > 0) {
  badges.push(
    <Badge key="lemon8" variant="outline" className="ml-2">
      <span className="w-3 h-3 bg-yellow-400 rounded text-white text-[8px] font-bold flex items-center justify-center mr-1">L8</span>
      Lemon8あり
    </Badge>
  );
}
```

**④ 視聴履歴ボタンの表示条件に `lemon8Posts` を追加（134行目付近）**

```tsx
{(instagramPosts.length > 0 || tiktokPosts.length > 0 || youtubePosts.length > 0 || lemon8Posts.length > 0) && (
```

**⑤ 投稿カードのレンダリングに Lemon8 を追加（147〜155行目付近）**

```tsx
{instagramPosts.map((post, index) => (
  <InstagramPostCard key={post.id || index} post={post} />
))}
{tiktokPosts.map((post, index) => (
  <TikTokPostCard key={post.id || index} post={post} />
))}
{youtubePosts.map((post: YouTubePostResponse, index: number) => (
  <YouTubePostCard key={post.id || index} post={post} />
))}
{lemon8Posts.map((post: any, index: number) => (  // OpenAPI再生成後に型修正
  <Lemon8PostCard key={post.id || index} post={post} />
))}
```

**⑥ 投稿なし判定に lemon8 を追加（156〜159行目付近）**

```tsx
{instagramPosts.length === 0 && tiktokPosts.length === 0 && youtubePosts.length === 0 && lemon8Posts.length === 0 && (
```

**⑦ `ViewHistoryDialog` の lemon8Posts prop 追加（168〜176行目付近）**

```tsx
<ViewHistoryDialog
  isOpen={historyDialogOpen}
  onOpenChange={setHistoryDialogOpen}
  userName={entryDetail?.user?.name}
  campaignName={entryDetail?.campaign?.name}
  instagramPosts={instagramPosts}
  tiktokPosts={tiktokPosts}
  youtubePosts={youtubePosts}
  lemon8Posts={lemon8Posts}  // ← 追加
/>
```

**⑧ `Lemon8PostCard` コンポーネント追加（929行目以降）**

```tsx
interface Lemon8PostCardProps {
  post: any;  // OpenAPI再生成後に Lemon8PostResponse 型に変更
}

function Lemon8PostCard({ post }: Lemon8PostCardProps) {
  return (
    <div className="border rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="w-4 h-4 bg-yellow-400 rounded text-white text-[9px] font-bold flex items-center justify-center">
            L8
          </span>
          <span className="text-lg font-semibold">Lemon8投稿情報</span>
        </div>
        {post.post_url && (
          <Button
            onClick={() => window.open(post.post_url, "_blank")}
            className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 text-sm flex items-center gap-2"
          >
            <span>投稿を見る</span>
            <ExternalLink className="h-4 w-4" />
          </Button>
        )}
      </div>

      <div className="space-y-4">
        {/* 投稿基本情報 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-white rounded-md p-3 border">
            <div className="text-xs text-gray-500 mb-1">投稿日時</div>
            <div className="font-medium text-sm">
              {post.publish_time
                ? format(new Date(post.publish_time), "yyyy年MM月dd日 HH:mm", { locale: ja })
                : "不明（計測前）"}
            </div>
          </div>

          <div className="bg-white rounded-md p-3 border">
            <div className="text-xs text-gray-500 mb-1">投稿ID</div>
            <div className="font-medium text-sm text-xs">{post.group_id || "-"}</div>
          </div>

          <div className="bg-white rounded-md p-3 border">
            <div className="text-xs text-gray-500 mb-1">投稿URL</div>
            {post.post_url ? (
              <a
                href={post.post_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-800 text-sm flex items-center gap-1"
              >
                <ExternalLink className="h-3 w-3" />
                投稿を開く
              </a>
            ) : (
              <span className="text-sm text-gray-400">-</span>
            )}
          </div>

          <div className="bg-white rounded-md p-3 border">
            <div className="text-xs text-gray-500 mb-1">カテゴリ</div>
            <div className="font-medium text-sm">{post.article_class || "不明"}</div>
          </div>
        </div>

        {/* エンゲージメント情報（Phase2 時点では 0、Phase3 metrics job 後に更新） */}
        <div className="bg-gray-50 rounded-lg p-4">
          <h4 className="text-sm font-semibold mb-3">
            エンゲージメント
            <span className="ml-2 text-xs font-normal text-gray-400">（定期更新ジョブで取得）</span>
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="flex items-center gap-2">
              <Eye className="h-4 w-4 text-gray-500" />
              <div>
                <div className="text-xs text-gray-500">閲覧数</div>
                <div className="font-medium text-sm">{(post.read_count || 0).toLocaleString()}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Heart className="h-4 w-4 text-red-500" />
              <div>
                <div className="text-xs text-gray-500">いいね</div>
                <div className="font-medium text-sm">{(post.digg_count || 0).toLocaleString()}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <MessageCircle className="h-4 w-4 text-blue-500" />
              <div>
                <div className="text-xs text-gray-500">コメント</div>
                <div className="font-medium text-sm">{(post.comment_count || 0).toLocaleString()}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Heart className="h-4 w-4 text-yellow-500" />
              <div>
                <div className="text-xs text-gray-500">ブックマーク</div>
                <div className="font-medium text-sm">{(post.favorite_count || 0).toLocaleString()}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

---

### 10-3. `ViewHistoryDialog.tsx` — Lemon8 タブ追加

#### 変更ファイル: `frontend/admin-dashboard/src/components/video/ViewHistoryDialog.tsx`

**① Props に `lemon8Posts` を追加（48〜56行目付近）**

```typescript
interface ViewHistoryDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  userName?: string;
  campaignName?: string;
  instagramPosts?: InstagramPostDetailResponse[];
  tiktokPosts?: TikTokPostDetailResponse[];
  youtubePosts?: YouTubePostResponse[];
  lemon8Posts?: any[];   // ← 追加（OpenAPI再生成後に Lemon8PostResponse[] に変更）
}
```

**② `activeTab` 型に `"lemon8"` を追加（70行目付近）**

```typescript
const [activeTab, setActiveTab] = useState<"instagram" | "tiktok" | "youtube" | "lemon8">("instagram");
const [selectedLemon8GroupId, setSelectedLemon8GroupId] = useState<string | null>(null);  // ← 追加
```

**③ `useEffect` に Lemon8 初期化を追加（76〜98行目付近）**

```typescript
useEffect(() => {
  if (isOpen) {
    if (instagramPosts.length > 0) setSelectedPostId(instagramPosts[0].post_id);
    if (tiktokPosts.length > 0) setSelectedVideoId(tiktokPosts[0].video_id);
    if (youtubePosts.length > 0) setSelectedYoutubeVideoId(youtubePosts[0].video_id || null);
    if (lemon8Posts && lemon8Posts.length > 0) setSelectedLemon8GroupId(lemon8Posts[0].group_id || null);  // ← 追加

    if (instagramPosts.length > 0) setActiveTab("instagram");
    else if (tiktokPosts.length > 0) setActiveTab("tiktok");
    else if (youtubePosts.length > 0) setActiveTab("youtube");
    else if (lemon8Posts && lemon8Posts.length > 0) setActiveTab("lemon8");  // ← 追加
  }
}, [isOpen, instagramPosts, tiktokPosts, youtubePosts, lemon8Posts]);
```

**④ `Tabs` コンポーネントの `onValueChange` 型更新（172〜176行目付近）**

```tsx
onValueChange={(v) => setActiveTab(v as "instagram" | "tiktok" | "youtube" | "lemon8")}
```

**⑤ `TabsList` の `gridTemplateColumns` に lemon8 を追加（176行目付近）**

```tsx
style={{
  gridTemplateColumns: `repeat(${[
    instagramPosts.length > 0,
    tiktokPosts.length > 0,
    youtubePosts.length > 0,
    lemon8Posts && lemon8Posts.length > 0   // ← 追加
  ].filter(Boolean).length}, 1fr)`
}}
```

**⑥ Lemon8 タブトリガーを追加（YouTubeタブの後）**

```tsx
{lemon8Posts && lemon8Posts.length > 0 && (
  <TabsTrigger value="lemon8" className="flex items-center gap-2">
    <span className="w-4 h-4 bg-yellow-400 rounded text-white text-[9px] font-bold flex items-center justify-center">L8</span>
    <span className="font-semibold">Lemon8</span>
  </TabsTrigger>
)}
```

**⑦ Lemon8 `TabsContent` を追加（YouTubeタブの後）**

```tsx
{lemon8Posts && lemon8Posts.length > 0 && (
  <TabsContent value="lemon8" className="flex-1 overflow-y-auto">
    <div className="space-y-4">
      {lemon8Posts.length > 1 && (
        <select
          className="w-full p-2 border rounded"
          value={selectedLemon8GroupId || ""}
          onChange={(e) => setSelectedLemon8GroupId(e.target.value)}
        >
          {lemon8Posts.map((post: any) => (
            <option key={post.group_id} value={post.group_id || ""}>
              投稿ID: {post.group_id} -{" "}
              {post.publish_time && format(new Date(post.publish_time), "yyyy/MM/dd", { locale: ja })}
            </option>
          ))}
        </select>
      )}

      <div className="flex gap-2 items-center">
        <Button
          variant={viewMode === "graph" ? "default" : "outline"}
          size="sm"
          onClick={() => setViewMode("graph")}
          aria-label="グラフ表示"
        >
          <BarChart3 className="h-4 w-4 mr-2" />
          グラフ
        </Button>
        <Button
          variant={viewMode === "table" ? "default" : "outline"}
          size="sm"
          onClick={() => setViewMode("table")}
          aria-label="テーブル表示"
        >
          <TableIcon className="h-4 w-4 mr-2" />
          テーブル
        </Button>
        {lemon8Posts.find((p: any) => p.group_id === selectedLemon8GroupId)?.post_url && (
          <Button variant="outline" size="sm" asChild>
            <a
              href={lemon8Posts.find((p: any) => p.group_id === selectedLemon8GroupId)?.post_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1"
            >
              <ExternalLink className="h-4 w-4" />
              投稿を見る
            </a>
          </Button>
        )}
      </div>

      {/* Phase2 時点では履歴データなし → Phase3 の metrics job 後に useGetLemon8PostHistoryApi... を追加 */}
      <div className="flex items-center justify-center h-[300px] text-gray-500 border rounded">
        <div className="text-center">
          <p>閲覧数履歴は計測ジョブ実行後に表示されます</p>
          <p className="text-xs mt-1 text-gray-400">（Phase3: lemon8-metrics-collector job 実装後）</p>
        </div>
      </div>
    </div>
  </TabsContent>
)}
```

---

## 11. ownership 検証仕様（実装凍結）

| 入力パターン | 抽出後の link_name |
|---|---|
| `@JohnDoe` | `johndoe` |
| `johndoe` | `johndoe` |
| `https://www.lemon8-app.com/@johndoe/post/12345` | `johndoe` |
| `https://www.lemon8-app.com/@JohnDoe/` | `johndoe` |
| `　johndoe　`（全角空白） | `johndoe` |

照合: `normalize(url_link_name) == Lemon8Account.link_name`
- 連携時に link_name を正規化して保存 → 照合時も正規化後の値と比較
- 不一致時は HTTP 400 + 理由文言を返却

---

## 12. Phase2 DoD チェックリスト

```
[ ] Lemon8有効キャンペーンでのみ URL 入力欄が表示される
[ ] 未連携ユーザーへの適切なフォールバック UI が表示される
[ ] lemon8_url の submit 契約が OpenAPI に反映されている
[ ] validate-lemon8-url で ownership 不一致を理由付きで拒否できる
[ ] admin 審査画面で Lemon8 投稿が確認できる
[ ] migration 再実行時に重複作成/重複データが発生しない
[ ] ConnectedAccountsResponse に lemon8_accounts が含まれる
[ ] VideoEntryResponse に lemon8_posts が含まれる
[ ] OpenAPI 再生成後に frontend/packages/apis の型エラーがない
```

---

## 13. 実装上の注意点

### Alembic migration の順序
`Lemon8Account` テーブルが `Lemon8Post` より先に作成される必要がある。
`alembic revision --autogenerate` で依存関係が自動解決されるが、生成スクリプトを必ず目視確認すること。

### `is_lemon8` のデフォルト値
`False` で既存キャンペーンへの影響なし。migration で `DEFAULT FALSE` が付くことを確認する。

### group_id ユニーク制約
`Lemon8Post.group_id` にユニーク制約（候補A）を設定。
同じ投稿を複数エントリーに提出することを防ぐ。
将来的に候補Bへ変更する場合は migration で制約を変更する。

### Phase3 との接続ポイント
Phase2 完了後に Phase3 の metrics job が `Lemon8Post.group_id` を使ってスクレイピングを行う。
`Lemon8Post` の作成時点では `read_count=0` で OK（定期ジョブで更新）。

---

## 14. リリース順序（Phase2固定）

```
1. Alembic migration 適用（lemon8_account / lemon8_post / lemon8_post_history / is_lemon8 カラム）
2. backend deploy
3. OpenAPI 再生成 + frontend/packages/apis 更新
4. frontend deploy（user-app / admin-dashboard）
```
