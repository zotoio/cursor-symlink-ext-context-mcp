# cursor-symlink-ext-context-mcp

This repository prototypes the path from shared Cursor extensions to native Cursor
plugins with versioned context packs and semantic MCP indexing. Available extensions
are defined in `installer/extensions.json`, their committed Cursor primitives and
context files live in `installer/payload`, and machine-installed state is tracked separately in
`~/.extensions/extensions.json`.

The catalog and installed registry intentionally have different lifecycles:

- pulling a commit can add or change available payloads without installing them
- installing or uninstalling changes only the current machine's registry
- the installed set persists over time and is reconciled into each configured clone
- updating applies newer committed payload files only to extensions already installed

## Cursor plugin migration

Extensions are precursors to Cursor plugins: both package agents, commands, hooks,
rules, and skills, but extensions additionally own versioned `CONTEXT/` files that
are installed, linked, and indexed alongside those primitives.

The intended next step is migration to native Cursor plugins once the design for
linking a plugin to its corresponding context pack—and keeping that pack's semantic
index current—is settled. Until then, the extension catalog, installed registry, and
context MCP service make that relationship explicit and testable.

## Architecture and roadmap

This project deliberately separates version-controlled extension availability from
machine-local installation. That distinction, the deployed filesystem layout, and
the Context MCP runtime are documented in [Architecture](docs/architecture.md).

The [Roadmap](docs/roadmap.md) describes the milestones needed to harden the
prototype and evaluate a migration to native Cursor plugins. It presents several
design approaches rather than treating the native-plugin integration as a
pre-decided implementation.

## Setup

Prerequisites:

- POSIX shell utilities (`cp`, `find`, `ln`, `mv`)
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Docker Engine with Docker Compose v2
- Cursor's `agent` CLI, used by setup to enable the user-level MCP registration

From a clone, run:

```sh
./installer/setup.sh
uv sync --all-groups
```

The setup script installs CORE, reconciles extensions already recorded in the
machine registry, builds and starts the local `core-context` container, and
registers `http://127.0.0.1:8989/mcp` in `~/.cursor/mcp.json`. It preserves
unrelated user-level MCP registrations and enables `core-context` with
`agent mcp enable core-context`. It does not automatically install every
available payload. Restart Cursor or reload its MCP servers after the first
registration so the IDE connects to the new user-level server.
Consequently, a newly cloned project picks up the machine's existing extension set,
while a new catalog entry remains available until explicitly installed.

The installer synchronizes `~/CORE` in place so the running container retains
its bind mount and the watcher can reindex changes without a restart. It backs
up managed symlinks and replaced extension payloads beneath
`~/.local/state/cursor-symlink-ext-context-mcp/backups/<timestamp>/`. Preview
changes without writing anything:

```sh
./installer/setup.sh --dry-run
```

For an isolated setup, pass both locations explicitly:

```sh
./installer/setup.sh --home /tmp/symlink-home --project-root "$PWD"
```

## Installed layout

`installer/setup.sh` deploys:

- `installer/payload/CORE` to `~/CORE`
- `CONTEXT` in the repository as a symlink to `~/CORE/CONTEXT`
- previously installed extensions from the machine registry, when reconciling a
  new clone

It also creates the CORE and extension `.cursor` symlinks. The sole hook
configuration is `~/CORE/.cursor/hooks.json`, exposed to the project as
`.cursor/hooks.json`; installed extension hooks are assembled from the catalog.

Inspect catalog and machine state at any time:

```sh
python3 installer/manage_extensions.py list --status all
python3 installer/manage_extensions.py list --status available
python3 installer/manage_extensions.py list --status installed
```

These commands derive their output from the current catalog and machine registry;
the documentation does not define a fixed extension list.

## Extension lifecycle

Use `/extension-list` to inspect every catalog payload and whether it is installed
on the current machine.

Use `/extension-create` to add only committed catalog metadata and payload files.
It does not modify the home directory, project symlinks, ignore files, or installed
registry.

Use `/extension-install` to select an available payload through `AskQuestion`.
Installation:

- copies it to `~/.extensions/extensions/<NAME>`
- records it in `~/.extensions/extensions.json`
- creates `.cursor/*/ext/<NAME>` and `CONTEXT/ext/<NAME>` symlinks
- adds managed blocks to `.gitignore` and `.cursorignore`
- rebuilds the single installed hook configuration
- signals the running context index to refresh

Use `/extension-uninstall` to select an installed extension through `AskQuestion`.
It removes the managed links and ignore blocks, backs up the home-directory
extension, updates the registry and hooks, and leaves the committed payload intact.

