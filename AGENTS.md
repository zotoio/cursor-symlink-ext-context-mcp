# Agent Guide

This repository prototypes shared Cursor extensions before their migration to
native plugins. Catalog payloads are committed; installed state is deliberately
machine-local.

## Start here

1. Install the repository and Python environment:

   ```sh
   ./installer/setup.sh
   uv sync --all-groups
   ```

2. `installer/setup.sh` builds and starts the Docker Compose-managed Streamable
   HTTP Context MCP service, registers it at `http://127.0.0.1:8989/mcp` in
   `~/.cursor/mcp.json`, and enables it with the Cursor agent CLI. Verify
   readiness with `./installer/context_mcp.sh status` or `/ready` before
   relying on `context_search`, `context_read`, or `context_status`. The initial
   connection may take longer while the embedding model is first downloaded.
   Use `/context-search`, or let the automatic CORE
   `context-search` skill handle requests that depend on shared or extension
   context. Pass `source` to `context_search` only as a concrete source name
   such as `CORE`, `PRODUCT`, `QA`, or `SUPPORT`.
   The service uses stateful Streamable HTTP: Cursor manages the
   `Mcp-Session-Id` returned at initialization. When a search has closely
   ranked results from different sources, an elicitation-capable client can
   optionally refine it by source or topic. If elicitation is unavailable or
   declined, use the returned ranked results unchanged.

## Extension model

- `installer/extensions.json` is the committed catalog.
- `installer/payload/extensions/<NAME>/` contains an extension's committed
  Cursor primitives and `CONTEXT/` files.
- `~/.extensions/extensions.json` tracks only extensions installed on this
  machine.
- Installation materializes payloads under `~/.extensions/extensions/<NAME>`
  and manages project/context symlinks, ignore blocks, and hook configuration.

Use `installer/manage_extensions.py` or the `/extension-*` commands for
extension lifecycle changes. Do not copy payloads, create/remove managed
symlinks, edit generated ignore blocks, or modify the installed registry by
hand.

`install` changes machine installation state; `uninstall` removes that state
but preserves committed payloads; `update` refreshes only extensions already
installed. A pull or a new catalog entry does not install an extension.

## Verification

```sh
uv run ruff check .
uv run python -m pytest
sh -n installer/setup.sh
sh -n installer/context_mcp.sh
python3 -m json.tool installer/extensions.json
```

After setup, confirm the connected MCP with `context_status` and search an
installed extension topic; result sources identify the extension that supplied
the context. `context_status` reports `session_mode: "stateful"`. Container
stderr audit logs contain complete tool payloads and responses, including
potentially sensitive context content and search-clarification outcomes.
The service uses CPU-only PyTorch with a two-thread embedding budget and Docker
limits of 2 GiB memory, two CPUs, and 128 processes. Context changes are
coalesced by a short watcher debounce; search, read, and status calls use the
in-memory index without rescanning the corpus.
