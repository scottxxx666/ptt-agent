import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

CHANNEL_ID = "UCs-QBT4qkj_YiQw1ZntDO3g"
# The UULF playlist holds only long-form videos (no Shorts); UC… is the full channel.
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?playlist_id=UULF{CHANNEL_ID[2:]}"

PLAYLIST_ID = f"UULF{CHANNEL_ID[2:]}"
API_URL = "https://www.googleapis.com/youtube/v3/playlistItems"

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


def parse_api_items(payload: dict) -> list[Video]:
    videos = []
    for item in payload.get("items", []):
        video_id = item["contentDetails"]["videoId"]
        title = item["snippet"]["title"]
        if not title or not title.strip():
            raise ValueError(f"API item {video_id} has no title")
        videos.append(Video(
            id=video_id,
            title=title,
            published=datetime.fromisoformat(item["contentDetails"]["videoPublishedAt"].replace("Z", "+00:00")),
        ))
    return videos


def fetch_videos_api(api_key: str, timeout: float = 20) -> list[Video]:
    # Key goes in a header, not the URL, so it never shows up in an exception message.
    url = f"{API_URL}?part=snippet,contentDetails&maxResults=15&playlistId={PLAYLIST_ID}"
    req = urllib.request.Request(url, headers={"X-Goog-Api-Key": api_key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_api_items(json.load(resp))


def fetch_videos_rss(url: str = FEED_URL, timeout: float = 20) -> list[Video]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return parse_feed(resp.read().decode("utf-8"))


def fetch_videos(url: str = FEED_URL, timeout: float = 20) -> list[Video]:
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return fetch_videos_rss(url, timeout)
    try:
        return fetch_videos_api(api_key, timeout)
    except OSError:
        # API errors (quota 403, revoked key 400, network) are all OSError; RSS is the zero-config backup.
        return fetch_videos_rss(url, timeout)
