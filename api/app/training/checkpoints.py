"""Atomic checkpoint write/read/list (Phase 2).

Checkpoints are torch state dicts written atomically: serialize to a temp
file in the same directory, fsync, then os.replace. A crashed writer can
never leave a torn checkpoint behind.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from shared.domain import CheckpointInfo


def _torch():
    """Import torch lazily so importing this module never pays the import cost."""
    import torch

    return torch


def save_checkpoint(state: dict[str, Any], path: Path) -> None:
    """Atomically persist a checkpoint state dict.

    `state` must carry integer `epoch` and `step` keys (used by the
    registry listing). Raises FileNotFoundError if the parent dir is missing.
    """
    torch = _torch()
    path = Path(path)
    if not path.parent.exists():
        raise FileNotFoundError(f"checkpoint dir does not exist: {path.parent}")
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            torch.save(state, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_checkpoint(path: Path) -> dict[str, Any]:
    """Load a checkpoint state dict; FileNotFoundError when missing."""
    torch = _torch()
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"checkpoint not found: {path}")
    state = torch.load(str(path), map_location="cpu", weights_only=True)
    if not isinstance(state, dict):
        raise ValueError(f"checkpoint {path} does not contain a state dict")
    return state


def _iter_checkpoint_files(checkpoints_dir: Path) -> list[Path]:
    d = Path(checkpoints_dir)
    if not d.is_dir():
        return []
    return sorted(d.glob("ckpt-*.pt"))


def latest_checkpoint(checkpoints_dir: Path) -> Path | None:
    """Newest checkpoint by epoch (ties broken by filename); None when empty."""
    best: Path | None = None
    best_epoch = -1
    for path in _iter_checkpoint_files(checkpoints_dir):
        try:
            epoch = int(load_checkpoint(path).get("epoch", -1))
        except Exception:  # corrupt file: skip, never crash the listing
            continue
        if epoch > best_epoch or (epoch == best_epoch and (best is None or path.name > best.name)):
            best, best_epoch = path, epoch
    return best


def list_checkpoints(checkpoints_dir: Path) -> list[CheckpointInfo]:
    """CheckpointInfo list sorted by epoch ascending; corrupt files skipped."""
    infos: list[CheckpointInfo] = []
    for path in _iter_checkpoint_files(checkpoints_dir):
        try:
            state = load_checkpoint(path)
        except Exception:
            continue
        stat = path.stat()
        infos.append(
            CheckpointInfo(
                id=path.stem,  # 'ckpt-0003'
                epoch=int(state.get("epoch", 0)),
                step=int(state.get("step", 0)),
                bytes=stat.st_size,
                created_at=_iso(stat.st_mtime),
            )
        )
    return sorted(infos, key=lambda i: (i.epoch, i.id))


def _iso(ts: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts, UTC).isoformat()
