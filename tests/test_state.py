from ptt_agent.state import load_seen, save_seen


def test_missing_file_means_first_run(tmp_path):
    assert load_seen(tmp_path / "state.json") is None


def test_roundtrip_and_empty_set_is_not_first_run(tmp_path):
    p = tmp_path / "state.json"
    save_seen(p, set())
    assert load_seen(p) == set()
    save_seen(p, {"a", "b"})
    assert load_seen(p) == {"a", "b"}
