import sys

from ptt_agent import __main__ as cli


def run_cli(monkeypatch, argv, env=()):
    captured = {}
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(cli, "PttPoster", lambda *a, **kw: captured.setdefault("poster", (a, kw)) and type("P", (), {"post": None})())
    for k in ("STATE_PATH", "PTT_BOARD", "PTT_TITLE_INDEX", "PTT_PROXY"):
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


def test_weverse_source_uses_its_own_default_state_and_builder(monkeypatch):
    c = run_cli(monkeypatch, ["--source", "weverse"])
    assert c["state_path"].name == "state.weverse.dev.json"
    assert c["make_title"].__name__ == "build_weverse_title"
    assert c["do_post"] is False


def test_crash_notifies_and_reraises_only_when_posting(monkeypatch):
    import pytest
    msgs = []
    monkeypatch.setattr(cli, "notify", msgs.append)

    def boom(**kw):
        raise RuntimeError("session expired")
    for argv, expected in ((["--post"], 1), ([], 0)):
        msgs.clear()
        run_cli(monkeypatch, [])  # sets up env/stubs
        monkeypatch.setattr(cli, "run", boom)
        monkeypatch.setattr(sys, "argv", ["ptt_agent", *argv])
        with pytest.raises(RuntimeError):
            cli.main()
        assert len(msgs) == expected and all("session expired" in m for m in msgs)


def test_proxy_defaults_to_none_and_comes_from_ptt_proxy(monkeypatch):
    _, kw = run_cli(monkeypatch, ["--post"])["poster"]
    assert kw["proxy"] is None
    _, kw = run_cli(monkeypatch, ["--post"], env=[("PTT_PROXY", "socks5h://127.0.0.1:40000")])["poster"]
    assert kw["proxy"] == "socks5h://127.0.0.1:40000"
    _, kw = run_cli(monkeypatch, ["--post"], env=[("PTT_PROXY", "")])["poster"]
    assert kw["proxy"] is None
