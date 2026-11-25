import contextlib
import logging
import re

import pytest

from ptt_agent import ptt_edit
from ptt_agent.ptt import PttPoster
from ptt_agent.ptt_edit import EditError, edit_post, normalize_content, parse_editor, replace_keys

ESC = "\x1b"
HEADER = ["作者: me (暱稱) 看板: Test", "標題: [測試] edit me", "時間: Thu Nov 26 00:10:24 2026", ""]
BODY = [ESC + "[1;33m第一行黃色" + ESC + "[m", "", "第三行 https://youtu.be/v1VHwNp1LOo", "第四行", "第五行", ""]
FOOTER = ["--", "※ 發信站: 批踢踢實業坊(ptt.cc), 來自: 1.2.3.4 (美國)",
          "※ 文章網址: https://www.ptt.cc/bbs/Test/M.1795623026.A.695.html", ""]
BOARD_LIST = ["【板主:x】  看板《Test》  [i]看板設定", "", "●  457 11/26 me  □ [測試] edit me",
              " 文章列表  (^P)發表 (y)回應 (X)推文 (d)刪除 (→)閱讀 (b)進板  (←)離開 (h)說明"]


class Term:
    """Model of PTT's board list, article editor, its file menu and the title prompt, as seen live:
    the menu answer is a line-input field and any answer other than a/t/e saves."""

    def __init__(self, file=None, rows=24, title_clears=True, after_save=None, drop_char=None, menu_echo=None):
        self.file = list(file if file is not None else HEADER + BODY + FOOTER)
        self.saved = None
        self.saved_title = None
        self.title = "[測試] edit me"
        self.rows, self.title_clears, self.after_save, self.drop_char = rows, title_clears, after_save, drop_char
        self.menu_echo = menu_echo  # what the menu field shows instead of the typed text (a glitch)
        self.reader_extra = 0  # rows the reader shows more (a wrapped long line) or fewer than the editor
        self.top = 0
        self.state, self.queue, self.sent, self.closed, self.submitted = "board", [], [], False, []

    # --- input -----------------------------------------------------------------------------------
    def feed(self, keys: str) -> None:
        self.sent.append(keys)
        i = 0
        while i < len(keys):
            if keys.startswith(("\x1bOB", "\x1bOA"), i):
                self.key("DOWN" if keys[i + 2] == "B" else "UP")
                i += 3
            else:
                self.key(keys[i])
                i += 1

    def key(self, k: str) -> None:
        if k == "\x0c":
            return
        s = self.state
        if s == "board":
            if k == "E":
                self.lines, self.row, self.col, self.state = list(self.file), 0, 0, "editor"
                self.top = 0
                self.new_title = self.title
        elif s == "editor":
            line = self.lines[self.row]
            if k == "DOWN":
                self.row, self.col = min(self.row + 1, len(self.lines) - 1), 0
                self.scroll()
            elif k == "UP":
                self.row, self.col = max(self.row - 1, 0), 0
                self.top = min(self.top, self.row)
            elif k == "\x19":
                del self.lines[self.row]
                self.col = 0
            elif k == "\r":
                self.lines[self.row:self.row + 1] = [line[:self.col], line[self.col:]]
                self.row, self.col = self.row + 1, 0
                self.scroll()
            elif k == "\x18":
                self.state, self.menu_buf = "menu", ""
            else:
                if k == self.drop_char:
                    return
                k = ESC if k == "\x15" else k
                self.lines[self.row] = line[:self.col] + k + line[self.col:]
                self.col += 1
        elif s == "menu":
            if k == "\x19":
                self.menu_buf = ""
            elif k == "\r":
                choice = self.menu_buf
                self.submitted.append(choice)
                if choice == "a":
                    self.state = "board"
                elif choice == "t":
                    self.state, self.title_buf = "title", self.title
                elif choice == "e":
                    self.state = "editor"
                else:  # PTT: (S) and anything unrecognised save
                    self.saved, self.saved_title = list(self.lines), self.new_title
                    self.title = self.new_title
                    i = max(i for i, r in enumerate(self.saved) if r.startswith("※"))
                    self.saved.insert(i + 1, "※ 編輯: me (1.2.3.4 美國), 11/26/2026 00:22:36")
                    self.file = self.saved
                    self.state = self.after_save or "board"
            else:
                self.menu_buf += k
        elif s == "title":
            if k == "\x19":
                if self.title_clears:
                    self.title_buf = ""
            elif k == "\r":
                self.new_title, self.state, self.row, self.col, self.top = self.title_buf, "editor", 0, 0, 0
            else:
                self.title_buf += k
        elif s == "anykey":
            self.state = "board"

    def scroll(self) -> None:
        """Live recon: past the last content row the view scrolls by one, cursor stays on that row."""
        self.top = max(self.top, self.row - (self.rows - 2))

    # --- output ----------------------------------------------------------------------------------
    def render(self) -> str:
        if self.state in ("board", "anykey"):
            rows = list(BOARD_LIST)
            if self.state == "anykey":
                rows[-1] = "請按任意鍵繼續"
            return "\n".join(rows)
        if self.state == "weird":
            return "something nobody expected"
        shown = [line.replace(ESC, "*") for line in self.lines][self.top:self.top + self.rows - 1]
        shown += ["~"] * (self.rows - 1 - len(shown))
        if self.state == "editor":
            status = f" 編輯文章  (^X)存檔 (^C)色碼   ║插入│aipr║{self.row + 1:3d}:{self.col + 1:3d}"
            return "\n".join(shown + [status])
        menu = ["【檔案處理】", "[S/V]儲存 (U)上傳資料 (T)改標題 (A)放棄 (E)繼續 (R/W/D)讀寫刪暫存檔"]
        if self.state == "menu":
            field = self.menu_echo if self.menu_echo is not None else self.menu_buf
            return "\n".join(shown[:-3] + menu + ["確定要儲存檔案嗎？ " + field])
        return "\n".join(shown[:-5] + menu + ["確定要儲存檔案嗎？ t", "舊標題：" + self.title,
                                              "新標題：" + self.title_buf])