Use `/extension-update` after pulling committed payload changes. It only copies
the payloads for currently installed extensions into their existing home
directories and signals the context index. It does not change installation state,
links, ignore files, or registry entries.

The same operations are available directly:

```sh
python3 installer/manage_extensions.py list --status available
python3 installer/manage_extensions.py install <NAME>
python3 installer/manage_extensions.py uninstall <NAME>
python3 installer/manage_extensions.py update
```

## Context MCP server

The local MCP server semantically searches Markdown in `~/CORE/CONTEXT` and its
extension context links. It uses FastMCP, `sentence-transformers`, and a persistent
index at `~/.local/state/cursor-symlink-ext-context-mcp/context-index.json`.
It indexes only the installed home layout: `~/CORE/CONTEXT` and
`~/CORE/CONTEXT/ext/<NAME>` symlinks into
`~/.extensions/extensions/<NAME>/CONTEXT`. Committed
`installer/payload/extensions/` directories are catalog sources and are never
indexed directly.

`core-context` runs as a Docker Compose-managed Streamable HTTP service at
`http://127.0.0.1:8989/mcp`. Docker restarts it with `unless-stopped`; the
installer registers it once at the user level in `~/.cursor/mcp.json`, so it
is available to every Cursor workspace on this machine. The service binds only
to loopback on the host. Cursor connects to the service but does not launch it.
The service runs in stateful Streamable HTTP mode: FastMCP issues an
`Mcp-Session-Id` during initialization and clients reuse it on later requests.
The session is transport-managed and contains no persisted search history.

Use the installer-managed lifecycle script when needed:

```sh
./installer/context_mcp.sh status
./installer/context_mcp.sh logs
./installer/context_mcp.sh refresh
./installer/context_mcp.sh restart
./installer/context_mcp.sh rebuild
```

`GET http://127.0.0.1:8989/health` reports process liveness; `/ready` reports
that the initial index and embedding model are ready. The initial connection may
take longer while the default sentence-transformer model is downloaded into the
Docker volume. Later changes to CORE or extension context files are re-indexed by
the file watcher and verified again on every search.
Extension install and uninstall update the `CONTEXT/ext/<NAME>` links; update
refreshes the installed extension content. All three operations touch
`.index-refresh`, so the watcher and the next MCP operation both rescan the
installed context set.

The server exposes:

- `context_search(query, limit=5, source=None)` for semantic search. `source`
  is an optional, case-insensitive exact source name such as `CORE`, `PRODUCT`,
  `QA`, or `SUPPORT`; it is not an extension category. Results contain `path`,
  `source`, `title`, `score`, and a `snippet`. When mixed results are closely
  ranked, an elicitation-capable client may offer an optional source or topic
  focus and rerun the search. Declining, cancelling, or lacking elicitation
  support returns the original ranked results.
- `context_read(path)` for an indexed document
- `context_status()` for indexed document count, sources, and active embedding
  model (`all-MiniLM-L6-v2` by default), readiness, service URL, and session
  mode

Every MCP tool call is written to the container's stderr as a JSON Line tagged
with `server: "core-context"` and containing complete arguments, responses, and
errors. These audit logs can include full context documents and queries; treat
`./installer/context_mcp.sh logs` output as sensitive. Search records also
include the clarification outcome (`not_ambiguous`, `accepted`, `decline`,
`cancel`, or `unavailable`), which can reveal that a client was offered focus.

Use `/context-search` for an explicit shared-context lookup. The installed
CORE `context-search` skill also applies automatically when a request depends
on shared conventions or an installed extension's context. Both check
`context_status` first, search with `context_search`, and use `context_read`
only for a selected result's complete content.

## Developing extensions

`/extension-create` writes new extension samples to
`installer/payload/extensions/<NAME>` and adds metadata to
`installer/extensions.json`. Run `/extension-install` when that payload should be
materialized for the current machine and project. Existing installations do not
change merely because a payload is added or committed.

## Production hosting

The local container is intentionally loopback-only and is not a production
deployment. For production, host Streamable HTTP behind TLS and authentication,
then register Cursor with that remote URL. Keep the service's context corpus
fresh by periodically reindexing and embedding changed documents; this is not
model training.

## Verification

```sh
uv run ruff check .
uv run python -m pytest
sh -n installer/setup.sh
sh -n installer/context_mcp.sh
python3 -m json.tool installer/extensions.json
HOST_HOME="$HOME" docker compose -f installer/docker/docker-compose.yml config
```

With `core-context` connected in Cursor, verify the live index and installed
extension results by checking `context_status`, then searching for a known
extension topic. For example, `context_search("boundary cases quality tests")`
should return a `QA` result when QA is installed.
