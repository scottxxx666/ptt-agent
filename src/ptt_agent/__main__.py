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
    parser.add_argument("--edit", metavar="AID", help="edit our post AID instead of watching a source")
    parser.add_argument("--board", default="Test", help="board of the post to --edit (default: Test)")
    parser.add_argument("--content-file", type=Path, help="--edit: new body (UTF-8; Ctrl+U for color codes)")
    parser.add_argument("--title", help="--edit: new title")
    parser.add_argument("--append", action="store_true",
                        help="--edit: add --content-file above the '--' row instead of replacing the body")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv(PROJECT_ROOT / ".env")
    if args.edit:
        edit(args)
        return

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
                      append=(lambda aid, content: poster.append(aid, content, save=True).verified)
                      if poster else None,
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


def edit(args) -> None:
    """--edit AID: no --content-file -> print the editor screen; without --post -> type and verify the
    new body, then abandon; with --post -> save. Always ends by abandoning unless saving.
    --append: the same, but adds the file above '--' (no --content-file: print the screen at '--')."""
    if args.append:
        if args.title is not None:
            raise SystemExit("--append does not change the title")
        content = args.content_file.read_text(encoding="utf-8") if args.content_file else None
        poster = PttPoster(os.environ["PTT_ID"], os.environ["PTT_PW"], board=args.board, title_index=1,
                           proxy=os.environ.get("PTT_PROXY") or None)
        result = poster.append(args.edit, content, save=args.post)
        print(result.screen)
        if result.saved:
            print("saved; read-back " + ("OK" if result.verified else "MISMATCH (see the warning above)"))
        return
    if args.title is not None and args.content_file is None:
        raise SystemExit("--title needs --content-file (the body is always replaced)")
    content = args.content_file.read_text(encoding="utf-8") if args.content_file else None
    # --board, not PTT_BOARD: an edit only goes to a live board when asked for on the command line.
    poster = PttPoster(os.environ["PTT_ID"], os.environ["PTT_PW"], board=args.board, title_index=1,
                       proxy=os.environ.get("PTT_PROXY") or None)
    print(poster.edit(args.edit, content, title=args.title, save=args.post))


if __name__ == "__main__":
    main()
