"""Edit one of our own PTT posts by driving the article editor (PyPtt 2.3.19 has no edit API).

Flow, mirroring PyPtt's own _api_post.post: goto_board, "#AID" Enter, "E" opens the editor with the
cursor on row 1 (the "作者:" header line). The body region is the rows between the blank line after
the 3 header lines and the "--" line that precedes "※ 發信站:". It is replaced by moving down to it,
deleting it with Ctrl+Y line by line and typing the new body, so the header and footer are never
touched. Only articles whose header..※ 發信站 fit on the first screen are supported; longer ones are
refused before any key that changes the text is sent.

append_post adds rows right above "--" and works on posts of any length: the "--" line number is
computed from the post text read beforehand, the cursor is moved there with verified Down keys, and
nothing is typed unless the editor shows the cursor on that line with "--" under it and "※ 發信站:"
below. Existing rows are never deleted.

Safety: nothing is saved unless the editor screen after typing equals exactly what we expect
(header unchanged, new body, blank line, the original footer incl. any "※ 編輯:" rows). Anything else
in the editor or its file menu -> Ctrl+X, "a" Enter (abandon). The menu answer is a line-input field
where an unrecognised answer means SAVE, so Enter is only sent once the field shows exactly the
intended letter. A screen we cannot place at all -> disconnect, which never saves either.
"""
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("ptt_agent")

CTRL_U, CTRL_X, CTRL_Y, ENTER = "\x15", "\x18", "\x19", "\r"
DOWN, UP = "\x1bOB", "\x1bOA"
SIGN_START = "※ 發信站:"
SEPARATOR = "───────────────────────────────────────"  # PyPtt screens.Target.content_start
MOVE_CHUNK = 20  # Down keys per send while moving to the "--" row; the line is checked after each
EDITOR_STATUS = "編輯文章"
MENU_PROMPT = "確定要儲存檔案嗎？"  # Ctrl+X file menu; its answer is a line-input field
OLD_TITLE, NEW_TITLE = "舊標題：", "新標題："
ANY_KEY = "任意鍵"
MAX_TITLE_BYTES = 44
HEADER_ROWS = 4  # 作者 / 標題 / 時間 / blank
_STATUS_POS = re.compile(r"(\d+):\s*(\d+)\s*$")
_REFRESH_TRIES = 4


class EditError(RuntimeError):
    """The edit was not saved (refused before typing, or abandoned)."""


@dataclass
class EditorScreen:
    lines: list[str]   # rstripped screen rows, status bar included
    status_row: int
    sig_row: int       # row of the "--" line

    @property
    def header(self) -> list[str]:
        return self.lines[:HEADER_ROWS]

    @property
    def body(self) -> list[str]:
        return self.lines[HEADER_ROWS:self.sig_row]

    @property
    def footer(self) -> list[str]:
        """'--' and what follows it on screen, up to the status bar, without the trailing '~' filler."""
        rows = self.lines[self.sig_row:self.status_row]
        while rows and rows[-1] in ("", "~"):
            rows.pop()
        return rows

    @property
    def cursor(self) -> tuple[int, int] | None:
        m = _STATUS_POS.search(self.lines[self.status_row])
        return (int(m.group(1)), int(m.group(2))) if m else None


def _rows(screen: str) -> list[str]:
    rows = [r.rstrip() for r in screen.split("\n")]
    while rows and not rows[-1]:
        rows.pop()
    return rows


def parse_editor(screen: str, ptt_id: str | None = None, board: str | None = None,
                 need_sig: bool = True) -> EditorScreen:
    """Recognise the editor of an article; raise EditError on any unexpected layout.
    need_sig=False accepts a first screen without the "--" row (sig_row is then -1).

    The 標題: row is not compared with the post's title: (T)改標題 only changes the board-list title,
    the article header keeps the title the post was made with."""
    lines = _rows(screen)
    if not lines or EDITOR_STATUS not in lines[-1]:
        raise EditError("not in the article editor (no 編輯文章 status bar)")
    status_row = len(lines) - 1
    if len(lines) < HEADER_ROWS + 2:
        raise EditError("editor screen too short")
    author, title_line, time_line, blank = lines[:HEADER_ROWS]
    if not (author.startswith("作者:") and "看板:" in author and title_line.startswith("標題:")
            and time_line.startswith("時間:") and blank == ""):
        raise EditError("editor header is not 作者/標題/時間/blank")
    if ptt_id and not re.match(rf"作者:\s*{re.escape(ptt_id)}\b", author, re.IGNORECASE):
        raise EditError(f"editor author is not {ptt_id}")
    if board and not re.search(rf"看板:\s*{re.escape(board)}\s*$", author, re.IGNORECASE):
        raise EditError(f"editor board is not {board}")
    sig_row = next((i for i in range(HEADER_ROWS, status_row - 1)
                    if lines[i] == "--" and lines[i + 1].startswith("※ 發信站:")), None)
    if sig_row is None:
        if not need_sig:
            return EditorScreen(lines, status_row, -1)
        raise EditError("'--' + '※ 發信站:' not on the first screen (body longer than one screen?)")
    return EditorScreen(lines, status_row, sig_row)


