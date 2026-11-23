import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest

from ptt_agent import weverse
from ptt_agent.weverse import WeverseError


def jwt(exp: float) -> str:
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'HS256'})}.{b64({'exp': exp})}.sig"


FRESH = lambda: jwt(time.time() + 7200)  # noqa: E731
STALE = lambda: jwt(time.time() + 60)  # noqa: E731


def api_post(post_id="4-1"):
    return {"postId": post_id, "title": "t", "publishedAt": 1795009216000,
            "author": {"profileType": "GROUP"}}


class FakeHttp:
    """Replaces weverse._request. Routes by URL substring; a value may be a list of responses."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, headers, body=None):
        self.calls.append((url, headers, body))
        for needle, resp in self.routes.items():
            if needle in url:
                if isinstance(resp, list):
                    resp = resp.pop(0)
                return resp
        raise AssertionError(f"unrouted {url}")

    def urls(self, needle):
        return [c for c in self.calls if needle in c[0]]


def ok(data):
    return 200, data


@pytest.fixture
def token_path(tmp_path, monkeypatch):
    p = tmp_path / "token.json"
    monkeypatch.setenv("WEVERSE_TOKEN_PATH", str(p))
    return p


def seed(path, **tokens):
    path.write_text(json.dumps(tokens))


def good_routes(**over):
    routes = {
        "communityIdUrlPathByUrlPathArtistCode": ok({"communityId": 42}),
        "/liveTabPosts": ok({"data": [api_post("4-1")]}),
        "/liveTab?": ok({"onAirLivePosts": {"data": [api_post("4-2")]}}),
    }
    routes.update(over)
    return routes


def run(monkeypatch, routes):
    http = FakeHttp(routes)
    monkeypatch.setattr(weverse, "_request", http)
    return http, weverse.fetch_lives()


def test_signature_is_hmac_sha1_of_path_and_timestamp():
    url = weverse.signed_url("/post/v1.0/x?a=1", now_ms=1700000000000)
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://global.apis.naver.com/weverse/wevweb/post/v1.0/x?")
    assert q["wmsgpad"] == ["1700000000000"]
    signed = "/post/v1.0/x?a=1&appId=" + weverse._APP_ID + "&language=en&os=WEB&platform=WEB&wpf=pc"
    assert q["wmd"] == [base64.b64encode(
        hmac.new(weverse._SIGNING_KEY, f"{signed[:255]}1700000000000".encode(), hashlib.sha1).digest()).decode()]
    assert q["a"] == ["1"]


def test_only_first_255_chars_of_path_are_signed():
    long_path = "/p?" + "&".join(f"k{i}=v" for i in range(80))
    url = weverse.signed_url(long_path, now_ms=1)
    q = parse_qs(urlparse(url).query)
    signed = url.split("/wevweb", 1)[1].split("&wmsgpad=")[0]
    assert len(signed) > 255
    assert q["wmd"] == [base64.b64encode(
        hmac.new(weverse._SIGNING_KEY, f"{signed[:255]}1".encode(), hashlib.sha1).digest()).decode()]


def test_fetch_returns_running_then_ended_lives(token_path, monkeypatch):
    seed(token_path, refresh_token=FRESH(), access_token=FRESH())
    http, lives = run(monkeypatch, good_routes())
    assert [l.id for l in lives] == ["4-2", "4-1"]
    assert not http.urls("/token/refresh")
    assert all(c[1]["Authorization"].startswith("Bearer ") for c in http.urls("/weverse/wevweb"))


def test_missing_token_file_tells_how_to_seed_it(token_path, monkeypatch):
    with pytest.raises(WeverseError, match="we2_refresh_token"):
        run(monkeypatch, good_routes())


@pytest.mark.parametrize("content", ["not json", "[]", '{"access_token": "x"}', '{"refresh_token": ""}'])
def test_bad_token_file_is_a_weverse_error(token_path, monkeypatch, content):
    token_path.write_text(content)
    with pytest.raises(WeverseError):
        run(monkeypatch, good_routes())


def test_missing_access_token_is_refreshed_and_rotated_refresh_token_is_saved(token_path, monkeypatch):
    seed(token_path, refresh_token=FRESH())
    new_access, new_refresh = FRESH(), FRESH() + "x"
    http, _ = run(monkeypatch, good_routes(**{
        "/token/refresh": ok({"accessToken": new_access, "refreshToken": new_refresh})}))
    saved = json.loads(token_path.read_text())
    assert saved == {"access_token": new_access, "refresh_token": new_refresh}
    assert oct(token_path.stat().st_mode & 0o777) == "0o600"
    assert http.urls("/weverse/wevweb")[0][1]["Authorization"] == f"Bearer {new_access}"


def test_refresh_request_sends_the_old_refresh_token(token_path, monkeypatch):
    old = FRESH()
    seed(token_path, refresh_token=old)
    http, _ = run(monkeypatch, good_routes(**{
        "/token/refresh": ok({"accessToken": FRESH(), "refreshToken": FRESH()})}))
    assert json.loads(http.urls("/token/refresh")[0][2]) == {"refreshToken": old}


def test_access_token_close_to_expiry_is_refreshed_first(token_path, monkeypatch):
    seed(token_path, refresh_token=FRESH(), access_token=STALE())
    http, _ = run(monkeypatch, good_routes(**{
        "/token/refresh": ok({"accessToken": FRESH(), "refreshToken": FRESH()})}))
    assert len(http.urls("/token/refresh")) == 1


def test_401_refreshes_once_and_retries(token_path, monkeypatch):
    seed(token_path, refresh_token=FRESH(), access_token=FRESH())
    http, lives = run(monkeypatch, good_routes(**{
        "communityIdUrlPathByUrlPathArtistCode": [(401, {}), ok({"communityId": 42})],
        "/token/refresh": ok({"accessToken": FRESH(), "refreshToken": FRESH()})}))
    assert len(http.urls("/token/refresh")) == 1
    assert [l.id for l in lives] == ["4-2", "4-1"]


def test_second_401_after_refresh_is_an_error_not_a_loop(token_path, monkeypatch):
    seed(token_path, refresh_token=FRESH(), access_token=FRESH())
    routes = good_routes(**{
        "communityIdUrlPathByUrlPathArtistCode": [(401, {}), (401, {})],
        "/token/refresh": ok({"accessToken": FRESH(), "refreshToken": FRESH()})})
    with pytest.raises(WeverseError, match="401"):
        run(monkeypatch, routes)


def test_expired_refresh_token_says_to_reseed(token_path, monkeypatch):
    seed(token_path, refresh_token=FRESH())
    with pytest.raises(WeverseError, match="we2_refresh_token"):
        run(monkeypatch, good_routes(**{"/token/refresh": (401, {})}))


def test_refresh_response_without_tokens_does_not_clobber_the_file(token_path, monkeypatch):
    original = FRESH()
    seed(token_path, refresh_token=original)
    with pytest.raises(WeverseError):
        run(monkeypatch, good_routes(**{"/token/refresh": ok({"accessToken": FRESH()})}))
    assert json.loads(token_path.read_text()) == {"refresh_token": original}


def test_403_is_an_error(token_path, monkeypatch):
    seed(token_path, refresh_token=FRESH(), access_token=FRESH())
    with pytest.raises(WeverseError, match="403"):
        run(monkeypatch, good_routes(**{"/liveTabPosts": (403, {})}))


def test_unexpected_community_id_response_is_a_weverse_error(token_path, monkeypatch):
    seed(token_path, refresh_token=FRESH(), access_token=FRESH())
    with pytest.raises(WeverseError):
        run(monkeypatch, good_routes(**{"communityIdUrlPathByUrlPathArtistCode": ok({})}))


def test_unexpected_live_payload_is_a_weverse_error(token_path, monkeypatch):
    seed(token_path, refresh_token=FRESH(), access_token=FRESH())
    with pytest.raises(WeverseError):
        run(monkeypatch, good_routes(**{"/liveTabPosts": ok({"nope": 1})}))
