---
name: extension-list
description: List available extension payloads and their installation status.
---

# /extension-list

Show the extension catalog and each payload's current machine-installation status.

## Instructions

1. Resolve the repository root from `$CURSOR_WORKING_DIRECTORY` (fall back to
   the current working directory).
2. Run:

   ```sh
   python3 installer/manage_extensions.py list --status all
   ```

3. Report every returned extension as `NAME — description` and clearly mark
   whether it is installed or available.
4. If the catalog is empty, report that no extension payloads are available.

This command is read-only. Do not modify files, registries, links, ignore files,
or hooks. Do not commit.
