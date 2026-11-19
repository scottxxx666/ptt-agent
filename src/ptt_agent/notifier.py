import json
import logging
import os
import urllib.request

log = logging.getLogger("ptt_agent")


def notify(text: str) -> None:
    """Send text to Telegram. No-op without TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID; never raises."""
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat_id, "text": text[:4000]}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).close()
    except Exception as e:  # str(e) may embed the URL (token), so log only the type
        log.warning("telegram notify failed: %s", type(e).__name__)
