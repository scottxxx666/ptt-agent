from ptt_agent.formatter import MAX_TITLE_BYTES, build_content, build_title, to_big5
from ptt_agent.translator import Translation


def tr(title_zh):
    return Translation(title_zh=title_zh, title_original="orig")


def test_title_date_uses_taiwan_time(make_video):
    # 15:30 UTC is 23:30 on 11-18 in Taipei (already 11-19 in Seoul); 16:00 UTC crosses midnight in Taipei
    assert build_title(make_video(published="2026-11-18T15:30:00+00:00"), tr("火鍋聚餐")) == "261118 火鍋聚餐"
    assert build_title(make_video(published="2026-11-18T16:00:00+00:00"), tr("火鍋聚餐")) == "261119 火鍋聚餐"


def test_title_never_exceeds_big5_limit(make_video):
    long = "瑜珈姿勢毫不晃動，連甜甜的甜點點餐都搞定！ | Gemini Intelligence | LE SSERAFIM's Day Off"
    title = build_title(make_video(), tr(long))
    assert len(title.encode("big5uao")) <= MAX_TITLE_BYTES
    assert title.startswith("261118 瑜珈姿勢")


def test_title_cut_does_not_split_a_double_byte_char(make_video):
    # 6 date chars + space = 7 bytes; 37 more bytes -> 18 CJK chars (36) fit, the 19th must be dropped whole
    title = build_title(make_video(), tr("字" * 30))
    assert title == "261118 " + "字" * 18


def test_unencodable_chars_are_dropped_not_raised(make_video):
    assert to_big5("夏天💙𝑺𝒖𝒎 ok") == "夏天 ok"
    assert build_title(make_video(), tr("夏天💙")) == "261118 夏天"
    assert "💙" not in build_content(make_video(), tr("夏天💙"))
    assert "夏天" in build_content(make_video(), tr("夏天💙"))


def test_content_is_yellow_title_blank_line_then_link(make_video):
    content = build_content(make_video(id="OflR_xZ6on4"), tr("火鍋聚餐"))
    assert content == "\x15[1;33m火鍋聚餐\x15[m\n\nhttps://youtu.be/OflR_xZ6on4\n"


def test_color_is_reset_so_link_is_not_yellow_and_title_stays_clean(make_video):
    title_line, blank, link_line, _ = build_content(make_video(), tr("夏天💙")).split("\n")
    assert blank == ""
    assert title_line.endswith("\x15[m") and "💙" not in title_line
    assert "\x15" not in link_line


def test_dup_keys():
    from datetime import datetime
    from types import SimpleNamespace
    from ptt_agent.formatter import weverse_dup_key, youtube_dup_key
    from ptt_agent.youtube import Video
    v = Video("a", "t", datetime.fromisoformat("2026-11-18T17:00:00+00:00"))  # 01:00 next day in Taipei
    assert youtube_dup_key(v) == "261119"
    live = SimpleNamespace(published=v.published, author="SAKURA")
    assert weverse_dup_key(live) == "261119 weverse live 宮脇咲良"
