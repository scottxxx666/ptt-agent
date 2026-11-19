import logging
from pathlib import Path

from .formatter import build_content, build_title
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
        make_title=build_title, make_content=build_content) -> int:
    """Translate and post unseen items oldest-first. Returns the number posted."""
    videos = fetch()
    seen = load_seen(state_path)
    if seen is None:
        save_seen(state_path, {v.id for v in videos})
        log.info("first run: marked %d existing videos as seen, nothing posted", len(videos))
        return 0

    posted = 0
    for video in sorted((v for v in videos if v.id not in seen), key=lambda v: v.published):
        try:
            translation = _translate_with_retry(translate, video.title)
        except TranslationError:
            log.exception("giving up on %s after %d attempts", video.id, TRANSLATE_RETRIES + 1)
            if do_post:  # skipped for good, otherwise it would burn agy time on every run
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
            continue
        seen.add(video.id)
        save_seen(state_path, seen)
        posted += 1
    return posted
