"""Event handling: turn AeroSpace events into split / refresh commands.

Dwindle emulation: when a window appears, `split` it along its longer edge.
That wraps it in its own container with that orientation, so the *next* new
window lands beside it -> binary-space-partition spiral. Nothing moves
visually at split time.

Only new windows are split by default. Splitting on focus-changed (the
`on_focus` mode) shuffles windows on close: focus jumps to a neighbour whose
frame is still the stale pre-close size, and the split reshapes the tree
mid-relayout. Instead, focus-changed just pokes AeroSpace to refresh.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .geometry import Size

log = logging.getLogger(__name__)

EVENTS = ("window-detected", "focus-changed")


@dataclass
class Settings:
    on_focus: bool = False  # legacy: split on every focus change too
    settle_step: float = 0.02  # seconds between frame polls of a new window
    settle_tries: int = 8  # max polls (~160 ms) until the frame is stable
    refresh_delay: float = 0.05  # let macOS finish destroying a closed window


class Daemon:
    def __init__(
        self,
        aerospace,  # anything with split(wid, orientation) and refresh()
        window_size: Callable[[int], Optional[Size]],
        settings: Optional[Settings] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.aerospace = aerospace
        self.window_size = window_size
        self.settings = settings or Settings()
        self.sleep = sleep

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
        w, h = size
        orientation = "horizontal" if w >= h else "vertical"
        log.info("split window %s %s (%gx%g)", wid, orientation, w, h)
        self.aerospace.split(wid, orientation)

    def refresh(self) -> None:
        self.sleep(self.settings.refresh_delay)
        log.debug("refresh")
        self.aerospace.refresh()

    def handle(self, event: dict) -> None:
        kind = event.get("_event")
        if kind == "focus-changed" and not self.settings.on_focus:
            self.refresh()
            return
        if kind not in EVENTS:
            return
        wid = event.get("windowId")
        if wid:
            self.split(wid)

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
