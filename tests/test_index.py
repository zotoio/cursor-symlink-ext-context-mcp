from __future__ import annotations

from pathlib import Path

from context_mcp.index import ContextIndex


class FakeEmbedder:
    def encode(self, sentences: list[str], *, normalize_embeddings: bool) -> list[list[float]]:
        vectors: list[list[float]] = []
        for sentence in sentences:
            lower = sentence.lower()
            vectors.append(
                [
                    float(lower.count("quality") + lower.count("test")),
                    float(lower.count("product") + lower.count("requirement")),
                ]
            )
        return vectors


def test_semantic_search_indexes_core_and_extension(tmp_path: Path) -> None:
    home = tmp_path / "home"
    core = home / "CORE" / "CONTEXT"
    installed_extension = home / ".extensions" / "extensions" / "QA" / "CONTEXT"
    installed_extension.mkdir(parents=True)
    extension = core / "ext" / "QA"
    extension.parent.mkdir(parents=True)
    extension.symlink_to(installed_extension, target_is_directory=True)
    (core / "overview.md").write_text("# Core\nShared architecture context.", encoding="utf-8")
    (installed_extension / "quality.md").write_text(
        "# Installed quality\nTest quality and boundary coverage.", encoding="utf-8"
    )
    payload = tmp_path / "installer" / "payload" / "extensions" / "QA" / "CONTEXT"
    payload.mkdir(parents=True)
    (payload / "quality.md").write_text("# Payload quality\nDo not index.", encoding="utf-8")

    index = ContextIndex(core, tmp_path / "state.json", embedder=FakeEmbedder())

    hits = index.search("quality tests")

    assert hits[0]["source"] == "QA"
    assert hits[0]["title"] == "Installed quality"
    assert hits[0]["path"] == str(extension / "quality.md")
    assert str(payload) not in hits[0]["path"]
    assert index.search("quality tests", source="qa")[0]["source"] == "QA"
    assert index.search("quality tests", source="PRODUCT") == []
    assert index.read(str(extension / "quality.md"))["content"].startswith("# Installed")


def test_sync_reembeds_edits_and_removes_deleted_files(tmp_path: Path) -> None:
    core = tmp_path / "CORE" / "CONTEXT"
    core.mkdir(parents=True)
    document = core / "overview.md"
    document.write_text("# Core\nArchitecture.", encoding="utf-8")
    index = ContextIndex(core, tmp_path / "state.json", embedder=FakeEmbedder())

    assert index.stats()["documents"] == 1
    document.write_text("# Core\nQuality testing.", encoding="utf-8")
    assert index.search("quality")[0]["score"] > 0
    document.unlink()
    assert index.stats()["documents"] == 0
