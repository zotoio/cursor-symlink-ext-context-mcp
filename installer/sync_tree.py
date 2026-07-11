"""Synchronize a payload tree in place without replacing its root directory."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def is_preserved(relative: Path, preserved: tuple[Path, ...]) -> bool:
    return any(relative == item or item in relative.parents for item in preserved)


def sync_tree(source: Path, target: Path, preserved: tuple[Path, ...] = ()) -> None:
    """Make target match source while retaining target's root directory inode."""
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")

    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True, copy_function=shutil.copy2)

    source_paths = {
        path.relative_to(source)
        for root, directories, files in os.walk(source)
        for path in [Path(root), *(Path(root) / name for name in [*directories, *files])]
    }

    for root, directories, files in os.walk(target, topdown=False, followlinks=False):
        root_path = Path(root)
        for name in [*files, *directories]:
            path = root_path / name
            relative = path.relative_to(target)
            if relative in source_paths or is_preserved(relative, preserved):
                continue
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--preserve", action="append", default=[])
    args = parser.parse_args()
    sync_tree(
        args.source.expanduser(),
        args.target.expanduser(),
        tuple(Path(item) for item in args.preserve),
    )


if __name__ == "__main__":
    main()
