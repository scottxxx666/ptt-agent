from datetime import datetime, timezone

import pytest

from ptt_agent.youtube import Video


@pytest.fixture
def make_video():
    def _make(id="vid1", title="원문 제목", published="2026-11-18T09:00:00+00:00"):
        return Video(id=id, title=title, published=datetime.fromisoformat(published))
    return _make
