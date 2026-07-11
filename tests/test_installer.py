from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def stage_repository(tmp_path: Path) -> Path:
    source = Path(__file__).parents[1]
    project = tmp_path / "project"
    shutil.copytree(source / "installer", project / "installer")
    project.joinpath(".cursor").mkdir(parents=True)
    (project / ".gitignore").write_text("# project ignores\n", encoding="utf-8")
    (project / ".cursorignore").write_text("# cursor ignores\n", encoding="utf-8")
    return project


def run_setup(project: Path, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "sh",
            str(project / "installer" / "setup.sh"),
            "--home",
            str(home),
            "--project-root",
            str(project),
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "CONTEXT_MCP_SKIP_RUNTIME": "1",
        },
    )


def run_manager(
    project: Path, home: Path, action: str, name: str | None = None
) -> subprocess.CompletedProcess[str]:
    command = [
        "python3",
        str(project / "installer" / "manage_extensions.py"),
        action,
    ]
    if name:
        command.append(name)
    command.extend(["--home", str(home), "--project-root", str(project)])
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
    )


def test_extension_catalog_matches_payloads() -> None:
    repository = Path(__file__).parents[1]
    catalog = json.loads((repository / "installer" / "extensions.json").read_text(encoding="utf-8"))
    names = {entry["name"] for entry in catalog["extensions"]}
    payload_names = {
        path.name
        for path in (repository / "installer" / "payload" / "extensions").iterdir()
        if path.is_dir()
    }

    assert names == payload_names
    for entry in catalog["extensions"]:
        for hook in entry["hooks"]:
            assert (
                repository
                / "installer"
                / "payload"
                / "extensions"
                / entry["name"]
                / ".cursor"
                / "hooks"
                / entry["name"]
                / hook["script"]
            ).is_file()


def test_setup_installs_core_and_reconciles_no_unregistered_payloads(tmp_path: Path) -> None:
    project = stage_repository(tmp_path)
    home = tmp_path / "home"

    run_setup(project, home)

    assert (home / "CORE" / "CONTEXT" / "overview.md").is_file()
    command = home / "CORE" / ".cursor" / "commands" / "CORE" / "context-search.md"
    skill = home / "CORE" / ".cursor" / "skills" / "CORE" / "context-search" / "SKILL.md"
    assert command.is_file()
    assert skill.is_file()
    assert "name: context-search" in command.read_text(encoding="utf-8")
    assert "context_status" in command.read_text(encoding="utf-8")
    assert "Use when" in skill.read_text(encoding="utf-8")
    assert "context_read" in skill.read_text(encoding="utf-8")
    assert (project / "CONTEXT").is_symlink()
    assert (project / ".cursor" / "hooks.json").is_symlink()
    assert (project / ".cursor" / "agents" / "CORE").is_symlink()
    assert not (project / ".cursor" / "agents" / "ext" / "QA").exists()

    run_setup(project, home)
    assert (project / ".cursor" / "hooks.json").is_symlink()


def test_setup_dry_run_does_not_create_targets(tmp_path: Path) -> None:
    project = stage_repository(tmp_path)
    home = tmp_path / "home"

    run_setup(project, home, "--dry-run")

    assert not (home / "CORE").exists()


def test_setup_synchronizes_core_in_place_and_preserves_extension_links(tmp_path: Path) -> None:
    project = stage_repository(tmp_path)
    home = tmp_path / "home"

    run_setup(project, home)
    core = home / "CORE"
    original_inode = core.stat().st_ino
    stale = core / "CONTEXT" / "stale-context.md"
    stale.write_text("# Stale\n", encoding="utf-8")
    extension_target = home / ".extensions" / "extensions" / "QA" / "CONTEXT"
    extension_target.mkdir(parents=True)
    extension_link = core / "CONTEXT" / "ext" / "QA"
    extension_link.parent.mkdir(parents=True, exist_ok=True)
    extension_link.symlink_to(extension_target, target_is_directory=True)

    run_setup(project, home)

    assert core.stat().st_ino == original_inode
    assert not stale.exists()
    assert extension_link.is_symlink()
    assert extension_link.resolve() == extension_target


