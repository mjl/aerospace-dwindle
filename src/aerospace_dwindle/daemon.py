"""Event handling: turn AeroSpace events into split / layout commands.

Dwindle emulation: when a window appears, `split` it along its longer edge.
That wraps it in its own container with that orientation, so the *next* new
window lands beside it -> binary-space-partition spiral. Nothing moves
visually at split time.

Small workspaces (<= SMALL_WORKSPACE tiling windows) are instead reset to the
default orientation: flatten the tree, set the root orientation, and with two
windows wrap each so a third window continues the spiral. Size-based
splitting alone got this wrong in practice:
- a new window's frame can still be its pre-tiling size (e.g. a 1247x1204
  terminal alone on a 3840x2160 monitor) when it looks settled;
- when windows close, the survivors keep their nested containers (flattening
  is off), so two windows can end up stacked in an old vertical container.
Closing produces no window-detected event, so focus-changed (which follows a
close) re-checks the window count of its workspace and resets it when the
count changed. Unchanged counts leave manual rearrangements alone.

Only new windows are split by default. Splitting on focus-changed (the
`on_focus` mode) shuffles windows on close: focus jumps to a neighbour whose
frame is still the stale pre-close size, and the split reshapes the tree
mid-relayout.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .geometry import Size

log = logging.getLogger(__name__)

EVENTS = ("window-detected", "focus-changed")
ORIENTATIONS = ("auto", "horizontal", "vertical")
SMALL_WORKSPACE = 2  # up to this many tiling windows: default orientation


@dataclass
class Settings:
    on_focus: bool = False  # legacy: split on every focus change too
    settle_step: float = 0.02  # seconds between frame polls of a new window
    settle_tries: int = 8  # max polls (~160 ms) until the frame is stable
    refresh_delay: float = 0.05  # let macOS finish destroying a closed window
    # Root orientation of small workspaces; like AeroSpace's
    # default-root-container-orientation, auto = by monitor aspect ratio.
    default_orientation: str = "auto"


def _orientation(size: Size) -> str:
    w, h = size
    return "horizontal" if w >= h else "vertical"


class Daemon:
    def __init__(
        self,
        aerospace,  # see aerospace.AeroSpace for the methods used
        window_size: Callable[[int], Optional[Size]],
        settings: Optional[Settings] = None,
        sleep: Callable[[float], None] = time.sleep,
        monitor_size: Callable[[int], Optional[Size]] = lambda monitor_id: None,
    ):
        self.aerospace = aerospace
        self.window_size = window_size
        self.monitor_size = monitor_size
        self.settings = settings or Settings()
        self.sleep = sleep
        self.tiling_counts: Dict[str, int] = {}  # last seen, per workspace

    def settled_size(self, wid: int) -> Optional[Size]:
        """Poll until two consecutive reads agree (new windows animate/resize
        right after creation); give up after settle_tries and use the last."""
        prev = self.window_size(wid)
        for _ in range(self.settings.settle_tries):
            self.sleep(self.settings.settle_step)
            cur = self.window_size(wid)
            if cur == prev:
                return cur
            prev = cur
        return prev

    def split(self, wid: int) -> None:
        size = self.settled_size(wid)
        if not size:
            log.debug("window %s gone before split", wid)
            return
        orientation = _orientation(size)
        log.info("split window %s %s (%gx%g)", wid, orientation, *size)
        self.aerospace.split(wid, orientation)

    def _windows(self, workspace: str) -> Optional[List[Tuple[int, str]]]:
        """[(wid, layout)] on `workspace` (None on failure); updates counts."""
        windows = self.aerospace.windows(workspace)
        if windows is not None:
            self.tiling_counts[workspace] = sum(1 for _, l in windows if l != "floating")
        return windows

    def _monitor(self, workspace: str) -> Optional[Size]:
        mid = self.aerospace.workspace_monitor(workspace)
        return self.monitor_size(mid) if mid is not None else None

    def reset_small(self, workspace: str, tiling: List[int]) -> None:
        """Lay out a workspace with 1-2 tiling windows in default orientation."""
        monitor = None
        root = self.settings.default_orientation
        if root == "auto":
            monitor = self._monitor(workspace)
            root = _orientation(monitor) if monitor else "horizontal"
        log.info("reset workspace %s: %d window(s), %s", workspace, len(tiling), root)
        self.aerospace.flatten(workspace)
        self.aerospace.set_root_orientation(workspace, root)
        if len(tiling) < 2:
            # Don't split a lone window: as only child, split would change the
            # root's orientation instead of wrapping the window.
            return
        # Wrap each half along its longer edge so a new window lands in (and
        # halves) the focused one. Frames are stale right after the reset, so
        # derive the halves from the monitor.
        if monitor is None:
            monitor = self._monitor(workspace)
        if monitor:
            w, h = monitor
            inner = _orientation((w / 2, h) if root == "horizontal" else (w, h / 2))
        else:
            inner = "vertical" if root == "horizontal" else "horizontal"
        for wid in tiling:
            self.aerospace.split(wid, inner)

    def place(self, wid: int, workspace: Optional[str]) -> None:
        """Handle a new (or, in on_focus mode, focused) window."""
        windows = self._windows(workspace) if workspace else None
        if windows is not None:
            layouts = dict(windows)
            if layouts.get(wid) == "floating":
                log.debug("window %s is floating; ignored", wid)
                return
            tiling = [w for w, layout in windows if layout != "floating"]
            if wid in layouts and len(tiling) <= SMALL_WORKSPACE:
                self.reset_small(workspace, tiling)
                return
        # Larger workspace, or no usable workspace info: dwindle by size.
        self.split(wid)

    def refresh(self, workspace: Optional[str]) -> None:
        self.sleep(self.settings.refresh_delay)
        if not workspace:
            log.debug("refresh")
            self.aerospace.refresh()
            return
        # The query doubles as the refresh poke.
        prev = self.tiling_counts.get(workspace)
        windows = self._windows(workspace)
        if windows is None:
            return
        tiling = [w for w, layout in windows if layout != "floating"]
        log.debug("refresh %s: %d tiling window(s)", workspace, len(tiling))
        if len(tiling) != prev and 0 < len(tiling) <= SMALL_WORKSPACE:
            self.reset_small(workspace, tiling)

    def handle(self, event: dict) -> None:
        kind = event.get("_event")
        workspace = event.get("workspace")
        if kind == "focus-changed" and not self.settings.on_focus:
            self.refresh(workspace)
            return
        if kind not in EVENTS:
            return
        wid = event.get("windowId")
        if wid:
            self.place(wid, workspace)

    def handle_line(self, line: str) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            log.debug("ignoring non-JSON line: %r", line)
            return
        if isinstance(event, dict):
            self.handle(event)

    def run(self, lines: Iterable[str]) -> None:
        """Process the subscribe stream until it ends."""
        for line in lines:
            self.handle_line(line)