def normalize_content(content: str) -> list[str]:
    """Body lines to type. Only printable text, newlines and Ctrl+U (color codes) are allowed:
    any other control key would act as an editor command mid-typing."""
    content = content.replace("\r\n", "\n").rstrip("\n")
    for c in content:
        if c not in ("\n", CTRL_U) and (ord(c) < 0x20 or ord(c) == 0x7f):
            raise EditError(f"content contains control character {c!r}")
    try:
        content.encode("big5uao")
    except UnicodeEncodeError as e:
        raise EditError(f"content has a character PTT cannot encode: {e}") from e
    return [line.rstrip() for line in content.split("\n")] if content else []


def check_title(title: str) -> None:
    if any(ord(c) < 0x20 or ord(c) == 0x7f for c in title):
        raise EditError("title must not contain control characters")
    try:
        size = len(title.encode("big5uao"))
    except UnicodeEncodeError as e:
        raise EditError(f"title has a character PTT cannot encode: {e}") from e
    if not title.strip() or size > MAX_TITLE_BYTES:
        raise EditError(f"title must be 1..{MAX_TITLE_BYTES} Big5 bytes (got {size})")


def displayed(line: str) -> str:
    """How the editor shows a typed line: the ESC that Ctrl+U inserts is drawn as '*'."""
    return line.replace(CTRL_U, "*")


def expected_rows(before: EditorScreen, body: list[str]) -> list[str]:
    """Rows the editor must show after the body is replaced: header, body, blank, footer."""
    return before.header + [displayed(b) for b in body] + [""] + before.footer


def replace_keys(before: EditorScreen, body: list[str]) -> str:
    """From the cursor at row 1 col 1: go to the first body row, delete the old body, type the new one.
    Typing at column 1 of the '--' row inserts above it, so each Enter pushes '--' down."""
    return (DOWN * HEADER_ROWS + CTRL_Y * len(before.body)
            + "".join(line + ENTER for line in body) + ENTER)


def check_replaced(before: EditorScreen, body: list[str], screen: str, check_cursor: bool = True) -> EditorScreen:
    after = parse_editor(screen)
    want = expected_rows(before, body)
    got = after.lines[:len(want)]
    if got != want:
        diff = [f"row {i + 1}: want {w!r} got {g!r}"
                for i, (w, g) in enumerate(zip(want, got + [None] * len(want))) if w != g]
        raise EditError("editor does not show the expected text: " + "; ".join(diff[:5]))
    if check_cursor and after.cursor != (HEADER_ROWS + len(body) + 2, 1):
        raise EditError(f"cursor at {after.cursor}, expected the start of the '--' row")
    return after


def last_row(screen: str) -> str:
    rows = _rows(screen)
    return rows[-1] if rows else ""


def menu_field(screen: str) -> str | None:
    """Text typed in the 確定要儲存檔案嗎？ field, or None if that field is not the focused (last) row.
    (The menu rows stay on screen under the title prompt, so the prompt anywhere is not enough.)"""
    row = last_row(screen)
    if not row.startswith(MENU_PROMPT):
        return None
    return row[len(MENU_PROMPT):].strip()


def title_field(screen: str) -> str | None:
    row = last_row(screen)
    return row[len(NEW_TITLE):] if row.startswith(NEW_TITLE) else None


