"""One-off: open a visible browser on the Weverse profile so you can log in by hand.

Run `uv run python -m ptt_agent.weverse_login`, log in, then close the window.
The session lives in the profile directory and is reused headlessly by the job.
"""
from playwright.sync_api import sync_playwright

from .weverse import LIVE_URL, profile_dir


def main() -> None:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(profile_dir()), channel="chrome", headless=False)
        ctx.pages[0].goto(LIVE_URL)
        print("Log in to Weverse, then close the browser window.")
        ctx.wait_for_event("close", timeout=0)


if __name__ == "__main__":
    main()
