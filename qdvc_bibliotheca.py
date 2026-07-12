#!/usr/bin/env python3
"""Launcher / dispatcher for QDVC Bibliotheca.

Picks the UI toolkit backend *before* importing any GTK code, so the chosen
front-end is the only one loaded. The backend is chosen by (in priority order):

  1. an explicit CLI flag: ``--gtk3`` or ``--gtk4``;
  2. the ``ui_backend`` key saved in the config (set from Preferences);
  3. the default, ``gtk3``.

Any other CLI arguments (e.g. a workspace path) are passed through to the
selected backend's ``main``.
"""

import sys


def _select_backend(argv):
    """Return (backend_name, remaining_argv).

    ``argv`` is the full process argv (including argv[0], the program name).
    A ``--gtk3`` / ``--gtk4`` flag anywhere in argv wins and is consumed;
    otherwise the saved config preference is used, then the "gtk3" default.
    argv[0] is preserved in ``remaining_argv`` because GApplication expects a
    program name there.
    """
    remaining = []
    cli_backend = None
    for i, arg in enumerate(argv):
        if i > 0 and arg in ("--gtk3", "--gtk4"):
            cli_backend = arg[2:]  # strip "--"
        else:
            remaining.append(arg)

    if cli_backend:
        return cli_backend, remaining

    # Fall back to the saved preference. Importing config does not import GTK.
    try:
        from qdvc.config import Config
        backend = Config.load().ui_backend
    except Exception:  # noqa: BLE001
        backend = "gtk3"
    return backend, remaining


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    backend, remaining = _select_backend(argv)

    if backend == "gtk4":
        try:
            from qdvc.gtk4.gtk4_app import main as run
        except Exception as exc:  # noqa: BLE001
            # GTK4/libadwaita may be unavailable; fall back to GTK3 rather
            # than failing to launch, and tell the user why.
            sys.stderr.write(
                f"Could not start the GTK4 interface ({exc}); "
                "falling back to GTK3.\n")
            from qdvc.gtk3.gtk3_app import main as run
    else:
        from qdvc.gtk3.gtk3_app import main as run

    return run(remaining)


if __name__ == "__main__":
    raise SystemExit(main())
