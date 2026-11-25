from ptt_agent.formatter import UnknownMemberError
from ptt_agent.pipeline import run
from ptt_agent.state import load_seen, save_seen
from ptt_agent.translator import Translation, TranslationError


def translate_ok(title):
    return Translation(title_zh=f"譯:{title}", title_original=title)


class Recorder:
    def __init__(self, fail_on=()):
        self.posts, self.fail_on = [], fail_on

    def __call__(self, title, content):
        if any(f in content for f in self.fail_on):
            raise RuntimeError("ptt down")
        self.posts.append((title, content))


def go(videos, state, post, translate=translate_ok, do_post=True):
    return run(fetch=lambda: videos, translate=translate, post=post, state_path=state, do_post=do_post)


def test_first_run_seeds_without_posting(tmp_path, make_video):
    state, rec = tmp_path / "s.json", Recorder()
    assert go([make_video("a"), make_video("b")], state, rec) == 0
    assert rec.posts == [] and load_seen(state) == {"a", "b"}


def test_posts_only_new_videos_oldest_first_and_remembers_them(tmp_path, make_video):
    state, rec = tmp_path / "s.json", Recorder()
    save_seen(state, {"old"})
    vids = [make_video("new2", "B", "2026-11-18T10:00:00+00:00"),
            make_video("old"),
            make_video("new1", "A", "2026-11-18T08:00:00+00:00")]
    assert go(vids, state, rec) == 2
    assert [c for _, c in rec.posts] == ["\x15[1;33m譯:A\x15[m\n\nhttps://youtu.be/new1\n",
                                        "\x15[1;33m譯:B\x15[m\n\nhttps://youtu.be/new2\n"]
    assert load_seen(state) == {"old", "new1", "new2"}
    assert go(vids, state, rec) == 0  # nothing reposted


def test_translation_is_retried_twice_then_succeeds(tmp_path, make_video):
    state, rec, calls = tmp_path / "s.json", Recorder(), []
    save_seen(state, set())

    def flaky(title):
        calls.append(title)
        if len(calls) < 3:
            raise TranslationError("agy timeout")
        return translate_ok(title)
    assert go([make_video("a")], state, rec, translate=flaky) == 1
    assert len(calls) == 3 and load_seen(state) == {"a"}


def test_translation_failing_three_times_is_skipped_for_good(tmp_path, make_video):
    state, rec, calls = tmp_path / "s.json", Recorder(), []
    save_seen(state, set())

    def bad_title_fails(title):
        calls.append(title)
        if title == "bad":
            raise TranslationError("agy timeout")
        return translate_ok(title)
    vids = [make_video("a", "bad", "2026-11-18T08:00:00+00:00"),
            make_video("b", "ok", "2026-11-18T09:00:00+00:00")]
    assert go(vids, state, rec, translate=bad_title_fails) == 1
    assert calls == ["bad", "bad", "bad", "ok"]  # 1 try + 2 retries, then moves on
    assert load_seen(state) == {"a", "b"} and len(rec.posts) == 1
    assert go(vids, state, rec, translate=bad_title_fails) == 0 and len(calls) == 4  # not retried next run


def test_dry_run_does_not_skip_for_good(tmp_path, make_video):
    state = tmp_path / "s.json"
    save_seen(state, set())

    def broken(title):
        raise TranslationError("agy timeout")
    assert go([make_video("a")], state, None, translate=broken, do_post=False) == 0
    assert load_seen(state) == set()


def test_post_failure_does_not_mark_seen_and_does_not_block_others(tmp_path, make_video):
    state, rec = tmp_path / "s.json", Recorder(fail_on=("bad",))
    save_seen(state, set())
    vids = [make_video("bad", published="2026-11-18T08:00:00+00:00"),
            make_video("good", published="2026-11-18T09:00:00+00:00")]
    assert go(vids, state, rec) == 1
    assert load_seen(state) == {"good"}


def test_dry_run_never_posts_or_marks_seen(tmp_path, make_video, capsys):
    state = tmp_path / "s.json"
    save_seen(state, set())
    assert go([make_video("a")], state, None, do_post=False) == 0
    assert load_seen(state) == set()
    assert "[dry-run] a" in capsys.readouterr().out


def test_custom_title_builder_is_used(tmp_path, make_video):
    state, rec = tmp_path / "s.json", Recorder()
    save_seen(state, set())
    n = run(fetch=lambda: [make_video("a")], translate=translate_ok, post=rec, state_path=state,
            do_post=True, make_title=lambda v, t: f"T-{v.id}")
    assert n == 1 and rec.posts[0][0] == "T-a"


def test_item_already_on_board_is_marked_seen_not_translated_or_posted(tmp_path, make_video):
    state, rec, translated = tmp_path / "s.json", Recorder(), []
    save_seen(state, set())

    def tr(title):
        translated.append(title)
        return translate_ok(title)
    vids = [make_video("hand", "A", "2026-11-18T08:00:00+00:00"),
            make_video("new", "B", "2026-11-19T08:00:00+00:00")]
    n = run(fetch=lambda: vids, translate=tr, post=rec, state_path=state, do_post=True,
            already_posted=lambda v: v.id == "hand")
    assert n == 1 and translated == ["B"] and len(rec.posts) == 1
    assert load_seen(state) == {"hand", "new"}


