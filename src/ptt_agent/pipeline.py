import logging
from pathlib import Path

from .formatter import UnknownMemberError, build_content, build_title
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
