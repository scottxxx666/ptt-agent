import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# The /ls skill lives in <project root>/.agents/skills, so agy must run from here.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S)


class TranslationError(Exception):
    pass


@dataclass(frozen=True)
class Translation:
    title_zh: str
    title_original: str


def _agy_bin() -> str:
    return shutil.which("agy") or str(Path.home() / ".local/bin/agy")


def translate_title(title: str, run=subprocess.run, timeout: int = 420) -> Translation:
    cmd = [_agy_bin(), "-p", f"/ls {title}", "--output-format", "json",
           "--print-timeout", f"{timeout - 20}s"]
    try:
        proc = run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        raise TranslationError(f"agy failed to run: {e}") from e

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise TranslationError(f"agy output is not JSON: {proc.stdout[:200]!r}") from e
    if not isinstance(envelope, dict):
        raise TranslationError(f"agy output is not a JSON object: {proc.stdout[:200]!r}")
    if envelope.get("status") != "SUCCESS":
        raise TranslationError(f"agy status {envelope.get('status')}: {envelope.get('error')}")

    response = envelope.get("response")
    if not isinstance(response, str):
        raise TranslationError(f"agy response is not a string: {response!r}")
    response = response.strip()
    fenced = _FENCE.match(response)
    if fenced:
        response = fenced.group(1)
    try:
        data = json.loads(response)
        title_zh = data["title_zh"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise TranslationError(f"skill response is not the expected JSON: {response[:200]!r}") from e
    if not isinstance(title_zh, str) or not title_zh.strip():
        raise TranslationError("title_zh is empty")
    return Translation(title_zh=title_zh.strip(), title_original=title)
