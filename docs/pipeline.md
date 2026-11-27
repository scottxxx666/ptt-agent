# Pipeline details

- Feed: playlist `UULF…` RSS = long-form only (Shorts excluded). No API key.
- Translator: runs `agy -p "/ls <title>" --output-format json` with cwd = project root, because the skill is `.agents/skills/le-sserafim-translator/SKILL.md`. Output is double JSON: agy envelope → `response` string → `{"title_zh", "title_original"}`. Changing the skill's output format breaks `translator.py`.
- State: `state.json` (seen video ids). A missing file means first run: seed everything as seen, post nothing. A video is marked seen only after it was posted.
- PyPtt needs Python >= 3.11 and a non-cloud IP (PTT blocks cloud IPs). Locally this is automatic; on a cloud VM set `PTT_PROXY=socks5h://127.0.0.1:40000` (WARP proxy mode). `PttPoster(proxy=...)` sets `WSS_PROXY` only while PyPtt logs in/posts/logs out: `websockets` reads it first for wss://, while urllib (YouTube, Telegram) and `agy` ignore it. Needs `python-socks`.
- Hand-post guard (`--post` only): before translating, `PttPoster.has_recent_post` searches the board for this account's last 10 posts (PyPtt author search). A post counts as this video only if its title contains the key (`YYMMDD`) **and** its body contains the video id (bodies are fetched only for title matches, cached per run); then the item is marked seen and skipped. The body check is there because the title date alone matched same-day posts of other things (another video, the `YYMMDD weverse live` post on the same board), which silently dropped videos. A hand post without the video URL in its body is not detected (it gets posted again). If the check itself fails, the item retries next run. Weverse has no such guard; see `docs/weverse.md` (one post per day). Real-board behaviour of the search is unverified; try it on `Test` first.
- Translation failure: `pipeline` retries `agy` twice (3 attempts); if all fail the item is logged and marked seen (skipped for good, not in dry-run). Post failures are not marked and retry next run. `agy` can take ~2 min for odd titles, hence `translate_title` timeout 420s.

## PTT constraints (from PyPtt source)
- Title is max 44 Big5 bytes and must be Big5-encodable; `formatter` drops unencodable chars (emoji, math alphanumerics) and cuts to the limit.
- The category (e.g. `[影音]`) is chosen by `title_index`, the menu number on that board, set via `PTT_TITLE_INDEX`. It differs per board.

## Editing a post (`--edit`, `ptt_edit.py`)
PyPtt has no edit API, so `ptt_edit` drives the editor through `api.connect_core.send`: `#AID` Enter, `E`, cursor down 4 rows to the body, Ctrl+Y per old body row, type the new body + a blank line above `--`, Ctrl+X, (T)改標題 if asked, `s` Enter.
- Body region = rows between the blank row after 作者/標題/時間 and the `--` row followed by `※ 發信站:`. Header and footer (incl. the `※ 編輯:` rows PTT appends after `※ 文章網址` on every save) are never touched.
- Only posts whose header..footer fit on the first editor screen (and whose new body still fits) are supported; others are refused before any text-changing key.
- Nothing is saved unless the redrawn editor equals exactly header + new body (ESC drawn as `*`) + blank + old footer, with the cursor at the start of `--`. Otherwise Ctrl+X, `a` Enter (abandon) and the screen is logged; a screen we cannot place -> disconnect (never saves).
- The Ctrl+X answer `確定要儲存檔案嗎？` is a line-input field and PTT treats an unrecognised answer as SAVE. So every answer is Ctrl+Y (clear) + one letter, and Enter is sent only when the field (the last screen row) shows exactly that letter; otherwise disconnect.
- Title (live recon): Ctrl+X, `t` Enter shows `舊標題：<old>` / `新標題：<old>` (prefilled). Ctrl+Y clears it, type, Enter goes back to the editor, whose header row still shows the old title. Then Ctrl+X `s` Enter. Each field is checked before the next key; the list title is read back after saving (mismatch = warning).
- (T)改標題 changes only the board-list title (`get_post(..., query=True)`); the `標題:` row in the article header (and a full `get_post` read) keeps the original title, and we do not rewrite it (header is never touched). So the editor's `標題:` row is not compared with the post's title, and the read-back uses the list title.
- Live-tested: four accumulated `※ 編輯:` rows still fit on the first screen with a 3-line body.
- Refuses posts not by `PTT_ID`, and editor headers whose author/board do not match the post.
- Content: printable Big5 text, `\n`, and Ctrl+U (`\x15`) for color codes; any other control char is refused. Lines wider than the screen will fail verification (abandoned).
- Board comes from `--board` (default `Test`), never from `PTT_BOARD`.
- www.ptt.cc caches articles for a while after an edit; check with `--edit AID` (dump) instead.

