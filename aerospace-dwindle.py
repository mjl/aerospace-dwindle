#!/usr/bin/env python3
"""Dwindle-like auto-split daemon for AeroSpace.

Listens to `aerospace subscribe window-detected` and, for each new window,
issues `aerospace split horizontal|vertical` along the window's longer edge,
so the next new window splits it in half (Hyprland "dwindle" style).

Only new windows are touched. Reacting to every focus change also fired when
a window closed and focus jumped to a neighbour whose frame was still stale,
which re-split the tree and shuffled windows. Pass --on-focus to get the old
behaviour (re-split whatever window you focus).

Requires:
  pip3 install --user pyobjc-framework-Quartz
  ~/.aerospace.toml:
    enable-normalization-flatten-containers = false
    after-startup-command = ['exec-and-forget exec python3 ~/bin/aerospace-dwindle.py']
"""
import json
import os
import shutil
import subprocess
import sys
import time

from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionIncludingWindow

# GUI-launched processes get a minimal PATH, so look in the usual places too.
# Override with AEROSPACE_CLI=/path/to/aerospace if it lives elsewhere.
AEROSPACE = next(
    (p for p in (
        os.environ.get("AEROSPACE_CLI"),
        shutil.which("aerospace"),
        os.path.expanduser("~/bin/aerospace"),
        "/usr/local/bin/aerospace",       # Intel Homebrew
        "/opt/homebrew/bin/aerospace",    # Apple Silicon Homebrew
    ) if p and os.path.isfile(p)),
    None,
)
if AEROSPACE is None:
    sys.exit("aerospace CLI not found; install it to /usr/local/bin or set AEROSPACE_CLI")

SETTLE_STEP = 0.02   # seconds between frame polls
SETTLE_TRIES = 8     # max ~160 ms waiting for a new window's frame to settle


def size(wid):
    info = CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, wid)
    if not info:
        return None
    b = info[0]["kCGWindowBounds"]
    return b["Width"], b["Height"]


def settled_size(wid):
    prev = size(wid)
    for _ in range(SETTLE_TRIES):
        time.sleep(SETTLE_STEP)
        cur = size(wid)
        if cur == prev:
            return cur
        prev = cur
    return prev


def refresh():
    """Poke AeroSpace so it notices closed windows and re-tiles right away.

    Any CLI command makes the server refresh its model. If holes still linger
    after closing windows, this is the knob to change.
    """
    time.sleep(0.05)  # let macOS finish destroying the closed window
    subprocess.run(
        [AEROSPACE, "list-windows", "--focused"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    on_focus = "--on-focus" in sys.argv[1:]
    proc = subprocess.Popen(
        [AEROSPACE, "subscribe", "--no-send-initial", "window-detected", "focus-changed"],
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        wid = ev.get("windowId")
        if ev.get("_event") == "focus-changed" and not on_focus:
            refresh()
            continue
        if not wid:
            continue
        s = settled_size(wid)
        if not s:
            continue
        w, h = s
        direction = "horizontal" if w >= h else "vertical"
        subprocess.run(
            [AEROSPACE, "split", "--window-id", str(wid), direction],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return proc.wait()


if __name__ == "__main__":
    sys.exit(main())
