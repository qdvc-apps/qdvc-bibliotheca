"""The Authors tab: unique authors derived from BibTeX, with starring."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GObject  # noqa: E402


class AuthorsTab(Gtk.Box):
    __gsignals__ = {
        # (author_id) -> ask the catalogue to filter by this author
        "show-author-works": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # (author_id, starred) -> star state changed
        "star-changed": (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
    }

    # store columns
    COL_STAR = 0    # bool
    COL_NAME = 1    # display name
    COL_ID = 2      # author_id
    COL_COUNT = 3   # number of works (int)

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.workspace = None

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_border_width(6)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Filter authors\u2026")
        self.search.connect("search-changed", lambda _e: self.filter.refilter())
        toolbar.pack_start(self.search, True, True, 0)
        self.starred_only = Gtk.CheckButton(label="Starred only")
        self.starred_only.connect("toggled", lambda _b: self.filter.refilter())
        toolbar.pack_start(self.starred_only, False, False, 0)
        self.pack_start(toolbar, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.store = Gtk.ListStore(bool, str, str, int)
        self.filter = self.store.filter_new()
        self.filter.set_visible_func(self._visible)
        self.view = Gtk.TreeView(model=self.filter)
        self.view.set_headers_visible(True)

        # star column (toggle)
        star_r = Gtk.CellRendererToggle()
        star_r.set_activatable(True)
        star_r.connect("toggled", self._on_star_toggled)
        star_col = Gtk.TreeViewColumn("\u2605", star_r, active=self.COL_STAR)
        star_col.set_sort_column_id(self.COL_STAR)
        self.view.append_column(star_col)

        # name column
        name_r = Gtk.CellRendererText()
        name_r.set_property("ellipsize", Pango.EllipsizeMode.END)
        name_col = Gtk.TreeViewColumn("Author", name_r, text=self.COL_NAME)
        name_col.set_expand(True)
        name_col.set_sort_column_id(self.COL_NAME)
        self.view.append_column(name_col)

        # id column
        id_col = Gtk.TreeViewColumn("Author ID", Gtk.CellRendererText(),
                                    text=self.COL_ID)
        id_col.set_sort_column_id(self.COL_ID)
        self.view.append_column(id_col)

        # works count
        count_col = Gtk.TreeViewColumn("Works", Gtk.CellRendererText(),
                                       text=self.COL_COUNT)
        count_col.set_sort_column_id(self.COL_COUNT)
        self.view.append_column(count_col)

        self.view.connect("row-activated", self._on_row_activated)
        sw.add(self.view)
        self.pack_start(sw, True, True, 0)

        # bottom action
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bottom.set_border_width(6)
        self.show_works_btn = Gtk.Button(label="Show works in Catalogue")
        self.show_works_btn.set_image(Gtk.Image.new_from_icon_name(
            "edit-find", Gtk.IconSize.BUTTON))
        self.show_works_btn.set_always_show_image(True)
        self.show_works_btn.connect("clicked", self._on_show_works)
        bottom.pack_end(self.show_works_btn, False, False, 0)
        self.pack_start(bottom, False, False, 0)

    # ------------------------------------------------------------------
    def set_workspace(self, workspace):
        self.workspace = workspace
        self.reload()

    def reload(self):
        self.store.clear()
        if not self.workspace:
            return
        for a in self.workspace.all_authors():
            self.store.append([a.starred, a.display_name, a.author_id,
                               len(a.record_ids)])

    def _visible(self, model, it, _data):
        if self.starred_only.get_active() and not model[it][self.COL_STAR]:
            return False
        needle = self.search.get_text().strip().lower()
        if not needle:
            return True
        return (needle in (model[it][self.COL_NAME] or "").lower()
                or needle in (model[it][self.COL_ID] or "").lower())

    def _on_star_toggled(self, _renderer, filter_path):
        # map filtered path back to the child store
        child_path = self.filter.convert_path_to_child_path(
            Gtk.TreePath.new_from_string(filter_path))
        it = self.store.get_iter(child_path)
        new_val = not self.store[it][self.COL_STAR]
        self.store[it][self.COL_STAR] = new_val
        author_id = self.store[it][self.COL_ID]
        if self.workspace:
            self.workspace.set_author_starred(author_id, new_val)
        self.emit("star-changed", author_id, new_val)

    def _selected_author_id(self):
        model, it = self.view.get_selection().get_selected()
        if it:
            return model[it][self.COL_ID]
        return None

    def _on_row_activated(self, _view, _path, _col):
        aid = self._selected_author_id()
        if aid:
            self.emit("show-author-works", aid)

    def _on_show_works(self, _btn):
        aid = self._selected_author_id()
        if aid:
            self.emit("show-author-works", aid)
