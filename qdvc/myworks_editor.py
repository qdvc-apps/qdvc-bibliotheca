"""Dialog for editing a 'my work': its citation list and published version."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


class MyWorkEditor(Gtk.Dialog):
    """Edit a MyWork's name, cited records, and published_as field."""

    def __init__(self, parent, workspace, work):
        super().__init__(title=f"Edit Work \u2014 {work.name}",
                         transient_for=parent, modal=True)
        self.workspace = workspace
        self.work = work
        self.set_default_size(640, 480)

        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(8)
        box.set_border_width(10)

        # --- name --------------------------------------------------------
        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name_row.pack_start(Gtk.Label(label="Name:"), False, False, 0)
        self.name_entry = Gtk.Entry()
        self.name_entry.set_text(work.name)
        name_row.pack_start(self.name_entry, True, True, 0)
        box.pack_start(name_row, False, False, 0)

        # --- published_as ------------------------------------------------
        pub_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pub_row.pack_start(Gtk.Label(label="Published as:"), False, False, 0)
        self.pub_combo = Gtk.ComboBoxText.new_with_entry()
        self.pub_combo.append_text("")  # allow "none"
        self._all_ids = sorted(workspace.records.keys(), key=str.lower)
        for bid in self._all_ids:
            self.pub_combo.append_text(bid)
        if work.published_as:
            self.pub_combo.get_child().set_text(work.published_as)
        pub_row.pack_start(self.pub_combo, True, True, 0)
        box.pack_start(pub_row, False, False, 0)

        # --- two-list citation editor -----------------------------------
        lists = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lists.set_homogeneous(True)
        box.pack_start(lists, True, True, 0)

        # cited (left)
        cited_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cited_box.pack_start(_bold("Cited in this work"), False, False, 0)
        self.cited_store = Gtk.ListStore(str)
        self.cited_view = self._make_list(self.cited_store)
        cited_box.pack_start(self._scroller(self.cited_view), True, True, 0)
        lists.pack_start(cited_box, True, True, 0)

        # buttons (middle)
        btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        btns.set_valign(Gtk.Align.CENTER)
        add_btn = Gtk.Button.new_from_icon_name(
            "go-previous-symbolic", Gtk.IconSize.BUTTON)
        add_btn.set_tooltip_text("Add selected to this work")
        add_btn.connect("clicked", self._on_add)
        rm_btn = Gtk.Button.new_from_icon_name(
            "go-next-symbolic", Gtk.IconSize.BUTTON)
        rm_btn.set_tooltip_text("Remove selected from this work")
        rm_btn.connect("clicked", self._on_remove)
        btns.pack_start(add_btn, False, False, 0)
        btns.pack_start(rm_btn, False, False, 0)
        lists.pack_start(btns, False, False, 0)

        # available (right)
        avail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        avail_box.pack_start(_bold("Available records"), False, False, 0)
        self.avail_filter_entry = Gtk.SearchEntry()
        self.avail_filter_entry.set_placeholder_text("Filter\u2026")
        self.avail_filter_entry.connect("search-changed",
                                        lambda _e: self.avail_filter.refilter())
        avail_box.pack_start(self.avail_filter_entry, False, False, 0)
        self.avail_store = Gtk.ListStore(str)
        self.avail_filter = self.avail_store.filter_new()
        self.avail_filter.set_visible_func(self._avail_visible)
        self.avail_view = self._make_list(self.avail_filter)
        avail_box.pack_start(self._scroller(self.avail_view), True, True, 0)
        lists.pack_start(avail_box, True, True, 0)

        self._populate()
        self.show_all()

    # ------------------------------------------------------------------
    @staticmethod
    def _make_list(model):
        view = Gtk.TreeView(model=model)
        view.set_headers_visible(False)
        view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        col = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0)
        view.append_column(col)
        return view

    @staticmethod
    def _scroller(view):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(view)
        return sw

    def _populate(self):
        cited = sorted({c for c in self.work.cites}, key=str.lower)
        cited_set = set(cited)
        self.cited_store.clear()
        for c in cited:
            self.cited_store.append([c])
        self._refresh_available(cited_set)

    def _refresh_available(self, cited_set):
        self.avail_store.clear()
        for bid in self._all_ids:  # _all_ids is already sorted
            if bid not in cited_set:
                self.avail_store.append([bid])

    def _avail_visible(self, model, it, _data):
        needle = self.avail_filter_entry.get_text().strip().lower()
        if not needle:
            return True
        return needle in (model[it][0] or "").lower()

    def _insert_cited_sorted(self, bid):
        """Insert bid into the cited store at its alphabetical position."""
        low = bid.lower()
        pos = 0
        for i, row in enumerate(self.cited_store):
            if row[0].lower() < low:
                pos = i + 1
            else:
                break
        self.cited_store.insert(pos, [bid])

    def _on_add(self, _btn):
        model, paths = self.avail_view.get_selection().get_selected_rows()
        ids = [model[p][0] for p in paths]
        existing = {row[0] for row in self.cited_store}
        for bid in ids:
            if bid not in existing:
                self._insert_cited_sorted(bid)
                existing.add(bid)
        self._refresh_available(existing)

    def _on_remove(self, _btn):
        model, paths = self.cited_view.get_selection().get_selected_rows()
        for ref in reversed([Gtk.TreeRowReference.new(model, p)
                             for p in paths]):
            it = model.get_iter(ref.get_path())
            model.remove(it)
        cited_now = {row[0] for row in self.cited_store}
        self._refresh_available(cited_now)

    # ------------------------------------------------------------------
    def apply(self) -> None:
        """Write edited values back to the MyWork and save it."""
        self.work.name = self.name_entry.get_text().strip() or self.work.name
        pub = self.pub_combo.get_child().get_text().strip()
        self.work.published_as = pub or None
        # cited store is already alphabetical; MyWork.save re-canonicalises too.
        self.work.cites = [row[0] for row in self.cited_store]
        self.work.save()


def _bold(text):
    lbl = Gtk.Label(xalign=0)
    lbl.set_markup(f"<b>{text}</b>")
    return lbl
