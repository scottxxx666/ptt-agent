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
