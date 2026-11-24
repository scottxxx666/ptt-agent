import os

import pytest

from ptt_agent.ptt import PttPoster


class FakeApi:
    def __init__(self, fail_post=False):
        self.calls, self.fail_post = [], fail_post

    def login(self, **kw):
        self.calls.append(("login", kw))

    def post(self, **kw):
        self.calls.append(("post", kw))
        if self.fail_post:
            raise RuntimeError("boom")

    def logout(self):
        self.calls.append(("logout", {}))


def test_login_post_logout_in_order():
    api = FakeApi()
    PttPoster("id", "pw", "Test", 2, api_factory=lambda: api).post("T", "C")
    assert [c[0] for c in api.calls] == ["login", "post", "logout"]
    assert api.calls[0][1] == {"ptt_id": "id", "ptt_pw": "pw"}
    assert api.calls[1][1] == dict(board="Test", title_index=2, title="T", content="C", sign_file=0)


def test_logout_runs_even_when_post_fails():
    api = FakeApi(fail_post=True)
    with pytest.raises(RuntimeError):
        PttPoster("id", "pw", "Test", 1, api_factory=lambda: api).post("T", "C")
    assert api.calls[-1][0] == "logout"


class SearchApi(FakeApi):
    def __init__(self, titles):
        super().__init__()
        self.titles = titles  # oldest first, like the author-filtered board index

    def get_newest_index(self, index_type, **kw):
        import PyPtt
        self.calls.append(("newest", kw))
        if not self.titles:
            PyPtt.i18n.init(PyPtt.Language.MANDARIN)  # PyPtt.API() does this; the exception needs it
            raise PyPtt.NoSearchResult()
        return len(self.titles)

    def get_post(self, **kw):
        import PyPtt
        self.calls.append(("get_post", kw))
        return {PyPtt.PostField.title: self.titles[kw["index"] - 1]}


def poster(api):
    return PttPoster("me", "pw", "Test", 1, api_factory=lambda: api)


def test_recent_titles_searches_own_posts_newest_first_and_logs_out():
    import PyPtt
    api = SearchApi(["[影音] 261101 a", "[影音] 261102 b", "[影音] 261103 c"])
    assert poster(api).recent_titles(limit=2) == ["[影音] 261103 c", "[影音] 261102 b"]
    kw = api.calls[1][1]
    assert kw["search_type"] == PyPtt.SearchType.AUTHOR and kw["search_condition"] == "me"
    assert api.calls[-1][0] == "logout"


def test_recent_titles_limit_larger_than_posts_and_no_posts():
    assert len(poster(SearchApi(["t1", "t2"])).recent_titles(limit=10)) == 2
    api = SearchApi([])
    assert poster(api).recent_titles() == [] and api.calls[-1][0] == "logout"


def test_has_recent_post_matches_key_inside_title():
    p = poster(SearchApi(["[影音] 261102 手動發的"]))
    assert p.has_recent_post("261102") is True
    assert poster(SearchApi(["[影音] 261102 手動發的"])).has_recent_post("261103") is False


def test_logout_failure_after_successful_post_does_not_fail_the_post():
    api = FakeApi()
    api.logout = lambda: (_ for _ in ()).throw(RuntimeError("logout boom"))
    PttPoster("id", "pw", "Test", 1, api_factory=lambda: api).post("T", "C")


def test_has_recent_post_logs_in_once_for_many_items():
    api = SearchApi(["[影音] 261102 a"])
    p = poster(api)
    p.has_recent_post("261101"), p.has_recent_post("261102"), p.has_recent_post("261103")
    assert [c[0] for c in api.calls].count("login") == 1


def test_post_invalidates_recent_titles_cache():
    api = SearchApi(["[影音] 261102 a"])
    p = poster(api)
    p.has_recent_post("261102")
    p.post("T", "C")
    p.has_recent_post("261102")
    assert [c[0] for c in api.calls].count("login") == 3


