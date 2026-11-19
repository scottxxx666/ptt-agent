import logging
from pathlib import Path

from .formatter import build_content, build_title
from .state import load_seen, save_seen

log = logging.getLogger("ptt_agent")


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
            translation = translate(video.title)
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
