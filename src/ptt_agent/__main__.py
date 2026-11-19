import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .pipeline import run
from .ptt import PttPoster
from .translator import PROJECT_ROOT, translate_title
from .youtube import fetch_videos


def main() -> None:
    parser = argparse.ArgumentParser(prog="ptt_agent")
    parser.add_argument("--post", action="store_true", help="actually post to PTT (default: dry-run)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(PROJECT_ROOT / ".env")

    post = None
    if args.post:
        poster = PttPoster(os.environ["PTT_ID"], os.environ["PTT_PW"],
                           board=os.environ.get("PTT_BOARD", "Test"),
                           title_index=int(os.environ.get("PTT_TITLE_INDEX", "1")))
        post = poster.post
    run(fetch=fetch_videos, translate=translate_title, post=post,
        state_path=Path(os.environ.get("STATE_PATH", PROJECT_ROOT / "state.json")),
        do_post=args.post)


if __name__ == "__main__":
    main()