class EditDriver:
    """Talks to a logged-in PyPtt.API through its low-level connect_core.

    The file menu answer is a line-input field and PTT treats an unrecognised answer as (S)儲存, so
    Enter is only ever sent to it after the field was seen to hold exactly the intended letter."""

    def __init__(self, api):
        import PyPtt
        from PyPtt import _api_util, command, connect_core, screens
        self.api, self.PyPtt = api, PyPtt
        self._util, self._core, self._screens, self._cmd = _api_util, connect_core, screens, command

    # --- low level -------------------------------------------------------------------------------
    def _send(self, keys: str, targets: list, timeout: float = 0, refresh: bool = True) -> int:
        units = [self._core.TargetUnit(t, break_detect=True) for t in targets]
        return self.api.connect_core.send(keys, units, screen_timeout=timeout, refresh=refresh)

    def screen(self) -> str:
        return self._util.last_screen(self.api)

    def _log_screen(self, why: str, level: int = logging.ERROR) -> None:
        log.log(level, "PTT edit: %s; screen:\n%s", why, self.screen())

    def _in_board_list(self) -> bool:
        return self._util.is_article_list(self.api, self.screen())

    def _redraw_editor(self, check):
        """Ctrl+L until `check(screen)` passes (the first match can be a half-drawn screen)."""
        error = None
        for _ in range(_REFRESH_TRIES):
            try:
                return check(self.screen())
            except EditError as e:
                error = e
            if self._send(self._cmd.refresh, [EDITOR_STATUS], refresh=False) != 0:
                break
        raise error

    def _disconnect(self, why: str) -> None:
        """Screen we cannot place: send nothing more (a key could answer a prompt), just hang up."""
        self._log_screen(why + " -> disconnecting without saving")
        self._util.close_session(self.api)

    def _answer_menu(self, letter: str, targets: list) -> int:
        """At the file menu field: clear it, type `letter`, and press Enter only if the field shows
        exactly `letter`. Returns the index in `targets` after Enter; -2 if Enter was not sent."""
        # Sent like PyPtt's own menu answers (Ctrl+L appended, which redraws so the field can be read).
        self._send(CTRL_Y + letter, [MENU_PROMPT])
        if menu_field(self.screen()) != letter:
            return -2
        return self._send(ENTER, targets)

    def _to_menu(self) -> bool:
        """From the editor: Ctrl+X until the (focused, empty or not) file menu field is shown."""
        if menu_field(self.screen()) is not None:
            return True
        if EDITOR_STATUS not in last_row(self.screen()):
            return False
        self._send(CTRL_X, [MENU_PROMPT])
        return menu_field(self.screen()) is not None

    def abandon(self, why: str, level: int = logging.ERROR) -> None:
        """From the editor, its file menu or the title prompt: back to the board list via (A)放棄.
        Never saves: anything that is not a verified 'a' in the menu field ends in a disconnect."""
        self._log_screen(why + " -> abandoning the edit", level)
        if title_field(self.screen()) is not None:
            # Enter here only sets the pending title (applied on save, which we then abandon).
            self._send(CTRL_Y, [NEW_TITLE])
            if self._send(ENTER, [EDITOR_STATUS]) != 0:
                self._disconnect("could not leave the title prompt")
                return
        if not self._to_menu():
            self._disconnect("file menu did not open")
            return
        in_board = self._screens.Target.InBoard
        index = self._answer_menu("a", [in_board, ANY_KEY])
        if index == -2:
            self._disconnect("file menu field does not show 'a'")
            return
        if index == 1:
            self._send(" ", [in_board])
        if not self._in_board_list():
            self._disconnect("not back on the board list after abandoning")

    # --- steps -----------------------------------------------------------------------------------
    def open_editor(self, board: str, aid: str, need_sig: bool = True) -> tuple[EditorScreen, dict]:
        api, PyPtt = self.api, self.PyPtt
        post = api.get_post(board, aid=aid, query=True)
        if post.get(PyPtt.PostField.post_status) != PyPtt.PostStatus.EXISTS:
            raise EditError(f"post {aid} does not exist on {board}")
        if (post.get(PyPtt.PostField.author) or "").lower() != api.ptt_id.lower():
            raise EditError(f"post {aid} is by {post.get(PyPtt.PostField.author)}, not {api.ptt_id}")
        self._util.goto_board(api, board)
        self._util.forget_current_board(api)  # we move the cursor ourselves from here on
        if self._send("#" + aid + ENTER, [self._screens.Target.InBoard]) != 0:
            self._disconnect(f"board list not shown after #{aid}")
            raise EditError(f"could not select #{aid}")
        cursor_line = next((r for r in self.screen().split("\n") if r.startswith(("●", ">"))), "")
        if api.ptt_id.lower() not in cursor_line.lower():
            self._log_screen("cursor line is not our post")
            raise EditError(f"#{aid} cursor line is not a post by {api.ptt_id}: {cursor_line!r}")

        index = self._send("E", [EDITOR_STATUS, ANY_KEY, self._screens.Target.InBoard])
        if index != 0:
            if index == 1:
                self._send(" ", [self._screens.Target.InBoard])
            self._log_screen("E did not open the editor")
            if not self._in_board_list():
                self._disconnect("unknown screen after E")
            raise EditError("E did not open the editor")
        try:
            before = self._redraw_editor(lambda s: parse_editor(s, api.ptt_id, board, need_sig))
        except EditError as e:
            self.abandon(str(e))
            raise
        if before.cursor != (1, 1):
            self.abandon(f"editor cursor at {before.cursor}, expected 1:1")
            raise EditError("editor did not start at row 1 col 1")
        return before, post

    def replace_body(self, before: EditorScreen, body: list[str]) -> EditorScreen:
        if len(expected_rows(before, body)) > before.status_row:
            self.abandon("new body does not fit on the first screen")
            raise EditError("new body + footer would not fit on one editor screen")
        self._send(replace_keys(before, body), [EDITOR_STATUS], timeout=self.api.config.screen_post_timeout)
        try:
            return self._redraw_editor(lambda s: check_replaced(before, body, s))
        except EditError as e:
            self.abandon(str(e))
            raise

    def _fail(self, why: str):
        self.abandon(why)
        raise EditError(why)

    def change_title(self, old: str, title: str, before: EditorScreen, body: list[str]) -> None:
        """From the verified editor: Ctrl+X, 't' Enter, then the 舊標題/新標題 prompt (prefilled with the
        old title): Ctrl+Y, type, Enter, back in the editor. Each step is checked before the next key.
        `old` is the board-list title; after an earlier rename the header's 標題: row may differ, so
        either is accepted as the prompt's old title."""
        olds = {old, before.lines[1][len("標題:"):].strip()}
        if not self._to_menu():
            self._fail("Ctrl+X did not show the file menu")
        if self._answer_menu("t", [NEW_TITLE]) != 0:
            self._fail("no 新標題 prompt after (T)")
        rows = _rows(self.screen())
        if (title_field(self.screen()) not in olds or len(rows) < 2
                or rows[-2][len(OLD_TITLE):] not in olds or not rows[-2].startswith(OLD_TITLE)):
            self._fail(f"title prompt does not show the old title {old!r}")
        self._send(CTRL_Y, [NEW_TITLE])
        if title_field(self.screen()) != "":
            self._fail("Ctrl+Y did not clear the 新標題 field")
        self._send(title, [NEW_TITLE + title])
        if title_field(self.screen()) != title:
            self._fail(f"新標題 field does not show {title!r}")
        if self._send(ENTER, [EDITOR_STATUS]) != 0:
            self._fail("not back in the editor after the title prompt")
        # The header row keeps the old title until saved; the body must be untouched.
        try:
            self._redraw_editor(lambda s: check_replaced(before, body, s, check_cursor=False))
        except EditError as e:
            self._fail(str(e))

    def save(self) -> None:
        """From the verified editor: Ctrl+X, verified 's' Enter, any 任意鍵 pages, back to the board list."""
        if not self._to_menu():
            self._fail("Ctrl+X did not show the file menu")
        in_board = self._screens.Target.InBoard
        index = self._answer_menu("s", [in_board, ANY_KEY])
        if index == -2:
            self._fail("file menu field does not show 's'")
        for _ in range(3):
            if index != 1:
                break
            log.info("PTT edit: after save:\n%s", self.screen())
            index = self._send(" ", [in_board, ANY_KEY])
        if index != 0:
            # Already past (S): it may or may not be saved. Do not press anything else.
            self._disconnect("unknown screen after saving")
            raise EditError("unknown screen after saving; check the post by hand")


