import sys

from ptt_agent import __main__ as cli


def run_cli(monkeypatch, argv, env=()):
    captured = {}
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(cli, "run_daily", lambda **kw: captured.update(kw))
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


def test_weverse_source_uses_its_own_default_state_and_daily_runner(monkeypatch):
    c = run_cli(monkeypatch, ["--source", "weverse"])
    assert c["state_path"].name == "state.weverse.dev.json"
    assert c["append"] is None and c["find_post"] is None
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


def run_edit(monkeypatch, tmp_path, argv, env=()):
    captured = {}

    class P:
        def __init__(self, *a, **kw):
            captured["poster"] = (a, kw)

        def edit(self, aid, content, **kw):
            captured["edit"] = (aid, content, kw)
            return "screen"

        def append(self, aid, content, **kw):
            from ptt_agent.ptt_edit import AppendResult
            captured["append"] = (aid, content, kw)
            return AppendResult("screen", saved=kw["save"])
    (tmp_path / "body.txt").write_text("\x15[1;33m黃\x15[m\n", encoding="utf-8")
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run", lambda **kw: captured.update(ran=True))
    monkeypatch.setattr(cli, "PttPoster", P)
    monkeypatch.setenv("PTT_ID", "id")
    monkeypatch.setenv("PTT_PW", "pw")
    for k, v in env:
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "argv", ["ptt_agent", *[a.replace("BODY", str(tmp_path / "body.txt")) for a in argv]])
    cli.main()
    return captured


def test_edit_defaults_to_test_board_even_with_live_env_and_does_not_save(monkeypatch, tmp_path):
    c = run_edit(monkeypatch, tmp_path, ["--edit", "1h1mXoQL", "--content-file", "BODY"],
                 env=[("PTT_BOARD", "LE_SSERAFIM")])
    assert c["poster"][1]["board"] == "Test" and "ran" not in c
    assert c["edit"] == ("1h1mXoQL", "\x15[1;33m黃\x15[m\n", dict(title=None, save=False))


def test_edit_saves_only_with_post_and_dumps_without_content(monkeypatch, tmp_path):
    c = run_edit(monkeypatch, tmp_path, ["--edit", "1h1mXoQL", "--board", "Test", "--content-file", "BODY",
                                         "--title", "[測試] t", "--post"])
    assert c["edit"][2] == dict(title="[測試] t", save=True)
    c = run_edit(monkeypatch, tmp_path, ["--edit", "1h1mXoQL"])
    assert c["edit"] == ("1h1mXoQL", None, dict(title=None, save=False))


def test_append_defaults_to_test_board_rehearsal_and_dump(monkeypatch, tmp_path, capsys):
    c = run_edit(monkeypatch, tmp_path, ["--edit", "1h1nE93B", "--append", "--content-file", "BODY"],
                 env=[("PTT_BOARD", "LE_SSERAFIM")])
    assert c["poster"][1]["board"] == "Test" and "edit" not in c and "ran" not in c
    assert c["append"] == ("1h1nE93B", "\x15[1;33m黃\x15[m\n", dict(save=False))
    c = run_edit(monkeypatch, tmp_path, ["--edit", "1h1nE93B", "--append"])
    assert c["append"] == ("1h1nE93B", None, dict(save=False))
    c = run_edit(monkeypatch, tmp_path, ["--edit", "1h1nE93B", "--append", "--content-file", "BODY", "--post"])
    assert c["append"][2] == dict(save=True) and "read-back OK" in capsys.readouterr().out


def test_append_refuses_title(monkeypatch, tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        run_edit(monkeypatch, tmp_path, ["--edit", "1h1nE93B", "--append", "--content-file", "BODY", "--title", "x"])


def test_weverse_post_wires_append_with_save(monkeypatch):
    from ptt_agent.ptt_edit import AppendResult
    calls = []

    class P:
        post = comment = find_post_aid = None

        def __init__(self, *a, **kw):
            pass

        def append(self, aid, content, **kw):
            calls.append((aid, content, kw))
            return AppendResult("s", saved=True, verified=False)
    captured = {}
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run_daily", lambda **kw: captured.update(kw))
    monkeypatch.setattr(cli, "PttPoster", P)
    monkeypatch.setenv("PTT_ID", "id")
    monkeypatch.setenv("PTT_PW", "pw")
    monkeypatch.setattr(sys, "argv", ["ptt_agent", "--source", "weverse", "--post"])
    cli.main()
    assert captured["append"]("AID", "text") is False and calls == [("AID", "text", dict(save=True))]