def test_failed_duplicate_check_leaves_item_unseen_and_unposted(tmp_path, make_video):
    state, rec = tmp_path / "s.json", Recorder()
    save_seen(state, set())

    def boom(v):
        raise RuntimeError("ptt down")
    n = run(fetch=lambda: [make_video("a")], translate=translate_ok, post=rec, state_path=state,
            do_post=True, already_posted=boom)
    assert n == 0 and rec.posts == [] and load_seen(state) == set()


def test_dry_run_skips_duplicate_check(tmp_path, make_video):
    state = tmp_path / "s.json"
    save_seen(state, set())

    def boom(v):
        raise AssertionError("must not log in during dry-run")
    run(fetch=lambda: [make_video("a")], translate=translate_ok, post=None, state_path=state,
        do_post=False, already_posted=boom)


def test_notifies_on_translation_giveup_and_post_failure_only_when_posting(tmp_path, make_video):
    def bad(title):
        raise TranslationError("agy timeout")
    msgs, state = [], tmp_path / "s.json"
    save_seen(state, set())
    run(fetch=lambda: [make_video("a")], translate=bad, post=Recorder(), state_path=state,
        do_post=True, notify=msgs.append)
    assert len(msgs) == 1 and "translation failed" in msgs[0] and "a" in msgs[0]

    msgs.clear()
    save_seen(state, set())
    run(fetch=lambda: [make_video("b", "x")], translate=translate_ok, post=Recorder(fail_on=("youtu.be/b",)),
        state_path=state, do_post=True, notify=msgs.append)
    assert len(msgs) == 1 and "post failed" in msgs[0]


def test_notifies_when_duplicate_check_fails(tmp_path, make_video):
    msgs, state = [], tmp_path / "s.json"
    save_seen(state, set())

    def broken(item):
        raise RuntimeError("search failed")
    run(fetch=lambda: [make_video("a")], translate=translate_ok, post=Recorder(), state_path=state,
        do_post=True, already_posted=broken, notify=msgs.append)
    assert len(msgs) == 1 and "duplicate check failed" in msgs[0]


def test_unknown_member_notifies_clearly_and_stays_unseen(tmp_path, make_video):
    msgs, state = [], tmp_path / "s.json"
    save_seen(state, set())

    def unknown(item):
        raise UnknownMemberError("unknown Weverse member 'X'; add it to MEMBER_ZH")
    n = run(fetch=lambda: [make_video("a")], translate=translate_ok, post=Recorder(), state_path=state,
            do_post=True, already_posted=unknown, notify=msgs.append)
    assert n == 0 and load_seen(state) == set()
    assert len(msgs) == 1 and "MEMBER_ZH" in msgs[0] and "duplicate check failed" not in msgs[0]


def test_notifies_when_item_is_skipped_as_already_posted(tmp_path, make_video):
    msgs, state = [], tmp_path / "s.json"
    save_seen(state, set())
    run(fetch=lambda: [make_video("a")], translate=translate_ok, post=Recorder(), state_path=state,
        do_post=True, already_posted=lambda v: True, notify=msgs.append)
    assert load_seen(state) == {"a"}
    assert len(msgs) == 1 and "already posted" in msgs[0]


# ---- run_daily (Weverse: one post per Taipei day) ----
from datetime import datetime

from ptt_agent.pipeline import run_daily
from ptt_agent.weverse import Live


def mk(id, author="HUH YUNJIN", published="2026-11-18T09:00:00+00:00"):
    return Live(id=id, title=f"T{id}", published=datetime.fromisoformat(published), author=author)


class Board:
    def __init__(self, aid=None, fail_append=False, body="", readback_ok=True):
        self.aid, self.posts, self.appends, self.fail_append = aid, [], [], fail_append
        self.body, self.readback_ok = body, readback_ok

    def post(self, title, content):
        self.posts.append((title, content))

    def append(self, aid, make_content):
        if self.fail_append:
            raise RuntimeError("edit failed")
        text = make_content(self.body)
        self.appends.append((aid, text))
        self.body += text
        return self.readback_ok

    def find_post(self, title):
        self.looked_up = title
        return self.aid


def go_daily(lives, state, board, translate=translate_ok, do_post=True, notify=None):
    return run_daily(fetch=lambda: lives, translate=translate, post=board.post, append=board.append,
                     find_post=board.find_post, state_path=state, do_post=do_post, notify=notify)


def test_daily_first_run_seeds_without_posting(tmp_path):
    state, board = tmp_path / "s.json", Board()
    assert go_daily([mk("a")], state, board) == 0
    assert board.posts == [] and load_seen(state) == {"a"}


