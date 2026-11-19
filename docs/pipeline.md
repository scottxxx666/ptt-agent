# Pipeline details

- Feed: playlist `UULF…` RSS = long-form only (Shorts excluded). No API key.
- Translator: runs `agy -p "/ls <title>" --output-format json` with cwd = project root, because the skill is `.agents/skills/le-sserafim-translator/SKILL.md`. Output is double JSON: agy envelope → `response` string → `{"title_zh", "title_original"}`. Changing the skill's output format breaks `translator.py`.
- State: `state.json` (seen video ids). A missing file means first run: seed everything as seen, post nothing. A video is marked seen only after it was posted.
- PyPtt needs Python >= 3.11 and a non-cloud IP (PTT blocks cloud IPs), so run it on a local machine.
- Hand-post guard (`--post` only): before translating, `PttPoster.has_recent_post` searches the board for this account's last 10 posts (PyPtt author search). A title containing the key (YouTube: `YYMMDD`; Weverse: the full title) means it was posted by hand, so the item is marked seen and skipped. Same-day videos therefore collide on YouTube. If the check itself fails, the item retries next run. Real-board behaviour of the search is unverified; try it on `Test` first.
- Translation failure: `pipeline` retries `agy` twice (3 attempts); if all fail the item is logged and marked seen (skipped for good, not in dry-run). Post failures are not marked and retry next run. `agy` can take ~2 min for odd titles, hence `translate_title` timeout 420s.

## PTT constraints (from PyPtt source)
- Title is max 44 Big5 bytes and must be Big5-encodable; `formatter` drops unencodable chars (emoji, math alphanumerics) and cuts to the limit.
- The category (e.g. `[影音]`) is chosen by `title_index`, the menu number on that board, set via `PTT_TITLE_INDEX`. It differs per board.

## Notifications
`notifier.notify` sends a Telegram message (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` in `.env`; no-op if unset, never raises). Only with `--post`: on a crash (`__main__`), translation give-up, post failure, or duplicate-check failure (`pipeline`). Failures that retry next run notify again every run (no dedupe).

## Schedule (launchd)
`~/Library/LaunchAgents/com.ptt-agent.plist` runs the job every 900s (commands in README.md). `StartInterval` does not fire at load; use `kickstart` to test (only if the user asks). launchd has a minimal PATH, so the plist adds `~/.local/bin` for `agy`. The plist sets `PTT_BOARD=LE_SSERAFIM`, `STATE_PATH=state.json`, `PTT_TITLE_INDEX=1`; these override `.env` because `load_dotenv` does not overwrite existing env vars.
