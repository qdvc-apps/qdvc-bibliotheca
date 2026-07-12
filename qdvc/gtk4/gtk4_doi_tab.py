"""The DOI Lookup view (GTK4): enter a DOI, jump to the matching record."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject  # noqa: E402


class DoiLookupView(Gtk.Box):
    __gsignals__ = {
        # emitted with a bibliotheca_id when a match should be revealed
        "goto-record": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.workspace = None

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(24)
        inner.set_margin_bottom(24)
        inner.set_margin_start(24)
        inner.set_margin_end(24)
        inner.set_halign(Gtk.Align.CENTER)
        inner.set_valign(Gtk.Align.START)

        prompt = Gtk.Label(xalign=0)
        prompt.set_markup("<b>DOI Lookup</b>")
        inner.append(prompt)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("e.g. 10.1234/example")
        self.entry.set_width_chars(48)
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self._on_lookup)
        self.button = Gtk.Button(label="Lookup")
        self.button.add_css_class("suggested-action")
        self.button.connect("clicked", self._on_lookup)
        row.append(self.entry)
        row.append(self.button)
        inner.append(row)

        self.status = Gtk.Label(xalign=0)
        self.status.set_wrap(True)
        inner.append(self.status)

        self.append(inner)

    def set_workspace(self, workspace):
        self.workspace = workspace
        self.status.set_text("")
        self.entry.set_text("")

    def _on_lookup(self, _widget):
        raw = self.entry.get_text().strip()
        if not self.workspace:
            self.status.set_text("No workspace is open.")
            return
        if not raw:
            self.status.set_text("Please enter a DOI.")
            return
        bid = self.workspace.lookup_doi(raw)
        if bid:
            self.status.set_markup(
                f"Found: <b>{GObject.markup_escape_text(bid)}</b> \u2014 "
                "opening in Catalogue\u2026")
            self.emit("goto-record", bid)
        else:
            safe = GObject.markup_escape_text(raw)
            self.status.set_text(f"Sorry, no records found for DOI = {safe}")
