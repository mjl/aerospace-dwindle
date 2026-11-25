# Copyright (c) 2026, Martin J. Laubach
# SPDX-License-Identifier: BSD-3-Clause
"""AeroSpace CLI access: discovery, version check, subscribe stream, commands."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from typing import Callable, List, Mapping, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

# `aerospace subscribe` was added in 0.21.0-Beta.
MIN_VERSION: Tuple[int, int, int] = (0, 21, 0)

# Runs argv, returns (exit code, stdout). Injectable for tests.
Runner = Callable[[Sequence[str]], Tuple[int, str]]


class VersionError(RuntimeError):
    pass


def _is_app_bundle_binary(path: str) -> bool:
    # /Applications/AeroSpace.app/Contents/MacOS/aerospace resolves (case-
    # insensitive FS) to the *server* binary `AeroSpace`: it answers --version
    # but rejects `subscribe` with "Unrecognized flag". The real CLI ships
    # separately (release zip bin/, or Homebrew's bin dir).
    return "/Contents/MacOS/" in os.path.abspath(path)


def find_cli(explicit: Optional[str] = None, env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Locate the aerospace CLI; absolute path or None.

    An explicit path is used as-is (None if it isn't a file). Otherwise:
    $AEROSPACE_CLI, PATH, ~/bin, Intel and Apple Silicon Homebrew. The fixed
    locations matter because GUI-launched processes (AeroSpace's
    exec-and-forget) get a minimal PATH.
    """
    env = os.environ if env is None else env
    if explicit:
        candidates: List[Optional[str]] = [explicit]
    else:
        candidates = [
            env.get("AEROSPACE_CLI"),
            shutil.which("aerospace", path=env.get("PATH")),
            os.path.expanduser("~/bin/aerospace"),
            "/usr/local/bin/aerospace",  # Intel Homebrew
            "/opt/homebrew/bin/aerospace",  # Apple Silicon Homebrew
        ]
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        if _is_app_bundle_binary(path):
            log.warning("ignoring %s: that is the AeroSpace server binary, not the CLI", path)
            continue
        return os.path.abspath(path)
    return None


def parse_versions(text: str) -> List[Tuple[int, int, int]]:
    """All x.y.z versions in `aerospace --version` output (client and server)."""
    return [tuple(map(int, m)) for m in re.findall(r"(\d+)\.(\d+)\.(\d+)", text)]  # type: ignore[misc]


def check_version(text: str) -> None:
    """Raise VersionError if any reported version is older than MIN_VERSION.

    Unparseable output only logs a warning: better to try than refuse to run.
    """
    versions = parse_versions(text)
    if not versions:
        log.warning("could not parse aerospace version from %r; continuing", text.strip())
        return
    oldest = min(versions)
    if oldest < MIN_VERSION:
        need = ".".join(map(str, MIN_VERSION))
        raise VersionError(
            f"AeroSpace {'.'.join(map(str, oldest))} is too old; "
            f"need >= {need} for `aerospace subscribe`"
        )


def run_command(argv: Sequence[str]) -> Tuple[int, str]:
    """Default runner: run a CLI command, log failures, never raise."""
    try:
        r = subprocess.run(list(argv), capture_output=True, text=True)
    except OSError as e:
        log.error("cannot run %s: %s", argv[0], e)
        return 127, ""
    if r.returncode:
        # Expected now and then, e.g. split on a dialog/floating window.
        log.debug("%s exited %d: %s", " ".join(argv[1:]), r.returncode, r.stderr.strip())
    return r.returncode, r.stdout


class AeroSpace:
    def __init__(self, cli: str, runner: Runner = run_command):
        self.cli = cli
        self._run = runner

    def version_output(self, timeout: float = 5.0) -> str:
        try:
            r = subprocess.run(
                [self.cli, "--version"], capture_output=True, text=True, timeout=timeout
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("`%s --version` failed: %s", self.cli, e)
            return ""
        return r.stdout + r.stderr

    def split(self, wid: int, orientation: str) -> int:
        # Always explicit horizontal/vertical, never `opposite`: that is not
        # idempotent if a window gets split twice.
        return self._run([self.cli, "split", "--window-id", str(wid), orientation])[0]

    def refresh(self) -> int:
        """Poke the server: any CLI command makes AeroSpace refresh its model,
        so it notices closed windows and re-tiles instead of leaving a hole."""
        return self._run([self.cli, "list-windows", "--focused"])[0]

    def windows(self, workspace: str) -> Optional[List[Tuple[int, str]]]:
        """(window id, parent container layout) of all windows on `workspace`,
        None if the query failed. Layout is e.g. h_tiles, v_accordion, floating.
        Like any command, this also pokes the server to refresh (see refresh)."""
        rc, out = self._run(
            [
                self.cli, "list-windows", "--workspace", workspace,
                "--format", "%{window-id}|%{window-parent-container-layout}",
            ]
        )
        if rc:
            return None
        result = []
        for line in out.splitlines():
            wid, _, layout = line.strip().partition("|")
            if wid.isdigit():
                result.append((int(wid), layout))
        return result

    def workspace_monitor(self, workspace: str) -> Optional[int]:
        """AeroSpace monitor id (1-based, monitors ordered left to right)."""
        rc, out = self._run(
            [self.cli, "list-workspaces", "--all", "--format", "%{workspace}|%{monitor-id}"]
        )
        if rc:
            return None
        for line in out.splitlines():
            name, _, mid = line.strip().rpartition("|")
            if name == workspace and mid.isdigit():
                return int(mid)
        return None

    def flatten(self, workspace: str) -> int:
        return self._run([self.cli, "flatten-workspace-tree", "--workspace", workspace])[0]

    def set_root_orientation(self, workspace: str, orientation: str) -> int:
        # horizontal|vertical keeps the root's tiles/accordion layout.
        return self._run(
            [self.cli, "layout", "--workspace", workspace, "--root", orientation]
        )[0]

    def subscribe(self, events: Sequence[str]) -> "subprocess.Popen[str]":
        return subprocess.Popen(
            [self.cli, "subscribe", "--no-send-initial", *events],
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
