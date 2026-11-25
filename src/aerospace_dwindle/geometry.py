# Copyright (c) 2026, Martin J. Laubach
# SPDX-License-Identifier: BSD-3-Clause
"""Window geometry via Quartz (CoreGraphics).

Isolated so the rest of the package (and the tests) never import Quartz.
AeroSpace's `windowId` equals the CoreGraphics `CGWindowID` (true in practice,
not documented by AeroSpace). Reading `kCGWindowBounds` needs no
Accessibility / Screen Recording permission; only window titles are protected.
"""
from __future__ import annotations

from typing import Optional, Tuple

Size = Tuple[float, float]


def ensure_available() -> None:
    """Raise ImportError early if pyobjc's Quartz bindings are missing."""
    import Quartz  # noqa: F401


def window_size(wid: int) -> Optional[Size]:
    """(width, height) of window `wid`, or None if it no longer exists."""
    # Imported lazily so importing this module works without pyobjc.
    from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionIncludingWindow

    info = CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, wid)
    if not info:
        return None
    bounds = info[0]["kCGWindowBounds"]
    return bounds["Width"], bounds["Height"]


def monitor_size(monitor_id: int) -> Optional[Size]:
    """(width, height) of AeroSpace monitor `monitor_id`, or None.

    AeroSpace numbers monitors 1.. ordered left to right, so sort the active
    displays by origin. Window positions can't be used to find a workspace's
    monitor: AeroSpace parks windows of hidden workspaces off-screen.
    """
    from Quartz import CGDisplayBounds, CGDisplayMirrorsDisplay, CGGetActiveDisplayList

    err, ids, _ = CGGetActiveDisplayList(32, None, None)
    if err or not ids:
        return None
    # A mirroring display isn't a separate monitor for AeroSpace.
    rects = [CGDisplayBounds(d) for d in ids if not CGDisplayMirrorsDisplay(d)]
    rects.sort(key=lambda r: (r.origin.x, r.origin.y))
    if not 1 <= monitor_id <= len(rects):
        return None
    r = rects[monitor_id - 1]
    return r.size.width, r.size.height
