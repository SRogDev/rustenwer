"""Immutable, versioned artifact store (plan §43).

Artifacts are content blobs produced by training runs (model weights,
configs, exported bundles). Each publish creates a NEW immutable version
under `root/{name}/v{n}/payload`; the sha256 recorded at publish time is
re-verified on every read, so tampering is detected, not silently served.

A JSONL registry (`root/registry.jsonl`) makes the store crash-safe and
re-openable without a database.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from shared.domain import ArtifactRecord


class ArtifactNotFoundError(KeyError):
    """No such artifact name/version in the store."""


class ArtifactCorruptedError(ValueError):
    """Payload bytes no longer match the sha256 recorded at publish time."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ArtifactStore:
    """Storage contract for versioned artifacts (plan §43)."""

    def publish(self, name: str, src: Path, run_id: UUID) -> ArtifactRecord:
        """Persist `src` as a new immutable version of `name`."""
        raise NotImplementedError

    def get(self, name: str, version: int) -> Path:
        """Path to the verified payload; raises on missing/corrupt."""
        raise NotImplementedError

    def list(self, name: str | None = None) -> list[ArtifactRecord]:
        """All records, optionally filtered by name, oldest first."""
        raise NotImplementedError


class LocalArtifactStore(ArtifactStore):
    """Filesystem artifact store: `root/{name}/v{n}/payload` + JSONL registry."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._registry = self._root / "registry.jsonl"
        self._registry.touch(exist_ok=True)

    # -- writes ---------------------------------------------------------

    def publish(self, name: str, src: Path, run_id: UUID) -> ArtifactRecord:
        src = Path(src)
        if not src.is_file():
            raise FileNotFoundError(f"artifact source not found: {src}")
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            raise ValueError(f"invalid artifact name: {name!r}")

        version = self._next_version(name)
        dest_dir = self._root / name / f"v{version}"
        dest_dir.mkdir(parents=True, exist_ok=False)  # fail loudly on collision
        dest = dest_dir / "payload"

        digest = _sha256(src)
        # Atomic install: copy to tmp, then rename into place.
        fd, tmp_name = tempfile.mkstemp(dir=str(dest_dir))
        try:
            with os.fdopen(fd, "wb") as out, open(src, "rb") as fh:
                shutil.copyfileobj(fh, out)
            os.replace(tmp_name, dest)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

        record = ArtifactRecord(
            name=name,
            version=version,
            sha256=digest,
            bytes=dest.stat().st_size,
            created_at=_utc_now(),
        )
        with open(self._registry, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({**record.model_dump(), "run_id": str(run_id)}) + "\n")
        return record

    # -- reads ----------------------------------------------------------

    def get(self, name: str, version: int) -> Path:
        payload = self._root / name / f"v{version}" / "payload"
        if not payload.is_file():
            raise ArtifactNotFoundError(f"artifact {name} v{version} not found")
        record = self._find(name, version)
        if record is None:
            raise ArtifactNotFoundError(f"artifact {name} v{version} not in registry")
        if _sha256(payload) != record.sha256:
            raise ArtifactCorruptedError(
                f"artifact {name} v{version} failed sha256 verification"
            )
        return payload

    def list(self, name: str | None = None) -> list[ArtifactRecord]:
        records = [self._record_from_line(line) for line in self._read_registry()]
        records = [r for r in records if r is not None]
        if name is not None:
            records = [r for r in records if r.name == name]
        return sorted(records, key=lambda r: (r.name, r.version))

    # -- internals ------------------------------------------------------

    def _next_version(self, name: str) -> int:
        versions = [r.version for r in self.list(name)]
        return (max(versions) + 1) if versions else 1

    def _read_registry(self) -> list[str]:
        with open(self._registry, encoding="utf-8") as fh:
            return [line for line in fh.read().splitlines() if line.strip()]

    def _record_from_line(self, line: str) -> ArtifactRecord | None:
        try:
            data = json.loads(line)
            return ArtifactRecord(
                name=data["name"],
                version=int(data["version"]),
                sha256=data["sha256"],
                bytes=int(data["bytes"]),
                created_at=data["created_at"],
            )
        except (KeyError, ValueError, TypeError):
            return None

    def _find(self, name: str, version: int) -> ArtifactRecord | None:
        for record in self.list(name):
            if record.version == version:
                return record
        return None