def edit_post(api, board: str, aid: str, content: str | None, title: str | None = None,
              save: bool = False) -> str:
    """Replace the body (and optionally the title) of our post `aid`; return the last editor screen.

    content=None only opens the editor and abandons (inspect the screen). save=False types and verifies
    the new body, then abandons: a rehearsal that changes nothing."""
    aid = aid.lstrip("#")
    if len(aid) != 8:
        raise EditError(f"bad AID {aid!r}")
    body = normalize_content(content) if content is not None else None
    if title is not None:
        check_title(title)
    driver = EditDriver(api)
    try:
        return _edit(driver, api, board, aid, body, title, save)
    except EditError:
        raise
    except BaseException:
        # e.g. a PyPtt timeout mid-flow: logout keys must not be typed into the editor or a prompt.
        if getattr(api, "_is_login", False) and not driver._in_board_list():
            driver._disconnect("unexpected error")
        raise


def _edit(driver: EditDriver, api, board: str, aid: str, body: list[str] | None, title: str | None,
          save: bool) -> str:
    before, post = driver.open_editor(board, aid)
    if body is None:
        driver.abandon("dump only", logging.INFO)
        return "\n".join(before.lines)
    after = driver.replace_body(before, body)
    shown = "\n".join(after.lines)
    if not save:
        driver.abandon("rehearsal (no --post), verified OK", logging.INFO)
        return shown
    old_title = (post.get(driver.PyPtt.PostField.title) or "").strip()
    if title is not None and title.strip() != old_title:
        driver.change_title(old_title, title.strip(), before, body)
    driver.save()
    log.info("PTT edit: saved #%s on %s", aid, board)
    _check_saved(api, board, aid, body, title.strip() if title is not None else None)
    return shown


