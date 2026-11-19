# Weverse (`--source weverse`)

Same pipeline, other source: `weverse.fetch_lives` → `translator` → `formatter.build_weverse_title` / `build_content` → `PttPoster`. Title is `[影音] YYMMDD weverse live <成員>` (the translation goes in the body, with the live URL).
- Weverse needs a login. `uv run python -m ptt_agent.weverse_login` opens Chrome on `.weverse-profile/` (gitignored); log in by hand and close it. The job reuses that profile headless (`channel="chrome"`). When the session expires `fetch_lives` raises `WeverseError`; run the login command again.
- The live page's own request to `.../liveTabPosts` is signed, so `fetch_lives` reads the page's response instead of calling the API. Only ended lives (replays) appear there.
- Member comes from `author.artistOfficialProfile.officialName` (stable), never from the nickname. `formatter.MEMBER_ZH` maps it to the Chinese name; an unknown name is skipped and logged until added. The group account (`profileType` GROUP) gets no member suffix.
- State defaults to `state.weverse.dev.json`; the live job is `~/Library/LaunchAgents/com.ptt-agent.weverse.plist` with `STATE_PATH=state.weverse.json`.
