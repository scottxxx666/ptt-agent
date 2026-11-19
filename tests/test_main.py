import sys

from ptt_agent import __main__ as cli


def run_cli(monkeypatch, argv, env=()):
    captured = {}
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(cli, "PttPoster", lambda *a, **kw: captured.setdefault("poster", (a, kw)) and type("P", (), {"post": None})())
    for k in ("STATE_PATH", "PTT_BOARD", "PTT_TITLE_INDEX"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PTT_ID", "id")
    monkeypatch.setenv("PTT_PW", "pw")
    for k, v in env:
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "argv", ["ptt_agent", *argv])
    cli.main()
    return captured


def test_default_run_is_dry_run_with_dev_state(monkeypatch):
    c = run_cli(monkeypatch, [])
    assert c["do_post"] is False and c["post"] is None
    assert c["state_path"].name == "state.dev.json"


def test_post_without_board_config_goes_to_test_board_not_live(monkeypatch):
    c = run_cli(monkeypatch, ["--post"])
    _, kw = c["poster"]
    assert kw["board"] == "Test" and c["state_path"].name == "state.dev.json"


def test_live_requires_explicit_env(monkeypatch):
    c = run_cli(monkeypatch, ["--post"], env=[("PTT_BOARD", "LE_SSERAFIM"), ("PTT_TITLE_INDEX", "1"),
                                              ("STATE_PATH", "/x/state.json")])
    _, kw = c["poster"]
    assert kw["board"] == "LE_SSERAFIM" and kw["title_index"] == 1
    assert str(c["state_path"]) == "/x/state.json"
