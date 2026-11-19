import json

from ptt_agent import notifier


def test_noop_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(notifier.urllib.request, "urlopen", lambda *a, **k: 1 / 0)
    notifier.notify("hi")


def test_posts_to_telegram_send_message(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T0K")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    sent = []

    class Resp:
        def close(self): pass
    monkeypatch.setattr(notifier.urllib.request, "urlopen", lambda req, timeout: sent.append(req) or Resp())
    notifier.notify("boom")
    assert sent[0].full_url == "https://api.telegram.org/botT0K/sendMessage"
    assert json.loads(sent[0].data) == {"chat_id": "42", "text": "boom"}


def test_failure_never_raises_nor_leaks_token(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T0K")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def fail(req, timeout):
        raise OSError("https://api.telegram.org/botT0K/sendMessage unreachable")
    monkeypatch.setattr(notifier.urllib.request, "urlopen", fail)
    notifier.notify("boom")
    assert "T0K" not in caplog.text
