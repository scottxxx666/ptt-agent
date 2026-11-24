import logging
from pathlib import Path

from .formatter import (UnknownMemberError, WeverseEntry, build_content, build_title, build_weverse_comment,
                        build_weverse_content, build_weverse_title, weverse_day, weverse_member_name)
from .state import load_seen, save_seen
from .translator import TranslationError

log = logging.getLogger("ptt_agent")

TRANSLATE_RETRIES = 2


def _translate_with_retry(translate, title: str):
    for attempt in range(1, TRANSLATE_RETRIES + 2):
        try:
            return translate(title)
        except TranslationError as e:
            if attempt > TRANSLATE_RETRIES:
                raise
            log.warning("translation attempt %d failed (%s), retrying", attempt, e)


def run(*, fetch, translate, post, state_path: Path, do_post: bool,
        make_title=build_title, make_content=build_content, already_posted=None, notify=None) -> int:
    """Translate and post unseen items oldest-first. Returns the number posted.

    already_posted(item) -> bool is asked before translating; True means it was posted by hand,
    so the item is marked seen and skipped. If the check itself fails the item retries next run.
    """
    notify = notify or (lambda text: None)
    videos = fetch()
    seen = load_seen(state_path)
    if seen is None:
        save_seen(state_path, {v.id for v in videos})
        log.info("first run: marked %d existing videos as seen, nothing posted", len(videos))
        return 0

    posted = 0
    for video in sorted((v for v in videos if v.id not in seen), key=lambda v: v.published):
        if do_post and already_posted:
            try:
                duplicate = already_posted(video)
            except UnknownMemberError as e:
                log.error("skipping %s: %s", video.id, e)
                notify(f"[ptt-agent] {e}; skipping {video.id} until it is added")
                continue
            except Exception:
                log.exception("duplicate check failed for %s, will retry next run", video.id)
                notify(f"[ptt-agent] duplicate check failed for {video.id}, retrying next run")
                continue
            if duplicate:
                log.info("%s is already on the board, marking as seen", video.id)
                notify(f"[ptt-agent] {video.id} looks already posted (same dup key), marked seen without posting")
                seen.add(video.id)
                save_seen(state_path, seen)
                continue
        try:
            translation = _translate_with_retry(translate, video.title)
        except TranslationError:
            log.exception("giving up on %s after %d attempts", video.id, TRANSLATE_RETRIES + 1)
            if do_post:  # skipped for good, otherwise it would burn agy time on every run
                notify(f"[ptt-agent] translation failed, skipped for good: {video.id} {video.title}")
                seen.add(video.id)
                save_seen(state_path, seen)
            continue
        try:
            title, content = make_title(video, translation), make_content(video, translation)
            if not do_post:
                print(f"[dry-run] {video.id}\n  title: {title}\n  content: {content}")
                continue
            post(title, content)
        except Exception:
            log.exception("skipping %s, will retry next run", video.id)
            notify(f"[ptt-agent] post failed for {video.id}, retrying next run")
            continue
        seen.add(video.id)
        save_seen(state_path, seen)
        posted += 1
    return posted


def run_daily(*, fetch, translate, post, comment, find_post, state_path: Path, do_post: bool, notify=None) -> int:
    """Weverse: one PTT post per Taipei day. Returns the number of lives published.

    The first live of a day becomes the post (or is added to a post already on the board, e.g. a
    hand-made one); later lives of that day are added as comments on it. A live is marked seen
    only after it was published; find_post(title) -> aid | None, comment(aid, text).
    """
    notify = notify or (lambda text: None)
    lives = fetch()
    seen = load_seen(state_path)
    if seen is None:
        save_seen(state_path, {v.id for v in lives})
        log.info("first run: marked %d existing lives as seen, nothing posted", len(lives))
        return 0

    days: dict[str, list[WeverseEntry]] = {}
    for live in sorted((v for v in lives if v.id not in seen), key=lambda v: v.published):
        try:
            name = weverse_member_name(live)
        except UnknownMemberError as e:
            log.error("skipping %s: %s", live.id, e)
            if do_post:
                notify(f"[ptt-agent] {e}; skipping {live.id} until it is added")
            continue
        try:
            translation = _translate_with_retry(translate, live.title)
        except TranslationError:
            log.exception("giving up on %s after %d attempts", live.id, TRANSLATE_RETRIES + 1)
            if do_post:
                notify(f"[ptt-agent] translation failed, skipped for good: {live.id} {live.title}")
                seen.add(live.id)
                save_seen(state_path, seen)
            continue
        days.setdefault(weverse_day(live), []).append(WeverseEntry(live, name, translation))

    published = 0
    for day, entries in days.items():
        title = build_weverse_title(day)
        if not do_post:
            print(f"[dry-run] {title}\n  content: {build_weverse_content(entries)}")
            continue
        try:
            aid = find_post(title)
        except Exception:
            log.exception("post lookup failed for %s, will retry next run", title)
            notify(f"[ptt-agent] post lookup failed for {title}, retrying next run")
            continue
        batches = [entries] if aid is None else [[e] for e in entries]
        for batch in batches:
            try:
                (post(title, build_weverse_content(batch)) if aid is None
                 else comment(aid, build_weverse_comment(batch[0])))
            except Exception:
                log.exception("publishing %s failed, will retry next run", title)
                notify(f"[ptt-agent] post failed for {title}, retrying next run")
                break
            seen.update(e.live.id for e in batch)
            save_seen(state_path, seen)
            published += len(batch)
    return published
