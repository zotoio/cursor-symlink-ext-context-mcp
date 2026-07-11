"""Streamable HTTP MCP server for installed shared context."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC
from pathlib import Path
from typing import Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp import types as mt
from pydantic import Field, create_model
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .index import ContextIndex

HOME = Path(os.environ.get("HOME", "~")).expanduser()
CORE_CONTEXT = Path(os.environ.get("CORE_CONTEXT_DIR", HOME / "CORE" / "CONTEXT")).expanduser()
EXTENSIONS_DIR = Path(
    os.environ.get("EXTENSIONS_DIR", HOME / ".extensions" / "extensions")
).expanduser()
STATE_PATH = Path(
    os.environ.get(
        "CONTEXT_INDEX_PATH",
        HOME / ".local" / "state" / "cursor-symlink-ext-context-mcp" / "context-index.json",
    )
).expanduser()
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8989"))
MCP_PATH = os.environ.get("MCP_PATH", "/mcp")

index = ContextIndex(CORE_CONTEXT, STATE_PATH)
logger = logging.getLogger("context_mcp.audit")
_ready = False
_startup_error: str | None = None
_search_clarification: ContextVar[str] = ContextVar(
    "context_search_clarification", default="not_applicable"
)

# Avoid interrupting a focused request, or one that has a clear leading result.
AMBIGUITY_MAX_SCORE = 0.7
AMBIGUITY_MAX_DELTA = 0.08
NO_SOURCE_FOCUS = "Any source"
NO_TOPIC_FOCUS = "No topic focus"


def configure_logging() -> None:
    """Emit audit records to stderr without interfering with MCP HTTP responses."""
    if logger.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _json_value(value: object) -> object:
    """Convert FastMCP/Pydantic values into JSON-safe audit payloads."""
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="json"))  # type: ignore[union-attr]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


class ToolCallLoggingMiddleware(Middleware):
    """Write complete MCP tool-call requests and responses as JSON Lines."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: Any,
    ) -> ToolResult:
        started = time.perf_counter()
        clarification_token = _search_clarification.set("not_applicable")
        payload: dict[str, object] = {
            "timestamp": context.timestamp.astimezone(UTC).isoformat(),
            "server": "core-context",
            "tool": context.message.name,
            "arguments": _json_value(context.message.arguments or {}),
        }
        try:
            result = await call_next(context)
        except Exception as error:
            payload.update(
                {
                    "outcome": "error",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "error": {"type": type(error).__name__, "message": str(error)},
                }
            )
            if context.message.name == "context_search":
                payload["clarification"] = _search_clarification.get()
            logger.info(json.dumps(payload, default=str, sort_keys=True))
            _search_clarification.reset(clarification_token)
            raise

        payload.update(
            {
                "outcome": "error" if result.is_error else "success",
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "response": {
                    "structured_content": _json_value(result.structured_content),
                    "content": _json_value(result.content),
                    "meta": _json_value(result.meta),
                    "is_error": result.is_error,
                },
            }
        )
        if context.message.name == "context_search":
            payload["clarification"] = _search_clarification.get()
        logger.info(json.dumps(payload, default=str, sort_keys=True))
        _search_clarification.reset(clarification_token)
        return result


def _set_ready(value: bool, error: str | None = None) -> None:
    global _ready, _startup_error
    _ready = value
    _startup_error = error


def initialize_index() -> None:
    """Build the initial index and load the embedding model before readiness."""
    try:
        index.sync()
        index._model()
    except Exception as error:
        logger.exception("Context MCP startup failed")
        _set_ready(False, str(error))
    else:
        _set_ready(True)


class ContextChangeHandler(FileSystemEventHandler):
    def on_any_event(self, _event: object) -> None:
        try:
            index.sync()
        except OSError:
            # A file can disappear between a watcher event and the rescan.
            pass


def start_watcher() -> Observer:
    observer = Observer()
    handler = ContextChangeHandler()
    for directory in (CORE_CONTEXT, EXTENSIONS_DIR):
        if directory.is_dir():
            observer.schedule(handler, str(directory), recursive=True)
    observer.start()
    return observer


@asynccontextmanager
async def server_lifespan(_server: FastMCP) -> Any:
    """Start indexing without delaying the HTTP liveness endpoint."""
    observer = start_watcher()
    thread = threading.Thread(target=initialize_index, name="context-index-warmup", daemon=True)
    thread.start()
    try:
        yield
    finally:
        observer.stop()
        await asyncio.to_thread(observer.join)