def test_daily_merges_same_day_lives_into_one_post(tmp_path):
    state, board = tmp_path / "s.json", Board()
    save_seen(state, set())
    lives = [mk("b", "SAKURA", "2026-11-18T10:00:00+00:00"), mk("a", "HUH YUNJIN", "2026-11-18T08:00:00+00:00")]
    assert go_daily(lives, state, board) == 2
    (title, content), = board.posts
    assert title == "261118 weverse live" and board.looked_up == title
    assert content.index("譯:Ta") < content.index("譯:Tb")
    assert "允真" in content and "SAKURA" in content and board.appends == []
    assert load_seen(state) == {"a", "b"}


def test_daily_posts_one_post_per_day(tmp_path):
    state, board = tmp_path / "s.json", Board()
    save_seen(state, set())
    go_daily([mk("a", published="2026-11-18T09:00:00+00:00"), mk("b", published="2026-11-19T09:00:00+00:00")],
             state, board)
    assert [t for t, _ in board.posts] == ["261118 weverse live", "261119 weverse live"]


def test_daily_appends_to_the_existing_post_instead_of_posting(tmp_path):
    state, board = tmp_path / "s.json", Board(aid="AID1")
    save_seen(state, set())
    assert go_daily([mk("a"), mk("b", "SAKURA")], state, board) == 2
    assert board.posts == [] and board.appends == [("AID1", (
        "\x15[1;33m譯:Ta\x15[m \x15[1;36m允真\x15[m\n\nhttps://weverse.io/lesserafim/live/a\n\n"
        "\x15[1;33m譯:Tb\x15[m \x15[1;36mSAKURA\x15[m\n\nhttps://weverse.io/lesserafim/live/b\n"))]
    assert load_seen(state) == {"a", "b"}


def test_daily_appends_in_batches_that_fit_one_screen(tmp_path):
    state, board = tmp_path / "s.json", Board(aid="AID1")
    save_seen(state, set())
    lives = [mk(str(i), published=f"2026-11-18T0{i}:00:00+00:00") for i in range(6)]
    assert go_daily(lives, state, board) == 6
    assert [t.count("weverse.io") for _, t in board.appends] == [4, 2]


def test_daily_append_skips_lives_already_in_the_body(tmp_path):
    # e.g. the previous run saved but then failed before marking them seen
    state, board = tmp_path / "s.json", Board(aid="AID1", body="x\n\nhttps://weverse.io/lesserafim/live/a\n")
    save_seen(state, set())
    assert go_daily([mk("a"), mk("b")], state, board) == 2
    (_, text), = board.appends
    assert "live/a" not in text and "live/b" in text and load_seen(state) == {"a", "b"}


def test_daily_append_saved_but_not_reading_back_notifies_and_marks_seen(tmp_path):
    state, board, msgs = tmp_path / "s.json", Board(aid="AID1", readback_ok=False), []
    save_seen(state, set())
    assert go_daily([mk("a")], state, board, notify=msgs.append) == 1
    assert load_seen(state) == {"a"} and len(msgs) == 1 and "by hand" in msgs[0]


def test_daily_failed_append_stays_unseen_and_notifies(tmp_path):
    state, board, msgs = tmp_path / "s.json", Board(aid="AID1", fail_append=True), []
    save_seen(state, set())
    assert go_daily([mk("a")], state, board, notify=msgs.append) == 0
    assert load_seen(state) == set() and len(msgs) == 1 and "retrying" in msgs[0]


def test_daily_lookup_failure_retries_next_run(tmp_path):
    state, board, msgs = tmp_path / "s.json", Board(), []
    save_seen(state, set())
    board.find_post = lambda title: (_ for _ in ()).throw(RuntimeError("search failed"))
    assert go_daily([mk("a")], state, board, notify=msgs.append) == 0
    assert board.posts == [] and load_seen(state) == set() and "lookup failed" in msgs[0]


def test_daily_unknown_member_is_skipped_but_others_still_post(tmp_path):
    state, board, msgs = tmp_path / "s.json", Board(), []
    save_seen(state, set())
    assert go_daily([mk("a", "NEW PERSON"), mk("b")], state, board, notify=msgs.append) == 1
    assert load_seen(state) == {"b"} and "MEMBER_ZH" in msgs[0]


def test_daily_translation_failure_is_skipped_for_good(tmp_path):
    state, board, msgs = tmp_path / "s.json", Board(), []
    save_seen(state, set())

    def bad(title):
        raise TranslationError("nope")
    assert go_daily([mk("a")], state, board, translate=bad, notify=msgs.append) == 0
    assert load_seen(state) == {"a"} and "translation failed" in msgs[0]


def test_daily_dry_run_prints_and_touches_nothing(tmp_path, capsys):
    state, board = tmp_path / "s.json", Board(aid="X")
    save_seen(state, set())
    assert go_daily([mk("a")], state, board, do_post=False) == 0
    assert "261118 weverse live" in capsys.readouterr().out
    assert board.posts == board.appends == [] and load_seen(state) == set()
