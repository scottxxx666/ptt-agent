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
