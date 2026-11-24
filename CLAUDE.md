# ptt-agent

Watch the LE SSERAFIM YouTube channel (and Weverse lives); for each new item, translate the title with the `/ls` skill (via `agy`) and post it to a PTT board.

Flow: `youtube.fetch_videos` → `pipeline.run` → `translator.translate_title` → `formatter` → `ptt.PttPoster` (Weverse: `--source weverse`, `weverse.fetch_lives` instead of youtube).

## Docs (read when relevant)
- `docs/pipeline.md`: translator output contract, state/seen semantics, hand-post guard, failure handling, PTT title limits, Telegram notifications
- `docs/weverse.md`: Weverse API signing, token rotation, member mapping
- `docs/known-limitations.md`: accepted review findings, not to be re-raised; add new ones there
- `README.md`: setup and launchd enable/disable commands

## Hard rules
- Changing the skill's output format (`.agents/skills/le-sserafim-translator/SKILL.md`) breaks `translator.py` (double JSON parsing).
- Never `bootstrap`/`kickstart` the launchd jobs (`~/Library/LaunchAgents/com.ptt-agent*.plist`) unless the user asks; they post to a live board.
- Safe by default: with no env set the CLI targets board `Test` and state `state.dev.json`. Only the plists and the systemd units set live values (`PTT_BOARD`, `STATE_PATH`, `PTT_TITLE_INDEX`). Keep `PTT_BOARD` out of `.env`. Manual runs must never touch live `state.json` / `state.weverse.json`.
- Never read or print `.env` (see `.env.example`).
- Needs Python >= 3.11 and a non-cloud IP (PTT blocks cloud IPs): run locally, or on a cloud VM with `PTT_PROXY` pointing at a non-cloud SOCKS5 proxy (Cloudflare WARP proxy mode). `PTT_PROXY` only affects PyPtt's websocket (via `WSS_PROXY`); unset = direct, which is what the Mac uses.
- `deploy/` holds the Linux systemd units/timers (YouTube and Weverse); the VM side (WARP, host layout) is in the `gcp-free-agents` repo. The Mac launchd jobs and the VM timer must never both be live (duplicate posts).

## Run
```
uv sync --python 3.13
uv run python -m ptt_agent          # dry-run: prints, never posts
uv run python -m ptt_agent --post   # posts to $PTT_BOARD (default Test)
uv run pytest
```
