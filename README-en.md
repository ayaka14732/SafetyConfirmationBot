# Safety Confirmation Bot

This repository provides a system for personal safety confirmation. It integrates Telegram Bot interactions, GitHub Actions, and GitHub Pages. The system asks the user daily to confirm their safety and location via Telegram Bot, updates GitHub repository variables, and automatically deploys a status page via GitHub Pages.

## Overview

This project is separated into three components:

- **Telegram Integration** (`/integrations/telegram/`): A Python bot that sends daily confirmation requests via Telegram and updates repository variables accordingly.
- **Website** (`/website/`): A static status page (HTML) with placeholders replaced at build time using repository variables.
- **GitHub Actions** (`.github/workflows`): A deployment pipeline that reads repository variables and builds the HTML for GitHub Pages.

## Step-by-Step Setup

### 1. Fork this Repository

Start by forking this repository to your GitHub account.

### 2. Set Repository Variables

Navigate to **Settings > Secrets and variables > Actions > Variables**.

Create the following variables:

| Name | Sample Value |
| :- | :- |
| `LOCATION_JA` | 京都府 |
| `LOCATION_EN` | Kyoto Prefecture, Japan |
| `NAME_JA` | 三日月綾香 |
| `NAME_EN` | Ayaka Mikazuki |
| `TIME_EN` | 26 October 2025, 18:00 |
| `TIME_JA` | 2025年10月26日　18：00 |
| `WARNING_CLASS` | hidden |
| `WARNING_DAYS` | 0 |

### 3. Create a Fine-grained GitHub Personal Access Token

Go to [GitHub Fine-grained Personal Access Tokens](https://github.com/settings/personal-access-tokens).

Create a new token with the following:

- **Expiration**: No expiration
- **Repository access**: Only select repositories > your fork
- **Permissions**:
    - **Actions**: Read and write
    - **Metadata (Required)**: Read-only
    - **Variables**: Read and write

Save the token for later use in your server.

### 4. Enable GitHub Pages

In your repository:

- Go to **Settings > Pages**
- Under **Source**, select **GitHub Actions**

The status page will be published at `https://<your-username>.github.io/<repo-name>/`.

### 5. Create Telegram Bot

Open Telegram and talk to **@BotFather**.

1. Send `/newbot`
2. Provide a name (e.g., `Ayaka Safety Confirmation Bot`)
3. Provide a username (e.g., `sftyconfayakabot`)
4. Save the provided bot token (used as `TELEGRAM_BOT_TOKEN`)

### 6. Get Your Telegram User ID

Open Telegram and talk to **@myidbot**.

Send `/getid`.

It will return your Telegram user ID. Save this.

### 7. Server Setup

On your server, clone your fork:

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>/integrations/telegram/
````

### 8. Set Up Python Environment

```bash
python -m venv venv
venv/bin/python -m pip install -r requirements.txt
```

### 9. Create Daily Cron Job

Set up a cron job to run once a day.

Example `crontab -e` entry:

```cron
0 7 * * * GITHUB_REPO="your-username/your-repo" \
GITHUB_TOKEN="github_pat_..." \
TELEGRAM_BOT_TOKEN="1234567890:AA..." \
TELEGRAM_USER_ID="123456789" \
/path/to/your/repo/integrations/telegram/venv/bin/python \
/path/to/your/repo/integrations/telegram/main.py
```

This will send the confirmation message every day at 07:00.

## How It Works

1. The Telegram bot sends a daily safety confirmation message.
2. User must respond by clicking:
    * **[はい]** to confirm current location
    * **[位置情報の変更]** to submit new Japanese and English location names
3. The bot updates GitHub repository variables accordingly:
    * Last confirmation time
    * Location
    * Whether or not to display a warning message, including the number of days elapsed since the last confirmation
4. If no response is received by the Telegram bot within 23 hours:
    * If the last confirmation was ≥ 4 days ago, a warning message will be shown.
5. The bot triggers a GitHub Actions workflow (`deploy.yml`) which:
    * Reads GitHub repository variables
    * Generates a static HTML file by replacing placeholders
    * Publishes the file to GitHub Pages

## Output

The public GitHub Pages site shows a bilingual safety message like this:

```
　　　　　　　　　三日月綾香の安否確認情報


2025年10月26日　18：00現在：　元気にやっています。
所在地：　京都府




　　Safety Confirmation Information for
　　　　　　　Ayaka Mikazuki


As of 26 October 2025, 18:00: I'm doing fine.
Location: Kyoto Prefecture, Japan
```

## Notes

* All time is handled in **JST (Asia/Tokyo)**.
* This system is intentionally minimal, without databases or external infrastructure.
* GitHub Pages will automatically reflect the latest information after every confirmation.
