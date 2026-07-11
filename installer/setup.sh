#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
HOME_ROOT=${HOME:?HOME must be set}
DRY_RUN=false
SKIP_MCP_RUNTIME=${CONTEXT_MCP_SKIP_RUNTIME:-false}

usage() {
  printf '%s\n' "Usage: installer/setup.sh [--project-root PATH] [--home PATH] [--dry-run]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) PROJECT_ROOT=$2; shift 2 ;;
    --home) HOME_ROOT=$2; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --skip-mcp-runtime) SKIP_MCP_RUNTIME=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

PAYLOAD="$SCRIPT_DIR/payload"
[ -d "$PAYLOAD/CORE/.cursor" ] || { printf '%s\n' "Missing CORE payload." >&2; exit 1; }
[ -d "$PAYLOAD/extensions" ] || { printf '%s\n' "Missing extension payload." >&2; exit 1; }
[ -f "$SCRIPT_DIR/extensions.json" ] || {
  printf '%s\n' "Missing extension catalog: $SCRIPT_DIR/extensions.json" >&2
  exit 1
}
[ -d "$PROJECT_ROOT/.cursor" ] || { printf '%s\n' "Project root lacks .cursor: $PROJECT_ROOT" >&2; exit 1; }

BACKUP_ROOT="$HOME_ROOT/.local/state/cursor-symlink-ext-context-mcp/backups/$(date +%Y%m%dT%H%M%S)"

run() {
  if [ "$DRY_RUN" = true ]; then
    printf '[dry-run]'; printf ' %s' "$@"; printf '\n'
  else
    "$@"
  fi
}

backup_and_remove() {
  path=$1
  label=$2
  if [ -e "$path" ] || [ -L "$path" ]; then
    run mkdir -p "$BACKUP_ROOT"
    run mv "$path" "$BACKUP_ROOT/$label"
    printf 'Backed up %s\n' "$path"
  fi
}

replace_link() {
  target=$1
  link_path=$2
  label=$3
  backup_and_remove "$link_path" "$label"
  run mkdir -p "$(dirname "$link_path")"
  run ln -s "$target" "$link_path"
  printf 'Linked %s -> %s\n' "$link_path" "$target"
}

sync_tree() {
  source=$1
  target=$2
  if [ "$DRY_RUN" = true ]; then
    printf '[dry-run] sync %s -> %s (preserve CONTEXT/ext)\n' "$source" "$target"
    return
  fi
  python3 "$SCRIPT_DIR/sync_tree.py" \
    --source "$source" \
    --target "$target" \
    --preserve "CONTEXT/ext"
  printf 'Synchronized %s\n' "$target"
}

sync_tree "$PAYLOAD/CORE" "$HOME_ROOT/CORE"

for kind in agents commands hooks rules skills; do
  replace_link \
    "$HOME_ROOT/CORE/.cursor/$kind/CORE" \
    "$PROJECT_ROOT/.cursor/$kind/CORE" \
    "project-CORE-$kind"
done

replace_link "$HOME_ROOT/CORE/.cursor/hooks.json" "$PROJECT_ROOT/.cursor/hooks.json" "project-hooks-json"
replace_link "$HOME_ROOT/CORE/CONTEXT" "$PROJECT_ROOT/CONTEXT" "project-context"

if [ "$DRY_RUN" = false ]; then
  find "$HOME_ROOT/CORE/.cursor/hooks" -name '*.sh' -type f -exec chmod +x {} +
  python3 "$SCRIPT_DIR/manage_extensions.py" reconcile \
    --home "$HOME_ROOT" \
    --project-root "$PROJECT_ROOT"

  if [ "$SKIP_MCP_RUNTIME" = false ]; then
    chmod +x "$SCRIPT_DIR/context_mcp.sh"
    HOME="$HOME_ROOT" "$SCRIPT_DIR/context_mcp.sh" up
    python3 "$SCRIPT_DIR/configure_cursor_mcp.py" --home "$HOME_ROOT"
    AGENT_BIN=${CURSOR_AGENT_BIN:-agent}
    command -v "$AGENT_BIN" >/dev/null 2>&1 || {
      printf '%s\n' "Cursor agent CLI is required to enable core-context." >&2
      exit 1
    }
    "$AGENT_BIN" mcp enable core-context
    "$AGENT_BIN" mcp list
  else
    printf '%s\n' "Skipped Docker MCP runtime setup."
  fi
else
  printf '%s\n' "[dry-run] skip reconciliation of machine-installed extensions"
  printf '%s\n' "[dry-run] skip Docker MCP runtime setup"
fi

printf '%s\n' "Setup complete. Backup directory: $BACKUP_ROOT"
