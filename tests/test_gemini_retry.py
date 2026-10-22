"""Retry policy of the one Gemini wrapper (D23), with a fake client: no network."""
import json
from types import SimpleNamespace

import pytest

from cqa import gemini


class APIConnectionError(Exception):
    pass


class APITimeoutError(Exception):
    pass


class BadRequest(Exception):
    status_code = 400


def fake_client(script):
    """script: list of exceptions to raise, then a successful reply."""
    calls = iter(script)

    def create(**kw):
        assert kw["store"] is False  # every call is stateless (D5)
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(usage=None, status="completed", output_text=json.dumps(item))

    return SimpleNamespace(interactions=SimpleNamespace(create=create))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)


def run(monkeypatch, script):
    c = fake_client(script)  # one client for the whole call, like the real cached one
    monkeypatch.setattr(gemini, "client", lambda: c)
    return gemini.interact("sys", [gemini.text("x")], {"type": "object"})


def test_connection_blips_are_retried(monkeypatch):
    r = run(monkeypatch, [APIConnectionError(), APIConnectionError(), APIConnectionError(), {"ok": 1}])
    assert r.data == {"ok": 1} and r.api_errors == 3


def test_gives_up_after_three_transient_retries(monkeypatch):
    with pytest.raises(APIConnectionError):
        run(monkeypatch, [APIConnectionError()] * 4 + [{"ok": 1}])


def test_one_timeout_retry_only(monkeypatch):
    assert run(monkeypatch, [APITimeoutError(), {"ok": 1}]).data == {"ok": 1}
    with pytest.raises(APITimeoutError):
        run(monkeypatch, [APITimeoutError(), APITimeoutError(), {"ok": 1}])


def test_bad_request_is_not_retried(monkeypatch):
    with pytest.raises(BadRequest):
        run(monkeypatch, [BadRequest(), {"ok": 1}])
