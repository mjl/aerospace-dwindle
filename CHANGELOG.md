# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- BSD 3-Clause license (`LICENSE`, package metadata, SPDX headers in sources).
- `--default-orientation auto|horizontal|vertical` (default `auto`: by monitor
  aspect ratio, like AeroSpace's `default-root-container-orientation`).

### Changed
- Workspaces with one or two tiling windows always use the default
  orientation: tree flattened and root orientation set when a window appears
  and when the window count drops (e.g. after closing a window). With two
  windows each is wrapped so a third window continues the dwindle spiral.
  Manual rearrangements are kept until the window count changes.
- On focus change, the workspace's window list is queried instead of
  `list-windows --focused`; it serves as the refresh poke as well.
- New floating windows are ignored (previously a no-op `split` was sent).

### Fixed
- Two windows sometimes stacked instead of side by side: a new window's
  pre-tiling frame decided the root orientation, or survivors of closed
  windows stayed in an old nested container.

## [0.1.20261125] - 2026-11-25

### Added
- Initial package of the `aerospace-dwindle.py` prototype: `pyproject.toml`,
  `src/` layout, `aerospace-dwindle` console script.
- Options `--aerospace-cli`, `--on-focus`, `--settle-step`, `--settle-tries`,
  `--refresh-delay`, `--log-file`, `-v/--verbose`, `--version`.
- `print-config` subcommand: `~/.aerospace.toml` snippet with absolute paths.
- Startup check for AeroSpace >= 0.21.0 (`subscribe` support).
- Logging of failed AeroSpace commands instead of discarding output.
- Tests with faked AeroSpace CLI and Quartz.
