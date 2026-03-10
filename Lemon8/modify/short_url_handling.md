# Lemon8における短縮URLの考慮と対処方法

## 背景・問題

Lemon8では投稿URLとして、以下の2形式が存在します。

- **通常URL**: `https://www.lemon8-app.com/@username/1234567890`
- **短縮URL**: `https://s.lemon8-app.com/al/xxxxxxx`

ユーザーがキャンペーン参加時に提出するURLは、アプリのシェア機能からコピーした短縮URLである場合が多く、そのままでは投稿者の特定ができません。

---

## 対処方法

### 1. リダイレクトを自動追跡してURLを解決する

`lemon8_client.py` の `fetch_post_html` 関数にて、`httpx` クライアントに `follow_redirects=True` を設定することで、短縮URLへのリクエスト時に自動的にリダイレクトを追跡し、最終的な通常URLとHTMLを取得しています。

```python
with httpx.Client(timeout=timeout_sec, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
    response = client.get(url)
```

### 2. リダイレクト先が正当な投稿URLか検証する

リダイレクト後のURLが本当にLemon8の投稿ページかどうかを、以下の2点で厳格に検証しています。

- **ホスト検証**: `lemon8-app.com` またはそのサブドメインに限定
- **パスパターン検証**: `/@<username>/<post_id>` の形式に一致するか正規表現でチェック

```python
_POST_PATH_PATTERN = re.compile(r"^/@[^/]+/\d+/?$")

def _is_safe_redirect_target(response: httpx.Response) -> bool:
    parsed = urlparse(str(response.url))
    return (
        200 <= response.status_code < 300
        and _is_allowed_host(parsed.hostname)
        and _is_post_path(parsed.path)
    )
```

投稿ページ以外（例: `/discover/trending` 等）へリダイレクトされた場合は `error_type="redirected"` として失敗扱いにします。

### 3. 最終URLから投稿者のユーザー名を抽出してownership検証

リダイレクト後の最終URLが `/@username/post_id` 形式なので、そこからユーザー名（`link_name`）を抽出できます。`lemon8_parser.py` の `extract_author_from_post_url` がこれを担います。

さらに、ページのHTMLに埋め込まれた `$UserDetail` JSONからも `linkName` を取得し、2段階でownershipを確認します（URL → HTML JSONの順でフォールバック）。

最終的に `ownership_validator.py` で、投稿者のユーザー名と、ユーザーが事前に連携済みのLemon8アカウント（`link_name`）が一致するかを照合します。

---

## フロー全体図

```
ユーザーが投稿URLを提出（短縮URL or 通常URL）
    ↓
httpx で GET（follow_redirects=True）
    ↓
リダイレクト先が lemon8-app.com の /@user/post_id 形式か検証
    ├─ NG → error_type="redirected" で却下
    └─ OK → HTML取得成功
              ↓
         HTMLから author_link_name を抽出
         （$UserDetail JSON → URLパターンのフォールバック順）
              ↓
         ユーザーの連携済みアカウントと一致するか照合
              ├─ 一致 → ownership_status="matched"（承認可）
              ├─ 不一致 → "mismatched"（別人の投稿）
              └─ 取得不可 → "unknown"（判定不能）
```

---

## まとめ

短縮URLへの対処は「リダイレクトの自動追跡」と「リダイレクト先の厳格な検証」の組み合わせで実現しています。短縮URLか通常URLかを呼び出し側で意識する必要はなく、`fetch_post_html` を呼ぶだけで最終的な投稿ページのHTMLが得られ、その後のownership検証に繋げられる設計になっています。
