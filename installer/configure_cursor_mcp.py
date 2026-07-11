"""Register the local Docker-backed context MCP in Cursor's user config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SERVER_NAME = "core-context"
SERVER_CONFIG = {"url": "http://127.0.0.1:8989/mcp"}


def configure(home: Path) -> Path:
    path = home / ".cursor" / "mcp.json"
    if path.is_file():
        try:
            config: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Cursor MCP configuration is not valid JSON: {path}") from error
        if not isinstance(config, dict):
            raise ValueError(f"Cursor MCP configuration must be a JSON object: {path}")
    else:
        config = {}

    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"Cursor MCP configuration has a non-object mcpServers field: {path}")
    servers[SERVER_NAME] = SERVER_CONFIG

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args()
    print(configure(args.home.expanduser()))


if __name__ == "__main__":
    main()