class Core:
    def __init__(self, term):
        self.term, self.last_timeout_was_silent = term, False

    def send(self, keys, target_list, screen_timeout=0, refresh=True):
        self.term.feed(keys)
        screen = self.term.render()
        self.term.queue.append(screen)
        for i, t in enumerate(target_list):
            if t.is_match(screen, "●"):
                return i
        return -1

    def get_screen_queue(self):
        return self.term.queue[-1:]

    def close(self):
        self.term.closed = True


class Api:
    def __init__(self, term, author="me"):
        import PyPtt
        self.term, self.ptt_id, self.cursor, self._is_login = term, "me", "●", True
        self.config = type("C", (), {"screen_timeout": 3.0, "screen_post_timeout": 60.0})()
        self.connect_core = Core(term)
        self._current_board, self._current_search = "test", ()
        self.author, self.calls = author, []
        self.post_fields = PyPtt.PostField

    def get_post(self, board, aid=None, query=False):
        import PyPtt
        self.calls.append(("get_post", board, aid, query))
        lines = self.term.saved or self.term.file
        content = "\n".join(lines).replace(ESC, "")
        # The reader: header boxes and a ─── separator instead of the editor's blank row, colours rendered.
        body = [re.sub(ESC + r"\[[0-9;]*m", "", r) for r in lines[4:]][max(-self.term.reader_extra, 0):]
        reader = ([f" 作者  {lines[0][4:]}", f" 標題  {lines[1][4:]}", f" 時間  {lines[2][4:]}", "─" * 78]
                  + ["(wrapped)"] * self.term.reader_extra + body)
        # Like PyPtt: query=True gives the board-list title, a full read parses the header row.
        title = self.term.title if query else lines[1][len("標題: "):]
        return {PyPtt.PostField.post_status: PyPtt.PostStatus.EXISTS, PyPtt.PostField.author: self.author,
                PyPtt.PostField.title: title, PyPtt.PostField.content: content,
                PyPtt.PostField.full_content: "\n".join(reader)}


