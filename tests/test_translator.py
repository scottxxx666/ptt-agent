import json
import subprocess
from types import SimpleNamespace

import pytest

from ptt_agent.translator import TranslationError, translate_title


def fake_run(stdout="", exc=None):
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        if exc:
            raise exc
        return SimpleNamespace(stdout=stdout)
    run.calls = calls
    return run


def envelope(response, status="SUCCESS", **extra):
    return json.dumps({"status": status, "response": response, **extra})


def test_success_parses_double_json_and_passes_slash_command():
    run = fake_run(envelope(json.dumps({"title_zh": "你好", "title_original": "x"}) + "\n"))
    t = translate_title("안녕", run=run)
    assert (t.title_zh, t.title_original) == ("你好", "안녕")
    cmd, kw = run.calls[0]
    assert cmd[1:3] == ["-p", "/ls 안녕"] and "json" in cmd
    assert kw["cwd"].name == "ptt-agent"


def test_tolerates_code_fence():
    run = fake_run(envelope('```json\n{"title_zh": "你好"}\n```'))
    assert translate_title("t", run=run).title_zh == "你好"


@pytest.mark.parametrize("out", [
    "not json at all",
    envelope("", status="ERROR", error="timeout"),
    envelope("### 【繁中翻譯】 markdown instead of json"),
    envelope('{"title_original": "x"}'),
    envelope('{"title_zh": "   "}'),
    envelope('{"title_zh": 123}'),
    envelope("[1, 2]"),
])
def test_bad_outputs_raise(out):
    with pytest.raises(TranslationError):
        translate_title("t", run=fake_run(out))


def test_timeout_raises_translation_error():
    exc = subprocess.TimeoutExpired("agy", 1)
    with pytest.raises(TranslationError):
        translate_title("t", run=fake_run(exc=exc))
