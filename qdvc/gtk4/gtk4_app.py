"""QDVC Bibliotheca — GTK4 / libadwaita application entry point.

Idiomatic GNOME entry point: an ``Adw.Application`` owns the application id, the
``app.*``/``win.*`` action scopes, window lifecycle, accelerators, and the main
loop, and initialises libadwaita styling. The window is built in
``do_activate`` (not at import time) and shown with ``present()``.
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from .. import APP_ID
from ..config import Config
from .gtk4_window import BibliothecaWindow  # noqa: E402

ICON_NAME = "accessories-dictionary"

# Match the GTK3 backend's WM class / .desktop association.
GLib.set_prgname("qdvc-bibliotheca")

# Accelerators, keyed by the win.* action they trigger. Installed once, by the
# application, so a single action drives the menu item, any header button, and
# the shortcut together.
ACCELS = {
    "win.open-workspace": ["<Primary>o"],
    "win.import": ["<Primary>i"],
    "win.refresh-workspace": ["<Primary>r"],
    "win.refresh-view": ["F5"],
    "win.sort": ["<Primary><Shift>s"],
    "win.rename-record": ["F2"],
    "win.validate": [],
    "win.preferences": ["<Primary>comma"],
    "win.shortcuts": ["<Primary>question"],
    "win.close-workspace": ["<Primary>w"],
    "win.quit": ["<Primary>q"],
    "win.view-catalogue": ["<Alt>1"],
    "win.view-authors": ["<Alt>2"],
    "win.view-outlets": ["<Alt>3"],
    "win.view-doi": ["<Alt>4"],
}


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.config = Config.load()
        self.window = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        for action_name, accels in ACCELS.items():
            if accels:
                self.set_accels_for_action(action_name, accels)

    def do_activate(self):
        if not self.window:
            self.window = BibliothecaWindow(self, self.config)
            self.window.open_last_workspace_if_any()
        self.window.present()

    def do_open(self, files, n_files, hint):
        self.do_activate()
        if files:
            self.window.open_path(files[0].get_path())


def main(argv=None):
    app = Application()
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
