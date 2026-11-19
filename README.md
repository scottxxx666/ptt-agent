# ptt-agent

監控 LE SSERAFIM 官方 YouTube 頻道，有新的長影片（不含 Shorts）就用 `/ls` skill 翻譯標題，並發文到 PTT 看板。

## 排程：啟用與停用

排程設定檔：`~/Library/LaunchAgents/com.ptt-agent.plist`，每 15 分鐘執行一次，日誌在專案內的 `run.log`。

```bash
# 啟用
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ptt-agent.plist

# 停用
launchctl bootout gui/$(id -u)/com.ptt-agent

# 立刻手動執行一次（啟用後不會馬上跑，要等第一個 15 分鐘）
launchctl kickstart gui/$(id -u)/com.ptt-agent

# 查看狀態
launchctl print gui/$(id -u)/com.ptt-agent
```

- 修改 plist 前要先停用，改完再啟用，否則不會生效。
- Mac 睡眠或關機時不會執行，開機後繼續。

## Weverse LIVE

另一個排程 `~/Library/LaunchAgents/com.ptt-agent.weverse.plist`（每 15 分鐘，日誌 `run.weverse.log`），指令同上，把 `com.ptt-agent` 換成 `com.ptt-agent.weverse`。
LIVE 結束後（出現在回放列表）才會發文，標題 `[影音] YYMMDD weverse live 成員名`。

```bash
uv run python -m ptt_agent.weverse_login          # 手動登入一次；session 過期（log 出現 WeverseError）時重跑
uv run python -m ptt_agent --source weverse       # dry-run
```

- 第一次啟用只會把現有 LIVE 記成已看過，不發文。
- 新成員／改名對不到 `formatter.MEMBER_ZH` 時會略過並在 log 報錯。

## 切換看板

**預設是測試，只有排程是正式。** 手動執行時沒有設定看板就是 `Test`，狀態檔是 `state.dev.json`；正式設定只寫在 plist 的 `EnvironmentVariables`（會蓋過 `.env`）：

| 變數 | 正式（plist） | 手動執行預設 |
|---|---|---|
| `PTT_BOARD` | `LE_SSERAFIM` | `Test` |
| `PTT_TITLE_INDEX` | `1`（`[影音]`；每個看板編號不同） | `1` |
| `STATE_PATH` | `state.json`（已看過的影片） | `state.dev.json` |

`.env` 只放帳密，**不要在裡面設 `PTT_BOARD`**，否則手動執行也可能發到正式版。

## 手動執行

```bash
uv sync --python 3.13
uv run python -m ptt_agent          # dry-run：只印出，不發文
uv run python -m ptt_agent --post   # 實際發文
uv run pytest
```

帳密放在 `.env`（參考 `.env.example`）：`PTT_ID`、`PTT_PW`。

更多實作細節與限制見 `CLAUDE.md`。
