# Copyright (c) 2026, Martin J. Laubach
# SPDX-License-Identifier: BSD-3-Clause
"""End-to-end: real subprocesses against a fake `aerospace` script, fake Quartz."""
import sys
import textwrap
import types

import pytest

from aerospace_dwindle import cli, config

EVENTS = [
    '{"_event":"window-detected","windowId":1,"workspace":"M"}',
    '{"_event":"focus-changed","windowId":1,"workspace":"M"}',
    '{"_event":"window-detected","windowId":2,"workspace":"M"}',
]


@pytest.fixture
def fake_quartz(monkeypatch):
    sizes = {1: (800, 600), 2: (400, 600)}
    mod = types.ModuleType("Quartz")
    mod.kCGWindowListOptionIncludingWindow = 8

    def info(opt, wid):
        assert opt == 8
        if wid not in sizes:
            return []
        w, h = sizes[wid]
        return [{"kCGWindowBounds": {"X": 0, "Y": 0, "Width": w, "Height": h}}]

    mod.CGWindowListCopyWindowInfo = info
    # one 3840x2160 display
    mod.CGGetActiveDisplayList = lambda n, a, b: (0, (7,), 1)
    mod.CGDisplayMirrorsDisplay = lambda d: 0
    mod.CGDisplayBounds = lambda d: types.SimpleNamespace(
        origin=types.SimpleNamespace(x=0, y=0),
        size=types.SimpleNamespace(width=3840, height=2160),
    )
    monkeypatch.setitem(sys.modules, "Quartz", mod)


@pytest.fixture
def fake_cli(tmp_path):
    def make(version="0.21.3-Beta", windows=("1|h_tiles", "2|v_tiles", "9|v_tiles")):
        log = tmp_path / "calls.log"
        window_list = tmp_path / "windows.txt"  # static list-windows answer
        window_list.write_text("".join(w + "\n" for w in windows))
        script = tmp_path / "bin" / "aerospace"
        script.parent.mkdir(exist_ok=True)
        events = tmp_path / "events.jsonl"
        events.write_text("\n".join(EVENTS) + "\n")
        script.write_text(
            textwrap.dedent(
                f"""\
                #!/bin/sh
                echo "$*" >> '{log}'
                case "$1" in
                  --version)
                    echo "aerospace CLI client version: {version} abc"
                    echo "AeroSpace.app server version: {version} abc" ;;
                  subscribe) cat '{events}' ;;
                  list-windows) cat '{window_list}' ;;
                  list-workspaces) echo 'M|1' ;;
                esac
                """
            )
        )
        script.chmod(0o755)
        return str(script), log

    return make


RUN = ["--settle-step", "0", "--refresh-delay", "0"]
QUERY = "list-windows --workspace M --format %{window-id}|%{window-parent-container-layout}"


def test_daemon_end_to_end_large_workspace(fake_quartz, fake_cli):
    script, log = fake_cli()
    assert cli.main(["--aerospace-cli", script, *RUN]) == 0
    assert log.read_text().splitlines() == [
        "--version",
        "subscribe --no-send-initial window-detected focus-changed",
        QUERY,
        "split --window-id 1 horizontal",
        QUERY,
        QUERY,
        "split --window-id 2 vertical",
    ]


def test_daemon_end_to_end_small_workspace(fake_quartz, fake_cli):
    script, log = fake_cli(windows=["1|v_tiles"])
    assert cli.main(["--aerospace-cli", script, *RUN]) == 0
    assert log.read_text().splitlines() == [
        "--version",
        "subscribe --no-send-initial window-detected focus-changed",
        QUERY,
        "list-workspaces --all --format %{workspace}|%{monitor-id}",
        "flatten-workspace-tree --workspace M",
        "layout --workspace M --root horizontal",
        QUERY,  # focus-changed: count unchanged
        QUERY,  # window 2 not (yet) listed: size-based fallback
        "split --window-id 2 vertical",
    ]


def test_too_old_aerospace_fails_clearly(fake_quartz, fake_cli, capsys):
    script, log = fake_cli(version="0.20.2-Beta")
    assert cli.main(["--aerospace-cli", script]) == 2
    assert "too old" in capsys.readouterr().err
    assert "subscribe" not in log.read_text()


def test_missing_cli(tmp_path, capsys):
    assert cli.main(["--aerospace-cli", str(tmp_path / "nope")]) == 2
    assert "aerospace CLI not found" in capsys.readouterr().err


def test_negative_option_rejected():
    with pytest.raises(SystemExit):
        cli.main(["--settle-tries", "-1"])


def test_print_config(fake_cli, capsys):
    script, _ = fake_cli()
    assert cli.main(["--aerospace-cli", script, "print-config", "--log", "/tmp/my log"]) == 0
    out = capsys.readouterr().out
    assert "enable-normalization-flatten-containers = false" in out
    assert "after-startup-command = [" in out
    assert f"--aerospace-cli {script}" in out
    assert "exec-and-forget exec " in out
    assert ">>'/tmp/my log' 2>&1" in out
    assert "WARNING" not in out


def test_print_config_is_valid_toml():
    tomllib = pytest.importorskip("tomllib")
    text = config.render(["/a b/aerospace-dwindle"], "/opt/x/aerospace", "/tmp/l\"og")
    data = tomllib.loads(text)
    assert data["enable-normalization-flatten-containers"] is False
    (cmd,) = data["after-startup-command"]
    assert cmd == (
        "exec-and-forget exec '/a b/aerospace-dwindle' --aerospace-cli /opt/x/aerospace"
        " >>'/tmp/l\"og' 2>&1"
    )


def test_print_config_warns_without_cli():
    assert "WARNING: aerospace CLI not found" in config.render(["x"], None)
