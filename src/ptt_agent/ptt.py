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

    @staticmethod
    def _default_api():
        import PyPtt
        return PyPtt.API()