_COLOR = re.compile(r"\x15\[[0-9;]*m")


def _check_saved(api, board: str, aid: str, body: list[str], title: str | None = None) -> None:
    """Read the post back; the save already happened, so a mismatch is only reported."""
    import PyPtt
    try:
        text = api.get_post(board, aid=aid).get(PyPtt.PostField.content) or ""
        # The list title (query=True); a full read parses the header row, which (T) does not change.
        listed = (api.get_post(board, aid=aid, query=True).get(PyPtt.PostField.title) or "").strip()
    except Exception:
        log.warning("PTT edit: could not read #%s back", aid, exc_info=True)
        return
    if title is not None and listed != title:
        log.warning("PTT edit: saved #%s but its list title is %r, not %r", aid, listed, title)
    missing = [line for line in (_COLOR.sub("", b).strip() for b in body) if line and line not in text]
    if missing:
        log.warning("PTT edit: saved #%s but these lines are not in the post: %r", aid, missing)


# --- append (posts of any length) -----------------------------------------------------------------
# Live recon (24-row screen): 23 content rows + status bar. The reader (get_post's full_content) shows the
# 3 header rows as boxes, then a ─── separator row, then the file from its line 4 (the blank after the
# header) on, so the editor line number of a reader row is its index (live: '--' at index 33 = line 33).
# Down from 1:1 moves one line per key; within the first 23 lines the view does not scroll, after that
# every Down scrolls by one and the cursor stays on the last content row.
MAX_APPEND_ROWS = 19  # typed rows; with the row above, a blank, "--" and "※ 發信站:" that is 23 rows


@dataclass
class PostText:
    sig_line: int    # editor line (1-based) of the "--" row
    body: list[str]  # rendered body rows (no colour codes): editor lines 5 .. sig_line - 1


@dataclass
class AppendResult:
    screen: str            # last verified editor screen ("" if nothing was appended)
    saved: bool = False
    verified: bool = True  # False: saved, but the read-back did not match (already saved; not fixed)


def parse_post_text(full_content: str) -> PostText:
    """Locate the '--' row in get_post's full_content (the reader's text): 作者/標題/時間, ───, the
    blank file line 4, body from index 5 = editor line 5. Any other shape is refused (fail safe)."""
    lines = [r.rstrip() for r in (full_content or "").split("\n")]
    body_start = HEADER_ROWS + 1
    if (len(lines) < body_start + 2 or "作者" not in lines[0] or "標題" not in lines[1]
            or "時間" not in lines[2] or SEPARATOR not in lines[3] or lines[4] != ""):
        raise EditError("post text does not start with 作者/標題/時間/───/blank; cannot count its lines")
    hits = [i for i in range(body_start, len(lines) - 1)
            if lines[i] == "--" and lines[i + 1].startswith(SIGN_START)]
    if len(hits) != 1:
        raise EditError(f"post text has {len(hits)} '--' + '※ 發信站:' rows, expected exactly 1")
    return PostText(hits[0], lines[body_start:hits[0]])


