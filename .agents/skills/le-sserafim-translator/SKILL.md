---
name: le-sserafim-translator
description: Translate LE SSERAFIM content (Weverse, interviews, SNS, Japanese/Korean/English) into natural Taiwan Traditional Chinese. Trigger immediately when the user message starts with /ls or asks for LE SSERAFIM translation.
---

# LE SSERAFIM 專用台灣繁體中文翻譯規範

當使用者以 `/ls` 開頭或提供 LE SSERAFIM 相關內容時，請依據以下規範進行翻譯與潤稿。

## 1. 成員與團體名稱官方譯名對照
- **LE SSERAFIM**：保留英文，不另作音譯（社群口語或速記情境可稱「梯」或「塞拉」）。
- **宮脇咲良**（Sakura / 사쿠라）：宮脇咲良（暱稱：小櫻花、Kkura、櫻花）。
- **金采源**（Kim Chaewon / 김채원）：金采源（暱稱：采采、Ssamachi、金隊長）。
- **許允真**（Huh Yunjin / 허윤진）：許允真（暱稱：允真、Jennifer、熱血少女）。
- **中村一葉**（Kazuha / 카즈하）：中村一葉（暱稱：一葉、Zuha、一葉天鵝）。
- **洪恩採**（Hong Eunchae / 홍은채）：洪恩採（暱稱：恩採、忙內、微笑土豆、MC恩採）。
- **FEARNOT**（피어나）：保留「FEARNOT」或音譯「皮歐娜」。

## 2. 翻譯與在地化原則
1. **台灣在地繁體中文**：
   - 語氣自然、口語化，完全符合台灣網路社群與 K-POP 追星用語習慣（例：影片、貼文、社群、追蹤、IG、限動、應援、回歸、主打歌、打歌舞台、簽售）。
   - 嚴格避免中國大陸用語（如：視頻、艾特、取關、安利、打call、網紅、給力、立馬、抓馬等）。
2. **語氣還原**：
   - **Weverse / SNS 貼文與回覆**：還原成員親切、撒嬌或日常的語氣（使用適當的台灣日常語助詞如「啦」、「呢」、「～」、「><」）。
   - **採訪 / 官方公告**：保持得體、真誠與專業語氣。
   - **成員互動 / 吵鬧風格**：保留自然口語互虧與開玩笑氛圍。
3. **輸出格式規範（嚴格遵守）**：
   - 輸入為單純一行影片標題，不需要讀取或搜尋任何檔案，也不要執行任何 shell 指令，直接翻譯後輸出 JSON。
   - 只輸出一個純 JSON 物件，嚴禁包含任何其他文字：不要 markdown、不要 ``` 或 ```json 程式碼框、不要標題、分隔線或任何補充說明。
   - JSON 欄位：
     - `title_zh`：影片標題的繁體中文翻譯，只有標題本身，不要加潤飾建議或其他備註。
     - `title_original`：原文標題，原樣照抄。
   - 輸出範例：
   {"title_zh": "影片標題繁中翻譯", "title_original": "原文標題"}