def test_cursor_mcp_configuration_preserves_other_servers(tmp_path: Path) -> None:
    project = stage_repository(tmp_path)
    home = tmp_path / "home"
    mcp_path = home / ".cursor" / "mcp.json"
    mcp_path.parent.mkdir(parents=True)
    mcp_path.write_text(
        json.dumps({"mcpServers": {"other-server": {"url": "http://example.test/mcp"}}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(project / "installer" / "configure_cursor_mcp.py"),
            "--home",
            str(home),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    configured = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert result.stdout.strip() == str(mcp_path)
    assert configured["mcpServers"] == {
        "other-server": {"url": "http://example.test/mcp"},
        "core-context": {"url": "http://127.0.0.1:8989/mcp"},
    }


def test_docker_compose_exposes_local_http_service() -> None:
    repository = Path(__file__).parents[1]
    compose = (repository / "installer" / "docker" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    dockerfile = (repository / "installer" / "docker" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert 'restart: unless-stopped' in compose
    assert '"127.0.0.1:8989:8989"' in compose
    assert "MCP_PORT: \"8989\"" in compose
    assert "/ready" in compose
    assert "ENTRYPOINT [\"context-mcp\"]" in dockerfile


def test_install_updates_registry_links_ignores_hooks_and_index(tmp_path: Path) -> None:
    project = stage_repository(tmp_path)
    home = tmp_path / "home"
    run_setup(project, home)
    marker = home / "CORE" / "CONTEXT" / ".index-refresh"
    marker.unlink()

    run_manager(project, home, "install", "PRODUCT")

    registry = json.loads((home / ".extensions" / "extensions.json").read_text(encoding="utf-8"))
    assert registry["installed"] == ["PRODUCT"]
    assert (home / ".extensions" / "extensions" / "PRODUCT" / "CONTEXT").is_dir()
    assert (home / "CORE" / "CONTEXT" / "ext" / "PRODUCT").is_symlink()
    assert (project / ".cursor" / "agents" / "ext" / "PRODUCT").is_symlink()
    assert "cursor-symlink-ext-context-mcp:extension:PRODUCT:begin" in (
        project / ".gitignore"
    ).read_text(encoding="utf-8")
    assert "!.cursor/agents/ext/PRODUCT/**" in (project / ".cursorignore").read_text(
        encoding="utf-8"
    )
    hooks = json.loads((home / "CORE" / ".cursor" / "hooks.json").read_text())
    assert hooks["hooks"]["afterFileEdit"] == [
        {"command": ".cursor/hooks/ext/PRODUCT/after-file-edit.sh"}
    ]
    assert marker.is_file()

    run_setup(project, home)
    assert (project / ".cursor" / "agents" / "ext" / "PRODUCT").is_symlink()
    assert (home / "CORE" / "CONTEXT" / "ext" / "PRODUCT").is_symlink()


def test_uninstall_removes_runtime_state_but_preserves_payload(tmp_path: Path) -> None:
    project = stage_repository(tmp_path)
    home = tmp_path / "home"
    run_setup(project, home)
    run_manager(project, home, "install", "SUPPORT")
    marker = home / "CORE" / "CONTEXT" / ".index-refresh"
    marker.unlink()

    run_manager(project, home, "uninstall", "SUPPORT")

    registry = json.loads((home / ".extensions" / "extensions.json").read_text(encoding="utf-8"))
    assert registry["installed"] == []
    assert not (project / ".cursor" / "agents" / "ext" / "SUPPORT").exists()
    assert not (home / ".extensions" / "extensions" / "SUPPORT").exists()
    assert "cursor-symlink-ext-context-mcp:extension:SUPPORT" not in (
        project / ".gitignore"
    ).read_text(encoding="utf-8")
    assert "cursor-symlink-ext-context-mcp:extension:SUPPORT" not in (
        project / ".cursorignore"
    ).read_text(encoding="utf-8")
    hooks = json.loads((home / "CORE" / ".cursor" / "hooks.json").read_text())
    assert "afterFileEdit" not in hooks["hooks"]
    assert (project / "installer" / "payload" / "extensions" / "SUPPORT").is_dir()
    assert marker.is_file()


def test_update_only_copies_payloads_for_installed_extensions(tmp_path: Path) -> None:
    project = stage_repository(tmp_path)
    home = tmp_path / "home"
    run_setup(project, home)
    run_manager(project, home, "install", "QA")
    gitignore_before = (project / ".gitignore").read_text(encoding="utf-8")
    cursorignore_before = (project / ".cursorignore").read_text(encoding="utf-8")
    link_target_before = (project / ".cursor" / "agents" / "ext" / "QA").readlink()
    stale_context = home / ".extensions" / "extensions" / "QA" / "CONTEXT" / "obsolete.md"
    stale_context.write_text("# Obsolete\n", encoding="utf-8")

    payload_context = project / "installer" / "payload" / "extensions" / "QA" / "CONTEXT"
    (payload_context / "quality.md").write_text(
        "# QA Context\n\nCommitted payload update.\n",
        encoding="utf-8",
    )
    marker = home / "CORE" / "CONTEXT" / ".index-refresh"
    marker.unlink()
    run_manager(project, home, "update")

    installed_context = home / ".extensions" / "extensions" / "QA" / "CONTEXT" / "quality.md"
    assert "Committed payload update" in installed_context.read_text(encoding="utf-8")
    assert not stale_context.exists()
    assert (project / ".gitignore").read_text(encoding="utf-8") == gitignore_before
    assert (project / ".cursorignore").read_text(encoding="utf-8") == cursorignore_before
    assert (project / ".cursor" / "agents" / "ext" / "QA").readlink() == link_target_before
    registry = json.loads((home / ".extensions" / "extensions.json").read_text(encoding="utf-8"))
    assert registry["installed"] == ["QA"]
    assert marker.is_file()
