---
name: extension-install
description: Select and install available extension payloads.
---

# /extension-install

Install one or more extensions from `installer/payload/extensions/`.

## Instructions

1. Resolve the repository root from `$CURSOR_WORKING_DIRECTORY` (fall back to
   the current working directory).
2. Run:

   ```sh
   python3 installer/manage_extensions.py list --status available
   ```

3. If no extensions are available, report that every payload is already
   installed and stop.
4. Use the **AskQuestion** tool with exactly one multi-select question:
   - Prompt: `Which extensions should be installed?`
   - Add one option per returned extension, using its `name` as the option ID
     and `NAME — description` as the label.
   - Add `Cancel` as the final option.
   - Set `allow_multiple: true`.
5. If the user selects `Cancel`, stop without changing files.
6. Install every selected extension name, one at a time:

   ```sh
   python3 installer/manage_extensions.py install <NAME>
   ```

The manager copies the payload into the home directory, writes the machine
registry, creates project and context symlinks, updates `.gitignore` and
`.cursorignore`, rebuilds the single hook configuration, and notifies the hot
context index.

Do not copy files, edit ignore files, or create links manually. Do not commit.
