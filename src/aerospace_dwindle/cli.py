"""Command line entry point."""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional, Sequence

from . import __version__, config, geometry
from .aerospace import AeroSpace, VersionError, check_version, find_cli
from .daemon import EVENTS, ORIENTATIONS, SMALL_WORKSPACE, Daemon, Settings

log = logging.getLogger("aerospace_dwindle")


def _non_negative(conv):
    def parse(s: str):
        v = conv(s)
        if v < 0:
            raise argparse.ArgumentTypeError(f"must be >= 0: {s}")
        return v

    return parse


def build_parser() -> argparse.ArgumentParser:
    d = Settings()
    p = argparse.ArgumentParser(
        prog="aerospace-dwindle",
        description="Hyprland-style dwindle auto-splitting daemon for AeroSpace. "
        "Without a command, runs the daemon until AeroSpace quits.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--aerospace-cli",
        metavar="PATH",
        help="aerospace CLI binary (default: $AEROSPACE_CLI, PATH, ~/bin, "
        "/usr/local/bin, /opt/homebrew/bin)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    p.add_argument("--log-file", metavar="PATH", help="append log here instead of stderr")

    g = p.add_argument_group("daemon options")
    g.add_argument(
        "--on-focus",
        action="store_true",
        help="legacy: also split the focused window on every focus change "
        "(shuffles windows when one closes)",
    )
    g.add_argument(
        "--default-orientation",
        choices=ORIENTATIONS,
        default=d.default_orientation,
        help=f"layout of workspaces with <= {SMALL_WORKSPACE} tiling windows; match "
        "AeroSpace's default-root-container-orientation (default: %(default)s = "
        "horizontal on wide monitors, vertical on tall ones)",
    )
    g.add_argument(
        "--settle-step",
        type=_non_negative(float),
        default=d.settle_step,
        metavar="SEC",
        help="seconds between frame polls of a new window (default: %(default)s)",
    )
    g.add_argument(
        "--settle-tries",
        type=_non_negative(int),
        default=d.settle_tries,
        metavar="N",
        help="max frame polls until the size is stable (default: %(default)s)",
    )
    g.add_argument(
        "--refresh-delay",
        type=_non_negative(float),
        default=d.refresh_delay,
        metavar="SEC",
        help="delay before poking AeroSpace after a focus change (default: %(default)s)",
    )

    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    pc = sub.add_parser(
        "print-config",
        help="print the ~/.aerospace.toml snippet with resolved absolute paths",
    )
    pc.add_argument(
        "--log",
        default=config.DEFAULT_LOG,
        metavar="PATH",
        help="log file used in the snippet (default: %(default)s)",
    )
    return p


def _setup_logging(verbose: bool, log_file: Optional[str]) -> None:
    handler = logging.FileHandler(log_file) if log_file else logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.handlers[:] = [handler]  # replace, so repeated main() calls don't stack
    log.setLevel(logging.DEBUG if verbose else logging.INFO)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose, args.log_file)

    cli = find_cli(args.aerospace_cli)

    if args.command == "print-config":
        sys.stdout.write(config.render(config.self_command(), cli, args.log))
        return 0

    if cli is None:
        where = args.aerospace_cli or "$AEROSPACE_CLI, PATH, ~/bin, /usr/local/bin, /opt/homebrew/bin"
        log.error("aerospace CLI not found (looked in: %s); use --aerospace-cli PATH", where)
        return 2
    try:
        geometry.ensure_available()
    except ImportError as e:
        log.error("Quartz bindings missing (pip install pyobjc-framework-Quartz): %s", e)
        return 2

    aerospace = AeroSpace(cli)
    try:
        check_version(aerospace.version_output())
    except VersionError as e:
        log.error("%s", e)
        return 2

    settings = Settings(
        on_focus=args.on_focus,
        settle_step=args.settle_step,
        settle_tries=args.settle_tries,
        refresh_delay=args.refresh_delay,
        default_orientation=args.default_orientation,
    )
    daemon = Daemon(
        aerospace, geometry.window_size, settings, monitor_size=geometry.monitor_size
    )
    log.info("aerospace-dwindle %s started (cli: %s)", __version__, cli)
    try:
        proc = aerospace.subscribe(EVENTS)
    except OSError as e:
        log.error("cannot run %s subscribe: %s", cli, e)
        return 2
    try:
        assert proc.stdout is not None
        daemon.run(proc.stdout)
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        return 130
    # The stream ends when AeroSpace quits/crashes. Don't reconnect: the next
    # AeroSpace start launches a fresh instance via after-startup-command.
    rc = proc.wait()
    log.info("subscribe stream ended (exit %s); exiting", rc)
    return rc
