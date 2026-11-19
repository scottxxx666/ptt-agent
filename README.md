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

## 切換看板

看板和分類編號設在 plist 的 `EnvironmentVariables`（會蓋過 `.env`）：

| 變數 | 說明 |
|---|---|
| `PTT_BOARD` | `LE_SSERAFIM`（正式）或 `Test`（測試） |
| `PTT_TITLE_INDEX` | 發文分類編號，`[影音]` 為 `1`；每個看板編號不同 |

## 手動執行

```bash
uv sync --python 3.13
uv run python -m ptt_agent          # dry-run：只印出，不發文
uv run python -m ptt_agent --post   # 實際發文
uv run pytest
```

帳密放在 `.env`（參考 `.env.example`）：`PTT_ID`、`PTT_PW`。

更多實作細節與限制見 `CLAUDE.md`。
