"""QDVC Bibliotheca application entry point."""

import os
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib, GdkPixbuf  # noqa: E402

from . import APP_ID
from .config import Config
from .main_window import MainWindow

ICON_NAME = "qdvc-bibliotheca"

# Set a deterministic program name early. This becomes the second element of
# the X11 WM_CLASS (the "class" part), which the MATE panel uses to match a
# running window to its .desktop launcher. The .desktop file's StartupWMClass
# must equal this value ("qdvc-bibliotheca").
GLib.set_prgname(ICON_NAME)


def bundled_icon_path():
    """Absolute path to the SVG icon shipped inside the package, or None."""
    p = os.path.join(os.path.dirname(__file__), "data", f"{ICON_NAME}.svg")
    return p if os.path.exists(p) else None


def install_default_icon():
    """Make the app icon available to every window.

    Prefer a themed icon named `qdvc-bibliotheca` (installed system-wide by a
    packager); if the theme doesn't have it, fall back to the SVG bundled in
    the package, loaded directly from disk. Setting a real pixbuf/name here is
    what lets the window manager and the MATE panel show our icon rather than a
    generic one.
    """
    try:
        theme = Gtk.IconTheme.get_default()
        if theme.has_icon(ICON_NAME):
            Gtk.Window.set_default_icon_name(ICON_NAME)
            return
    except Exception:  # noqa: BLE001
        pass
    path = bundled_icon_path()
    if path:
        try:
            # load at a few sizes so the WM/panel can pick a suitable one
            icons = []
            for size in (16, 24, 32, 48, 64, 128, 256):
                icons.append(GdkPixbuf.Pixbuf.new_from_file_at_size(
                    path, size, size))
            Gtk.Window.set_default_icon_list(icons)
            return
        except Exception:  # noqa: BLE001
            pass
    # last resort: a stock themed icon so at least something shows
    try:
        Gtk.Window.set_default_icon_name("accessories-dictionary")
    except Exception:  # noqa: BLE001
        pass


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.config = Config.load()
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        install_default_icon()

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
