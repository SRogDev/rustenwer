"""ComputeProvider abstraction (plan §46).

A provider turns a validated run into a live execution. Phase 2 ships two:

- LocalComputeProvider — real: spawns the training runner as a local
  subprocess (CPU). Fully working, used by every local test.
- DigitalOceanComputeProvider — code-complete, NOT live-tested: provisions
  a GPU droplet via the DO API v2, bootstraps it with cloud-init (clones
  this repo, installs torch), runs the runner over SSH, ships events.jsonl
  back over SSH, and DESTROYS the droplet on stop (GPU droplets bill while
  powered off). Refuses to start without DO_TOKEN — no fake execution.

The manager only talks to the ComputeProvider protocol.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import UUID


class ProviderCredentialsError(RuntimeError):
    """The provider cannot run: credentials or environment missing."""


@dataclass
class ExecutionHandle:
    provider: str
    pid: int | None = None            # local subprocess
    droplet_id: int | None = None     # digitalocean
    ip: str | None = None             # digitalocean
    extra: dict = field(default_factory=dict)


class ComputeProvider(Protocol):
    """Machine-lifecycle contract. The manager owns run state; the
    provider owns the machine/process."""

    name: str

    def start(
        self,
        *,
        run_id: UUID,
        workdir: Path,
        command: list[str],
        env: dict[str, str],
    ) -> ExecutionHandle:
        """Launch execution of one attempt; return an opaque handle."""
        ...

    def stop(self, handle: ExecutionHandle, *, graceful: bool = True) -> None:
        """End execution. DigitalOcean MUST destroy the droplet here."""
        ...

    def poll(self, handle: ExecutionHandle) -> int | None:
        """Exit code, or None while still running."""
        ...

    def fetch_events(self, handle: ExecutionHandle, local_events: Path) -> None:
        """Ship remote progress into the local events.jsonl (no-op locally)."""
        ...


# --------------------------------------------------------------------------
# Local: real subprocess on this machine
# --------------------------------------------------------------------------


class LocalComputeProvider:
    """Runs the training runner as a local subprocess (CPU)."""

    name = "local"

    def __init__(self, *, api_root: Path | str, python_executable: str | None = None) -> None:
        import sys

        self._api_root = Path(api_root)
        self._python = python_executable or sys.executable
        self._procs: dict[int, subprocess.Popen] = {}

    def start(self, *, run_id: UUID, workdir: Path, command: list[str],
              env: dict[str, str]) -> ExecutionHandle:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        stdout_log = open(workdir / "stdout.log", "ab")  # noqa: PTH123
        merged_env = {**os.environ, **env}
        proc = subprocess.Popen(  # noqa: S603
            command,
            cwd=str(self._api_root),
            env=merged_env,
            stdout=stdout_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self._procs[proc.pid] = proc
        return ExecutionHandle(provider=self.name, pid=proc.pid)

    def stop(self, handle: ExecutionHandle, *, graceful: bool = True) -> None:
        if handle.pid is None:
            return
        try:
            if graceful:
                os.kill(handle.pid, signal.SIGTERM)
                if self._wait_exit(handle.pid, timeout=10.0):
                    return
            os.kill(handle.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def pause(self, handle: ExecutionHandle) -> None:
        """Ask the runner for a graceful pause (SIGUSR1)."""
        if handle.pid is None:
            return
        try:
            os.kill(handle.pid, signal.SIGUSR1)
        except (ProcessLookupError, PermissionError):
            pass

    def poll(self, handle: ExecutionHandle) -> int | None:
        proc = self._procs.get(handle.pid) if handle.pid else None
        if proc is None:
            return None
        code = proc.poll()
        if code is not None:
            self._procs.pop(handle.pid, None)  # type: ignore[arg-type]
        return code

    def fetch_events(self, handle: ExecutionHandle, local_events: Path) -> None:
        return None  # local runner writes events.jsonl directly

    def preflight(self) -> str | None:
        """Eager feasibility check; None when the provider can run."""
        return None

    def _wait_exit(self, pid: int, timeout: float) -> bool:
        # Reap via the Popen handle first: an exited-but-unreaped (zombie)
        # child still answers os.kill(pid, 0), which would burn the whole
        # timeout even though the process is already gone.
        proc = self._procs.get(pid)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if proc is not None and proc.poll() is not None:
                return True
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.1)
        return False


# --------------------------------------------------------------------------
# DigitalOcean: code-complete, credential-blocked (NOT live-tested)
# --------------------------------------------------------------------------

_DO_API = "https://api.digitalocean.com/v2"

_CLOUD_INIT = """\
#cloud-config
packages: [python3, python3-venv, python3-pip, git]
runcmd:
  - python3 -m pip install --upgrade pip
  - python3 -m pip install torch --index-url https://download.pytorch.org/whl/cu121
  - python3 -m pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
  - git clone --depth 1 --branch {git_ref} https://github.com/SRogDev/rustenwer /root/rustenwer