class EnvSpyApi(FakeApi):
    """Records WSS_PROXY as PyPtt would see it at each call."""
    def __init__(self, fail_post=False):
        super().__init__(fail_post)
        self.seen = []

    def login(self, **kw):
        self.seen.append(os.environ.get("WSS_PROXY"))

    def post(self, **kw):
        self.seen.append(os.environ.get("WSS_PROXY"))
        if self.fail_post:
            raise RuntimeError("boom")

    def logout(self):
        self.seen.append(os.environ.get("WSS_PROXY"))


PROXY = "socks5h://127.0.0.1:40000"


def test_proxy_is_set_only_while_talking_to_ptt(monkeypatch):
    monkeypatch.delenv("WSS_PROXY", raising=False)
    api = EnvSpyApi()
    PttPoster("id", "pw", "Test", 1, api_factory=lambda: api, proxy=PROXY).post("T", "C")
    assert api.seen == [PROXY, PROXY, PROXY]
    assert "WSS_PROXY" not in os.environ


def test_proxy_covers_recent_titles_and_is_removed_when_it_fails(monkeypatch):
    monkeypatch.delenv("WSS_PROXY", raising=False)
    api = EnvSpyApi(fail_post=True)
    p = PttPoster("id", "pw", "Test", 1, api_factory=lambda: api, proxy=PROXY)
    with pytest.raises(RuntimeError):
        p.post("T", "C")
    assert "WSS_PROXY" not in os.environ

    class Empty(SearchApi, EnvSpyApi):
        pass
    api = Empty([])
    PttPoster("me", "pw", "Test", 1, api_factory=lambda: api, proxy=PROXY).recent_titles()
    assert api.seen and set(api.seen) == {PROXY} and "WSS_PROXY" not in os.environ


def test_proxy_restores_a_preexisting_value(monkeypatch):
    monkeypatch.setenv("WSS_PROXY", "socks5h://other:1")
    PttPoster("id", "pw", "Test", 1, api_factory=EnvSpyApi, proxy=PROXY).post("T", "C")
    assert os.environ["WSS_PROXY"] == "socks5h://other:1"


def test_no_proxy_leaves_the_environment_alone(monkeypatch):
    monkeypatch.setenv("WSS_PROXY", "socks5h://other:1")
    api = EnvSpyApi()
    PttPoster("id", "pw", "Test", 1, api_factory=lambda: api).post("T", "C")
    assert api.seen == ["socks5h://other:1"] * 3


def test_websockets_picks_wss_proxy_for_ptt_but_not_https_proxy_alone(monkeypatch):
    """The reason WSS_PROXY is used: it is what websockets reads first for wss://."""
    from websockets.proxy import get_proxy
    from websockets.uri import parse_uri
    for k in ("WSS_PROXY", "wss_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy",
              "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(k, raising=False)
    uri = parse_uri("wss://ws.ptt.cc/bbs")
    assert get_proxy(uri) is None
    monkeypatch.setenv("WSS_PROXY", PROXY)
    assert get_proxy(uri) == PROXY


class AidApi(SearchApi):
    def get_post(self, **kw):
        import PyPtt
        post = super().get_post(**kw)
        post[PyPtt.PostField.aid] = f"AID{kw['index']}"
        return post

    def comment(self, **kw):
        self.calls.append(("comment", kw))


def test_find_post_aid_returns_newest_match_and_none_when_absent():
    api = AidApi(["[影音] 261101 weverse live", "[影音] 261102 x", "[影音] 261101 weverse live 允真"])
    assert poster(api).find_post_aid("261101 weverse live") == "AID3"
    assert api.calls[-1][0] == "logout"
    assert poster(AidApi(["a", "b"])).find_post_aid("zzz") is None
    assert poster(AidApi([])).find_post_aid("zzz") is None


def test_find_post_aid_only_looks_at_the_last_limit_posts():
    assert poster(AidApi(["key", "a", "b"])).find_post_aid("key", limit=2) is None


def test_comment_logs_in_comments_with_arrow_and_logs_out():
    import PyPtt
    api = AidApi([])
    poster(api).comment("AID9", "hi")
    assert [c[0] for c in api.calls] == ["login", "comment", "logout"]
    assert api.calls[1][1] == dict(board="Test", comment_type=PyPtt.CommentType.ARROW, content="hi", aid="AID9")
