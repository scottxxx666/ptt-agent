import io
import json
import urllib.error

import pytest

from ptt_agent import youtube
from ptt_agent.youtube import FEED_URL, parse_api_items, parse_feed

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <title>Uploads from LE SSERAFIM</title>
 <published>2021-10-19T08:33:17+00:00</published>
 <entry>
  <id>yt:video:nbQ70Pk5_eg</id>
  <yt:videoId>nbQ70Pk5_eg</yt:videoId>
  <title>LE SSERAFIM 2027 SEASON'S GREETINGS SPOT #2</title>
  <published>2026-11-18T09:00:00+00:00</published>
 </entry>
 <entry>
  <yt:videoId>TSrGHn4M9yE</yt:videoId>
  <title>르세라핌이 전하는 2027학년도 수능 응원 메시지💙</title>
  <published>2026-11-18T04:00:00+00:00</published>
 </entry>
</feed>"""


def test_parse_feed_extracts_entries_not_feed_header():
    videos = parse_feed(FEED)
    assert [v.id for v in videos] == ["nbQ70Pk5_eg", "TSrGHn4M9yE"]
    assert videos[1].title == "르세라핌이 전하는 2027학년도 수능 응원 메시지💙"
    assert videos[0].published.isoformat() == "2026-11-18T09:00:00+00:00"
    assert videos[0].url == "https://youtu.be/nbQ70Pk5_eg"


def test_parse_empty_feed():
    assert parse_feed('<feed xmlns="http://www.w3.org/2005/Atom"></feed>') == []


def test_feed_url_is_long_form_only_playlist():
    assert "playlist_id=UULFs-QBT4qkj_YiQw1ZntDO3g" in FEED_URL


@pytest.mark.parametrize("title_xml", ["", "<title></title>", "<title>   </title>"])
def test_entry_without_title_raises(title_xml):
    xml = ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">'
           f'<entry><yt:videoId>abc</yt:videoId>{title_xml}<published>2026-11-18T09:00:00+00:00</published></entry></feed>')
    with pytest.raises(ValueError, match="abc has no title"):
        parse_feed(xml)


API_PAYLOAD = {"items": [
    {"snippet": {"title": "Video A"}, "contentDetails": {"videoId": "aaa", "videoPublishedAt": "2026-11-18T09:00:00Z"}},
    {"snippet": {"title": "Video B"}, "contentDetails": {"videoId": "bbb", "videoPublishedAt": "2026-11-17T04:00:00Z"}},
]}


def test_parse_api_items():
    videos = parse_api_items(API_PAYLOAD)
    assert [v.id for v in videos] == ["aaa", "bbb"]
    assert videos[0].published.isoformat() == "2026-11-18T09:00:00+00:00"


def test_parse_api_items_empty_and_blank_title():
    assert parse_api_items({}) == []
    bad = {"items": [{"snippet": {"title": " "}, "contentDetails": {"videoId": "x", "videoPublishedAt": "2026-11-18T09:00:00Z"}}]}
    with pytest.raises(ValueError, match="x has no title"):
        parse_api_items(bad)


def _fake_urlopen(api_error=None, feed_error=None):
    calls = []

    def urlopen(target, timeout):
        calls.append(target)
        if isinstance(target, str):
            if feed_error:
                raise feed_error
            return io.BytesIO(FEED.encode())
        if api_error:
            raise api_error
        return io.BytesIO(json.dumps(API_PAYLOAD).encode())
    return urlopen, calls


def _http_error(code):
    return urllib.error.HTTPError("https://example.test", code, "err", {}, None)


def test_fetch_uses_api_first_when_key_set(monkeypatch):
    urlopen, calls = _fake_urlopen()
    monkeypatch.setattr(youtube.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    assert [v.id for v in youtube.fetch_videos()] == ["aaa", "bbb"]
    assert len(calls) == 1
    req = calls[0]
    assert req.get_header("X-goog-api-key") == "k"
    assert "playlistId=UULFs-QBT4qkj_YiQw1ZntDO3g" in req.full_url and "key=" not in req.full_url


@pytest.mark.parametrize("code", [400, 403, 503])
def test_fetch_falls_back_to_rss_when_api_fails(monkeypatch, code):
    urlopen, calls = _fake_urlopen(api_error=_http_error(code))
    monkeypatch.setattr(youtube.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    assert [v.id for v in youtube.fetch_videos()] == ["nbQ70Pk5_eg", "TSrGHn4M9yE"]
    assert len(calls) == 2


def test_fetch_uses_rss_only_without_api_key(monkeypatch):
    urlopen, calls = _fake_urlopen()
    monkeypatch.setattr(youtube.urllib.request, "urlopen", urlopen)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert [v.id for v in youtube.fetch_videos()] == ["nbQ70Pk5_eg", "TSrGHn4M9yE"]
    assert calls == [FEED_URL]


def test_fetch_raises_when_both_sources_fail(monkeypatch):
    urlopen, _ = _fake_urlopen(api_error=_http_error(403), feed_error=_http_error(503))
    monkeypatch.setattr(youtube.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    with pytest.raises(urllib.error.HTTPError, match="503"):
        youtube.fetch_videos()
