import os

import pytest

from aerospace_dwindle.aerospace import (
    AeroSpace,
    VersionError,
    check_version,
    find_cli,
    parse_versions,
)


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return str(path)


def test_find_cli_explicit(tmp_path):
    p = touch(tmp_path / "aerospace")
    assert find_cli(p, env={}) == p


def test_find_cli_explicit_missing_does_not_fall_back(tmp_path):
    env = {"AEROSPACE_CLI": touch(tmp_path / "other")}
    assert find_cli(str(tmp_path / "nope"), env=env) is None


def test_find_cli_env_var_first(tmp_path):
    env_cli = touch(tmp_path / "env" / "aerospace")
    path_dir = tmp_path / "pathdir"
    touch(path_dir / "aerospace")
    assert find_cli(env={"AEROSPACE_CLI": env_cli, "PATH": str(path_dir)}) == env_cli


def test_find_cli_from_path(tmp_path):
    path_cli = touch(tmp_path / "pathdir" / "aerospace")
    assert find_cli(env={"PATH": str(tmp_path / "pathdir")}) == path_cli


def test_find_cli_rejects_app_bundle_server_binary(tmp_path):
    p = touch(tmp_path / "AeroSpace.app" / "Contents" / "MacOS" / "aerospace")
    assert find_cli(p, env={}) is None


VERSION_OUTPUT = (
    "aerospace CLI client version: 0.21.3-Beta 1a2b3c\n"
    "AeroSpace.app server version: 0.21.3-Beta 1a2b3c\n"
)


def test_parse_versions():
    assert parse_versions(VERSION_OUTPUT) == [(0, 21, 3), (0, 21, 3)]


def test_check_version_ok():
    check_version(VERSION_OUTPUT)
    check_version("1.0.0")


@pytest.mark.parametrize("text", ["0.20.2-Beta", "client 0.21.3\nserver 0.19.0"])
def test_check_version_too_old(text):
    with pytest.raises(VersionError, match="too old"):
        check_version(text)


def test_check_version_unparseable_is_tolerated():
    check_version("garbage")


def test_commands_use_runner():
    calls = []
    a = AeroSpace("/x/aerospace", runner=lambda argv: calls.append(list(argv)) or 0)
    a.split(42, "vertical")
    a.refresh()
    assert calls == [
        ["/x/aerospace", "split", "--window-id", "42", "vertical"],
        ["/x/aerospace", "list-windows", "--focused"],
    ]
