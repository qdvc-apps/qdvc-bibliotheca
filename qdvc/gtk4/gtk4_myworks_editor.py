"""Edit a 'my work' (GTK4): its name, published_as, and cited-records list.

A two-list transfer editor (cited on the left, available on the right) with
add/remove buttons, plus a name entry and a "published as" picker. Save/Cancel
in the header bar; on Save the values are written back and ``on_apply()`` is
called.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, GObject, Adw  # noqa: E402


class _IdItem(GObject.Object):
    __gtype_name__ = "QdvcIdItem"

    def __init__(self, bid):
        super().__init__()
        self.bid = bid


class MyWorkEditor(Adw.Window):
    def __init__(self, parent, workspace, work, on_apply=None):
        super().__init__(transient_for=parent, modal=True,
                         title=f"Edit Work \u2014 {work.name}")
        self.workspace = workspace
        self.work = work
        self._on_apply = on_apply
        self.set_default_size(660, 500)
        self._all_ids = sorted(workspace.records.keys(), key=str.lower)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel)
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_save_clicked)
        header.pack_end(save)
        toolbar.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(10)

        name_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name_row.append(Gtk.Label(label="Name:"))
        self.name_entry = Gtk.Entry()
        self.name_entry.set_hexpand(True)
        self.name_entry.set_text(work.name)
        name_row.append(self.name_entry)
        box.append(name_row)

        pub_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pub_row.append(Gtk.Label(label="Published as:"))
        self.pub_entry = Gtk.Entry()
        self.pub_entry.set_hexpand(True)
        self.pub_entry.set_placeholder_text("a Bibliotheca ID, or blank")
        if work.published_as:
            self.pub_entry.set_text(work.published_as)
        pub_row.append(self.pub_entry)
        # dropdown to pick an existing id into the entry
        self._pub_model = Gio.ListStore(item_type=_IdItem)
        self._pub_model.append(_IdItem(""))
        for bid in self._all_ids:
            self._pub_model.append(_IdItem(bid))
        self.pub_dropdown = Gtk.DropDown(model=self._pub_model)
        self._setup_id_factory(self.pub_dropdown)
        self.pub_dropdown.connect("notify::selected", self._on_pub_picked)
        pub_row.append(self.pub_dropdown)
        box.append(pub_row)

        lists = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lists.set_homogeneous(True)
        lists.set_vexpand(True)
        box.append(lists)

        # cited (left)
        cited_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cited_box.append(_bold("Cited in this work"))
        self.cited_store = Gio.ListStore(item_type=_IdItem)
        self.cited_selection = Gtk.MultiSelection(model=self.cited_store)
        self.cited_view = self._make_list(self.cited_selection)
        cited_box.append(self._scroller(self.cited_view))
        lists.append(cited_box)

        btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        btns.set_valign(Gtk.Align.CENTER)
        add_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        add_btn.set_tooltip_text("Add selected to this work")
        add_btn.connect("clicked", self._on_add)
        rm_btn = Gtk.Button.new_from_icon_name("go-next-symbolic")
        rm_btn.set_tooltip_text("Remove selected from this work")
        rm_btn.connect("clicked", self._on_remove)
        btns.append(add_btn)
        btns.append(rm_btn)
        lists.append(btns)

        # available (right)
        avail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        avail_box.append(_bold("Available records"))
        self.avail_filter_entry = Gtk.SearchEntry()
        self.avail_filter_entry.set_placeholder_text("Filter\u2026")
        self.avail_filter_entry.connect(
            "search-changed", lambda _e: self.avail_filter.changed(
                Gtk.FilterChange.DIFFERENT))
        avail_box.append(self.avail_filter_entry)
        self.avail_store = Gio.ListStore(item_type=_IdItem)
        self.avail_filter = Gtk.CustomFilter.new(self._avail_visible, None)
        self.avail_filter_model = Gtk.FilterListModel(
            model=self.avail_store, filter=self.avail_filter)
        self.avail_selection = Gtk.MultiSelection(
            model=self.avail_filter_model)
        self.avail_view = self._make_list(self.avail_selection)
        avail_box.append(self._scroller(self.avail_view))
        lists.append(avail_box)

        toolbar.set_content(box)
        self.set_content(toolbar)

        self._populate()

    # ------------------------------------------------------------------
    def _make_list(self, selection):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup",
                        lambda _f, li: li.set_child(Gtk.Label(xalign=0)))
        factory.connect(
            "bind", lambda _f, li: li.get_child().set_text(
                li.get_item().bid))
        view = Gtk.ListView(model=selection, factory=factory)
        view.set_vexpand(True)
        return view

    @staticmethod
    def _scroller(view):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True)
        sw.set_child(view)
        return sw

    def _setup_id_factory(self, dropdown):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup",
                        lambda _f, li: li.set_child(Gtk.Label(xalign=0)))
        factory.connect(
            "bind", lambda _f, li: li.get_child().set_text(
                li.get_item().bid or "(none)"))
        dropdown.set_factory(factory)

    def _on_pub_picked(self, *_a):
        item = self.pub_dropdown.get_selected_item()
        if item is not None:
            self.pub_entry.set_text(item.bid)

    def _populate(self):
        cited = sorted({c for c in self.work.cites}, key=str.lower)
        self.cited_store.remove_all()
        for c in cited:
            self.cited_store.append(_IdItem(c))
        self._refresh_available(set(cited))

    def _refresh_available(self, cited_set):
        self.avail_store.remove_all()
        for bid in self._all_ids:
            if bid not in cited_set:
                self.avail_store.append(_IdItem(bid))

    def _avail_visible(self, item, _user_data=None):
        needle = self.avail_filter_entry.get_text().strip().lower()
        if not needle:
            return True
        return needle in (item.bid or "").lower()

    def _cited_ids(self):
        return [self.cited_store.get_item(i).bid
                for i in range(self.cited_store.get_n_items())]

    def _insert_cited_sorted(self, bid):
        low = bid.lower()
        pos = self.cited_store.get_n_items()
        for i in range(self.cited_store.get_n_items()):
            if self.cited_store.get_item(i).bid.lower() >= low:
                pos = i
                break
        self.cited_store.insert(pos, _IdItem(bid))

    def _selected_ids(self, selection, model):
        ids = []
        bitset = selection.get_selection()
        n = bitset.get_size()
        for i in range(n):
            pos = bitset.get_nth(i)
            item = model.get_item(pos)
            if item is not None:
                ids.append(item.bid)
        return ids

    def _on_add(self, _btn):
        ids = self._selected_ids(self.avail_selection, self.avail_filter_model)
        existing = set(self._cited_ids())
        for bid in ids:
            if bid not in existing:
                self._insert_cited_sorted(bid)
                existing.add(bid)
        self._refresh_available(existing)

    def _on_remove(self, _btn):
        ids = set(self._selected_ids(self.cited_selection, self.cited_store))
        keep = [bid for bid in self._cited_ids() if bid not in ids]
        self.cited_store.remove_all()
        for bid in keep:
            self.cited_store.append(_IdItem(bid))
        self._refresh_available(set(keep))

    # ------------------------------------------------------------------
    def apply(self) -> None:
        self.work.name = self.name_entry.get_text().strip() or self.work.name
        pub = self.pub_entry.get_text().strip()
        self.work.published_as = pub or None
        self.work.cites = self._cited_ids()
        self.work.save()

    def _on_save_clicked(self, _btn):
        self.apply()
        self.close()
        if self._on_apply:
            self._on_apply()


def _bold(text):
    lbl = Gtk.Label(xalign=0)
    lbl.set_markup(f"<b>{text}</b>")
    return lbl
