"""Edit one of our own PTT posts by driving the article editor (PyPtt 2.3.19 has no edit API).

Flow, mirroring PyPtt's own _api_post.post: goto_board, "#AID" Enter, "E" opens the editor with the
cursor on row 1 (the "作者:" header line). The body region is the rows between the blank line after
the 3 header lines and the "--" line that precedes "※ 發信站:". It is replaced by moving down to it,
deleting it with Ctrl+Y line by line and typing the new body, so the header and footer are never
touched. Only articles whose header..※ 發信站 fit on the first screen are supported; longer ones are
refused before any key that changes the text is sent.

Safety: nothing is saved unless the editor screen after typing equals exactly what we expect
(header unchanged, new body, blank line, the original footer). Anything else in the editor or its
file menu -> Ctrl+X, "a" Enter (abandon). A screen we cannot place at all -> disconnect, which never
saves either.
"""
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("ptt_agent")

CTRL_U, CTRL_X, CTRL_Y, ENTER = "\x15", "\x18", "\x19", "\r"
DOWN = "\x1bOB"
EDITOR_STATUS = "編輯文章"
FILE_MENU = "確定要儲存檔案嗎"
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
                 title: str | None = None) -> EditorScreen:
    """Recognise the editor of an article; raise EditError on any unexpected layout."""
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
    if title is not None and title_line[len("標題:"):].strip() != title.strip():
        raise EditError("editor title does not match the post's title")
    sig_row = next((i for i in range(HEADER_ROWS, status_row - 1)
                    if lines[i] == "--" and lines[i + 1].startswith("※ 發信站:")), None)
    if sig_row is None:
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


def check_replaced(before: EditorScreen, body: list[str], screen: str) -> EditorScreen:
    after = parse_editor(screen)
    want = expected_rows(before, body)
    got = after.lines[:len(want)]
    if got != want:
        diff = [f"row {i + 1}: want {w!r} got {g!r}"
                for i, (w, g) in enumerate(zip(want, got + [None] * len(want))) if w != g]
        raise EditError("editor does not show the expected text: " + "; ".join(diff[:5]))
    if after.cursor != (HEADER_ROWS + len(body) + 2, 1):
        raise EditError(f"cursor at {after.cursor}, expected the start of the '--' row")
    return after


class EditDriver:
    """Talks to a logged-in PyPtt.API through its low-level connect_core."""

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

    def abandon(self, why: str, level: int = logging.ERROR) -> None:
        """From the editor or its file menu: Ctrl+X, (A)放棄, back to the board list. Never saves."""
        self._log_screen(why + " -> abandoning the edit", level)
        screen = self.screen()
        if FILE_MENU not in screen and (EDITOR_STATUS not in screen or self._send(CTRL_X, [FILE_MENU]) != 0):
            self._disconnect("file menu did not open")
            return
        if self._send("a" + ENTER, [self._screens.Target.InBoard, ANY_KEY]) == 1:
            self._send(" ", [self._screens.Target.InBoard])
        if not self._in_board_list():
            self._disconnect("not back on the board list after abandoning")

    # --- steps -----------------------------------------------------------------------------------
    def open_editor(self, board: str, aid: str) -> tuple[EditorScreen, dict]:
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
            before = self._redraw_editor(lambda s: parse_editor(
                s, api.ptt_id, board, post.get(PyPtt.PostField.title)))
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

    def open_file_menu(self) -> None:
        if self._send(CTRL_X, [FILE_MENU]) != 0:
            self.abandon("Ctrl+X did not show the file menu")
            raise EditError("file menu did not open")

    def change_title(self, title: str) -> None:
        """At the file menu: (T)改標題. The prompt is verified before Enter; the new title only
        takes effect on save, so a wrong prompt is abandoned with the rest of the edit."""
        # Ctrl+Y clears a prefilled title in PTT's line editor; refresh=False so no Ctrl+L lands in it.
        if self._send("t" + CTRL_Y + title, [title], refresh=False) != 0:
            self._send(ENTER, [FILE_MENU, EDITOR_STATUS])  # leave whatever prompt took the keys
            self.abandon("title prompt did not echo the new title")
            raise EditError("title prompt not recognised")
        line = next((r.rstrip() for r in reversed(self.screen().split("\n")) if r.rstrip().endswith(title)), "")
        prompt = line[:len(line) - len(title)].strip()
        if "標題" not in prompt or not prompt.endswith((":", "：")) or len(prompt) > 8:
            self._send(ENTER, [FILE_MENU, EDITOR_STATUS])
            self.abandon(f"unexpected title prompt {line!r}")
            raise EditError("title prompt not recognised")
        index = self._send(ENTER, [FILE_MENU, EDITOR_STATUS])
        if index == 1:
            self.open_file_menu()
        elif index != 0:
            self.abandon("no file menu / editor after the title prompt")
            raise EditError("unknown screen after the title prompt")

    def save(self) -> None:
        """At the file menu: (S)儲存, then any 任意鍵 pages, until the board list is back."""
        in_board = self._screens.Target.InBoard
        index = self._send("s" + ENTER, [in_board, ANY_KEY], timeout=self.api.config.screen_post_timeout)
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
    driver.open_file_menu()
    if title is not None and title.strip() != (post.get(driver.PyPtt.PostField.title) or "").strip():
        driver.change_title(title)
    driver.save()
    log.info("PTT edit: saved #%s on %s", aid, board)
    _check_saved(api, board, aid, body)
    return shown


_COLOR = re.compile(r"\x15\[[0-9;]*m")


def _check_saved(api, board: str, aid: str, body: list[str]) -> None:
    """Read the post back; the save already happened, so a mismatch is only reported."""
    import PyPtt
    try:
        text = api.get_post(board, aid=aid).get(PyPtt.PostField.content) or ""
    except Exception:
        log.warning("PTT edit: could not read #%s back", aid, exc_info=True)
        return
    missing = [line for line in (_COLOR.sub("", b).strip() for b in body) if line and line not in text]
    if missing:
        log.warning("PTT edit: saved #%s but these lines are not in the post: %r", aid, missing)
