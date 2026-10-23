"""Command-line entry point mirroring btop 1.3.0's flags, messages and exit codes."""

from __future__ import annotations

import os
import sys

from . import config as config_mod
from . import log
from .app import BTOP_COMPAT_VERSION, MAX_UPDATE_MS, MIN_UPDATE_MS, VERSION, App, CliOptions, run
from .defaults import DEFAULTS

HELP_TEXT = """usage: pybtop [-h] [-v] [-/+t] [-p <id>] [-u <ms>] [--utf-force] [--debug]

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         show version info and exit
  -lc, --low-color      disable truecolor, converts 24-bit colors to 256-color
  -t, --tty_on          force (ON) tty mode, max 16 colors and tty friendly graph symbols
  +t, --tty_off         force (OFF) tty mode
  -p, --preset <id>     start with preset, integer value between 0-9
  -u, --update <ms>     set the program update rate in milliseconds
  --utf-force           force start even if no UTF-8 locale was detected
  --debug               start in DEBUG mode: shows microsecond timer for information collect
                        and screen draw functions and sets loglevel to DEBUG
"""


class ArgError(Exception):
    """Raised for an argument problem. `stream` is where btop prints it (stdout), `code` the exit status."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def parse_args(argv: list[str]) -> CliOptions:
    opts = CliOptions()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-h", "--help"):
            sys.stdout.write(HELP_TEXT)
            raise SystemExit(0)
        if arg in ("-v", "--version"):
            sys.stdout.write(f"pybtop version: {VERSION} (btop++ {BTOP_COMPAT_VERSION} compatible)\n")
            raise SystemExit(0)
        if arg in ("-lc", "--low-color"):
            opts.low_color = True
        elif arg in ("-t", "--tty_on"):
            opts.tty = True
        elif arg in ("+t", "--tty_off"):
            opts.tty = False
        elif arg in ("-p", "--preset"):
            if i + 1 >= len(argv):
                raise ArgError("ERROR: Preset option needs an argument.")
            i += 1
            value = argv[i]
            if not (value.isdigit() and len(value) == 1):
                raise ArgError("ERROR: Preset option only accepts an integer value between 0-9.")
            opts.preset = int(value)
        elif arg in ("-u", "--update"):
            if i + 1 >= len(argv):
                raise ArgError("ERROR: Update option needs an argument")
            i += 1
            opts.update_ms = _parse_update(argv[i])
        elif arg == "--utf-force":
            opts.utf_force = True
        elif arg == "--debug":
            opts.debug = True
        else:
            raise ArgError(f" Unknown argument: {arg}\n Use -h or --help for help.")
        i += 1
    return opts


def _parse_update(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise ArgError("ERROR: Invalid update rate") from None
    return max(MIN_UPDATE_MS, min(MAX_UPDATE_MS, number))


def has_utf8_locale() -> bool:
    for name in ("LC_ALL", "LC_CTYPE", "LANG"):
        value = os.environ.get(name, "")
        if value:
            return "utf-8" in value.lower() or "utf8" in value.lower()
    return False


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        cli = parse_args(argv)
    except ArgError as exc:
        sys.stdout.write(f"{exc}\n")
        return exc.code
    except SystemExit as exc:
        return int(exc.code or 0)

    if not cli.utf_force and not has_utf8_locale():
        sys.stderr.write(
            "ERROR: No UTF-8 locale detected!\n"
            "Use --utf-force argument to force start if you're sure your terminal can handle it.\n"
        )
        return 1
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stderr.write("ERROR: No tty detected!\npybtop needs an interactive shell to run.\n")
        return 1

    path = config_mod.config_path()
    if cli.debug:
        log.open_log(VERSION, BTOP_COMPAT_VERSION)
        log.debug("Starting in DEBUG mode!")
        log.info("Logger set to DEBUG")
        log.debug(f"Arguments: {' '.join(argv) or '(none)'}")
        try:
            log.info(f"Running on {os.ttyname(sys.stdout.fileno())}")
        except OSError:
            pass
    cfg = config_mod.Config(DEFAULTS, config_mod.load_config(path))
    if cli.debug:
        if os.path.isfile(path):
            log.debug(f"Loaded config from {path}")
        else:
            log.info(f"No config file at {path}, using defaults")
    if cli.update_ms is not None:
        cfg["update_ms"] = cli.update_ms
    user_theme_dir = os.path.join(config_mod.config_dir(), "themes")
    app = App(cfg, cli, user_theme_dir)
    return run(app, path)


if __name__ == "__main__":
    raise SystemExit(main())