@pytest.fixture(autouse=True)
def no_goto_board(monkeypatch):
    from PyPtt import _api_util
    monkeypatch.setattr(_api_util, "goto_board", lambda api, board, **kw: api.calls.append(("goto", board)))


NEW = "\x15[1;33m新的第一行\x15[m\n\n新的 https://youtu.be/x\n"
NEW_ROWS = ["*[1;33m新的第一行*[m", "", "新的 https://youtu.be/x"]


def test_parse_editor_on_the_recon_screen():
    term = Term()
    term.key("E")
    ed = parse_editor(term.render(), "me", "Test")
    assert ed.body == ["*[1;33m第一行黃色*[m", "", "第三行 https://youtu.be/v1VHwNp1LOo", "第四行", "第五行", ""]
    assert ed.footer == FOOTER[:3] and ed.cursor == (1, 1)


def test_parse_editor_rejects_wrong_author_board_title_and_missing_signature():
    term = Term()
    term.key("E")
    for kw in (dict(ptt_id="other"), dict(board="Gossiping")):
        with pytest.raises(EditError):
            parse_editor(term.render(), **kw)
    long = Term(file=HEADER + [f"line {i}" for i in range(30)] + FOOTER)
    long.key("E")
    with pytest.raises(EditError, match="first screen"):
        parse_editor(long.render())


def test_replace_keys_goes_to_the_body_deletes_it_and_types_above_the_signature():
    term = Term()
    term.key("E")
    ed = parse_editor(term.render())
    keys = replace_keys(ed, ["a", "b"])
    assert keys == "\x1bOB" * 4 + "\x19" * 6 + "a\rb\r\r"


def test_normalize_content_allows_only_text_newlines_and_ctrl_u():
    assert normalize_content("a\r\nb\n\n") == ["a", "b"]
    assert normalize_content("") == []
    for bad in ("a\x18b", "a\tb", "a\x1b[m", "😀"):
        with pytest.raises(EditError):
            normalize_content(bad)


def test_dump_opens_the_editor_and_abandons(caplog):
    term = Term()
    shown = edit_post(Api(term), "Test", "#1h1mXoQL", None)
    assert shown.startswith("作者: me") and "--" in shown.split("\n")
    assert term.saved is None and term.state == "board" and not term.closed
    assert term.submitted == ["a"]


def test_rehearsal_types_and_verifies_then_abandons():
    term = Term()
    shown = edit_post(Api(term), "Test", "1h1mXoQL", NEW)
    assert shown.split("\n")[:11] == HEADER + NEW_ROWS + [""] + FOOTER[:3]
    assert term.saved is None and term.state == "board"


def test_save_replaces_only_the_body():
    term = Term()
    api = Api(term)
    edit_post(api, "Test", "1h1mXoQL", NEW, save=True)
    assert term.saved == (HEADER + [r.replace("*", ESC) for r in NEW_ROWS] + [""] + FOOTER[:3]
                          + ["※ 編輯: me (1.2.3.4 美國), 11/26/2026 00:22:36", ""])
    assert term.submitted == ["s"]
    assert term.state == "board" and not term.closed
    assert api.calls[-2:] == [("get_post", "Test", "1h1mXoQL", False), ("get_post", "Test", "1h1mXoQL", True)]


def test_save_through_any_key_page():
    term = Term(after_save="anykey")
    edit_post(Api(term), "Test", "1h1mXoQL", "x", save=True)
    assert term.saved is not None and term.state == "board"


def test_save_with_new_title():
    term = Term()
    edit_post(Api(term), "Test", "1h1mXoQL", "x", title="[測試] new title", save=True)
    assert term.saved_title == "[測試] new title" and term.saved[:4] == HEADER
    assert term.submitted == ["t", "s"]


