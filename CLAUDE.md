# ptt-agent

Watch the LE SSERAFIM YouTube channel; for each new long-form video, translate the title with the `/ls` skill (via `agy`) and post it to a PTT board.

## Flow
`youtube.fetch_videos` → `pipeline.run` → `translator.translate_title` → `formatter` → `ptt.PttPoster`

- Feed: playlist `UULF…` RSS = long-form only (Shorts excluded). No API key.
- Translator: runs `agy -p "/ls <title>" --output-format json` with cwd = project root, because the skill is `.agents/skills/le-sserafim-translator/SKILL.md`. Output is double JSON: agy envelope → `response` string → `{"title_zh", "title_original"}`. Changing the skill's output format breaks `translator.py`.
- State: `state.json` (seen video ids). A missing file means first run: seed everything as seen, post nothing. A video is marked seen only after it was posted.
- PyPtt needs Python >= 3.11 and a non-cloud IP (PTT blocks cloud IPs), so run it on a local machine.

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
- The plist's `EnvironmentVariables` (`PTT_BOARD`, `PTT_TITLE_INDEX`) override `.env`, because `load_dotenv` does not overwrite existing env vars.
- launchd has a minimal PATH, so the plist adds `~/.local/bin` for `agy`.

Config in `.env` (see `.env.example`): `PTT_ID`, `PTT_PW`, `PTT_BOARD`, `PTT_TITLE_INDEX`, optional `STATE_PATH`. Never read or print `.env`.
