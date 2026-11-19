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
MEMBER_ZH = {
    "KIM CHAEWON": "金采源",
    "SAKURA": "宮脇咲良",
    "HUH YUNJIN": "許允真",
    "KAZUHA": "中村一葉",
    "HONG EUNCHAE": "洪恩採",
}


def build_weverse_title(live, translation: Translation) -> str:
    """"YYMMDD weverse live <member>"; the official group account has no member suffix."""
    date = live.published.astimezone(_TAIPEI).strftime("%y%m%d")
    title = f"{date} weverse live"
    if live.author is not None:
        if live.author not in MEMBER_ZH:
            raise ValueError(f"unknown Weverse member {live.author!r}; add it to MEMBER_ZH")
        title += f" {MEMBER_ZH[live.author]}"
    return _fit_bytes(to_big5(title), MAX_TITLE_BYTES)
