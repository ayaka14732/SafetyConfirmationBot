# 安否確認ボット

[English README](./README-en.md)

このリポジトリは、個人の安否確認のためのシステムを提供します。Telegramボットとの連携、GitHub Actions、そしてGitHub Pagesを統合しています。Telegramボットを通じて毎日安否確認と現在地を問い合わせ、GitHubリポジトリの変数を更新し、GitHub Pagesでステータスページを自動展開します。

## 概要

このプロジェクトは以下の3つのコンポーネントに分かれています。

* **Telegram 連携**（`/integrations/telegram/`）：Telegram経由で毎日安否確認リクエストを送信し、リポジトリ変数を更新するPythonボット。
* **ウェブサイト**（`/website/`）：リポジトリ変数をビルド時にプレースホルダと置換する静的HTMLステータスページ。
* **GitHub Actions**（`.github/workflows`）：リポジトリ変数を読み取り、GitHub Pages向けにHTMLをビルド・展開する自動パイプライン。

## 設定手順

### 1. このリポジトリをフォーク

まず、このリポジトリを自身のGitHubアカウントにフォークしてください。

### 2. リポジトリ変数の設定

**Settings > Secrets and variables > Actions > Variables** に移動し、以下の変数を作成します：

| 名前 | サンプル値 |
| :- | :- |
| `LOCATION_JA` | 京都府 |
| `LOCATION_EN` | Kyoto Prefecture, Japan |
| `NAME_JA` | 三日月綾香 |
| `NAME_EN` | Ayaka Mikazuki |
| `TIME_EN` | 26 October 2025, 18:00  |
| `TIME_JA` | 2025年10月26日　18：00 |
| `WARNING_CLASS` | hidden |
| `WARNING_DAYS` | 0 |

### 3. GitHubのファイングレインド・パーソナルアクセストークンを作成

[GitHub Fine-grained Personal Access Tokens](https://github.com/settings/personal-access-tokens) にアクセスし、新しいトークンを作成します。

- **Expiration**: No expiration
- **Repository access**: Only select repositories > your fork
- **Permissions**:
    - **Actions**: Read and write
    - **Metadata (Required)**: Read-only
    - **Variables**: Read and write

このトークンは後でサーバーで使用するため保存しておいてください。

### 4. GitHub Pagesを有効化

リポジトリの設定に移動：

* **Settings > Pages** に行く
* **Source** で **GitHub Actions** を選択

これにより、ステータスページは `https://<your-username>.github.io/<repo-name>/` に公開されます。

### 5. Telegramボットの作成

Telegramを開き、**@BotFather** にメッセージを送ります。

1. `/newbot` を送信
2. 名前を入力（例：`Ayaka Safety Confirmation Bot`）
3. ユーザー名を入力（例：`sftyconfayakabot`）
4. 提供されたボットトークンを保存（後に `TELEGRAM_BOT_TOKEN` として使用）

### 6. TelegramユーザーIDを取得

Telegramで **@myidbot** に話しかけて、`/getid` を送信してください。

TelegramユーザーIDが返されるので、それを保存しておきます。

### 7. サーバーのセットアップ

自分のサーバーでフォークしたリポジトリをクローン：

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>/integrations/telegram/
```

### 8. Python環境の構築

```bash
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

### 9. 毎日のCronジョブを作成

毎日1回ボットが実行されるようCronを設定します。

例：`crontab -e` に以下を追加

```cron
0 7 * * * GITHUB_REPO="your-username/your-repo" \
GITHUB_TOKEN="github_pat_..." \
TELEGRAM_BOT_TOKEN="1234567890:AA..." \
TELEGRAM_USER_ID="123456789" \
/path/to/your/repo/integrations/telegram/venv/bin/python \
/path/to/your/repo/integrations/telegram/main.py
```

これにより、毎日7時に安否確認メッセージが送信されます。

## 動作概要

1. Telegramボットが毎日安否確認のメッセージを送信します。
2. ユーザーは以下のいずれかを選択して応答します：
    * **[はい]**：現在の所在地を確認
    * **[位置情報の変更]**：新しい日本語および英語の所在地を入力
3. ボットはGitHubリポジトリの変数を更新します：
    * 最終確認日時
    * 所在地情報
    * 警告メッセージの表示有無、および最後の確認からの経過日数
4. ボットが23時間以内に応答を受け取らなかった場合：
    * 最終確認が4日以上前であれば、警告メッセージが表示されます。
5. GitHub Actionsの `deploy.yml` ワークフローが起動され：
    * リポジトリ変数を読み取る
    * プレースホルダを置換して静的HTMLファイルを生成
    * GitHub Pagesへ公開

## 出力

公開されるGitHub Pagesサイトには、以下のような日英バイリンガルの安否メッセージが表示されます：

```
　　　　　　　　　三日月綾香の安否確認情報


2025年10月26日　18：00現在：　元気にやっています。
所在地：　京都府




　　Safety Confirmation Information for
　　　　　　　Ayaka Mikazuki


As of 26 October 2025, 18:00: I'm doing fine.
Location: Kyoto Prefecture, Japan
```

## 備考

* 全ての時間は **日本標準時（JST, Asia/Tokyo）** で扱われます。
* データベースや外部インフラは使用せず、意図的に最小限の構成です。
* 毎回の確認後、自動でGitHub Pagesに最新情報が反映されます。