def parse_status(screen: str) -> EditorScreen:
    """Any editor screen (the header may be scrolled away); sig_row is -1."""
    lines = _rows(screen)
    if not lines or EDITOR_STATUS not in lines[-1]:
        raise EditError("not in the article editor (no 編輯文章 status bar)")
    return EditorScreen(lines, len(lines) - 1, -1)


def _sig_pairs(ed: EditorScreen) -> list[int]:
    return [i for i in range(ed.status_row - 1) if ed.lines[i] == "--" and ed.lines[i + 1].startswith(SIGN_START)]


def check_line(screen: str, line: int) -> EditorScreen:
    ed = parse_status(screen)
    if ed.cursor != (line, 1):
        raise EditError(f"editor cursor at {ed.cursor}, expected ({line}, 1)")
    return ed


def check_at_sig(screen: str, line: int) -> EditorScreen:
    """After Down x line (cursor on '※ 發信站:', line + 1) and one Up: the cursor is on line `line`, on
    screen row min(line + 1, rows) - 1, which shows '--' with '※ 發信站:' right below it."""
    ed = check_line(screen, line)
    row = min(line + 1, ed.status_row) - 2
    pairs = _sig_pairs(ed)
    if pairs != [row]:
        where = f"; '--' + '※ 發信站:' shown on screen row(s) {[p + 1 for p in pairs]}" if pairs else ""
        raise EditError(f"cursor row {row + 1} (line {line}) is not '--' followed by '※ 發信站:'{where}"
                        " (the post's line count from get_post differs from the editor's?)")
    ed.sig_row = row
    return ed


def check_appended(at: EditorScreen, line: int, typed: list[str], screen: str) -> EditorScreen:
    """After typing `typed` + a blank at the '--' row (line `line`), then Down and Up: the cursor is
    on '--' (now line + len(typed) + 1), the rows above it on screen are the old row above '--', the
    typed rows and a blank, and the rows from '--' on are the old ones."""
    ed = check_line(screen, line + len(typed) + 1)
    pairs = _sig_pairs(ed)
    if len(pairs) != 1:
        raise EditError(f"{len(pairs)} '--' + '※ 發信站:' rows on screen after typing, expected 1")
    sig = pairs[0]
    want = [at.lines[at.sig_row - 1]] + [displayed(t) for t in typed] + [""]
    got = ed.lines[max(sig - len(want), 0):sig]
    if got != want:
        diff = [f"want {w!r} got {g!r}" for w, g in zip(want, [None] * (len(want) - len(got)) + got) if w != g]
        raise EditError("rows above '--' are not the expected text: " + "; ".join(diff[:5]))
    old_footer, new_footer = at.lines[at.sig_row:at.status_row], ed.lines[sig:ed.status_row]
    k = min(len(old_footer), len(new_footer))
    if old_footer[:k] != new_footer[:k]:
        raise EditError(f"rows from '--' on changed: {old_footer[:k]!r} -> {new_footer[:k]!r}")
    ed.sig_row = sig
    return ed


def _plain(line: str) -> str:
    return _COLOR.sub("", line).rstrip()


class AppendDriver(EditDriver):
    def go_to_sig(self, line: int) -> EditorScreen:
        """From the verified editor at 1:1: Down to line + 1 in checked chunks, then one Up."""
        at = 1
        try:
            while at < line + 1:
                step = min(MOVE_CHUNK, line + 1 - at)
                self._send(DOWN * step, [EDITOR_STATUS])
                at += step
                self._redraw_editor(lambda s, at=at: check_line(s, at))
            self._send(UP, [EDITOR_STATUS])
            return self._redraw_editor(lambda s: check_at_sig(s, line))
        except EditError as e:
            self.abandon(str(e))
            raise

    def type_above_sig(self, at: EditorScreen, line: int, typed: list[str]) -> EditorScreen:
        """Typing at column 1 of '--' inserts above it; each Enter pushes '--' down."""
        keys = "".join(t + ENTER for t in typed) + ENTER
        self._send(keys, [EDITOR_STATUS], timeout=self.api.config.screen_post_timeout)
        self._send(DOWN, [EDITOR_STATUS])  # Down + Up: '※ 發信站:' is then visible below the cursor
        self._send(UP, [EDITOR_STATUS])
        try:
            return self._redraw_editor(lambda s: check_appended(at, line, typed, s))
        except EditError as e:
            self.abandon(str(e))
            raise


