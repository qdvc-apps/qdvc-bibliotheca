"""QDVC Bibliotheca application entry point."""

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio  # noqa: E402

from . import APP_ID
from .config import Config
from .main_window import MainWindow


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.config = Config.load()
        self.window = None

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
