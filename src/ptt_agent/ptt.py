RECENT_LIMIT = 10


class PttPoster:
    def __init__(self, ptt_id: str, ptt_pw: str, board: str, title_index: int, api_factory=None):
        self._id, self._pw = ptt_id, ptt_pw
        self._board, self._title_index = board, title_index
        self._api_factory = api_factory

    def post(self, title: str, content: str) -> None:
        api = self._api_factory() if self._api_factory else self._default_api()
        api.login(ptt_id=self._id, ptt_pw=self._pw)
        try:
            api.post(board=self._board, title_index=self._title_index,
                     title=title, content=content, sign_file=0)
        finally:
            api.logout()

    def has_recent_post(self, key: str, limit: int = RECENT_LIMIT) -> bool:
        """True if one of this account's last `limit` posts on the board has `key` in its title."""
        return any(key in t for t in self.recent_titles(limit))

    def recent_titles(self, limit: int = RECENT_LIMIT) -> list[str]:
        import PyPtt
        api = self._api_factory() if self._api_factory else self._default_api()
        api.login(ptt_id=self._id, ptt_pw=self._pw)
        try:
            search = dict(search_type=PyPtt.SearchType.AUTHOR, search_condition=self._id)
            try:
                newest = api.get_newest_index(PyPtt.NewIndex.BOARD, board=self._board, **search)
            except PyPtt.NoSearchResult:
                return []
            return [api.get_post(board=self._board, index=i, query=True, **search)[PyPtt.PostField.title]
                    for i in range(newest, max(newest - limit, 0), -1)]
        finally:
            api.logout()

    @staticmethod
    def _default_api():
        import PyPtt
        return PyPtt.API()
