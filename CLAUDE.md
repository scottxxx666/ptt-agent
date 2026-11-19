# ptt-agent

Watch the LE SSERAFIM YouTube channel; for each new long-form video, translate the title with the `/ls` skill (via `agy`) and post it to a PTT board.

## Flow
`youtube.fetch_videos` → `pipeline.run` → `translator.translate_title` → `formatter` → `ptt.PttPoster`

- Feed: playlist `UULF…` RSS = long-form only (Shorts excluded). No API key.
- Translator: runs `agy -p "/ls <title>" --output-format json` with cwd = project root, because the skill is `.agents/skills/le-sserafim-translator/SKILL.md`. Output is double JSON: agy envelope → `response` string → `{"title_zh", "title_original"}`. Changing the skill's output format breaks `translator.py`.
- State: `state.json` (seen video ids). A missing file means first run: seed everything as seen, post nothing. A video is marked seen only after it was posted.
- PyPtt needs Python >= 3.11 and a non-cloud IP (PTT blocks cloud IPs), so run it on a local machine.

## Weverse (`--source weverse`)
Same pipeline, other source: `weverse.fetch_lives` → `translator` → `formatter.build_weverse_title` / `build_content` → `PttPoster`. Title is `[影音] YYMMDD weverse live <成員>` (the translation goes in the body, with the live URL).
- Weverse needs a login. `uv run python -m ptt_agent.weverse_login` opens Chrome on `.weverse-profile/` (gitignored); log in by hand and close it. The job reuses that profile headless (`channel="chrome"`). When the session expires `fetch_lives` raises `WeverseError`; run the login command again.
- The live page's own request to `.../liveTabPosts` is signed, so `fetch_lives` reads the page's response instead of calling the API. Only ended lives (replays) appear there.
- Member comes from `author.artistOfficialProfile.officialName` (stable), never from the nickname. `formatter.MEMBER_ZH` maps it to the Chinese name; an unknown name is skipped and logged until added. The group account (`profileType` GROUP) gets no member suffix.
- State defaults to `state.weverse.dev.json`; the live job is `~/Library/LaunchAgents/com.ptt-agent.weverse.plist` with `STATE_PATH=state.weverse.json`. Never `bootstrap`/`kickstart` it unless the user asks.

## PTT constraints (from PyPtt source)
- Title is max 44 Big5 bytes and must be Big5-encodable; `formatter` drops unencodable chars (emoji, math alphanumerics) and cuts to the limit.
- The category (e.g. `[影音]`) is chosen by `title_index`, the menu number on that board, set via `PTT_TITLE_INDEX`. It differs per board.

## Run
```
uv sync --python 3.13
uv run python -m ptt_agent          # dry-run: prints, never posts
uv run python -m ptt_agent --post   # posts to $PTT_BOARD (default Test)
uv run pytest
```
## Schedule (launchd)
`~/Library/LaunchAgents/com.ptt-agent.plist` runs the job every 900s (enable/disable commands in README.md). It posts to a live board, so never `kickstart` or `bootstrap` it unless the user asks.
- `StartInterval` does not fire at load; use `kickstart` to test.
- Safe by default: with no env set, the CLI targets board `Test` and state `state.dev.json`. Only the plist sets the live values (`PTT_BOARD=LE_SSERAFIM`, `STATE_PATH=state.json`, `PTT_TITLE_INDEX=1`), and they override `.env` because `load_dotenv` does not overwrite existing env vars. Keep `PTT_BOARD` out of `.env`. Manual runs must never touch the live `state.json`.
- launchd has a minimal PATH, so the plist adds `~/.local/bin` for `agy`.

`.env` (see `.env.example`) holds only `PTT_ID`, `PTT_PW`. Never read or print `.env`.
