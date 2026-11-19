import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .translator import PROJECT_ROOT

LIVE_URL = "https://weverse.io/lesserafim/live"
# The live page itself calls this endpoint; its URL carries a signature, so we read the
# page's own response instead of building the request.
_LIVE_LIST_SUFFIX = "/liveTabPosts"


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


def profile_dir() -> Path:
    return Path(os.environ.get("WEVERSE_PROFILE", PROJECT_ROOT / ".weverse-profile"))


def parse_lives(payload: dict) -> list[Live]:
    lives = []
    for post in payload["data"]:
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


def fetch_lives(timeout_ms: int = 30_000) -> list[Live]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(profile_dir()), channel="chrome", headless=True)
        try:
            page = ctx.pages[0]
            try:
                with page.expect_response(lambda r: r.url.split("?")[0].endswith(_LIVE_LIST_SUFFIX),
                                          timeout=timeout_ms) as info:
                    page.goto(LIVE_URL)
            except PlaywrightTimeout as e:
                raise WeverseError(
                    f"no live list response (landed on {page.url.split('?')[0]}); session expired? "
                    "re-run: uv run python -m ptt_agent.weverse_login") from e
            if not info.value.ok:
                raise WeverseError(f"live list returned HTTP {info.value.status}; session expired?")
            return parse_lives(info.value.json())
        finally:
            ctx.close()