def append_post(api, board: str, aid: str, content, save: bool = False) -> AppendResult:
    """Add `content` as new rows right above the '--' row of our post `aid` (any length).

    content: text, None (dump: move to '--', return that screen, abandon), or a callable that gets the
    current body text (no colour codes) and returns the text to append ("" = nothing to do; no edit).
    A blank row is added first if the body does not end with one, and one after the new rows, so the
    layout matches formatter.build_weverse_content. save=False types and verifies, then abandons."""
    aid = aid.lstrip("#")
    if len(aid) != 8:
        raise EditError(f"bad AID {aid!r}")
    if content is not None and not callable(content):
        normalize_content(content)  # refuse bad text before any network traffic
    driver = AppendDriver(api)
    try:
        return _append(driver, api, board, aid, content, save)
    except EditError:
        raise
    except BaseException:
        if getattr(api, "_is_login", False) and not driver._in_board_list():
            driver._disconnect("unexpected error")
        raise


def _append(driver: AppendDriver, api, board: str, aid: str, content, save: bool) -> AppendResult:
    import PyPtt
    post = api.get_post(board, aid=aid)
    if post.get(PyPtt.PostField.post_status) != PyPtt.PostStatus.EXISTS:
        raise EditError(f"post {aid} does not exist on {board}")
    old = parse_post_text(post.get(PyPtt.PostField.full_content))
    if callable(content):
        content = content("\n".join(old.body))
    new = normalize_content(content) if content is not None else None
    if new == []:
        log.info("PTT edit: nothing to append to #%s", aid)
        return AppendResult("")
    typed, pad = None, bool(old.body) and old.body[-1] != ""  # pad: a blank row first
    if new is not None:
        typed = [""] * pad + new
        if len(typed) > MAX_APPEND_ROWS:
            raise EditError(f"{len(typed)} rows to append, at most {MAX_APPEND_ROWS} (must fit on one screen)")
    log.info("PTT edit: #%s '--' is at editor line %d", aid, old.sig_line)
    driver.open_editor(board, aid, need_sig=False)
    at = driver.go_to_sig(old.sig_line)
    if typed is None:
        driver.abandon("dump only", logging.INFO)
        return AppendResult("\n".join(at.lines))
    above = at.lines[at.sig_row - 1]
    if (above != "") != pad:
        why = f"row above '--' is {above!r}; the post text says {old.body[-1:]!r}"
        driver.abandon(why)
        raise EditError(why)
    after = driver.type_above_sig(at, old.sig_line, typed)
    shown = "\n".join(after.lines)
    if not save:
        driver.abandon("rehearsal (no --post), verified OK", logging.INFO)
        return AppendResult(shown)
    driver.save()
    log.info("PTT edit: appended %d rows to #%s on %s", len(typed) + 1, aid, board)
    return AppendResult(shown, saved=True, verified=_check_append_saved(api, board, aid, old, typed))


def _check_append_saved(api, board: str, aid: str, old: PostText, typed: list[str]) -> bool:
    """Read the post back: body must be the old body + the new rows + a blank. Already saved, so a
    mismatch is only reported, never fixed."""
    import PyPtt
    try:
        got = parse_post_text(api.get_post(board, aid=aid).get(PyPtt.PostField.full_content)).body
    except Exception:
        log.warning("PTT edit: could not read #%s back after appending", aid, exc_info=True)
        return False
    want = old.body + [_plain(t) for t in typed] + [""]
    if got != want:
        diff = [f"line {i + 5}: want {w!r} got {g!r}" for i, (w, g) in
                enumerate(zip(want + [None] * len(got), got + [None] * len(want))) if w != g]
        log.warning("PTT edit: appended to #%s but the post body is not old body + new rows: %s",
                    aid, "; ".join(diff[:5]))
        return False
    return True
