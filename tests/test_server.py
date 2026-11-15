from __future__ import annotations

import asyncio
import json
import logging
import time
from io import StringIO
from types import SimpleNamespace

import pytest
from fastmcp import FastMCP
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp import types as mt
from starlette.testclient import TestClient

from context_mcp import server


def test_main_runs_streamable_http(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(server, "configure_logging", lambda: None)
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: captured.update(kwargs))

    server.main()

    assert captured == {
        "transport": "streamable-http",
        "host": server.MCP_HOST,
        "port": server.MCP_PORT,
        "path": server.MCP_PATH,
        "stateless_http": False,
    }


def test_health_and_readiness_endpoints() -> None:
    server._set_ready(False, "warming")
    health = asyncio.run(server.health(None))  # type: ignore[arg-type]
    pending = asyncio.run(server.ready(None))  # type: ignore[arg-type]
    server._set_ready(True)
    ready = asyncio.run(server.ready(None))  # type: ignore[arg-type]

    assert health.status_code == 200
    assert json.loads(health.body) == {"status": "ok", "server": "core-context"}
    assert pending.status_code == 503
    assert json.loads(pending.body)["error"] == "warming"
    assert ready.status_code == 200
    assert json.loads(ready.body) == {"ready": True, "server": "core-context"}


def test_start_watcher_ignores_reads(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    scheduled: list[list[type]] = []

    class FakeObserver:
        def schedule(self, _handler, _path, *, recursive, event_filter):
            assert recursive is True
            scheduled.append(event_filter)

        def start(self) -> None:
            return None

    monkeypatch.setattr(server, "Observer", FakeObserver)
    monkeypatch.setattr(server, "CORE_CONTEXT", tmp_path)
    monkeypatch.setattr(server, "EXTENSIONS_DIR", tmp_path / "missing")

    server.start_watcher()

    assert scheduled == [server.CONTENT_WATCH_EVENTS]
    assert server.FileClosedEvent in server.CONTENT_WATCH_EVENTS


def test_reading_a_watched_file_does_not_refresh_the_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    calls: list[None] = []
    monkeypatch.setattr(server.index, "sync", lambda: calls.append(None))
    root = tmp_path / "CONTEXT"
    root.mkdir()
    document = root / "overview.md"
    document.write_text("# Core\nArchitecture.", encoding="utf-8")

    observer = server.Observer()
    handler = server.ContextChangeHandler(debounce_seconds=0.05)
    observer.schedule(
        handler,
        str(root),
        recursive=True,
        event_filter=server.CONTENT_WATCH_EVENTS,
    )
    observer.start()
    try:
        with document.open("r", encoding="utf-8") as handle:
            handle.read()
        time.sleep(0.25)
        assert calls == []

        document.write_text("# Core\nQuality testing.", encoding="utf-8")
        deadline = time.time() + 2
        while time.time() < deadline and not calls:
            time.sleep(0.05)
        assert calls
    finally:
        handler.close()
        observer.stop()
        observer.join(timeout=2)


def test_context_change_handler_debounces_refreshes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[None] = []
    handler = server.ContextChangeHandler(debounce_seconds=0.01)
    monkeypatch.setattr(server.index, "sync", lambda: calls.append(None))

    handler.on_any_event(object())
    handler.on_any_event(object())
    time.sleep(0.05)
    handler.close()

    assert calls == [None]


def test_context_status_reports_stateful_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        server.index,
        "stats",
        lambda: {"documents": 3, "sources": ["CORE"], "model": "test-model"},
    )

    assert server.context_status()["session_mode"] == "stateful"


def test_streamable_http_issues_and_validates_session_ids() -> None:
    mcp = FastMCP("session-test")
    app = mcp.http_app(path="/mcp", transport="streamable-http", stateless_http=False)
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        },
    }
    headers = {"Accept": "application/json, text/event-stream"}

    with TestClient(app) as client:
        initialized = client.post("/mcp", json=initialize, headers=headers)
        session_id = initialized.headers["mcp-session-id"]
        missing_session = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=headers,
        )
        resumed = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
            headers={**headers, "mcp-session-id": session_id},
        )
        invalid_session = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
            headers={**headers, "mcp-session-id": "not-a-session"},
        )

    assert initialized.status_code == 200
    assert session_id
    assert missing_session.status_code == 400
    assert resumed.status_code == 200
    assert invalid_session.status_code == 404


