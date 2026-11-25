# aerospace-dwindle

Hyprland-style **dwindle** layout for the [AeroSpace](https://github.com/nikitabobko/AeroSpace)
tiling window manager on macOS: each new window splits the previous one in
half along its longer edge (binary space partition).

A small daemon listens to `aerospace subscribe` and, for every new window,
runs `aerospace split --window-id <id> horizontal|vertical` based on the
window's size (read via Quartz). On focus changes it pokes AeroSpace so closed
windows don't leave holes.

## Requirements

- macOS, AeroSpace **>= 0.21.0-Beta** (needs `aerospace subscribe`)
- the AeroSpace **CLI** (`aerospace`), not the app bundle's server binary:
  Homebrew cask installs it to `/usr/local/bin` or `/opt/homebrew/bin`;
  the release zip ships it in `bin/aerospace`
- Python >= 3.9

## Install

```sh
python3 -m venv ~/.venvs/aerospace-dwindle
~/.venvs/aerospace-dwindle/bin/pip install /path/to/aerospace-dwindle
~/.venvs/aerospace-dwindle/bin/aerospace-dwindle print-config
```

`print-config` prints the `~/.aerospace.toml` snippet with absolute paths
(GUI-launched processes get a minimal `PATH`). Paste it **above any `[table]`
header**, then restart AeroSpace (`after-startup-command` does not run on
`reload-config`). Roughly:

```toml
enable-normalization-flatten-containers = false   # mandatory
after-startup-command = [
  "exec-and-forget exec /abs/venv/bin/aerospace-dwindle --aerospace-cli /usr/local/bin/aerospace >>/tmp/aerospace-dwindle.log 2>&1",
]
```

The daemon exits when AeroSpace quits; the next AeroSpace start launches it again.

## Options

```
aerospace-dwindle [--aerospace-cli PATH] [-v] [--log-file PATH]
                  [--on-focus] [--settle-step SEC] [--settle-tries N]
                  [--refresh-delay SEC]
aerospace-dwindle print-config [--log PATH]
```

`--on-focus` is a legacy mode that also splits on every focus change; it
shuffles windows when one closes.

## Limitations

- Only new windows get the dwindle treatment; opening a window after focusing
  an older one follows the existing container orientation.
- Nested single-child containers accumulate (flattening is off);
  `aerospace flatten-workspace-tree` resets a workspace.
- Only tested on Intel macOS 13 with AeroSpace 0.21.3-Beta.

## How this was made

This is a small personal tool, written largely with AI assistance (Claude Opus 5.5),
then tested and used on my own machine. It does one job and I try to keep it
working for my setup; issues and pull requests are welcome, but there are
no guarantees beyond that.

## Development

```sh
pip install -e '.[dev]'
pytest
```

Tests fake both boundaries (AeroSpace CLI and Quartz) and run on any OS.
