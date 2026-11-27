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

Weverse 只在 VM 上跑（`ptt-agent-weverse.timer`，每 15 分鐘，安裝見下方「Linux」），Mac 沒有排程。
LIVE 結束後（出現在回放列表）才會發文，同一天只發一篇，標題 `[影音] YYMMDD weverse live`；當天之後的直播以編輯文章的方式加在該篇內文最後（`--` 上方，格式與首播相同；該篇 = 標題含 `YYMMDD weverse live` 的最近 10 篇自己的文章，手動發的也算）。

```bash
uv run python -m ptt_agent --source weverse       # dry-run
```

**Weverse token**：直接打 API，不用瀏覽器。下面只是本機 dry-run 用的（VM 的 token 另外放，見下方）。在已登入的 Chrome 開發者工具（Application → Cookies → `https://weverse.io`）點 `we2_refresh_token` 複製值，**複製完再**執行（值不會進 shell history）。refresh token 每次 refresh 都會輪替，程式會自動寫回檔案；只有過期（log 出現 `refresh token rejected`）或被登出時才要重做。

```bash
python3 -c 'import json,subprocess;print(json.dumps({"refresh_token":subprocess.check_output("pbpaste",text=True).strip()}))' > .weverse-token.json && chmod 600 .weverse-token.json
```

- state 檔不存在時（第一次執行）只會把現有 LIVE 記成已看過，不發文。
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

# 編輯自己的文章（預設 Test 板；不加 --post 只會打字驗證後放棄，不存檔）
uv run python -m ptt_agent --edit <AID> [--board Test] --content-file body.txt [--title "..."] [--post]
uv run python -m ptt_agent --edit <AID> --append [--content-file add.txt] [--post]   # 加在 -- 上方，不限長度
```

帳密放在 `.env`（參考 `.env.example`）：`PTT_ID`、`PTT_PW`；選填 `YOUTUBE_API_KEY`（YouTube Data API v3，沒設或失敗時改用 RSS）。

更多實作細節與限制見 `CLAUDE.md`。

## Linux（GCP VM，systemd）

`deploy/` 是 Linux 版排程：`ptt-agent`（YouTube）和 `ptt-agent-weverse`（Weverse）兩組 service/timer。VM 端（WARP、機器設定）在 `gcp-free-agents` repo 的 `scripts/startup.sh`。PTT 擋雲端 IP，所以 unit 設了 `PTT_PROXY=socks5h://127.0.0.1:40000`（WARP proxy 模式），只有 PyPtt 的 websocket 會走它。

翻譯用的 `agy` 用你的 Google 帳號（Gemini Pro）登入，不用 API key。登入 token 存在 OS keyring（Linux Secret Service/dbus），而 VM 沒有桌面，所以 `deploy/with-keyring.sh` 每次執行時開一個私有 D-Bus session，並用**空密碼**解鎖 `gnome-keyring`，token 存在 `/opt/ptt-agent/.local/share/keyrings/`。代價：能讀 `ptt-agent` 家目錄的人就能讀到 token，所以 user 要專用。這是社群在 headless 環境的做法，官方文件沒有說明 Linux 無 keyring 時的行為，**我沒有驗證過**；官方的 headless 替代方案是 API key 或 ADC。

在 VM 上（Debian 12）。前提是 `gcp-free-agents` 的 `startup.sh` 已跑過（WARP、keyring 套件）：

```bash
# 一個指令，可重複執行：uv、ptt-agent user、clone/更新、依賴、agy、systemd unit、/etc/ptt-agent.env 範本。
# 不會寫 secrets、不會登入 agy、不會啟用 timer。（repo 是 public 才能這樣 curl）
curl -fsSL https://raw.githubusercontent.com/scottxxx666/ptt-agent/main/deploy/install.sh | sudo bash
sudoedit /etc/ptt-agent.env      # 填 PTT_ID PTT_PW TELEGRAM_*，選填 YOUTUBE_API_KEY
```

Weverse 要另外放 token。refresh token 會輪替，所以 **VM 要用自己獨立的一份**，不能從 Mac 的 `.weverse-token.json` 複製（兩邊共用會互相讓對方失效）：在無痕視窗登入 weverse.io，複製那個 session 的 `we2_refresh_token`，在 VM 貼進下面的指令後按 Enter、Ctrl-D（值不會進 history）：

```bash
sudo -u ptt-agent sh -c 'umask 077; python3 -c "import json,sys;print(json.dumps({\"refresh_token\":sys.stdin.read().strip()}))" > /opt/ptt-agent/weverse-token.json'
```

先手動測。下面的 `EXEC` 用 systemd-run 載入同一份 `EnvironmentFile` 和 keyring 包裝；沒有設 `PTT_BOARD`/`STATE_PATH`，所以是 `Test` 看板和 `state.dev.json`，不會動正式：