def test_title_prompt_not_cleared_abandons_without_saving():
    term = Term(title_clears=False)
    with pytest.raises(EditError, match="新標題"):
        edit_post(Api(term), "Test", "1h1mXoQL", "x", title="[測試] new title", save=True)
    assert term.saved is None and term.submitted == ["t", "a"] and term.state == "board"


def test_mistyped_body_is_abandoned_not_saved(caplog):
    term = Term(drop_char="新")
    with caplog.at_level(logging.ERROR, logger="ptt_agent"):
        with pytest.raises(EditError, match="expected text"):
            edit_post(Api(term), "Test", "1h1mXoQL", NEW, save=True)
    assert term.saved is None and term.state == "board"
    assert "編輯文章" in caplog.text  # the screen is logged


def test_body_longer_than_one_screen_is_refused_before_typing():
    term = Term(file=HEADER + [f"line {i}" for i in range(30)] + FOOTER)
    with pytest.raises(EditError, match="first screen"):
        edit_post(Api(term), "Test", "1h1mXoQL", "x", save=True)
    assert term.saved is None and term.state == "board"
    assert not any("\x1bOB" in k for k in term.sent)


def test_new_body_too_long_for_one_screen_is_refused_before_typing():
    term = Term()
    with pytest.raises(EditError, match="fit"):
        edit_post(Api(term), "Test", "1h1mXoQL", "\n".join(["x"] * 20), save=True)
    assert term.saved is None and not any("\x1bOB" in k for k in term.sent)


def test_someone_elses_post_is_refused_before_any_key():
    term = Term()
    with pytest.raises(EditError, match="not me"):
        edit_post(Api(term, author="other"), "Test", "1h1mXoQL", "x", save=True)
    assert term.sent == []


def test_bad_inputs_are_refused_before_any_key():
    term = Term()
    for kw in (dict(aid="123", content="x"), dict(aid="1h1mXoQL", content="a\x18"),
               dict(aid="1h1mXoQL", content="x", title="x" * 45)):
        with pytest.raises(EditError):
            edit_post(Api(term), "Test", kw.pop("aid"), **kw)
    assert term.sent == []


def test_unknown_screen_after_save_disconnects():
    term = Term(after_save="weird")
    with pytest.raises(EditError, match="after saving"):
        edit_post(Api(term), "Test", "1h1mXoQL", "x", save=True)
    assert term.closed


def test_poster_edit_logs_in_uses_its_board_and_logs_out(monkeypatch):
    seen = {}

    class FakeApi:
        def login(self, **kw):
            seen["login"] = kw

        def logout(self):
            seen["logout"] = True
    monkeypatch.setattr(ptt_edit, "edit_post", lambda api, board, aid, content, **kw: seen.update(
        board=board, aid=aid, content=content, kw=kw) or "screen")
    p = PttPoster("me", "pw", "Test", 1, api_factory=FakeApi)
    assert p.edit("1h1mXoQL", "body", title="t") == "screen"
    assert seen["board"] == "Test" and seen["kw"] == dict(title="t", save=False) and seen["logout"]


