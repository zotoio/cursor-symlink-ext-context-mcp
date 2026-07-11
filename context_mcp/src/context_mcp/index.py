"""Persistent, incrementally refreshed Markdown embedding index."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


class Embedder(Protocol):
    def encode(self, sentences: list[str], *, normalize_embeddings: bool) -> object: ...


@dataclass(frozen=True)
class ContextDocument:
    path: str
    source: str
    title: str
    text: str
    mtime_ns: int
    embedding: list[float]


class ContextIndex:
    """Indexes CORE and extension Markdown, embedding only changed files."""

    def __init__(
        self,
        core_context: Path,
        state_path: Path,
        model_name: str = "all-MiniLM-L6-v2",
        embedder: Embedder | None = None,
    ) -> None:
        self.core_context = core_context.expanduser()
        self.state_path = state_path.expanduser()
        self.model_name = model_name
        self._embedder = embedder
        self._documents: dict[str, ContextDocument] = {}
        self._lock = threading.RLock()
        self._load()

    def _model(self) -> Embedder:
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(self.model_name)
        return self._embedder

    def _roots(self) -> Iterable[tuple[str, Path]]:
        yield "CORE", self.core_context
        extensions = self.core_context / "ext"
        if extensions.is_dir():
            for extension in sorted(extensions.iterdir()):
                if extension.is_dir():
                    yield extension.name, extension

    @staticmethod
    def _title(text: str, fallback: str) -> str:
        for line in text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return fallback

    def _scan(self) -> dict[str, tuple[str, Path, int, str]]:
        found: dict[str, tuple[str, Path, int, str]] = {}
        for source, root in self._roots():
            if not root.is_dir():
                continue
            for path in root.rglob("*.md"):
                if any(part.startswith(".") for part in path.relative_to(root).parts):
                    continue
                stat = path.stat()
                text = path.read_text(encoding="utf-8")
                found[str(path)] = (source, path, stat.st_mtime_ns, text)
        return found

    def sync(self) -> None:
        """Apply additions, edits, and deletions to the persisted index."""
        with self._lock:
            scanned = self._scan()
            changed = [
                item
                for path, item in scanned.items()
                if path not in self._documents or self._documents[path].mtime_ns != item[2]
            ]
            if not changed and set(scanned) == set(self._documents):
                return

            if changed:
                vectors = self._model().encode(
                    [item[3] for item in changed], normalize_embeddings=True
                )
                for (source, path, mtime_ns, text), vector in zip(changed, vectors, strict=True):
                    self._documents[str(path)] = ContextDocument(
                        path=str(path),
                        source=source,
                        title=self._title(text, path.stem),
                        text=text,
                        mtime_ns=mtime_ns,
                        embedding=[float(value) for value in vector],
                    )

            for path in set(self._documents) - set(scanned):
                del self._documents[path]
            self._save()

    def _load(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._documents = {
                item["path"]: ContextDocument(**item) for item in payload.get("documents", [])
            }
        except (OSError, TypeError, ValueError):
            self._documents = {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model_name,
            "documents": [asdict(doc) for doc in self._documents.values()],
        }
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self.state_path)

    def search(
        self, query: str, limit: int = 5, source: str | None = None
    ) -> list[dict[str, object]]:
        self.sync()
        if not query.strip():
            return []
        vector = [
            float(value) for value in self._model().encode([query], normalize_embeddings=True)[0]
        ]
        with self._lock:
            matches = [
                (
                    sum(
                        left * right for left, right in zip(vector, document.embedding, strict=True)
                    ),
                    document,
                )
                for document in self._documents.values()
                if source is None or document.source.lower() == source.lower()
            ]
        matches.sort(key=lambda match: match[0], reverse=True)
        return [
            {
                "path": document.path,
                "source": document.source,
                "title": document.title,
                "score": round(score, 4),
                "snippet": document.text[:500],
            }
            for score, document in matches[: max(1, min(limit, 20))]
        ]

    def read(self, path: str) -> dict[str, str]:
        self.sync()
        with self._lock:
            document = self._documents.get(path)
        if document is None:
            raise ValueError("The requested path is not an indexed context document.")
        return {"path": document.path, "source": document.source, "content": document.text}

    def stats(self) -> dict[str, object]:
        self.sync()
        with self._lock:
            sources = sorted({document.source for document in self._documents.values()})
            return {"documents": len(self._documents), "sources": sources, "model": self.model_name}
