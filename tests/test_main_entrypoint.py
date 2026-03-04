import logging
import runpy

import pytest

import relay_logging


class FakeTask:
    def __init__(self, called: dict[str, bool]):
        self.called = called

    def cancel(self):
        self.called["cancelled"] = True


class FakeLoop:
    def __init__(self, exc: Exception, called: dict[str, bool]):
        self._exc = exc
        self._called = called

    def create_task(self, coro):
        coro.close()
        return object()

    def run_forever(self):
        raise self._exc

    def close(self):
        return None


@pytest.fixture
def entrypoint_runner(monkeypatch: pytest.MonkeyPatch):
    def _run(exc: Exception) -> dict[str, bool]:
        called = {
            "shutdown": False,
            "unexpected": False,
            "shutting_down": False,
            "cancelled": False,
        }

        def log_shutdown():
            called["shutdown"] = True

        def log_unexpected(*_args):
            called["unexpected"] = True

        def log_shutting_down():
            called["shutting_down"] = True

        monkeypatch.setattr(relay_logging, "log_shutdown_requested", log_shutdown)
        monkeypatch.setattr(relay_logging, "log_unexpected_error", log_unexpected)
        monkeypatch.setattr(relay_logging, "log_shutting_down", log_shutting_down)
        monkeypatch.setattr(logging, "basicConfig", lambda *args, **kwargs: None)

        import asyncio

        monkeypatch.setattr(asyncio, "new_event_loop", lambda: FakeLoop(exc, called))
        monkeypatch.setattr(asyncio, "set_event_loop", lambda _loop: None)
        monkeypatch.setattr(asyncio, "all_tasks", lambda _loop: [FakeTask(called)])

        runpy.run_module("main", run_name="__main__")
        return called

    return _run


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (KeyboardInterrupt(), "shutdown"),
        (RuntimeError("boom"), "unexpected"),
    ],
)
def test_main_entrypoint_logs(
    entrypoint_runner,
    exc: Exception,
    expected: str,
) -> None:
    called = entrypoint_runner(exc)
    assert called[expected] is True
    assert called["shutting_down"] is True
    assert called["cancelled"] is True