"""


class DigitalOceanComputeProvider:
    """GPU droplets via the DO API v2.

    Honest status: implemented against the public API v2 docs, NOT
    live-tested — no DO_TOKEN / GPU budget in this environment. start()
    refuses without credentials instead of faking anything.
    """

    name = "digitalocean"

    def __init__(
        self,
        *,
        token: str | None = None,
        region: str = "nyc3",
        size_slug: str = "gpu-rtx4000x1-20gb",
        image: str = "ubuntu-24-04-x64",
        ssh_key_ids: tuple[int, ...] = (),
        ssh_private_key: str | None = None,
        git_ref: str = "main",
    ) -> None:
        self._token = token
        self._region = region
        self._size_slug = size_slug
        self._image = image
        self._ssh_key_ids = list(ssh_key_ids)
        self._ssh_key = ssh_private_key
        self._git_ref = git_ref

    @classmethod
    def from_env(cls) -> DigitalOceanComputeProvider:
        key_ids = tuple(
            int(k) for k in os.environ.get("DO_SSH_KEY_IDS", "").split(",") if k.strip()
        )
        return cls(
            token=os.environ.get("DO_TOKEN"),
            region=os.environ.get("DO_REGION", "nyc3"),
            size_slug=os.environ.get("DO_GPU_SIZE", "gpu-rtx4000x1-20gb"),
            ssh_key_ids=key_ids,
            ssh_private_key=os.environ.get("DO_SSH_PRIVATE_KEY"),
            git_ref=os.environ.get("RUSTENWER_GIT_REF", "main"),
        )

    # -- ComputeProvider ---------------------------------------------------

    def preflight(self) -> str | None:
        """Refuse early (at enqueue) when credentials are missing.

        Nothing is provisioned and nothing is billed — the failure is
        honest and happens before a run row is even created.
        """
        if not self._token:
            return (
                "digitalocean provider needs DO_TOKEN (plus DO_SSH_KEY_IDS of an "
                "SSH key whose private half is in DO_SSH_PRIVATE_KEY). "
                "No droplet was created; nothing was billed."
            )
        if not self._ssh_key:
            return "digitalocean provider needs DO_SSH_PRIVATE_KEY to reach the droplet."
        return None

    def start(self, *, run_id: UUID, workdir: Path, command: list[str],
              env: dict[str, str]) -> ExecutionHandle:
        blocked = self.preflight()
        if blocked:
            raise ProviderCredentialsError(blocked)
        name = f"rustenwer-{run_id.hex[:12]}"
        droplet = self._api("POST", "/droplets", {
            "name": name,
            "region": self._region,
            "size": self._size_slug,
            "image": self._image,
            "ssh_keys": self._ssh_key_ids,
            "tags": ["rustenwer", f"run-{run_id.hex[:12]}"],
            "user_data": _CLOUD_INIT.format(git_ref=self._git_ref),
        })["droplet"]
        droplet_id = int(droplet["id"])
        ip = self._wait_for_ip(droplet_id, timeout=600)
        handle = ExecutionHandle(
            provider=self.name, droplet_id=droplet_id, ip=ip,
            extra={"fetched_bytes": 0},
        )
        remote = "/root/rustenwer-run"
        self._ssh(ip, f"mkdir -p {remote} && rm -f {remote}/events.jsonl")
        strategy_src = Path(workdir) / "strategy.json"
        self._scp(str(strategy_src), f"root@{ip}:{remote}/strategy.json")
        # Launch the runner detached; it writes events.jsonl + final.json.
        self._ssh(
            ip,
            f"cd /root/rustenwer/api && nohup python3 -m app.training.runner "
            f"--attempt-dir {remote} >{remote}/stdout.log 2>&1 & echo $!",
        )
        return handle

    def stop(self, handle: ExecutionHandle, *, graceful: bool = True) -> None:
        # GPU droplets bill while powered off: ALWAYS destroy, never just stop.
        if handle.droplet_id is None or not self._token:
            return
        try:
            self._api("DELETE", f"/droplets/{handle.droplet_id}", None)
        except Exception:  # noqa: BLE001 — teardown must never raise
            pass

    def poll(self, handle: ExecutionHandle) -> int | None:
        if handle.droplet_id is None or handle.ip is None:
            return None
        out = self._ssh(
            handle.ip, "test -f /root/rustenwer-run/final.json && echo done || echo run",
            check=False,
        )
        if out.strip() != "done":
            return None
        final_raw = self._ssh(handle.ip, "cat /root/rustenwer-run/final.json", check=False)
        try:
            status = json.loads(final_raw).get("status")
        except (json.JSONDecodeError, ValueError):
            status = None
        return 0 if status == "COMPLETED" else 1

    def fetch_events(self, handle: ExecutionHandle, local_events: Path) -> None:
        if handle.ip is None:
            return
        out = self._ssh(handle.ip, "cat /root/rustenwer-run/events.jsonl", check=False)
        if not out:
            return
        data = out.encode()
        seen = int(handle.extra.get("fetched_bytes", 0))
        new = data[seen:]
        if new:
            with open(local_events, "ab") as fh:
                fh.write(new)
            handle.extra["fetched_bytes"] = seen + len(new)

    # -- internals ----------------------------------------------------------

    def _api(self, method: str, path: str, payload: dict | None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            _DO_API + path, data=body, method=method,
            headers={"Authorization": f"Bearer {self._token}",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:500]
            raise ProviderCredentialsError(
                f"DigitalOcean API {method} {path} failed: {exc.code} {detail}"
            ) from exc

    def _wait_for_ip(self, droplet_id: int, timeout: float) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            droplet = self._api("GET", f"/droplets/{droplet_id}", None)["droplet"]
            nets = droplet.get("networks", {}).get("v4", [])
            public = [n["ip_address"] for n in nets if n.get("type") == "public"]
            if droplet.get("status") == "active" and public:
                time.sleep(20)  # let cloud-init start before SSH
                return public[0]
            time.sleep(10)
        raise ProviderCredentialsError(
            f"droplet {droplet_id} never became active; destroying it."
        )

    def _ssh(self, ip: str, remote_cmd: str, *, check: bool = True) -> str:
        cmd = ["ssh", "-i", self._ssh_key, "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=accept-new",
               "-o", "ConnectTimeout=15", f"root@{ip}", remote_cmd]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # noqa: S603
        if check and proc.returncode != 0:
            raise ProviderCredentialsError(f"SSH to {ip} failed: {proc.stderr[:300]}")
        return proc.stdout

    def _scp(self, src: str, dst: str) -> None:
        cmd = ["scp", "-i", self._ssh_key, "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=accept-new", src, dst]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # noqa: S603
        if proc.returncode != 0:
            raise ProviderCredentialsError(f"SCP to {dst} failed: {proc.stderr[:300]}")
