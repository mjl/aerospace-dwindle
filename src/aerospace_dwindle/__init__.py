"""Hyprland-style dwindle auto-splitting for the AeroSpace tiling WM."""

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("aerospace-dwindle")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0+unknown"