```bash
EXEC='sudo systemd-run --pty --wait --collect -p User=ptt-agent -p WorkingDirectory=/opt/ptt-agent/app \
  -p RuntimeDirectory=ptt-agent -p Environment=XDG_RUNTIME_DIR=/run/ptt-agent \
  -p EnvironmentFile=/etc/ptt-agent.env -p Environment=PATH=/opt/ptt-agent/.local/bin:/usr/local/bin:/usr/bin:/bin'
KR=/opt/ptt-agent/app/deploy/with-keyring.sh

# a. 第一次登入：agy 會印出網址，用別台電腦的瀏覽器登入 Google，把顯示的授權碼貼回來，然後 /exit
eval "$EXEC" $KR agy
# b. 登入有沒有留住：再跑一次，不應該再問登入
eval "$EXEC" $KR agy -p '"/ls test"' --output-format json
# c. 乾跑：翻譯但不發文
eval "$EXEC" $KR uv run --frozen python -m ptt_agent
# d. 發到 Test 看板（經 WARP）
eval "$EXEC" -p Environment=PTT_PROXY=socks5h://127.0.0.1:40000 $KR uv run --frozen python -m ptt_agent --post
```

登入過期時（log 或 Telegram 出現翻譯失敗），重跑 a。

啟用前（**會發到正式看板**）：先停 Mac 的 launchd（`launchctl bootout gui/$(id -u)/com.ptt-agent`）、把 Mac 的 `state.json` 複製到 `/opt/ptt-agent/state.json`（`chown ptt-agent`），再 `sudo systemctl enable --now ptt-agent.timer`。Weverse 不用搬 state：先確認 token 可用（見上），再 `sudo systemctl enable --now ptt-agent-weverse.timer && sudo systemctl start ptt-agent-weverse.service`，第一輪會建立 `/opt/ptt-agent/state.weverse.json` 並把現有 LIVE 記成已看過，log 出現 `first run` 就是對的。這一輪之前出現的 LIVE 不會發，所以避開直播時段。Mac 和 VM 不可同時啟用。

### 查看執行狀態與 log

在 VM 上用有 sudo 的帳號執行（不是 `ptt-agent`）。兩組 unit：`ptt-agent`（YouTube）和 `ptt-agent-weverse`。

```bash
# 排程：NEXT 是下次、LAST 是上次觸發時間；未啟用的 timer 這兩欄是 n/a
systemctl list-timers 'ptt-agent*' --no-pager
systemctl is-enabled ptt-agent.timer ptt-agent-weverse.timer

# 上一輪結果：oneshot 跑完是 inactive (dead)，要看 status=0/SUCCESS 才算成功
systemctl status ptt-agent.service ptt-agent-weverse.service --no-pager
systemctl --failed --no-pager

# log
sudo journalctl -u ptt-agent-weverse.service -f              # 即時跟
sudo journalctl -u ptt-agent.service -n 100 --no-pager
sudo journalctl -u 'ptt-agent*' --since '1 hour ago' --no-pager   # 兩個一起

# 手動跑一輪（會發到正式看板，只在確定要時用）
sudo systemctl start ptt-agent-weverse.service

# 資源：兩個 service 同時跑 agy 可能吃光 1 GB 記憶體
free -m
```

### 搬到新 VM

新舊 VM 不要同時啟用 timer（會重複發文）。順序是先把新 VM 準備好但不啟用，最後才切換。

1. **建新 VM，等 startup script 跑完。** 在 `gcp-free-agents` 用 Terraform 建立（免費額度只有一台 e2-micro，新舊並存會多出費用）。確認 `sudo journalctl -u google-startup-scripts --no-pager | tail` 出現 `[startup] done`，且 `warp-cli --accept-tos status` 是 Connected。
2. **裝 ptt-agent，不啟用 timer：**
   ```bash
   curl -fsSL https://raw.githubusercontent.com/scottxxx666/ptt-agent/main/deploy/install.sh | sudo bash
   sudoedit /etc/ptt-agent.env      # 填 PTT_ID PTT_PW TELEGRAM_*，選填 YOUTUBE_API_KEY
   ```
3. **在新 VM 重新登入 agy**（keyring 是各 VM 自己的，token 不會跟著搬）：上面的測試 a，再用 b 確認登入留得住。
4. **確認 PTT 經 WARP 能登入**（只登入、搜尋、登出，不發文）：
   ```bash
   eval "$EXEC" -p Environment=PTT_PROXY=socks5h://127.0.0.1:40000 $KR uv run --frozen python -c 'import os; from ptt_agent.ptt import PttPoster as P; print(P(os.environ["PTT_ID"], os.environ["PTT_PW"], "Test", 1, proxy=os.environ["PTT_PROXY"]).recent_titles(3))'
   ```
5. **切換，這幾步連續做：**
   1. 舊 VM：`sudo systemctl disable --now ptt-agent.timer`
   2. 搬 state。它只是影片 id 的清單，直接貼：舊 VM `sudo cat /opt/ptt-agent/state.json`；新 VM `sudo -u ptt-agent tee /opt/ptt-agent/state.json`（貼上後按 Ctrl-D）。**不要讓新 VM 自己建 state**：它會把當下所有影片標成已看過，舊 VM 停機到新 VM 啟用之間出的影片就不會發。
   3. 新 VM：`sudo systemctl enable --now ptt-agent.timer`，必要時 `sudo systemctl start ptt-agent.service` 跑第一輪，用 `sudo journalctl -u ptt-agent.service -f` 看 log。
6. 確認新 VM 正常後，再刪舊 VM。

外部 IP 會變：PTT 用帳密登入，不依賴 IP 白名單，但同一個專案裡有設舊 IP 白名單的服務（例如 bbgo 的交易所 API）要更新。
