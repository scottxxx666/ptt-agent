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
