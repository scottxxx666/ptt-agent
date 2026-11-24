import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .formatter import youtube_dup_key
from .notifier import notify
from .pipeline import run, run_daily
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
                           title_index=int(os.environ.get("PTT_TITLE_INDEX", "1")),
                           proxy=os.environ.get("PTT_PROXY") or None)
        post = poster.post
    state_path = Path(os.environ.get("STATE_PATH", PROJECT_ROOT / (
        "state.weverse.dev.json" if args.source == "weverse" else "state.dev.json")))
    try:
        if args.source == "weverse":
            from .weverse import fetch_lives
            run_daily(fetch=fetch_lives, translate=translate_title, post=post,
                      comment=poster.comment if poster else None,
                      find_post=poster.find_post_aid if poster else None,
                      state_path=state_path, do_post=args.post, notify=notify if args.post else None)
        else:
            already_posted = (lambda item: poster.has_recent_post(youtube_dup_key(item))) if poster else None
            run(fetch=fetch_videos, translate=translate_title, post=post, already_posted=already_posted,
                state_path=state_path, do_post=args.post, notify=notify if args.post else None)
    except Exception as e:
        if args.post:
            notify(f"[ptt-agent:{args.source}] crashed: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
