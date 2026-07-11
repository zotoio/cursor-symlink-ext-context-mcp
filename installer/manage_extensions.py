#!/usr/bin/env python3
"""Install, uninstall, update, and list extension payloads."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KINDS = ("agents", "commands", "hooks", "rules", "skills")
NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*$")
BLOCK_PREFIX = "cursor-symlink-ext-context-mcp:extension"


class ExtensionError(RuntimeError):
    """Raised for invalid catalog or installation state."""


class ExtensionManager:
    def __init__(self, repository: Path, home: Path, dry_run: bool = False) -> None:
        self.repository = repository.resolve()
        self.home = home.resolve()
        self.dry_run = dry_run
        self.installer = self.repository / "installer"
        self.payloads = self.installer / "payload" / "extensions"
        self.catalog_path = self.installer / "extensions.json"
        self.registry_path = self.home / ".extensions" / "extensions.json"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.backup_root = (
            self.home
            / ".local"
            / "state"
            / "cursor-symlink-ext-context-mcp"
            / "backups"
            / timestamp
        )
        self.catalog = self._load_catalog()

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ExtensionError(f"Missing JSON file: {path}") from error
        except json.JSONDecodeError as error:
            raise ExtensionError(f"Invalid JSON in {path}: {error}") from error
        if not isinstance(payload, dict):
            raise ExtensionError(f"Expected a JSON object in {path}.")
        return payload

    def _load_catalog(self) -> dict[str, dict[str, Any]]:
        payload = self._read_json(self.catalog_path)
        entries = payload.get("extensions")
        if payload.get("schemaVersion") != 1 or not isinstance(entries, list):
            raise ExtensionError("installer/extensions.json has an unsupported schema.")

        catalog: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ExtensionError("Every extension catalog entry must be an object.")
            name = entry.get("name")
            if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
                raise ExtensionError(f"Invalid extension name in catalog: {name!r}")
            if name in catalog:
                raise ExtensionError(f"Duplicate extension in catalog: {name}")
            if not (self.payloads / name).is_dir():
                raise ExtensionError(f"Registered extension has no payload: {name}")
            hooks = entry.get("hooks", [])
            if not isinstance(hooks, list):
                raise ExtensionError(f"Extension hooks must be a list: {name}")
            for hook in hooks:
                if (
                    not isinstance(hook, dict)
                    or not isinstance(hook.get("event"), str)
                    or not isinstance(hook.get("script"), str)
                    or Path(hook["script"]).name != hook["script"]
                ):
                    raise ExtensionError(f"Invalid hook registration for {name}.")
            catalog[name] = entry
        return catalog

    def installed(self) -> set[str]:
        if not self.registry_path.exists():
            return set()
        payload = self._read_json(self.registry_path)
        entries = payload.get("installed")
        if payload.get("schemaVersion") != 1 or not isinstance(entries, list):
            raise ExtensionError(f"Unsupported installed registry: {self.registry_path}")
        names = set(entries)
        if not all(isinstance(name, str) and NAME_PATTERN.fullmatch(name) for name in names):
            raise ExtensionError(f"Invalid extension name in {self.registry_path}")
        return names

    def list_extensions(self, status: str) -> list[dict[str, Any]]:
        installed = self.installed()
        result = []
        for name, entry in self.catalog.items():
            is_installed = name in installed
            if status == "available" and is_installed:
                continue
            if status == "installed" and not is_installed:
                continue
            result.append(
                {
                    "name": name,
                    "description": entry.get("description", ""),
                    "installed": is_installed,
                }
            )
        return result

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        if self.dry_run:
            print(f"[dry-run] write {path}")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
        temporary.replace(path)

    def _write_registry(self, installed: set[str]) -> None:
        self._write_json(
            self.registry_path,
            {"schemaVersion": 1, "installed": sorted(installed)},
        )

    def _backup(self, path: Path, label: str) -> None:
        if not path.exists() and not path.is_symlink():
            return
        destination = self.backup_root / label
        if self.dry_run:
            print(f"[dry-run] backup {path} -> {destination}")
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))
        print(f"Backed up {path} -> {destination}")

    def _copy_payload(self, name: str, replace_existing: bool) -> None:
        source = self.payloads / name
        target = self.home / ".extensions" / "extensions" / name
        if replace_existing and (target.exists() or target.is_symlink()):
            self._backup(target, f"extension-{name}")
        if self.dry_run:
            print(f"[dry-run] copy {source} -> {target}")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True, copy_function=shutil.copy2)
        for script in target.glob(".cursor/hooks/**/*.sh"):
            script.chmod(script.stat().st_mode | 0o111)
        print(f"Updated {target}")

    def _ensure_link(self, target: Path, link: Path, label: str) -> None:
        if link.is_symlink() and Path(os.path.abspath(link)).resolve() == target.resolve():
            return
        if link.exists() or link.is_symlink():
            self._backup(link, label)
        if self.dry_run:
            print(f"[dry-run] link {link} -> {target}")
            return
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        print(f"Linked {link} -> {target}")

    def _remove_expected_link(self, target: Path, link: Path) -> None:
        if not link.exists() and not link.is_symlink():
            return
        if not link.is_symlink():
            raise ExtensionError(f"Refusing to remove non-symlink path: {link}")
        if link.resolve() != target.resolve():
            raise ExtensionError(f"Refusing to remove symlink with unexpected target: {link}")
        if self.dry_run:
            print(f"[dry-run] unlink {link}")
            return
        link.unlink()
        print(f"Removed link {link}")

    @staticmethod
    def _ignore_patterns(name: str, cursor: bool) -> list[str]:
        paths = [f".cursor/{kind}/ext/{name}" for kind in KINDS]
        if cursor:
            return [item for path in paths for item in (f"!{path}", f"!{path}/**")]
        return paths

    def _update_ignore_file(self, path: Path, name: str, install: bool, cursor: bool) -> None:
        start = f"# {BLOCK_PREFIX}:{name}:begin"
        end = f"# {BLOCK_PREFIX}:{name}:end"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

        filtered: list[str] = []
        inside = False
        legacy = set(self._ignore_patterns(name, cursor))
        for line in lines:
            if line == start:
                inside = True
                continue
            if line == end:
                inside = False
                continue
            if not inside and line not in legacy:
                filtered.append(line)
        while filtered and not filtered[-1]:
            filtered.pop()

        if install:
            if filtered:
                filtered.append("")
            filtered.extend([start, *self._ignore_patterns(name, cursor), end])

        content = "\n".join(filtered)
        if content:
            content += "\n"
        if self.dry_run:
            print(f"[dry-run] update {path}")
            return
        path.write_text(content, encoding="utf-8")
        action = "Added" if install else "Removed"
        print(f"{action} {name} entries in {path}")

    def _sync_ignore_files(self, name: str, install: bool) -> None:
        self._update_ignore_file(self.repository / ".gitignore", name, install, cursor=False)
        self._update_ignore_file(self.repository / ".cursorignore", name, install, cursor=True)

    def _rebuild_hooks(self, installed: set[str]) -> None:
        base_path = self.installer / "payload" / "CORE" / ".cursor" / "hooks.json"
        hooks_payload = self._read_json(base_path)
        hooks = hooks_payload.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise ExtensionError(f"Invalid hooks object in {base_path}")

        for name in sorted(installed):
            entry = self.catalog.get(name)
            if entry is None:
                raise ExtensionError(f"Installed extension is absent from catalog: {name}")
            for hook in entry.get("hooks", []):
                event = hook["event"]
                event_hooks = hooks.setdefault(event, [])
                event_hooks.append({"command": (f".cursor/hooks/ext/{name}/{hook['script']}")})
        destination = self.home / "CORE" / ".cursor" / "hooks.json"
        self._write_json(destination, hooks_payload)

    def _ensure_extension_links(self, name: str) -> None:
        extension_root = self.home / ".extensions" / "extensions" / name
        context_target = extension_root / "CONTEXT"
        self._ensure_link(
            context_target,
            self.home / "CORE" / "CONTEXT" / "ext" / name,
            f"context-{name}",
        )
        for kind in KINDS:
            self._ensure_link(
                extension_root / ".cursor" / kind / name,
                self.repository / ".cursor" / kind / "ext" / name,
                f"project-{name}-{kind}",
            )

    def _remove_extension_links(self, name: str) -> None:
        extension_root = self.home / ".extensions" / "extensions" / name
        self._remove_expected_link(
            extension_root / "CONTEXT",
            self.home / "CORE" / "CONTEXT" / "ext" / name,
        )
        for kind in KINDS:
            self._remove_expected_link(
                extension_root / ".cursor" / kind / name,
                self.repository / ".cursor" / kind / "ext" / name,
            )

    def _notify_index(self) -> None:
        marker = self.home / "CORE" / "CONTEXT" / ".index-refresh"
        if self.dry_run:
            print(f"[dry-run] touch {marker}")
            return
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"{time.time_ns()}\n", encoding="utf-8")
        print("Notified the context index watcher.")

    def _require_core(self) -> None:
        if not (self.home / "CORE" / ".cursor").is_dir():
            raise ExtensionError("CORE is not installed. Run installer/setup.sh first.")

    def install(self, name: str) -> None:
        self._require_core()
        if name not in self.catalog:
            raise ExtensionError(f"Unknown extension payload: {name}")
        installed = self.installed()
        if name in installed:
            raise ExtensionError(f"Extension is already installed: {name}")
        self._copy_payload(name, replace_existing=True)
        self._ensure_extension_links(name)
        self._sync_ignore_files(name, install=True)
        installed.add(name)
        self._write_registry(installed)
        self._rebuild_hooks(installed)
        self._notify_index()

    def uninstall(self, name: str) -> None:
        self._require_core()
        installed = self.installed()
        if name not in installed:
            raise ExtensionError(f"Extension is not installed: {name}")
        self._remove_extension_links(name)
        self._sync_ignore_files(name, install=False)
        self._backup(
            self.home / ".extensions" / "extensions" / name,
            f"uninstalled-{name}",
        )
        installed.remove(name)
        self._write_registry(installed)
        self._rebuild_hooks(installed)
        self._notify_index()

    def update(self, name: str | None = None) -> None:
        self._require_core()
        installed = self.installed()
        names = [name] if name else sorted(installed)
        if name and name not in installed:
            raise ExtensionError(f"Extension is not installed: {name}")
        for extension in names:
            if extension not in self.catalog:
                raise ExtensionError(f"Installed extension is absent from catalog: {extension}")
            self._copy_payload(extension, replace_existing=True)
        self._notify_index()

    def reconcile(self) -> None:
        """Restore links/config for extensions already registered on this machine."""
        self._require_core()
        installed = self.installed()
        for name in sorted(installed):
            if name not in self.catalog:
                raise ExtensionError(f"Installed extension is absent from catalog: {name}")
            self._copy_payload(name, replace_existing=False)
            self._ensure_extension_links(name)
            self._sync_ignore_files(name, install=True)
        self._rebuild_hooks(installed)
        self._notify_index()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("list", "install", "uninstall", "update", "reconcile"),
    )
    parser.add_argument("name", nargs="?")
    parser.add_argument(
        "--status",
        choices=("all", "available", "installed"),
        default="all",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manager = ExtensionManager(args.project_root, args.home, args.dry_run)
        if args.action == "list":
            print(json.dumps(manager.list_extensions(args.status), indent=2))
        elif args.action == "install":
            if not args.name:
                raise ExtensionError("install requires an extension name.")
            manager.install(args.name)
        elif args.action == "uninstall":
            if not args.name:
                raise ExtensionError("uninstall requires an extension name.")
            manager.uninstall(args.name)
        elif args.action == "update":
            manager.update(args.name)
        else:
            manager.reconcile()
    except ExtensionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
