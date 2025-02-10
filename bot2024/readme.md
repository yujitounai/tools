# **Slack送信機能付きRSSフィード監視システム (`sendtoslackwtrans.py`)**
## **概要**
このプログラムは、指定されたRSSフィードを定期的にチェックし、特定のキーワードを含む記事を検出した場合にSlackに通知を送信するシステムです。Flaskを使用したWebインターフェースを備え、キーワードやRSSフィードURLの管理が可能です。また、日本語翻訳機能を実装し、英語の記事を自動翻訳することができます。

---

## **動作概要**
1. **RSSフィードを定期的に取得**
2. **指定されたキーワードと記事内容を照合**
3. **一致する場合はSlackに通知を送信**
4. **送信済みのURLはデータベースに記録し、二重送信を防止**
5. **FlaskベースのWebインターフェースで設定管理**
6. **Google翻訳APIを利用して英語記事を日本語に翻訳**

---

## **使用技術**
- **Python ライブラリ**
  - `feedparser`：RSSフィードの取得
  - `sqlite3`：データベース管理
  - `requests`：Slack APIとの通信
  - `logging`：ログ管理
  - `apscheduler`：スケジュール実行
  - `flask`：Webインターフェース
  - `threading`：非同期実行
  - `googletrans`：英語から日本語への翻訳
- **データベース**
  - SQLite (`app.db`) を利用

---

## **セットアップ手順**
### **1. 必要なライブラリのインストール**
```sh
pip install feedparser requests apscheduler flask googletrans==4.0.0-rc1
```

### **2. スクリプトの実行**
```sh
python sendtoslackwtrans.py
```
スクリプトを実行すると、Flaskアプリが起動し、ローカルサーバーでアクセス可能になります。

---

## **データベース構造**
SQLite (`app.db`) を使用し、以下の4つのテーブルを管理します。

| テーブル名       | 説明 |
|----------------|------|
| `settings`     | Slack設定（トークン、チャンネル、実行間隔） |
| `keywords`     | 検索対象のキーワードリスト |
| `rss_urls`     | 監視対象のRSSフィードURLリスト |
| `sent_urls`    | 送信済みURLを記録（重複防止） |

---

## **主要関数の説明**
### **1. データベース関連**
#### `init_db()`
- データベースを初期化し、必要なテーブルを作成。

#### `get_settings()`
- Slackのトークンやチャンネル情報を取得。

#### `set_settings(slack_token, slack_channel, schedule_interval)`
- Slack設定を更新。

#### `get_keywords()`
- 監視対象のキーワードリストを取得。

#### `add_keyword(keyword)`, `delete_keyword(keyword)`
- キーワードを追加・削除。

#### `get_rss_urls()`
- 監視対象のRSSフィードURLリストを取得。

#### `add_rss_url(url)`, `delete_rss_url(url)`
- RSSフィードのURLを追加・削除。

#### `is_url_sent(url)`, `mark_url_as_sent(url)`
- 送信済みのURLを管理（重複送信防止）。

---

### **2. フィード処理関連**
#### `contains_japanese(text)`
- 文字列に日本語が含まれているか判定。

#### `translate_to_japanese(text)`
- Google翻訳APIを使用して英語から日本語に翻訳。

#### `process_feeds()`
- RSSフィードを取得し、記事をキーワードと照合。
- 日本語翻訳を適用し、Slackに送信。

---

### **3. Slack送信関連**
#### `send_to_slack(message, slack_token, slack_channel)`
- Slack APIを使用し、メッセージを送信。

---

### **4. スケジューリング**
#### `update_scheduler(interval_minutes)`
- 指定された時間間隔でRSSフィードのチェックを実行。

---

## **Webインターフェース**
Flaskを使用し、以下のURLで各機能にアクセス可能。

| エンドポイント | メソッド | 説明 |
|--------------|--------|------|
| `/`          | GET    | 設定・キーワード・RSS URLの一覧を表示 |
| `/update_settings` | POST | Slack設定を更新 |
| `/add_keyword` | POST | キーワードを追加 |
| `/delete_keyword` | POST | キーワードを削除 |
| `/add_rss_url` | POST | RSS URLを追加 |
| `/delete_rss_url` | POST | RSS URLを削除 |
| `/process_feeds` | GET | 手動でRSSフィードを処理 |

---

## **Slack通知フォーマット**
```
*タイトル:* {記事タイトル}
*URL:* {記事URL}
*概要:* {記事の概要（翻訳済み）}
*合致したキーワード:* {一致したキーワード}
```
例：
```
*タイトル:* Python 3.12 Released!
*URL:* https://example.com/python-release
*概要:* Python 3.12 has been officially released with new features.
*合致したキーワード:* Python, release
```

---

## **注意点**
1. **Google翻訳API (`googletrans`) の制限**
   - `googletrans` は非公式APIのため、使用できなくなる可能性あり。
   - 代替として `DeepL API` などの利用を検討。

2. **Slack APIのトークン**
   - 環境変数を使って管理するのが望ましい。
   - `slack_token` は `.env` ファイルで管理すると安全。

3. **スケジューリング**
   - デフォルトでは30分ごとにRSSをチェック。
   - 設定画面で間隔を変更可能。

---

## **カスタマイズ方法**
1. **通知のフォーマットを変更**
   - `send_to_slack()` 内の `message` フォーマットを編集。

2. **翻訳機能をオフにする**
   - `process_feeds()` の `translate_to_japanese()` を削除。

3. **Slack以外に送信**
   - `send_to_slack()` を `send_to_discord()` に変更すれば、Discordにも通知可能。

---

## **今後の拡張アイデア**
✅ **マルチ言語対応**（翻訳オプションの追加）  
✅ **RSSフィードのカテゴリ管理**（タグ付け機能）  
✅ **Webhook対応**（Slack以外にも通知可能に）  
✅ **通知頻度の最適化**（記事の重要度判定）

---

## **まとめ**
このスクリプトは、指定したRSSフィードを監視し、キーワードに合致する記事をSlackに通知するシステムです。Flaskを利用したWebインターフェースで簡単に管理でき、日本語翻訳機能も備えています。
