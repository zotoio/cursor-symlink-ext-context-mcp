# Agents

Project-local agents live directly in this directory. Shared trees use this
runtime layout:

- `CORE` is created by `installer/setup.sh` and links to
  `~/CORE/.cursor/agents/CORE`.
- `ext/<NAME>` is created by `/extension-install` and links to
  `~/.extensions/extensions/<NAME>/.cursor/agents/<NAME>`.

The extension names are not fixed. Available agent payloads come from
`installer/extensions.json`; the set currently linked into this project comes from
`~/.extensions/extensions.json`. Use `/extension-list` to inspect both sets.
`/extension-uninstall` removes a managed link
without deleting its committed payload, while `/extension-update` refreshes files
behind links for extensions that remain installed.

These extension trees are a precursor to Cursor plugins. They remain separate while
their versioned `CONTEXT/` packs and semantic index linkage are being designed for a
future plugin migration.

An in-repo sample directory may exist before that same extension is installed.
Installation safely backs up a conflicting real path before replacing it with the
managed symlink.