mcp = FastMCP("CORE Context Search", lifespan=server_lifespan)
mcp.add_middleware(ToolCallLoggingMiddleware())


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health(_request: Request) -> Response:
    """Report process liveness without requiring the model to be ready."""
    return JSONResponse({"status": "ok", "server": "core-context"})


@mcp.custom_route("/ready", methods=["GET"], include_in_schema=False)
async def ready(_request: Request) -> Response:
    """Report whether the initial index and embedding model are ready."""
    body = {"ready": _ready, "server": "core-context"}
    if _startup_error:
        body["error"] = _startup_error
    return JSONResponse(body, status_code=200 if _ready else 503)


def _is_ambiguous(results: list[dict[str, object]], source: str | None) -> bool:
    """Return whether mixed, closely ranked results need optional clarification."""
    if source is not None or len(results) < 2:
        return False

    try:
        best_score = float(results[0]["score"])
        next_score = float(results[1]["score"])
    except (KeyError, TypeError, ValueError):
        return False

    sources = {str(result.get("source", "")) for result in results[:3]}
    return len(sources - {""}) > 1 and (
        best_score < AMBIGUITY_MAX_SCORE or best_score - next_score <= AMBIGUITY_MAX_DELTA
    )


def _focus_form(results: list[dict[str, object]]) -> tuple[type[Any], dict[str, dict[str, object]]]:
    """Build an elicitation schema and resolve its topic labels back to results."""
    sources = tuple(sorted({str(result["source"]) for result in results if result.get("source")}))
    topics: dict[str, dict[str, object]] = {}
    for result in results[:5]:
        title = str(result.get("title", "Untitled result"))
        label = f"{result.get('source', 'Unknown')}: {title}"
        topics.setdefault(label, result)

    source_choices = (NO_SOURCE_FOCUS, *sources)
    topic_choices = (NO_TOPIC_FOCUS, *topics)
    source_type = Literal.__getitem__(source_choices)
    topic_type = Literal.__getitem__(topic_choices)
    form = create_model(
        "ContextSearchFocus",
        source=(
            source_type,
            Field(
                default=NO_SOURCE_FOCUS,
                title="Source focus",
                description="Optionally limit the refined search to one context source.",
            ),
        ),
        topic=(
            topic_type,
            Field(
                default=NO_TOPIC_FOCUS,
                title="Result topic",
                description="Optionally focus on one of the candidate result topics.",
            ),
        ),
    )
    return form, topics


async def _apply_focus(
    ctx: Context,
    query: str,
    limit: int,
    results: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Elicit optional search focus and rerun only after an accepted response."""
    form, topics = _focus_form(results)
    _search_clarification.set("offered")
    try:
        response = await ctx.elicit(
            "Several context sources could help. Optionally focus this search.",
            form,
        )
    except Exception:
        # MCP clients are not required to implement elicitation. Search remains usable.
        _search_clarification.set("unavailable")
        return results

    if response.action != "accept":
        _search_clarification.set(response.action)
        return results

    data = response.data
    selected_source = data.source if data.source != NO_SOURCE_FOCUS else None
    selected_topic = topics.get(data.topic)
    focused_query = query
    if selected_topic is not None:
        focused_query = f"{query} {selected_topic['title']}"

    _search_clarification.set("accepted")
    return index.search(query=focused_query, limit=limit, source=selected_source)


@mcp.tool
async def context_search(
    ctx: Context, query: str, limit: int = 5, source: str | None = None
) -> list[dict[str, object]]:
    """Semantically search CORE and extension Markdown context."""
    results = index.search(query=query, limit=limit, source=source)
    if not _is_ambiguous(results, source):
        _search_clarification.set("not_ambiguous")
        return results
    return await _apply_focus(ctx, query, limit, results)


@mcp.tool
def context_read(path: str) -> dict[str, str]:
    """Read an indexed context document by the path returned from context_search."""
    return index.read(path)


@mcp.tool
def context_status() -> dict[str, object]:
    """Report indexed document count, sources, and the active embedding model."""
    return {
        **index.stats(),
        "ready": _ready,
        "transport": "streamable-http",
        "session_mode": "stateful",
        "url": f"http://127.0.0.1:{MCP_PORT}{MCP_PATH}",
    }


def main() -> None:
    configure_logging()
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        path=MCP_PATH,
        stateless_http=False,
    )


if __name__ == "__main__":
    main()
