import pytest

from ptt_agent.formatter import MEMBER_ZH, build_weverse_title
from ptt_agent.translator import Translation
from ptt_agent.weverse import Live, WeverseError, parse_lives

T = Translation(title_zh="譯", title_original="원문")


def post(post_id="4-1", ms=1795009216000, profile_type="ARTIST", official="HUH YUNJIN", nick="huh?"):
    author = {"profileType": profile_type, "profileName": nick}
    if official:
        author["artistOfficialProfile"] = {"officialName": official}
    return {"postId": post_id, "title": "허훈환", "publishedAt": ms, "author": author}


def tab(*posts, on_air=()):
    return {"onAirLivePosts": {"data": list(on_air)}, "liveTabPosts": {"data": list(posts)}}


def test_parse_uses_official_name_not_nickname_and_converts_ms_to_utc():
    (live,) = parse_lives(tab(post(nick="새 닉네임")))
    assert live == Live(id="4-1", title="허훈환", published=live.published, author="HUH YUNJIN")
    assert live.published.isoformat() == "2026-11-18T13:40:16+00:00"
    assert live.url == "https://weverse.io/lesserafim/live/4-1"


def test_group_account_has_no_author():
    (live,) = parse_lives(tab(post(profile_type="GROUP", official=None, nick="LE SSERAFIM ")))
    assert live.author is None


def test_artist_without_official_name_is_an_error():
    with pytest.raises(WeverseError):
        parse_lives(tab(post(official=None)))


def test_running_live_is_included_before_ended_ones():
    lives = parse_lives(tab(post("4-1"), on_air=[post("4-2")]))
    assert [l.id for l in lives] == ["4-2", "4-1"]


def test_no_running_live_is_fine():
    assert [l.id for l in parse_lives(tab(post("4-1")))] == ["4-1"]


def live(author, ms=1795009216000):
    return parse_lives(tab(post(ms=ms, official=author, profile_type="ARTIST" if author else "GROUP")))[0]


def test_title_has_taipei_date_and_member_name():
    # 2026-11-18 13:40 UTC is 21:40 in Taipei, same day
    assert build_weverse_title(live("HUH YUNJIN"), T) == "261118 weverse live 許允真"


def test_title_date_rolls_over_in_taipei_time():
    # 2026-11-18 18:00 UTC is 02:00 on the 19th in Taipei
    assert build_weverse_title(live("KAZUHA", ms=1795024800000), T) == "261119 weverse live 中村一葉"


def test_group_account_title_has_no_member_suffix():
    assert build_weverse_title(live(None), T) == "261118 weverse live"


def test_unknown_member_is_rejected_not_posted_without_name():
    with pytest.raises(ValueError):
        build_weverse_title(live("SOMEONE NEW"), T)


def test_all_member_names_are_big5_encodable():
    import PyPtt  # noqa: F401  (registers big5uao)
    for name in MEMBER_ZH.values():
        name.encode("big5uao")


@pytest.mark.parametrize("payload", [
    {},
    {"liveTabPosts": {"data": []}},
    tab({"postId": "1"}),
    tab(None),
    {"onAirLivePosts": {"data": None}, "liveTabPosts": {"data": []}},
    tab(on_air=[{"postId": "1"}]),
])
def test_malformed_payload_raises_weverse_error(payload):
    with pytest.raises(WeverseError):
        parse_lives(payload)