### Appending (`--edit AID --append`, `append_post`)
Adds rows right above `--` on posts of any length (the Weverse job uses it for later lives). Never deletes a row; header and footer untouched; same verified file-menu answers as above.
1. `get_post` (full) → `full_content` (reader text). Live shape: index 0-2 作者/標題/時間, 3 `───`, 4 the file's blank line 4, body from index 5. So the editor line of a row is its index there (live: `--` at index 33 = editor line 33). Any other shape is refused (fail safe if PyPtt changes it). Exactly one `--` immediately followed by `※ 發信站:` is required, else refused before any key.
2. Editor at `1:1` (header verified as for `--edit`; the footer may be off-screen). Down x L (L = `--` line) in sends of at most 20, the status bar checked to show the expected `N:  1` after each, so the cursor lands on `※ 發信站:` (L+1); then one Up. Recon: within the first 23 lines the view does not scroll, after that each Down scrolls by one with the cursor on content row 23, so the cursor is on screen row min(L+1, 23) - 1. Nothing is typed unless the status is `L:  1`, that row is `--`, the row below starts `※ 發信站:` and it is the only such pair on screen. A mismatch (e.g. the reader wrapped a long line, so its count is off) is abandoned and the screen logged.
3. Type the rows + Enter each + one more Enter (a blank before `--`); if the body does not end with a blank row, one is typed first. Then Down, Up (so `※ 發信站:` is visible under the cursor) and verify: status `(L + typed + 1):  1`, one `--`/`※ 發信站:` pair on screen, the rows above it = old row above `--` + typed rows + blank, the rows from `--` on unchanged. At most 19 typed rows (all must be on one screen for this check).
4. Save (verified `s`), then read back: body must be old body + new rows (colour codes removed) + blank. Mismatch = WARNING and `AppendResult.verified=False`; it is saved, never auto-fixed.
- `content` may be a callable `body_text -> text` (the Weverse URL guard); `""` = nothing to append, no edit.
- Without `--content-file`: dump = move to `--`, print that screen, abandon. Without `--post`: type + verify, then abandon.

```
uv run python -m ptt_agent --edit 1h1mXoQL                                   # print the editor screen, abandon
uv run python -m ptt_agent --edit 1h1mXoQL --content-file body.txt           # type + verify, then abandon
uv run python -m ptt_agent --edit 1h1mXoQL --content-file body.txt --post    # save
printf '\x15[1;33m黃色\x15[m\n\n第二段\n' > body.txt                           # color codes in a body file
uv run python -m ptt_agent --edit 1h1nE93B --append                          # print the screen at '--', abandon
uv run python -m ptt_agent --edit 1h1nE93B --append --content-file add.txt   # type + verify above '--', abandon
uv run python -m ptt_agent --edit 1h1nE93B --append --content-file add.txt --post  # save + read back
```

## Notifications
`notifier.notify` sends a Telegram message (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; Mac: `.env`, VM: `/etc/ptt-agent.env`; no-op if unset, never raises). Only with `--post`: on a crash (`__main__`), translation give-up, post failure, duplicate-check or post-lookup failure or unknown member (`pipeline`). Failures that retry next run notify again every run (no dedupe). Applies to both sources (YouTube, Weverse). A Weverse token that is rejected, a 403 or a bad API response raises `WeverseError`, which is a crash notification.
- Prefixes: the crash message names the source (`[ptt-agent:youtube]` / `[ptt-agent:weverse]`); the per-item messages from `pipeline` are just `[ptt-agent]`, so tell the source from the id and title in the text.
- **Not covered** (the process dies or never starts, so `notify` never runs): OOM kill (`MemoryMax=500M`), `TimeoutStartSec` timeout, a unit that fails to start (bad unit file, broken `uv`/`.venv`, missing `/etc/ptt-agent.env`), a timer that is not enabled, and Telegram itself failing (logged as a warning only). On the VM check `systemctl --failed` and `journalctl` (README: "查看執行狀態與 log"). `OnFailure=` on the units would cover the first three; not done.

## Schedule (launchd)
`~/Library/LaunchAgents/com.ptt-agent.plist` runs the job every 900s (commands in README.md). `StartInterval` does not fire at load; use `kickstart` to test (only if the user asks). launchd has a minimal PATH, so the plist adds `~/.local/bin` for `agy`. The plist sets `PTT_BOARD=LE_SSERAFIM`, `STATE_PATH=state.json`, `PTT_TITLE_INDEX=1`; these override `.env` because `load_dotenv` does not overwrite existing env vars.
