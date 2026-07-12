"""QDVC Bibliotheca application entry point."""

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib  # noqa: E402

from .. import APP_ID
from ..config import Config
from .gtk3_main_window import MainWindow

# The standard freedesktop themed icon this app uses. Present on a typical
# GNOME/MATE install, so no icon file needs to be bundled or installed.
ICON_NAME = "accessories-dictionary"

# Set a deterministic program name early. This becomes the second element of
# the X11 WM_CLASS (the "class" part), which the MATE panel uses to match a
# running window to its .desktop launcher. The .desktop file's StartupWMClass
# must equal this value ("qdvc-bibliotheca").
GLib.set_prgname("qdvc-bibliotheca")


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.config = Config.load()
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        # Set the default window icon to a standard themed icon, so every
        # window (and, with a matching StartupWMClass, the MATE panel) shows it.
        try:
            Gtk.Window.set_default_icon_name(ICON_NAME)
        except Exception:  # noqa: BLE001
            pass

    def do_activate(self):
        if not self.window:
            self.window = MainWindow(self, self.config)
            self.window.show_all()
            self.window.open_last_workspace_if_any()
        self.window.present()

    def do_open(self, files, n_files, hint):
        self.do_activate()
        if files:
            self.window._open_path(files[0].get_path())


def main(argv=None):
    app = Application()
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
