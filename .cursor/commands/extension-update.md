---
name: extension-update
description: Apply committed payload changes to all installed extensions.
---

# /extension-update

Update every machine-installed extension from its committed payload.

## Instructions

Resolve the repository root from `$CURSOR_WORKING_DIRECTORY` (fall back to the
current working directory), then run:

```sh
python3 installer/manage_extensions.py update
```

This operation only copies payload contents into existing installed home
directories and notifies the hot context index. It does not add or remove
extensions, rewrite project symlinks, change ignore files, or alter the
machine-installed registry.

Report the updated extension names. Do not commit.
