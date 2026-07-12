"""Keyboard shortcuts window (GTK4).

Renders the shared ``ui_prefs.SHORTCUTS`` table. Uses a plain ``Adw.Window`` with
a simple grid rather than ``Gtk.ShortcutsWindow`` so the list stays in lockstep
with the shared table and needs no per-entry section metadata.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw  # noqa: E402

from .. import ui_prefs  # noqa: E402


class ShortcutsWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__(transient_for=parent, modal=True,
                         title="Keyboard Shortcuts")
        self.set_default_size(360, 420)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())

        grid = Gtk.Grid(column_spacing=24, row_spacing=6)
        for m in ("top", "bottom", "start", "end"):
            getattr(grid, f"set_margin_{m}")(16)
        for i, (keys, desc) in enumerate(ui_prefs.SHORTCUTS):
            k = Gtk.Label(xalign=0)
            k.set_markup(f"<tt>{keys}</tt>")
            grid.attach(k, 0, i, 1, 1)
            grid.attach(Gtk.Label(label=desc, xalign=0), 1, i, 1, 1)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_child(grid)
        toolbar.set_content(scroller)
        self.set_content(toolbar)
