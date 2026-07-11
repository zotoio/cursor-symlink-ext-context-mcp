---
name: extension-uninstall
description: Select and safely uninstall machine-installed extensions.
---

# /extension-uninstall

Uninstall one or more extensions while preserving their committed installer payloads.

## Instructions

1. Resolve the repository root from `$CURSOR_WORKING_DIRECTORY` (fall back to
   the current working directory).
2. Run:

   ```sh
   python3 installer/manage_extensions.py list --status installed
   ```

3. If no extensions are installed, report that there is nothing to uninstall
   and stop.
4. Use the **AskQuestion** tool with exactly one multi-select question:
   - Prompt: `Which extensions should be uninstalled?`
   - Add one option per returned extension, using its `name` as the option ID
     and `NAME — description` as the label.
   - Add `Cancel` as the final option.
   - Set `allow_multiple: true`.
5. If the user selects `Cancel`, stop without changing files.
6. Uninstall every selected extension name, one at a time:

   ```sh
   python3 installer/manage_extensions.py uninstall <NAME>
   ```

The manager removes only expected symlinks, removes managed ignore entries,
backs up the installed home-directory tree, updates the machine registry and
hook configuration, and notifies the hot context index. The payload remains
available for future installation.

Do not remove files or edit registries manually. Do not commit.
