from dataclasses import dataclass
from datetime import timedelta, timezone

import PyPtt  # noqa: F401  (registers the big5uao codec)

from .translator import Translation
from .youtube import Video

# PyPtt rejects titles over 44 Big5 bytes (see PyPtt._api_post.post).
MAX_TITLE_BYTES = 44
_TAIPEI = timezone(timedelta(hours=8))


def to_big5(text: str) -> str:
    """Drop characters PTT cannot display (emoji, math alphanumerics, ...)."""
    return "".join(c for c in text if _encodable(c))


def _encodable(c: str) -> bool:
    try:
        c.encode("big5uao")
        return True
    except UnicodeEncodeError:
        return False


def _fit_bytes(text: str, limit: int) -> str:
    out, size = [], 0
    for c in text:
        n = len(c.encode("big5uao"))
        if size + n > limit:
            break
        out.append(c)
        size += n
    return "".join(out).rstrip()


def build_title(video: Video, translation: Translation) -> str:
    # "YYMMDD <translated title>" cut to the 44-byte limit; the full title goes in the body.
    date = video.published.astimezone(_TAIPEI).strftime("%y%m%d")
    return _fit_bytes(to_big5(f"{date} {translation.title_zh}"), MAX_TITLE_BYTES)


# In the PTT editor, Ctrl+U followed by "[1;33m" inserts the ANSI escape for bright yellow.
YELLOW = "\x15[1;33m"
RESET = "\x15[m"


def build_content(video: Video, translation: Translation) -> str:
    return f"{YELLOW}{to_big5(translation.title_zh)}{RESET}\n\n{video.url}\n"


# Keyed by artistOfficialProfile.officialName from Weverse; nicknames change, this does not.
# Values are the names as written in the posts (given name only, Japanese members in Latin).
MEMBER_ZH = {
    "KIM CHAEWON": "采源",
    "SAKURA": "SAKURA",
    "HUH YUNJIN": "允真",
    "KAZUHA": "KAZUHA",
    "HONG EUNCHAE": "恩採",
}
CYAN = "\x15[1;36m"


class UnknownMemberError(ValueError):
    pass


@dataclass(frozen=True)
class WeverseEntry:
    live: object
    name: str | None  # None for the official group account
    translation: Translation


def weverse_member_name(live) -> str | None:
    if live.author is None:
        return None
    if live.author not in MEMBER_ZH:
        raise UnknownMemberError(f"unknown Weverse member {live.author!r}; add it to MEMBER_ZH")
    return MEMBER_ZH[live.author]


def weverse_day(live) -> str:
    return live.published.astimezone(_TAIPEI).strftime("%y%m%d")


def build_weverse_title(day: str) -> str:
    """One post per Taipei day; also the key used to find that day's post to append to."""
    return f"{day} weverse live"


def build_weverse_content(entries: list[WeverseEntry]) -> str:
    blocks = []
    for e in entries:
        line = f"{YELLOW}{to_big5(e.translation.title_zh)}{RESET}"
        if e.name:
            line += f" {CYAN}{to_big5(e.name)}{RESET}"
        blocks.append(f"{line}\n\n{e.live.url}\n")
    return "\n".join(blocks)


def youtube_dup_key(video: Video) -> str:
    """A hand-made post of this video has the same YYMMDD in its title."""
    return video.published.astimezone(_TAIPEI).strftime("%y%m%d")
