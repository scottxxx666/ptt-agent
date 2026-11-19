import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

CHANNEL_ID = "UCs-QBT4qkj_YiQw1ZntDO3g"
# The UULF playlist holds only long-form videos (no Shorts); UC… is the full channel.
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?playlist_id=UULF{CHANNEL_ID[2:]}"

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


@dataclass(frozen=True)
class Video:
    id: str
    title: str
    published: datetime

    @property
    def url(self) -> str:
        return f"https://youtu.be/{self.id}"


def parse_feed(xml_text: str) -> list[Video]:
    root = ET.fromstring(xml_text)
    videos = []
    for entry in root.findall("atom:entry", _NS):
        title = entry.findtext("atom:title", namespaces=_NS)
        if not title or not title.strip():
            raise ValueError(f"feed entry {entry.findtext('yt:videoId', namespaces=_NS)} has no title")
        videos.append(Video(
            id=entry.findtext("yt:videoId", namespaces=_NS),
            title=title,
            published=datetime.fromisoformat(entry.findtext("atom:published", namespaces=_NS)),
        ))
    return videos


def fetch_videos(url: str = FEED_URL, timeout: float = 20) -> list[Video]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return parse_feed(resp.read().decode("utf-8"))
