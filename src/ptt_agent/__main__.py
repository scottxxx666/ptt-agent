import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .formatter import build_weverse_title, weverse_dup_key, youtube_dup_key
from .pipeline import run
from .ptt import PttPoster
from .translator import PROJECT_ROOT, translate_title
from .youtube import fetch_videos


def main() -> None:
    parser = argparse.ArgumentParser(prog="ptt_agent")
    parser.add_argument("--source", choices=["youtube", "weverse"], default="youtube")
    parser.add_argument("--post", action="store_true", help="actually post to PTT (default: dry-run)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(PROJECT_ROOT / ".env")

    post, poster = None, None
    if args.post:
        poster = PttPoster(os.environ["PTT_ID"], os.environ["PTT_PW"],
                           board=os.environ.get("PTT_BOARD", "Test"),
                           title_index=int(os.environ.get("PTT_TITLE_INDEX", "1")))
        post = poster.post
    if args.source == "weverse":
        from .weverse import fetch_lives
        extra = dict(fetch=fetch_lives, make_title=build_weverse_title)
        dup_key = weverse_dup_key
        default_state = "state.weverse.dev.json"
    else:
        extra = dict(fetch=fetch_videos)
        dup_key = youtube_dup_key
        default_state = "state.dev.json"
    already_posted = (lambda item: poster.has_recent_post(dup_key(item))) if poster else None
    run(translate=translate_title, post=post, already_posted=already_posted,
        state_path=Path(os.environ.get("STATE_PATH", PROJECT_ROOT / default_state)),
        do_post=args.post, **extra)


if __name__ == "__main__":
    main()
