#!/usr/bin/env python3

from datetime import datetime
import math
import os
import requests
import sys
import time
import traceback
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

# Without a timeout, a response lost in transit blocks the process forever.
HTTP_TIMEOUT = 20  # seconds, for ordinary requests
LONG_POLL_SECONDS = 30  # how long Telegram holds a getUpdates request open
LONG_POLL_TIMEOUT = LONG_POLL_SECONDS + 10  # seconds, for getUpdates long polls
RETRY_DELAY_MIN = 5  # seconds
RETRY_DELAY_MAX = 60  # seconds

# A network failure must never end the run: requests are retried until this moment.
# It is a little later than the reply timeout, so a reply given at the last minute can still be recorded.
RETRY_DEADLINE = time.time() + TIMEOUT_SECONDS + 30 * 60

# =========================
# Utilities
# =========================

def log(message: str) -> None:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"[{now}] {message}", file=sys.stderr, flush=True)

def describe(e: requests.RequestException) -> str:
    """Describe a failed request, including the response body if there is one."""
    r = e.response
    if r is None:
        return type(e).__name__
    return f"HTTP {r.status_code}: {r.text[:500]}"

def is_temporary(e: requests.RequestException) -> bool:
    """Network errors, rate limits and server errors are worth retrying. Other HTTP errors are not."""
    r = e.response
    return r is None or r.status_code == 429 or r.status_code >= 500

def http(method: str, url: str, *, name: str, retry: bool = True, **kwargs) -> requests.Response:
    """Send a request with a timeout. Temporary failures are retried until RETRY_DEADLINE."""
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    delay = RETRY_DELAY_MIN
    while True:
        try:
            r = requests.request(method, url, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            log(f"{name} failed: {describe(e)}")
            if not retry or not is_temporary(e) or time.time() + delay > RETRY_DEADLINE:
                raise
            time.sleep(delay)
            delay = min(delay * 2, RETRY_DELAY_MAX)

get_updates_delay = RETRY_DELAY_MIN

def get_updates(offset: int | None) -> list[dict]:
    """Long-poll Telegram for updates. Returns an empty list on failure, so callers just poll again."""
    global get_updates_delay
    params = {"timeout": LONG_POLL_SECONDS}
    if offset:
        params["offset"] = offset
    try:
        r = http(
            "GET",
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            name="getUpdates",
            retry=False,
            params=params,
            timeout=LONG_POLL_TIMEOUT,
        )
    except requests.RequestException:
        time.sleep(get_updates_delay)
        get_updates_delay = min(get_updates_delay * 2, RETRY_DELAY_MAX)
        return []
    get_updates_delay = RETRY_DELAY_MIN
    return r.json()["result"]

def get_repo_variables() -> dict[str, str]:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables"
    r = http("GET", url, name="GitHub: read variables", headers=GITHUB_HEADERS)
    data = r.json()
    return {v["name"]: v["value"] for v in data["variables"]}

def update_variable(name: str, value: str) -> None:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables/{name}"
    payload = {"name": name, "value": value}
    http("PATCH", url, name=f"GitHub: update {name}", headers=GITHUB_HEADERS, json=payload)

def dispatch_workflow() -> None:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {"ref": "main"}
    http("POST", url, name="GitHub: dispatch workflow", headers=GITHUB_HEADERS, json=payload)

def telegram_api(method, data=None, retry=True):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    return http("POST", url, name=method, retry=retry, json=data).json()

def send_message(text, reply_markup=None):
    payload = {
        "chat_id": TELEGRAM_USER_ID,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram_api("sendMessage", payload)

def answer_callback(callback_id):
    # This only stops the loading animation on the button. The button press itself has
    # already been received, so a failure here (e.g. the query has expired) is ignored.
    try:
        telegram_api("answerCallbackQuery", {"callback_query_id": callback_id}, retry=False)
    except requests.RequestException:
        pass

def discard_old_updates():
    r = http(
        "GET",
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
        name="getUpdates",
        params={"timeout": 0},
    )
    updates = r.json()["result"]
    if updates:
        last_update_id = updates[-1]["update_id"]
        http(
            "GET",
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            name="getUpdates",
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

        updates = get_updates(offset)

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
        updates = get_updates(offset)

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
        if warning_class != "hidden":
            update_variable("WARNING_CLASS", "hidden")
        if warning_days != "0":
            update_variable("WARNING_DAYS", "0")

        send_message("ご確認ありがとうございます。")

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
    try:
        main()
    except Exception:
        log(traceback.format_exc())
        sys.exit(1)
