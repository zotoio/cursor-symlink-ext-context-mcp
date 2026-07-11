---
name: extension-create
description: Scaffold an installer payload extension with Cursor primitives, context, and a test hook.
---

# /extension-create

Create a new named extension in the committed installer catalog and payload.
This command must not install it, create runtime symlinks, or edit ignore files.

## Instructions

### 1. Ask for the extension name (required)

Use the **AskQuestion** tool (never a free-form chat prompt with `[Yes / No]` style options). Ask a single question:

- **Prompt:** `What should the new extension be named?`
- **Options:** offer 4–6 plausible UPPERCASE names suited to this repo’s layout, for example:
  - `PLATFORM`
  - `SECURITY`
  - `DATA`
  - `DOCS`
  - `QA`
  - `Something else (I will type it)`
- Single-select only (`allow_multiple: false`).
- At most one AskQuestion per assistant message.

If the user picks **Something else (I will type it)**, wait for their typed name in the next message. Do not invent a name.

If AskQuestion is unavailable, ask the same question conversationally and keep it short.

### 2. Normalize the name

From the chosen / typed value, derive:

| Token | Rule | Example |
|-------|------|---------|
| `NAME` | Uppercase identifier; letters/digits only; spaces/`-`/`_` → stripped or collapsed | `Security Ops` → `SECURITYOPS` or prefer `SECURITY` if they typed that |
| `slug` | Lowercase of `NAME` | `security` |
| `Title` | Title Case for headings | `Security` |

Reject empty names and names that already exist in `installer/extensions.json`
or as `installer/payload/extensions/<NAME>`. Abort with a clear message listing
the conflict.

Prefer keeping the user’s exact UPPERCASE token when they already typed one (`PLATFORM`, `QA`, etc.).

### 3. Derive plausible sample primitives from the name

Invent short, domain-fitting samples from `NAME` / `slug` / `Title`. Do **not** copy PRODUCT/SUPPORT wording verbatim — tailor verbs and responsibilities to the extension’s meaning.

Create exactly one of each under `installer/payload/extensions/<NAME>/`:

| Kind | Path | Naming pattern | Content intent |
|------|------|----------------|----------------|
| Agent | `.cursor/agents/<NAME>/<slug>-<role>.md` | role from domain (e.g. `reviewer`, `auditor`, `triage`) | YAML frontmatter `name` + `description`; brief responsibilities |
| Command | `.cursor/commands/<NAME>/<slug>-<action>.md` | action from domain (e.g. `status`, `check`, `report`) | Frontmatter + `# /<slug>-<action>` body |
| Hook | `.cursor/hooks/<NAME>/<slug>-hook.sh` | — | Executable test script that echoes `[<NAME> hook]`; register its event and script in the installer catalog |
| Rule | `.cursor/rules/<NAME>/<slug>-conventions.mdc` | — | Frontmatter `description` + `alwaysApply: true`; 2–3 conventions |
| Skill | `.cursor/skills/<NAME>/<slug>-<topic>/SKILL.md` | topic from domain (e.g. `brief`, `playbook`) | Frontmatter + short step list |
| Context | `CONTEXT/<slug>.md` | — | Short domain context for semantic MCP search |

**Derivation examples** (illustrative — adapt to the actual name):

- `SECURITY` → agent `security-auditor`, command `/security-check`, skill `security-playbook`
- `DATA` → agent `data-steward`, command `/data-status`, skill `data-brief`
- `QA` → agent `qa-reviewer`, command `/qa-report`, skill `qa-checklist`

Keep each file small (test samples, not production docs).

### 4. Create the directories and write files

Resolve the repo root from `$CURSOR_WORKING_DIRECTORY` (fall back to cwd).

For each kind in `agents`, `commands`, `hooks`, `rules`, `skills`:

1. `mkdir -p <repoRoot>/installer/payload/extensions/<NAME>/.cursor/<kind>/<NAME>`
2. Write that kind’s sample primitive into that directory (skill is a subdirectory containing `SKILL.md`; the hook is an executable `.sh` script).

Append an object for `NAME` to the `extensions` array in
`<repoRoot>/installer/extensions.json`, including a short `description` and a
`hooks` array containing the sample hook's `event` and filename. Also create
`installer/payload/extensions/<NAME>/CONTEXT/<slug>.md`.

Do not edit `installer/payload/CORE/.cursor/hooks.json`; `/extension-install`
builds the installed hook configuration from the catalog.

These are versioned installer payloads. Do not create or modify home-directory
files, runtime symlinks, `.gitignore`, `.cursorignore`, or the machine registry.
The user installs the payload later with `/extension-install`.

If the payload extension already exists, abort rather than overwriting unless the user explicitly asked to replace it in this turn.

Optionally refresh `.cursor/agents/README.md` and `.cursor/skills/README.md` with a bullet for `ext/<NAME>`.

### 5. Confirm

Print a short summary:

- Extension `NAME`
- Its `installer/extensions.json` catalog entry
- The six payload files created
- Reminder to run `/extension-list` to inspect the catalog
- Reminder to run `/extension-install` when ready

Do not commit unless the user asks.

## Layout reminder

```text
installer/payload/
  CORE/
    .cursor/hooks.json       # single hook configuration
    CONTEXT/
  extensions/
    <NAME>/
      .cursor/
        agents/<NAME>/<slug>-<role>.md
        commands/<NAME>/<slug>-<action>.md
        hooks/<NAME>/<slug>-hook.sh
        rules/<NAME>/<slug>-conventions.mdc
        skills/<NAME>/<slug>-<topic>/SKILL.md
      CONTEXT/<slug>.md

installer/extensions.json   # available payload catalog

# /extension-install later creates home files and project links.
```
