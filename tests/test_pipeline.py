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


def test_translation_failure_is_retried_next_run(tmp_path, make_video):
    state, rec = tmp_path / "s.json", Recorder()
    save_seen(state, set())

    def flaky(title):
        raise TranslationError("agy timeout")
    assert go([make_video("a")], state, rec, translate=flaky) == 0
    assert load_seen(state) == set() and rec.posts == []
    assert go([make_video("a")], state, rec) == 1


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
