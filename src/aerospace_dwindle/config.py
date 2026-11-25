# Copyright (c) 2026, Martin J. Laubach
# SPDX-License-Identifier: BSD-3-Clause
"""Render the ~/.aerospace.toml snippet that launches the daemon.

Most setup pain was paths, so everything is resolved to absolute paths here.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from typing import List, Optional, Sequence

DEFAULT_LOG = "/tmp/aerospace-dwindle.log"


def self_command() -> List[str]:
    """Absolute argv that starts this daemon.

    Prefer the console script next to the running interpreter (venv bin/);
    sys.executable is deliberately not resolved so a venv python symlink keeps
    pointing into the venv. Fallback: `python -m aerospace_dwindle`.
    """
    script = os.path.join(os.path.dirname(sys.executable), "aerospace-dwindle")
    if os.path.isfile(script) and os.access(script, os.X_OK):
        return [script]
    return [sys.executable, "-m", "aerospace_dwindle"]


def _toml_string(s: str) -> str:
    # JSON string escaping is a subset of TOML basic-string escaping. A TOML
    # literal ('...') string can't be used: shlex.quote emits single quotes.
    return json.dumps(s, ensure_ascii=False)


def render(command: Sequence[str], aerospace_cli: Optional[str], log_file: str = DEFAULT_LOG) -> str:
    argv = list(command)
    if aerospace_cli:
        argv += ["--aerospace-cli", aerospace_cli]
    # exec-and-forget runs `/bin/bash -c '<string>'` and discards output:
    # - `exec` replaces bash, so no lingering bash parent ("two instances")
    # - shell redirect (not --log-file) so even startup tracebacks are logged
    shell = "exec " + shlex.join(argv) + " >>" + shlex.quote(log_file) + " 2>&1"
    lines = [
        "# Add to ~/.aerospace.toml. These are top-level keys: put them BEFORE",
        "# any [table] header, or TOML assigns them to that table.",
        "# Needs AeroSpace >= 0.21.0. after-startup-command runs only when",
        "# AeroSpace starts (not on reload-config): restart AeroSpace to apply.",
    ]
    if not aerospace_cli:
        lines.append(
            "# WARNING: aerospace CLI not found; add --aerospace-cli /abs/path/aerospace"
        )
    lines += [
        "",
        "# mandatory: split is a no-op while flattening is on",
        "enable-normalization-flatten-containers = false",
        "after-startup-command = [",
        f"  {_toml_string('exec-and-forget ' + shell)},",
        "]",
    ]
    return "\n".join(lines) + "\n"
