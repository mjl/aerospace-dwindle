# Handoff: aerospace-dwindle → Python package

Prototype: `aerospace-dwindle.py` (single file, ~110 lines). Goal: turn it into a proper installable package.

## What it does

Emulates Hyprland's **dwindle** layout (automatic binary-space-partition: each new window splits the previous one in half along its longer edge) on top of the **AeroSpace** tiling WM for macOS, which natively only supports i3-style manual tree tiling (new windows become equal siblings).

AeroSpace has no built-in dwindle (upstream "dynamic TWM" issue #260 is planned post-1.0) and its config can't read window geometry, so the decision is made by an external daemon.

## Current design (works, user-verified)

Long-running process, one event stream, no per-event process spawn except the AeroSpace CLI calls:

1. `aerospace subscribe --no-send-initial window-detected focus-changed` → JSON lines on stdout, e.g. `{"_event":"focus-changed","windowId":28218,"workspace":"M"}`.
2. **`window-detected`**: poll the window's size via Quartz `CGWindowListCopyWindowInfo(kCGWindowListOptionIncludingWindow, wid)` until it is stable (20 ms steps, max ~160 ms), then run `aerospace split --window-id <wid> horizontal|vertical` (horizontal if width ≥ height). This wraps the new window in its own container with that orientation, so the *next* new window lands beside it → dwindle spiral. Visually nothing moves at split time.
3. **`focus-changed`**: sleep 50 ms, then run `aerospace list-windows --focused` (output discarded). Pure "poke": any CLI command makes the AeroSpace server refresh its model. Without it, a closed window leaves a hole until the next user action (see Lessons).
4. `--on-focus` flag: legacy mode that splits on every focus change instead (causes shuffling on close; kept only for experimentation).
5. Exits when the subscribe stream ends (AeroSpace quit/crashed). A fresh instance is started by AeroSpace's `after-startup-command` on next launch.

## Required AeroSpace config

```toml
# top-level keys BEFORE any [table] header (TOML scoping!)
enable-normalization-flatten-containers = false   # mandatory: split is a no-op when this is on
after-startup-command = [
  'exec-and-forget exec /abs/path/python /abs/path/aerospace-dwindle.py >/tmp/aerospace-dwindle.log 2>&1'
]
```

- Requires AeroSpace **≥ 0.21.0-Beta** (`subscribe` was added there).
- `enable-normalization-opposite-orientation-for-nested-containers`: was suspected of fighting the splits; not confirmed either way. The fix that actually worked was the window-detected/refresh design. Worth testing both values.

## Lessons learned / gotchas (all hit during prototyping)

**AeroSpace CLI location**
- The CLI is *not* inside the app bundle. `/Applications/AeroSpace.app/Contents/MacOS/aerospace` resolves (case-insensitive FS) to the **server** binary `AeroSpace`: it answers `--version` but rejects `subscribe` with "Unrecognized flag 'subscribe'". Never use that path.
- Release zip ships the CLI separately at `AeroSpace-v$VERSION/bin/aerospace`; Homebrew cask (`brew install --cask nikitabobko/tap/aerospace`) links it into `/usr/local/bin` (Intel) or `/opt/homebrew/bin` (Apple Silicon). Manual installs may have no CLI at all.
- Current lookup order: `$AEROSPACE_CLI`, `which aerospace`, `~/bin/aerospace`, `/usr/local/bin/aerospace`, `/opt/homebrew/bin/aerospace`. Exit with a clear message if none found.

**Launching from AeroSpace**
- `exec-and-forget` always runs `/bin/bash -c '<string>'`; stdout/stderr/exit code are discarded → always redirect to a log while debugging.
- There's no argv-style launcher (`exec-on-workspace-change` takes argv but fires per workspace switch — unusable). Prefix with `exec` so bash is replaced by Python (otherwise a `bash -c` parent lingers in `ps`, which looks like "two instances").
- GUI-launched processes get a minimal PATH → use absolute paths for python and the CLI.
- `after-startup-command` runs only on AeroSpace start, **not** on `reload-config` → no duplicate daemons on reload, but you must restart AeroSpace to (re)launch.
- `[exec.env-vars]` can extend PATH for exec commands, but beware TOML: keys after a `[table]` header belong to that table.

**AeroSpace semantics**
- `split <dir>`: if the window's parent has >1 child → wraps the window in a new container with orientation `<dir>`; if it's the only child → changes the parent's orientation. Use explicit `horizontal`/`vertical`, never `opposite` (non-idempotent when repeated).
- AeroSpace notices closed windows late (macOS's destroyed notification is unreliable); re-tiling happens on the next refresh. Any CLI command triggers a refresh — `list-windows --focused` is sufficient (verified).
- Splitting on *focus-changed* caused visible shuffling on close: focus jumps to a neighbour whose frame is still the stale pre-close size, and the split reshapes the tree mid-relayout.
- `subscribe` event types: `focus-changed`, `focused-monitor-changed`, `focused-workspace-changed`, `mode-changed`, `window-detected`, `binding-triggered`; `--all`, `--no-send-initial`.
- Callback env vars (if ever needed): `AEROSPACE_WINDOW_ID`, `AEROSPACE_WORKSPACE`; `aerospace list-exec-env-vars` shows exec environment.

**macOS / Quartz**
- AeroSpace `windowId` == CoreGraphics `CGWindowID` (works in practice; not documented by AeroSpace).
- Reading `kCGWindowBounds` needs no Accessibility/Automation/Screen Recording permission (only window *titles* are protected).
- `osascript`/System Events was the first approach: slow (~100 ms+ per call) and needs Automation permission. Avoid.

## User's environment (the only tested setup)

- Intel Mac, macOS 13 Ventura
- AeroSpace 0.21.3-Beta, installed manually (zip), CLI placed manually
- Python 3.12 (MacPorts) in a venv: `~/Projects/cms_sites/tools3/bin/python`; script at `~/Projects/cms_sites/tools3/bin/aerospace-dwindle.py`
- Dependency: `pyobjc-framework-Quartz`
- Untested: Apple Silicon, macOS 14+, multi-monitor, native fullscreen, many workspaces.

## Packaging suggestions

- `pyproject.toml` (hatchling or setuptools), src layout, `requires-python >= 3.9` (Ventura system Python is 3.9), dependency `pyobjc-framework-Quartz; sys_platform == "darwin"`, macOS-only classifiers.
- Console entry point, e.g. `aerospace-dwindle = aerospace_dwindle.cli:main`. Then the config line becomes `exec-and-forget exec /abs/venv/bin/aerospace-dwindle >…log 2>&1`.
- Module split: `cli.py` (argparse), `aerospace.py` (CLI discovery, subscribe stream, split/refresh), `geometry.py` (Quartz access — isolate so tests can mock it), `daemon.py` (event loop).
- CLI options: `--aerospace-cli PATH`, `--on-focus`, `--settle-step`, `--settle-tries`, `--refresh-delay`, `--log-file`, `-v/--verbose`. Replace the DEVNULL'd subprocess output with `logging` (log non-zero exit codes of split/refresh at debug level).
- Startup check: run `aerospace --version`, parse it, fail clearly if < 0.21.0 (subscribe missing) instead of the cryptic flag error.
- Optional `aerospace-dwindle print-config` subcommand that prints the TOML snippet with resolved absolute paths (most setup pain was paths).
- Optional launchd plist generator as an alternative launcher (real argv, `KeepAlive`); note it would respawn every ~10 s while AeroSpace is not running.

## Testing

Unit-testable without a Mac by faking both boundaries (this was used to verify the current event handling):

- Fake `Quartz` module on `PYTHONPATH` exposing `kCGWindowListOptionIncludingWindow` and `CGWindowListCopyWindowInfo(opt, wid)` returning `[{"kCGWindowBounds": {"Width": w, "Height": h}}]`.
- Fake `aerospace` shell script (via `AEROSPACE_CLI`) that logs its argv and, for `subscribe`, prints canned JSON event lines.
- Assert the call log, e.g. `window-detected` wid 1 (800×600) → `split --window-id 1 horizontal`; `focus-changed` → `list-windows --focused`.

Better in the package: inject the geometry function and a command runner so tests need no subprocess at all.

## Known limitations / ideas

- Nested single-child containers accumulate (flattening is off). `aerospace flatten-workspace-tree` resets a workspace. Possible feature: periodically flatten idle workspaces (careful: destroys dwindle structure).
- Only new windows get the dwindle treatment; focusing an older window and opening a new one places it per the existing container orientation (true dwindle would split the focused window — that's what `--on-focus` did, at the cost of shuffling).
- `window-detected` also fires for dialogs/floating windows; `split` on them fails harmlessly. Could filter by `appBundleId` or check layout via `list-windows --format`.
- Settle polling blocks the loop (~160 ms worst case); bursts of events queue up. Could coalesce focus-changed events (only the latest matters for the refresh poke).
- Could talk to AeroSpace's Unix socket directly instead of spawning the CLI for split/refresh (protocol undocumented; small gain).
- Alternative if hacks become too painful: OmniWM (formerly HyprSpace) has native dwindle + Niri layouts, but requires Apple Silicon + macOS 26.
