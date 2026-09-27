"""Artifact store tests (TDD: RED first, then implement).

Contract under test (plan §43: immutable, versioned artifacts):
  publish(name, src, run_id) -> ArtifactRecord (version auto-increments per name)
  get(name, version) -> Path (sha256-verified; tampering raises)
  list(name?) -> records
  Re-publishing identical bytes still creates a new version (immutability).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from shared.domain import ArtifactRecord

from app.training.artifacts import (
    ArtifactCorruptedError,
    ArtifactNotFoundError,
    LocalArtifactStore,
)


@pytest.fixture
def store(tmp_path: Path) -> LocalArtifactStore:
    return LocalArtifactStore(tmp_path / "artifacts")


def _src(tmp_path: Path, content: bytes = b"model-bytes") -> Path:
    p = tmp_path / "model.pt"
    p.write_bytes(content)
    return p


def test_publish_assigns_versions(store: LocalArtifactStore, tmp_path: Path) -> None:
    run_id = uuid4()
    r1 = store.publish("model", _src(tmp_path, b"v1"), run_id)
    r2 = store.publish("model", _src(tmp_path, b"v2"), run_id)
    assert isinstance(r1, ArtifactRecord)
    assert (r1.version, r2.version) == (1, 2)
    assert r1.sha256 != r2.sha256
    assert r1.bytes == 2


def test_publish_is_content_versioned_not_deduped(
    store: LocalArtifactStore, tmp_path: Path
) -> None:
    run_id = uuid4()
    r1 = store.publish("model", _src(tmp_path), run_id)
    r2 = store.publish("model", _src(tmp_path), run_id)  # identical bytes
    assert r2.version == r1.version + 1  # new immutable version, not dedup


def test_get_returns_verified_path(store: LocalArtifactStore, tmp_path: Path) -> None:
    run_id = uuid4()
    rec = store.publish("model", _src(tmp_path, b"hello"), run_id)
    path = store.get("model", 1)
    assert path.read_bytes() == b"hello"
    assert rec.bytes == 5


def test_get_detects_tampering(store: LocalArtifactStore, tmp_path: Path) -> None:
    run_id = uuid4()
    store.publish("model", _src(tmp_path, b"hello"), run_id)
    payload = store.get("model", 1)
    payload.write_bytes(b"tampered!")
    with pytest.raises(ArtifactCorruptedError):
        store.get("model", 1)


def test_get_missing_raises(store: LocalArtifactStore) -> None:
    with pytest.raises(ArtifactNotFoundError):
        store.get("model", 1)
    with pytest.raises(ArtifactNotFoundError):
        store.get("nope", 1)


def test_publish_missing_src_raises(store: LocalArtifactStore, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        store.publish("model", tmp_path / "missing.pt", uuid4())


def test_list_filters_by_name(store: LocalArtifactStore, tmp_path: Path) -> None:
    run_id = uuid4()
    store.publish("model", _src(tmp_path, b"a"), run_id)
    store.publish("config", _src(tmp_path, b"b"), run_id)
    assert len(store.list("model")) == 1
    assert len(store.list()) == 2


def test_registry_survives_reopen(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    s1 = LocalArtifactStore(root)
    s1.publish("model", _src(tmp_path, b"abc"), uuid4())
    s2 = LocalArtifactStore(root)  # "process restart"
    assert len(s2.list("model")) == 1
    assert s2.get("model", 1).read_bytes() == b"abc"
