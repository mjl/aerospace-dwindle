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
