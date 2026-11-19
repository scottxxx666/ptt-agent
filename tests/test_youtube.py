from ptt_agent.youtube import FEED_URL, parse_feed

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
