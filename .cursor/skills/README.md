# Skills

Project-local skills live directly in this directory. Shared trees use this
runtime layout:

- `CORE` is created by `installer/setup.sh` and links to
  `~/CORE/.cursor/skills/CORE`.
- `ext/<NAME>` is created by `/extension-install` and links to
  `~/.extensions/extensions/<NAME>/.cursor/skills/<NAME>`.

CORE includes the automatic `context-search` skill. It applies when a request
needs shared CORE or installed extension context and uses the user-level
Docker Compose-managed `core-context` Streamable HTTP MCP service.

Available skill payloads are discovered from `installer/extensions.json`; installed
skill trees follow the evolving machine registry at
`~/.extensions/extensions.json`. Use `/extension-list` to inspect both sets.
Pulling a new payload does not install it.
`/extension-update` refreshes only installed payloads, and
`/extension-uninstall` removes managed links while retaining committed sources.

These extension trees are a precursor to Cursor plugins. Their versioned
`CONTEXT/` packs and semantic index linkage stay explicit until that relationship
has a native plugin design.

An in-repo sample skill may exist before installation. The installer backs up a
conflicting real extension directory before creating its managed symlink.
