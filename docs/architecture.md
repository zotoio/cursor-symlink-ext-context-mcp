# Architecture

## Purpose and boundaries

`cursor-symlink-ext-context-mcp` is a local prototype for distributing shared
Cursor primitives and the Markdown context that supports them. It is not a
general-purpose package manager or a production remote MCP deployment.

The prototype has three intentional boundaries:

1. **Committed catalog:** the repository declares extension payloads that are
   available for installation.
2. **Machine-local installed state:** a user's installed extensions are stored
   outside the repository and can be reconciled into multiple clones.
3. **Local semantic search:** a Docker Compose-managed MCP service indexes only
   the installed context exposed through the home-directory layout.

Keeping these boundaries separate lets a repository commit new extension
versions without silently enabling them for every user or indexing unpublished
catalog content.

## Components

| Component | Source of truth | Responsibility |
| --- | --- | --- |
| Extension catalog | `installer/extensions.json` | Names, descriptions, and hook registrations for available extensions. |
| Extension payloads | `installer/payload/CORE/` and `installer/payload/extensions/<NAME>/` | Version-controlled Cursor primitives and `CONTEXT/` Markdown. |
| Lifecycle manager | `installer/manage_extensions.py` | Validates catalog entries and performs install, uninstall, update, and list operations. |
| Setup entry point | `installer/setup.sh` | Installs CORE, reconciles the current machine's installed extensions, starts the local service, and registers it with Cursor. |
| Installed registry | `~/.extensions/extensions.json` | Machine-local set of enabled extension names. It is not committed. |
| Installed payloads | `~/.extensions/extensions/<NAME>/` | Materialized copies of installed extension payloads. |
| Project links | `.cursor/*/ext/<NAME>` and `CONTEXT` | Expose installed primitives and CORE context to a particular clone. |
| Context MCP | `context_mcp/src/context_mcp/` | Serves stateful Streamable HTTP search, read, readiness, and status endpoints. |
| Docker runtime | `installer/docker/docker-compose.yml` | Runs the local service and persists the index and embedding-model cache. |

## State and filesystem model

The catalog and registry have different lifecycles:

```text
repository commit
 ├── installer/extensions.json         available extension metadata
 └── installer/payload/
     ├── CORE/                         shared base primitives and context
     └── extensions/<NAME>/            installable extension payloads

machine-local state
 ├── ~/.extensions/extensions.json     installed extension names
 ├── ~/.extensions/extensions/<NAME>/  installed payload copies
 └── ~/CORE/
     ├── CONTEXT/                      base context plus ext/<NAME> links
     └── .cursor/                      base hook configuration

per-project materialization
 ├── CONTEXT -> ~/CORE/CONTEXT
 └── .cursor/{agents,commands,hooks,rules,skills}/ext/<NAME>
     -> ~/.extensions/extensions/<NAME>/.cursor/...
```

`install` copies a catalog payload to machine-local storage, records the
extension, creates the expected links, updates managed ignore-file blocks, and
rebuilds the single hook configuration. `uninstall` reverses only the managed
machine/project materialization while preserving the committed catalog payload.
`update` refreshes payload copies for extensions that are already installed; it
does not change the installed set.

The lifecycle manager backs up replaced payloads and managed links under
`~/.local/state/cursor-symlink-ext-context-mcp/backups/`. It refuses to delete
non-symlink paths or symlinks that do not point at the expected target.

## Context indexing and request flow

The Context MCP indexes Markdown that is reachable through the installed layout:

1. `~/CORE/CONTEXT` supplies CORE documents.
2. `~/CORE/CONTEXT/ext/<NAME>` links each installed extension's `CONTEXT/`
   directory.
3. The server scans those paths, embeds the documents with
   `all-MiniLM-L6-v2` by default, and persists metadata and embeddings in the
   configured context-index path.
4. A filesystem watcher monitors the CORE context and installed-extension
   roots. It coalesces rapid changes before incrementally rescanning the
   installed context set. Lifecycle operations also touch `.index-refresh` to
   schedule that refresh.
5. `context_search` ranks matching documents. Without an explicit source
   filter, closely ranked results from multiple sources can offer an optional
   source/topic refinement when the client supports MCP elicitation.
6. `context_read` returns the full content of a path returned by search.

The service deliberately does **not** index
`installer/payload/extensions/` directly. Those directories describe what can
be installed, not what a user has activated.

## MCP service lifecycle

Docker Compose binds the Streamable HTTP endpoint to
`127.0.0.1:8989/mcp`; the container listens internally on all interfaces, but
the host port is loopback-only. It mounts the relevant home-directory context
and extension paths read-only, and persists the index and Hugging Face cache in
named volumes. It uses CPU-only PyTorch, limits embedding work to two CPU
threads, and has Docker limits of 2 GiB memory, two CPUs, and 128 processes.

At startup, the service starts its watcher and warms the index and embedding
model in a background thread. This permits:

- `GET /health` to indicate process liveness without waiting for model loading.
- `GET /ready` to return success only after initial indexing and model loading.
- `context_status()` to expose the indexed document count, sources, model,
  readiness, Streamable HTTP transport, and stateful-session mode.
- Search, read, and status requests to use the current in-memory index without
  a filesystem rescan.

The service uses stateful Streamable HTTP. Cursor manages the
`Mcp-Session-Id`; the server does not persist search history in that session.

## Security and operational considerations

- The local service is intentionally not a production endpoint. Any remote
  deployment needs TLS, authentication, authorization, and a defined
  reindexing policy.
- Tool calls are logged to container stderr as JSON Lines, including full
  arguments and responses. Context text and user queries can therefore appear
  in logs; restrict access and avoid treating log output as safe to share.
- The container mounts context inputs read-only. The lifecycle scripts, not the
  service, own payload installation and symlink mutation.
- The setup script edits the user-level Cursor MCP configuration while
  preserving unrelated registrations. It must be treated as a local-machine
  setup action, not as a repository-only build step.

## Extension authoring contract

An extension must have an uppercase catalog name, a matching committed payload
directory, and valid hook declarations. Its Cursor primitives belong beneath
the typed `.cursor` subdirectories in its payload; extension context belongs in
`CONTEXT/`. The catalog describes hooks, while the lifecycle manager composes
the installed hooks into the one CORE hook configuration.

When changing lifecycle behavior, keep the following in sync:

- catalog validation and payload layout;
- lifecycle commands and setup behavior;
- Context MCP indexing assumptions;
- user documentation and Cursor primitives;
- regression tests.

## Verification

Run the repository checks after changing this architecture:

```sh
uv run ruff check .
uv run python -m pytest
sh -n installer/setup.sh
sh -n installer/context_mcp.sh
python3 -m json.tool installer/extensions.json
HOST_HOME="$HOME" docker compose -f installer/docker/docker-compose.yml config
```
