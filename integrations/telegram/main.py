#!/usr/bin/env python3

from datetime import datetime
import math
import os
import requests
import sys
import time
from typing import Literal
from zoneinfo import ZoneInfo

# =========================
# Configuration
# =========================

GITHUB_REPO = os.environ["GITHUB_REPO"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_USER_ID = int(os.environ["TELEGRAM_USER_ID"])  # integer, not string
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", 23 * 3600))  # default to 23 hours

WORKFLOW_FILE = "deploy.yml"
JST = ZoneInfo("Asia/Tokyo")
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}

# =========================
# Utilities
# =========================

def get_repo_variables() -> dict[str, str]:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables"
    r = requests.get(url, headers=GITHUB_HEADERS)
    r.raise_for_status()
    data = r.json()
    return {v["name"]: v["value"] for v in data["variables"]}

def update_variable(name: str, value: str) -> None:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables/{name}"
    payload = {"name": name, "value": value}
    r = requests.patch(url, headers=GITHUB_HEADERS, json=payload)
    r.raise_for_status()

def dispatch_workflow() -> None:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {"ref": "main"}
    r = requests.post(url, headers=GITHUB_HEADERS, json=payload)
    r.raise_for_status()

def telegram_api(method, data=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    r = requests.post(url, json=data)
    r.raise_for_status()
    return r.json()

def send_message(text, reply_markup=None):
    payload = {
        "chat_id": TELEGRAM_USER_ID,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram_api("sendMessage", payload)

def answer_callback(callback_id):
    telegram_api("answerCallbackQuery", {"callback_query_id": callback_id})

def discard_old_updates():
    r = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
        params={"timeout": 0},
    )
    r.raise_for_status()
    updates = r.json()["result"]
    if updates:
        last_update_id = updates[-1]["update_id"]
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"offset": last_update_id + 1, "timeout": 0},
        )

def format_time_en(dt: datetime) -> str:
    return dt.strftime("%d %B %Y, %H:%M")

def format_time_ja(dt: datetime) -> str:
    return dt.strftime("%Y年%m月%d日　%H：%M")

def parse_time_en(s: str) -> datetime:
    return datetime.strptime(s, "%d %B %Y, %H:%M").replace(tzinfo=JST)

def floor_days(delta_seconds: float) -> str:
    return str(math.floor(delta_seconds / 86400))

# =========================
# Step 1 - Read repository variables from GitHub
# =========================

def step1_read() -> dict[str, str]:
    variables = get_repo_variables()
    return {
        "TIME_EN": variables["TIME_EN"],
        "LOCATION_JA": variables["LOCATION_JA"],
        "WARNING_CLASS": variables["WARNING_CLASS"],
        "WARNING_DAYS": variables["WARNING_DAYS"],
    }

# =========================
# Step 2 - Telegram interaction
# =========================

def wait_for_response(location_ja: str) -> Literal["confirm", "timeout"] | tuple[Literal["change"], str, str]:
    keyboard = {
        "inline_keyboard": [[
            {"text": "はい", "callback_data": "confirm"},
            {"text": "位置情報の変更", "callback_data": "change"},
        ]]
    }

    send_message(
        f"安否確認です。現在の所在地は「{location_ja}」でよろしいですか？",
        reply_markup=keyboard,
    )

    start_time = time.time()
    offset = None

    while True:
        if time.time() - start_time > TIMEOUT_SECONDS:
            return "timeout"

        params = {"timeout": 30}
        if offset:
            params["offset"] = offset

        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params=params,
        )
        r.raise_for_status()
        updates = r.json()["result"]

        for u in updates:
            offset = u["update_id"] + 1

            if "callback_query" in u:
                cq = u["callback_query"]
                if cq["from"]["id"] != TELEGRAM_USER_ID:
                    continue

                answer_callback(cq["id"])
                data = cq["data"]

                if data == "confirm":
                    return "confirm"

                if data == "change":
                    send_message("新しい所在地（日本語）を入力してください。（例：京都府）")
                    new_ja, offset = wait_text(offset)

                    send_message("新しい所在地（英語）を入力してください。（例：Kyoto Prefecture, Japan）")
                    new_en, offset = wait_text(offset)

                    return ("change", new_ja, new_en)

        time.sleep(1)

def wait_text(offset: int) -> tuple[str, int]:
    while True:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"timeout": 30, "offset": offset},
        )
        r.raise_for_status()
        updates = r.json()["result"]

        for u in updates:
            offset = u["update_id"] + 1
            if "message" in u and "text" in u["message"]:
                if u["message"]["from"]["id"] == TELEGRAM_USER_ID:
                    return u["message"]["text"], offset

        time.sleep(1)

# =========================
# Main logic
# =========================

def main():
    discard_old_updates()

    data = step1_read()
    old_time_en = data["TIME_EN"]
    location_ja = data["LOCATION_JA"]
    warning_class = data["WARNING_CLASS"]
    warning_days = data["WARNING_DAYS"]

    result = wait_for_response(location_ja)

    if result == "confirm":
        now = datetime.now(JST)
        update_variable("TIME_EN", format_time_en(now))
        update_variable("TIME_JA", format_time_ja(now))
        if warning_class != "hidden":
            update_variable("WARNING_CLASS", "hidden")
        if warning_days != "0":
            update_variable("WARNING_DAYS", "0")

        send_message("ご確認ありがとうございます。")

    elif isinstance(result, tuple) and result[0] == "change":
        _, new_ja, new_en = result
        now = datetime.now(JST)

        update_variable("LOCATION_JA", new_ja)
        update_variable("LOCATION_EN", new_en)
        update_variable("TIME_EN", format_time_en(now))
        update_variable("TIME_JA", format_time_ja(now))
        update_variable("WARNING_CLASS", "hidden")
        update_variable("WARNING_DAYS", "0")

    elif result == "timeout":
        old_dt = parse_time_en(old_time_en)
        now = datetime.now(JST)
        delta_seconds = (now - old_dt).total_seconds()
        days = int(floor_days(delta_seconds))

        if days < 4:
            sys.exit(0)

        update_variable("WARNING_DAYS", str(days))
        update_variable("WARNING_CLASS", "not_hidden")

    else:
        sys.exit(0)

    dispatch_workflow()
    sys.exit(0)

if __name__ == "__main__":
    main()
