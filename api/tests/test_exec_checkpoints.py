"""Checkpoint tests (TDD: RED first, then implement).

Contract under test:
  save_checkpoint(state, path) -> atomic write (tmp + rename; no partial files)
  load_checkpoint(path) -> round-trips the state dict
  latest_checkpoint(dir) -> newest ckpt by epoch (None when empty)
  list_checkpoints(dir) -> CheckpointInfo list sorted by epoch
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shared.domain import CheckpointInfo

from app.training.checkpoints import (
    latest_checkpoint,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)


def _state(epoch: int = 2, step: int = 40) -> dict:
    return {
        "epoch": epoch,
        "step": step,
        "model": {"w": [1.0, 2.0, 3.0]},
        "optimizer": {"lr": 0.05},
    }


def test_save_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "ckpt-0002.pt"
    save_checkpoint(_state(), path)
    loaded = load_checkpoint(path)
    assert loaded["epoch"] == 2
    assert loaded["step"] == 40
    assert loaded["model"] == {"w": [1.0, 2.0, 3.0]}


def test_save_is_atomic_no_tmp_leftovers(tmp_path: Path) -> None:
    path = tmp_path / "ckpt-0001.pt"
    save_checkpoint(_state(), path)
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp" or ".tmp" in p.name]
    assert leftovers == []
    assert path.exists()
    # The file must be complete and loadable (no torn writes).
    assert load_checkpoint(path)["epoch"] == 2


def test_save_overwrites_atomically(tmp_path: Path) -> None:
    path = tmp_path / "ckpt-0001.pt"
    save_checkpoint(_state(epoch=1), path)
    save_checkpoint(_state(epoch=2), path)
    assert load_checkpoint(path)["epoch"] == 2


def test_load_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_checkpoint(tmp_path / "nope.pt")


def test_latest_checkpoint_picks_highest_epoch(tmp_path: Path) -> None:
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    save_checkpoint(_state(epoch=1), ckpt_dir / "ckpt-0001.pt")
    save_checkpoint(_state(epoch=3), ckpt_dir / "ckpt-0003.pt")
    save_checkpoint(_state(epoch=2), ckpt_dir / "ckpt-0002.pt")
    latest = latest_checkpoint(ckpt_dir)
    assert latest is not None
    assert latest.name == "ckpt-0003.pt"


def test_latest_checkpoint_empty_dir(tmp_path: Path) -> None:
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    assert latest_checkpoint(ckpt_dir) is None
    assert latest_checkpoint(tmp_path / "missing") is None


def test_list_checkpoints_sorted(tmp_path: Path) -> None:
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    save_checkpoint(_state(epoch=2, step=40), ckpt_dir / "ckpt-0002.pt")
    save_checkpoint(_state(epoch=1, step=20), ckpt_dir / "ckpt-0001.pt")
    infos = list_checkpoints(ckpt_dir)
    assert [i.epoch for i in infos] == [1, 2]
    assert all(isinstance(i, CheckpointInfo) for i in infos)
    assert infos[0].id == "ckpt-0001"
    assert infos[0].step == 20
    assert infos[0].bytes > 0