def test_ambiguous_search_can_apply_source_and_topic_focus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = [
        {"source": "CORE", "title": "Conflict Resolution", "score": 0.61},
        {"source": "QA", "title": "Boundary Testing", "score": 0.6},
    ]
    calls: list[dict[str, object]] = []

    def search(**kwargs: object) -> list[dict[str, object]]:
        calls.append(kwargs)
        return initial if len(calls) == 1 else [{"source": "QA", "title": "Focused", "score": 0.9}]

    class FocusContext:
        async def elicit(self, _message: str, _form: object) -> object:
            return SimpleNamespace(
                action="accept",
                data=SimpleNamespace(source="QA", topic="QA: Boundary Testing"),
            )

    monkeypatch.setattr(server.index, "search", search)

    results = asyncio.run(server.context_search(FocusContext(), "test strategy", limit=5))

    assert results == [{"source": "QA", "title": "Focused", "score": 0.9}]
    assert calls == [
        {"query": "test strategy", "limit": 5, "source": None},
        {"query": "test strategy Boundary Testing", "limit": 5, "source": "QA"},
    ]


@pytest.mark.parametrize("action", ["decline", "cancel"])
def test_ambiguous_search_returns_original_results_when_elicitation_is_not_accepted(
    monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    initial = [
        {"source": "CORE", "title": "Conflict Resolution", "score": 0.61},
        {"source": "QA", "title": "Boundary Testing", "score": 0.6},
    ]

    class FocusContext:
        async def elicit(self, _message: str, _form: object) -> object:
            return SimpleNamespace(action=action)

    monkeypatch.setattr(server.index, "search", lambda **_kwargs: initial)

    assert asyncio.run(server.context_search(FocusContext(), "test strategy")) == initial


def test_ambiguous_search_falls_back_when_elicit_is_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = [
        {"source": "CORE", "title": "Conflict Resolution", "score": 0.61},
        {"source": "QA", "title": "Boundary Testing", "score": 0.6},
    ]

    class UnsupportedContext:
        async def elicit(self, _message: str, _form: object) -> object:
            raise RuntimeError("Client does not support elicitation")

    monkeypatch.setattr(server.index, "search", lambda **_kwargs: initial)

    assert asyncio.run(server.context_search(UnsupportedContext(), "test strategy")) == initial


def test_clear_or_source_filtered_search_does_not_elicit() -> None:
    clear = [
        {"source": "CORE", "title": "Clear Match", "score": 0.92},
        {"source": "QA", "title": "Other Match", "score": 0.5},
    ]

    assert not server._is_ambiguous(clear, None)
    assert not server._is_ambiguous(clear, "CORE")


def test_tool_call_logging_records_full_payload_and_response() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("context_mcp.audit.test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    middleware = server.ToolCallLoggingMiddleware()
    context = MiddlewareContext(
        message=mt.CallToolRequestParams(name="context_read", arguments={"path": "/context.md"})
    )

    async def next_tool(_context: object) -> ToolResult:
        return ToolResult(
            content=[],
            structured_content={"content": "full document content"},
            meta=None,
            is_error=False,
        )

    original_logger = server.logger
    server.logger = logger
    try:
        result = asyncio.run(middleware.on_call_tool(context, next_tool))
    finally:
        server.logger = original_logger
        logger.removeHandler(handler)

    event = json.loads(stream.getvalue())
    assert result.structured_content == {"content": "full document content"}
    assert event["server"] == "core-context"
    assert event["tool"] == "context_read"
    assert event["arguments"] == {"path": "/context.md"}
    assert event["response"]["structured_content"] == {"content": "full document content"}
    assert event["outcome"] == "success"


def test_tool_call_logging_records_search_clarification() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("context_mcp.audit.test_clarification")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    middleware = server.ToolCallLoggingMiddleware()
    context = MiddlewareContext(
        message=mt.CallToolRequestParams(name="context_search", arguments={"query": "testing"})
    )

    async def next_tool(_context: object) -> ToolResult:
        server._search_clarification.set("accepted")
        return ToolResult(content=[], structured_content={"results": []}, meta=None, is_error=False)

    original_logger = server.logger
    server.logger = logger
    try:
        asyncio.run(middleware.on_call_tool(context, next_tool))
    finally:
        server.logger = original_logger
        logger.removeHandler(handler)

    assert json.loads(stream.getvalue())["clarification"] == "accepted"


def test_tool_call_logging_records_and_reraises_errors() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("context_mcp.audit.test_error")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    middleware = server.ToolCallLoggingMiddleware()
    context = MiddlewareContext(message=mt.CallToolRequestParams(name="context_search"))

    async def next_tool(_context: object) -> ToolResult:
        raise ValueError("bad query")

    original_logger = server.logger
    server.logger = logger
    try:
        with pytest.raises(ValueError, match="bad query"):
            asyncio.run(middleware.on_call_tool(context, next_tool))
    finally:
        server.logger = original_logger
        logger.removeHandler(handler)

    event = json.loads(stream.getvalue())
    assert event["outcome"] == "error"
    assert event["error"] == {"type": "ValueError", "message": "bad query"}
