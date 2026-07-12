"""The Authors view (GTK4): unique authors derived from BibTeX, with starring.

A ``Gtk.ColumnView`` over a ``Gtk.SingleSelection(Gtk.FilterListModel(
Gio.ListStore))`` of ``_AuthorItem`` rows. Search + "starred only" drive a
``Gtk.CustomFilter``. Row-activate (double-click / Enter) or the bottom button
emits ``show-author-works``; toggling a star emits ``star-changed`` and
persists via the workspace.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject  # noqa: E402

from . import gtk4_widgets as W  # noqa: E402


class _AuthorItem(GObject.Object):
    __gtype_name__ = "QdvcAuthorItem"

    def __init__(self, author):
        super().__init__()
        self.author_id = author.author_id
        self.name = author.display_name
        self.starred = author.starred
        self.count = len(author.record_ids)


class AuthorsView(Gtk.Box):
    __gsignals__ = {
        "show-author-works": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "star-changed": (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
    }

    def __init__(self, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.workspace = None

        # search / filter toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_margin_top(6)
        toolbar.set_margin_bottom(6)
        toolbar.set_margin_start(6)
        toolbar.set_margin_end(6)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Filter authors\u2026")
        self.search.set_hexpand(True)
        self.search.connect("search-changed", lambda _e: self._refilter())
        toolbar.append(self.search)
        self.starred_only = Gtk.CheckButton(label="Starred only")
        self.starred_only.connect("toggled", lambda _b: self._refilter())
        toolbar.append(self.starred_only)
        self.append(toolbar)

        # model: base store -> filter -> single selection
        self.store = Gio.ListStore(item_type=_AuthorItem)
        self.filter = Gtk.CustomFilter.new(self._match, None)
        self.filter_model = Gtk.FilterListModel(model=self.store,
                                                filter=self.filter)
        self.selection = Gtk.SingleSelection(model=self.filter_model)

        self.column_view = Gtk.ColumnView(model=self.selection)
        self.column_view.set_vexpand(True)
        self.column_view.append_column(
            W.make_star_column("starred", self._on_star_toggled))
        self.column_view.append_column(
            W.make_text_column("Author", "name", expand=True, ellipsize=True))
        self.column_view.append_column(
            W.make_text_column("Author ID", "author_id"))
        self.column_view.append_column(
            W.make_text_column("Works", "count", xalign=1.0))
        self.column_view.connect("activate", self._on_activate)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_child(self.column_view)
        self.append(scroller)

        # bottom action
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bottom.set_margin_top(6)
        bottom.set_margin_bottom(6)
        bottom.set_margin_start(6)
        bottom.set_margin_end(6)
        self.show_works_btn = Gtk.Button(label="Show works in Catalogue")
        self.show_works_btn.connect("clicked", self._on_show_works)
        spacer = Gtk.Box(hexpand=True)
        bottom.append(spacer)
        bottom.append(self.show_works_btn)
        self.append(bottom)

    # ------------------------------------------------------------------
    def set_workspace(self, workspace):
        self.workspace = workspace
        self.reload()

    def reload(self):
        self.store.remove_all()
        if not self.workspace:
            return
        for a in self.workspace.all_authors():
            self.store.append(_AuthorItem(a))

    def _refilter(self):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def _match(self, item, _user_data=None):
        if self.starred_only.get_active() and not item.starred:
            return False
        needle = self.search.get_text().strip().lower()
        if not needle:
            return True
        return (needle in (item.name or "").lower()
                or needle in (item.author_id or "").lower())

    def _on_star_toggled(self, item, new_value):
        item.starred = new_value
        if self.workspace:
            self.workspace.set_author_starred(item.author_id, new_value)
        self.emit("star-changed", item.author_id, new_value)

    def _selected_author_id(self):
        item = self.selection.get_selected_item()
        return item.author_id if item else None

    def _on_activate(self, _view, _position):
        aid = self._selected_author_id()
        if aid:
            self.emit("show-author-works", aid)

    def _on_show_works(self, _btn):
        aid = self._selected_author_id()
        if aid:
            self.emit("show-author-works", aid)
