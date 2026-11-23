import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .translator import PROJECT_ROOT

ARTIST_CODE = "lesserafim"

# Constants below are public values from Weverse's web client, as used by yt-dlp's weverse
# extractor (yt_dlp/extractor/weverse.py). If requests start failing with 401/403 while the
# refresh token is fine, compare them with that file first.
_API_BASE = "https://global.apis.naver.com/weverse/wevweb"
_ACCOUNT_API = "https://accountapi.weverse.io/api/v1/token/refresh"
_SIGNING_KEY = b"1b9cb6378d959b45714bec49971ade22e6e24e42"
_APP_ID = "be4d79eb8fc7bd008ee82c8ec4ff6fd4"
_APP_SECRET = "5419526f1c624b38b10787e5c10b2a7a"
_WEB_HEADERS = {"Accept": "application/json", "Origin": "https://weverse.io",
                "Referer": "https://weverse.io/", "User-Agent": "Mozilla/5.0"}
_REFRESH_MARGIN_S = 300
_RESEED_HINT = ("copy the weverse.io cookie we2_refresh_token from a logged-in browser into "
                "the token file (README: Weverse token)")


class WeverseError(Exception):
    pass


@dataclass(frozen=True)
class Live:
    id: str
    title: str
    published: datetime
    # artistOfficialProfile.officialName (e.g. "HUH YUNJIN"); stable, unlike the changeable
    # nickname. None for the group's official account.
    author: str | None

    @property
    def url(self) -> str:
        return f"https://weverse.io/lesserafim/live/{self.id}"


def token_path() -> Path:
    return Path(os.environ.get("WEVERSE_TOKEN_PATH", PROJECT_ROOT / ".weverse-token.json"))


def parse_lives(payload: dict) -> list[Live]:
    try:
        return _parse_lives(payload)
    except (KeyError, TypeError, AttributeError, ValueError) as e:
        raise WeverseError(f"unexpected live list payload ({type(e).__name__}: {e})") from e


def _parse_lives(payload: dict) -> list[Live]:
    lives = []
    for post in payload["onAirLivePosts"]["data"] + payload["liveTabPosts"]["data"]:
        author = post["author"]
        official = (author.get("artistOfficialProfile") or {}).get("officialName")
        if author.get("profileType") == "ARTIST" and not official:
            raise WeverseError(f"artist without officialName on {post['postId']}")
        lives.append(Live(
            id=post["postId"],
            title=post["title"],
            published=datetime.fromtimestamp(post["publishedAt"] / 1000, tz=timezone.utc),
            author=official if author.get("profileType") == "ARTIST" else None,
        ))
    return lives


def signed_url(path: str, now_ms: int | None = None) -> str:
    sep = "&" if "?" in path else "?"
    path += sep + urllib.parse.urlencode(
        {"appId": _APP_ID, "language": "en", "os": "WEB", "platform": "WEB", "wpf": "pc"})
    ts = now_ms if now_ms is not None else int(time.time() * 1000)
    wmd = base64.b64encode(
        hmac.new(_SIGNING_KEY, f"{path[:255]}{ts}".encode(), hashlib.sha1).digest()).decode()
    return f"{_API_BASE}{path}&{urllib.parse.urlencode({'wmsgpad': ts, 'wmd': wmd})}"


def _request(url: str, headers: dict, body: bytes | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise WeverseError(f"request failed ({type(e).__name__}: {e})") from e


def _jwt_exp(token: str) -> float:
    try:
        payload = token.split(".")[1]
        return float(json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"])
    except (IndexError, ValueError, KeyError, TypeError):
        return 0.0


def _load_tokens() -> dict:
    path = token_path()
    try:
        tokens = json.loads(path.read_text())
        if not isinstance(tokens, dict) or not tokens.get("refresh_token"):
            raise ValueError("no refresh_token")
    except FileNotFoundError:
        raise WeverseError(f"{path} not found; {_RESEED_HINT}") from None
    except (ValueError, OSError) as e:
        raise WeverseError(f"cannot use {path} ({e}); {_RESEED_HINT}") from e
    return tokens


def _save_tokens(tokens: dict) -> None:
    path = token_path()
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(tokens, f)
    os.replace(tmp, path)


def _refresh(tokens: dict) -> dict:
    headers = {**_WEB_HEADERS, "Content-Type": "application/json", "X-ACC-APP-SECRET": _APP_SECRET,
               "X-ACC-SERVICE-ID": "weverse", "X-ACC-TRACE-ID": str(uuid.uuid4())}
    if tokens.get("access_token"):
        headers["Authorization"] = f"Bearer {tokens['access_token']}"
    body = json.dumps({"refreshToken": tokens["refresh_token"]}, separators=(",", ":")).encode()
    status, data = _request(_ACCOUNT_API, headers, body)
    if status in (400, 401):
        raise WeverseError(f"refresh token rejected (HTTP {status}); {_RESEED_HINT}")
    if status != 200 or not data.get("accessToken") or not data.get("refreshToken"):
        raise WeverseError(f"token refresh failed (HTTP {status})")
    # The refresh token is rotated: persist before using anything else.
    fresh = {"access_token": data["accessToken"], "refresh_token": data["refreshToken"]}
    _save_tokens(fresh)
    return fresh


class _Api:
    def __init__(self) -> None:
        self.tokens = _load_tokens()
        if _jwt_exp(self.tokens.get("access_token", "")) - time.time() < _REFRESH_MARGIN_S:
            self.tokens = _refresh(self.tokens)

    def get(self, path: str) -> dict:
        for retried in (False, True):
            headers = {**_WEB_HEADERS, "Authorization": f"Bearer {self.tokens['access_token']}",
                       "WEV-device-Id": str(uuid.uuid4())}
            status, data = _request(signed_url(path), headers)
            if status == 401 and not retried:
                self.tokens = _refresh(self.tokens)
                continue
            if status != 200:
                raise WeverseError(f"{path.split('?')[0]} returned HTTP {status}")
            return data
        raise AssertionError("unreachable")


def fetch_lives() -> list[Live]:
    api = _Api()
    try:
        community_id = api.get(
            f"/community/v1.0/communityIdUrlPathByUrlPathArtistCode?keyword={ARTIST_CODE}")["communityId"]
        on_air = api.get(f"/post/v1.0/community-{community_id}/liveTab?" + urllib.parse.urlencode(
            {"fields": "onAirLivePosts.fieldSet(postsV1).limit(10)"}))["onAirLivePosts"]
        ended = api.get(f"/post/v1.0/community-{community_id}/liveTabPosts?fieldSet=postsV1")
    except (KeyError, TypeError) as e:
        raise WeverseError(f"unexpected response ({type(e).__name__}: {e})") from e
    return parse_lives({"onAirLivePosts": on_air, "liveTabPosts": ended})