def test_unexpected_error_in_the_editor_disconnects_instead_of_logging_out_into_it(monkeypatch):
    term = Term()
    monkeypatch.setattr(ptt_edit.EditDriver, "replace_body", lambda *a: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(TimeoutError):
        edit_post(Api(term), "Test", "1h1mXoQL", "x", save=True)
    assert term.closed and term.saved is None


def test_menu_field_not_showing_the_letter_is_never_submitted():
    # PTT saves on an unrecognised answer, so a field that does not show exactly "s"/"a" gets no Enter.
    for save in (True, False):
        term = Term(menu_echo="?")
        with pytest.raises(EditError) if save else contextlib.nullcontext():
            edit_post(Api(term), "Test", "1h1mXoQL", "x", save=save)
        assert term.submitted == [] and term.saved is None and term.closed


def test_title_flow_failing_at_the_menu_is_not_submitted():
    term = Term(menu_echo="?")
    with pytest.raises(EditError):
        edit_post(Api(term), "Test", "1h1mXoQL", "x", title="[測試] new", save=True)
    assert term.submitted == [] and term.saved is None


def test_editing_again_keeps_earlier_edit_lines_and_adds_one():
    term = Term()
    edit_post(Api(term), "Test", "1h1mXoQL", "first", save=True)
    edit_post(Api(term), "Test", "1h1mXoQL", "second", save=True)
    assert term.saved[4:6] == ["second", ""]
    assert [r for r in term.saved if r.startswith("※ 編輯:")] == ["※ 編輯: me (1.2.3.4 美國), 11/26/2026 00:22:36"] * 2
    assert term.saved[6:9] == FOOTER[:3]


def test_title_read_back_uses_the_list_title_and_reports_a_mismatch(caplog):
    term = Term()
    api = Api(term)
    with caplog.at_level(logging.WARNING, logger="ptt_agent"):
        edit_post(api, "Test", "1h1mXoQL", "x", title="[測試] new", save=True)
    assert "list title" not in caplog.text  # header row still says the old title; that is expected
    real = api.get_post

    def stale_after_save(board, aid=None, query=False):
        post = real(board, aid, query)
        if query and term.saved[4] == "y":  # only the read-back of the second edit
            post[api.post_fields.title] = "stale"
        return post
    api.get_post = stale_after_save
    with caplog.at_level(logging.WARNING, logger="ptt_agent"):
        edit_post(api, "Test", "1h1mXoQL", "y", title="[測試] newer", save=True)
    assert "its list title is 'stale'" in caplog.text


def test_renamed_post_header_keeps_old_title_and_can_be_edited_and_renamed_again():
    term = Term()
    edit_post(Api(term), "Test", "1h1mXoQL", "x", title="[測試] renamed", save=True)
    assert term.title == "[測試] renamed" and term.saved[1] == HEADER[1]  # (T) leaves the header row alone
    assert edit_post(Api(term), "Test", "1h1mXoQL", None).split("\n")[1] == HEADER[1]  # dump still works
    edit_post(Api(term), "Test", "1h1mXoQL", "y", title="[測試] again", save=True)
    assert term.title == "[測試] again" and term.saved[4] == "y" and term.saved[:4] == HEADER
    assert sum(r.startswith("※ 編輯:") for r in term.saved) == 2


# ---- append (posts longer than one screen) ----
from ptt_agent.ptt_edit import append_post, parse_post_text


def live_rows(i):
    return [f"{ESC}[1;33m測試直播第{i}場{ESC}[m {ESC}[1;36m采源{ESC}[m", "", f"https://weverse.io/lesserafim/live/7-10000{i}", ""]


def lives_post(n, extra_edits=0):
    """Like the recon post 1h1nE93B: n blocks of 4 rows, then the footer and an empty last line."""
    rows = HEADER[:]
    for i in range(1, n + 1):
        rows += live_rows(i)
    edits = ["※ 編輯: me (1.2.3.4 美國), 11/26/2026 00:22:36"] * extra_edits
    return rows + FOOTER[:3] + edits + [""]


ADD = "\x15[1;33m新直播\x15[m \x15[1;36m允真\x15[m\n\nhttps://weverse.io/lesserafim/live/9-1\n"
ADD_ROWS = [f"{ESC}[1;33m新直播{ESC}[m {ESC}[1;36m允真{ESC}[m", "", "https://weverse.io/lesserafim/live/9-1"]


def with_added(file, rows, pad=False):
    sig = file.index("--")
    return file[:sig] + [""] * pad + rows + [""] + file[sig:]


def downs(term):
    return sum(k.count("\x1bOB") for k in term.sent), sum(k.count("\x1bOA") for k in term.sent)


def test_parse_post_text_counts_editor_lines_like_the_recon_post():
    term = Term(file=lives_post(7))
    text = Api(term).get_post("Test", aid="1h1nX93B")[Api(term).post_fields.full_content]
    pt = parse_post_text(text)
    assert pt.sig_line == 33 and len(pt.body) == 28 and pt.body[0] == "測試直播第1場 采源"
    with pytest.raises(EditError, match="───"):
        parse_post_text("\n".join(HEADER + FOOTER))  # editor text, not the reader's
    with pytest.raises(EditError, match="2 '--'"):
        parse_post_text(text.replace("live/7-100003", "x\n--\n※ 發信站: quoted"))


@pytest.mark.parametrize("n", [1, 4, 5, 7, 12])
def test_append_saves_the_rows_right_above_the_signature(n):
    term = Term(file=lives_post(n, extra_edits=2))
    old = list(term.file)
    result = append_post(Api(term), "Test", "1h1nX93B", ADD, save=True)
    assert result.saved and result.verified
    want = with_added(old, ADD_ROWS)
    i = max(i for i, r in enumerate(want) if r.startswith("※"))
    assert term.saved == want[:i + 1] + ["※ 編輯: me (1.2.3.4 美國), 11/26/2026 00:22:36"] + want[i + 1:]
    assert term.submitted == ["s"] and term.state == "board" and not term.closed
    sig_line = 4 + 4 * n + 1
    assert downs(term) == (sig_line + 1, 2)  # to '※ 發信站:', Up; after typing Down + Up
    assert all("\x19" not in k for k in term.sent if k != "\x19s")  # no row deleted (Ctrl+Y: menu answer only)


def test_append_rehearsal_verifies_then_abandons():
    term = Term(file=lives_post(7))
    old = list(term.file)
    result = append_post(Api(term), "Test", "1h1nX93B", ADD)
    assert not result.saved and term.saved is None and term.file == old and term.submitted == ["a"]
    rows = result.screen.split("\n")
    assert rows[-1].rstrip().endswith("37:  1")  # cursor back on '--', 4 rows lower
    sig = rows.index("--")
    assert rows[sig - 6:sig + 1] == ["https://weverse.io/lesserafim/live/7-100007", ""] + [
        r.replace(ESC, "*") for r in ADD_ROWS] + ["", "--"]


def test_append_dump_shows_the_signature_row_and_types_nothing():
    term = Term(file=lives_post(7))
    result = append_post(Api(term), "Test", "1h1nX93B", None)
    rows = result.screen.split("\n")
    assert rows[21:23] == ["--", FOOTER[1]] and rows[-1].endswith("33:  1")
    assert term.saved is None and term.submitted == ["a"] and not term.closed


def test_append_to_a_short_post_and_a_body_without_trailing_blank():
    term = Term()  # BODY ends with a blank row
    append_post(Api(term), "Test", "1h1mXoQL", "加一行", save=True)
    assert term.saved[:12] == HEADER + [r for r in BODY] + ["加一行", ""]
    file = HEADER + ["沒有空行結尾"] + FOOTER
    term = Term(file=file)
    append_post(Api(term), "Test", "1h1mXoQL", "加一行", save=True)
    assert term.saved[:9] == HEADER + ["沒有空行結尾", "", "加一行", "", "--"]


def test_append_twice_keeps_the_layout_and_accumulates_edit_rows():
    term = Term(file=lives_post(6))
    append_post(Api(term), "Test", "1h1nX93B", ADD, save=True)
    append_post(Api(term), "Test", "1h1nX93B", ADD.replace("9-1", "9-2"), save=True)
    sig = term.saved.index("--")
    assert term.saved[sig - 8:sig + 1] == ADD_ROWS + [""] + ADD_ROWS[:2] + [ADD_ROWS[2].replace("9-1", "9-2"), "", "--"]
    assert sum(r.startswith("※ 編輯:") for r in term.saved) == 2


def test_append_line_count_mismatch_is_abandoned_before_typing(caplog):
    for extra in (1, -1):  # reader shows one row more (wrapped line) / fewer than the editor
        term = Term(file=lives_post(7))
        term.reader_extra = extra
        with caplog.at_level(logging.ERROR, logger="ptt_agent"):
            with pytest.raises(EditError, match="not '--'"):
                append_post(Api(term), "Test", "1h1nX93B", ADD, save=True)
        assert term.saved is None and term.submitted == ["a"] and term.state == "board"
        assert not any("新直播" in k for k in term.sent)


def test_append_reader_longer_than_the_file_stops_at_the_clamped_cursor():
    term = Term(file=lives_post(7)[:-1])  # no empty last line: cannot go below '※ 文章網址'
    term.reader_extra = 3
    with pytest.raises(EditError, match="cursor at"):
        append_post(Api(term), "Test", "1h1nX93B", ADD, save=True)
    assert term.saved is None and not any("新直播" in k for k in term.sent)


def test_append_mistyped_is_abandoned_not_saved():
    term = Term(file=lives_post(7), drop_char="新")
    with pytest.raises(EditError, match="rows above"):
        append_post(Api(term), "Test", "1h1nX93B", ADD, save=True)
    assert term.saved is None and term.submitted == ["a"]


def test_append_refuses_bad_or_oversized_content_before_any_key():
    term = Term(file=lives_post(7))
    with pytest.raises(EditError, match="control"):
        append_post(Api(term), "Test", "1h1nX93B", "a\x18b")
    with pytest.raises(EditError, match="at most"):
        append_post(Api(term), "Test", "1h1nX93B", "\n".join(["x"] * 20))
    with pytest.raises(EditError, match="bad AID"):
        append_post(Api(term), "Test", "123", ADD)
    assert term.sent == []


def test_append_callable_gets_the_body_and_empty_means_no_edit():
    term = Term(file=lives_post(3))
    got = []
    result = append_post(Api(term), "Test", "1h1nX93B", lambda body: got.append(body) or "")
    assert "https://weverse.io/lesserafim/live/7-100002" in got[0].split("\n") and "*[" not in got[0]
    assert result.screen == "" and not result.saved and term.sent == []


def test_append_read_back_mismatch_is_reported_not_fixed(caplog):
    term = Term(file=lives_post(7))
    api = Api(term)
    real = api.get_post

    def stale(board, aid=None, query=False):
        post = real(board, aid, query)
        if term.saved is not None and not query:
            post[api.post_fields.full_content] = post[api.post_fields.full_content].replace("新直播", "舊")
        return post
    api.get_post = stale
    with caplog.at_level(logging.WARNING, logger="ptt_agent"):
        result = append_post(api, "Test", "1h1nX93B", ADD, save=True)
    assert result.saved and not result.verified and "not old body + new rows" in caplog.text
    assert term.submitted == ["s"]  # one save, no attempt to fix it


def test_append_unexpected_error_disconnects(monkeypatch):
    term = Term(file=lives_post(7))
    monkeypatch.setattr(ptt_edit.AppendDriver, "type_above_sig", lambda *a: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(TimeoutError):
        append_post(Api(term), "Test", "1h1nX93B", ADD, save=True)
    assert term.closed and term.saved is None


def test_poster_append_logs_in_uses_its_board_and_logs_out(monkeypatch):
    seen = {}

    class FakeApi:
        def login(self, **kw):
            seen["login"] = kw

        def logout(self):
            seen["logout"] = True
    monkeypatch.setattr(ptt_edit, "append_post", lambda api, board, aid, content, **kw: seen.update(
        board=board, aid=aid, content=content, kw=kw) or "result")
    assert PttPoster("me", "pw", "Test", 1, api_factory=FakeApi).append("1h1nX93B", "x") == "result"
    assert seen["board"] == "Test" and seen["kw"] == dict(save=False) and seen["logout"]


@pytest.mark.parametrize("sig_line", range(19, 27))
def test_append_around_the_first_scroll(sig_line):
    file = HEADER + [f"row {i}" for i in range(sig_line - 6)] + [""] + FOOTER[:3] + [""]
    term = Term(file=file)
    assert file.index("--") + 1 == sig_line
    append_post(Api(term), "Test", "1h1nX93B", ADD, save=True)
    assert term.saved[:sig_line + 4] == with_added(file, ADD_ROWS)[:sig_line + 4]
