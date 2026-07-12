"""Multi-key sort dialog (GTK4).

The user assembles an ordered list of (field, direction) rows; the first row is
the primary key, each below it a tie-breaker. Apply/Clear/Cancel live in the
header bar; results are delivered via ``on_apply(spec)`` / ``on_clear()``
callbacks (no ``run()`` in GTK4).
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, GObject, Adw  # noqa: E402

from ..catalogue_sort import SORT_LABELS  # noqa: E402


class _SortKeyItem(GObject.Object):
    __gtype_name__ = "QdvcSortKeyItem"

    def __init__(self, field_id, label, ascending):
        super().__init__()
        self.field_id = field_id
        self.label = label
        self.ascending = ascending

    @property
    def dir_label(self):
        return "Ascending" if self.ascending else "Descending"


class SortDialog(Adw.Window):
    def __init__(self, parent, current_spec, on_apply=None, on_clear=None):
        super().__init__(transient_for=parent, modal=True, title="Sort")
        self.set_default_size(480, 360)
        self._on_apply = on_apply
        self._on_clear = on_clear
        self._id_to_label = dict(SORT_LABELS)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel)
        clear = Gtk.Button(label="Clear")
        clear.connect("clicked", self._on_clear_clicked)
        header.pack_start(clear)
        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_clicked)
        header.pack_end(apply_btn)
        toolbar.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ("top", "bottom", "start", "end"):
            getattr(body, f"set_margin_{m}")(10)

        info = Gtk.Label(xalign=0)
        info.set_markup("Sort by the first row, breaking ties by each row "
                        "below it. Use the arrows to reorder.")
        info.set_wrap(True)
        body.append(info)

        middle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        middle.set_vexpand(True)

        self.store = Gio.ListStore(item_type=_SortKeyItem)
        self.selection = Gtk.SingleSelection(model=self.store)
        self.column_view = Gtk.ColumnView(model=self.selection)
        self.column_view.append_column(self._col("Field", "label"))
        self.column_view.append_column(self._col("Direction", "dir_label"))
        self.column_view.set_vexpand(True)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_hexpand(True)
        sw.set_child(self.column_view)
        middle.append(sw)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for icon, tip, cb in (
                ("go-up-symbolic", "Move up (higher priority)", self._on_up),
                ("go-down-symbolic", "Move down (lower priority)",
                 self._on_down),
                ("view-sort-descending-symbolic",
                 "Toggle ascending / descending", self._on_toggle_dir),
                ("list-remove-symbolic", "Remove this key", self._on_remove)):
            b = Gtk.Button.new_from_icon_name(icon)
            b.set_tooltip_text(tip)
            b.connect("clicked", cb)
            side.append(b)
        middle.append(side)
        body.append(middle)

        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._add_model = Gio.ListStore(item_type=_SortKeyItem)
        for fid, label in SORT_LABELS:
            self._add_model.append(_SortKeyItem(fid, label, True))
        self.add_dropdown = Gtk.DropDown(model=self._add_model)
        self.add_dropdown.set_hexpand(True)
        self._setup_add_factory()
        add_row.append(self.add_dropdown)
        add_btn = Gtk.Button(label="Add sort key")
        add_btn.connect("clicked", self._on_add)
        add_row.append(add_btn)
        body.append(add_row)

        toolbar.set_content(body)
        self.set_content(toolbar)

        for fid, asc in (current_spec or []):
            if fid in self._id_to_label:
                self.store.append(_SortKeyItem(
                    fid, self._id_to_label[fid], asc))

    def _col(self, title, attr):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup",
                        lambda _f, li: li.set_child(Gtk.Label(xalign=0)))

        def bind(_f, li):
            li.get_child().set_text(getattr(li.get_item(), attr, "") or "")
        factory.connect("bind", bind)
        col = Gtk.ColumnViewColumn(title=title, factory=factory)
        col.set_expand(True)
        return col

    def _setup_add_factory(self):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup",
                        lambda _f, li: li.set_child(Gtk.Label(xalign=0)))

        def bind(_f, li):
            item = li.get_item()
            li.get_child().set_text(item.label if item else "")
        factory.connect("bind", bind)
        self.add_dropdown.set_factory(factory)

    def _selected_index(self):
        idx = self.selection.get_selected()
        return idx if idx != Gtk.INVALID_LIST_POSITION else None

    def _on_add(self, _btn):
        item = self.add_dropdown.get_selected_item()
        if not item:
            return
        for i in range(self.store.get_n_items()):
            if self.store.get_item(i).field_id == item.field_id:
                return  # no duplicate fields
        self.store.append(_SortKeyItem(item.field_id, item.label, True))

    def _on_remove(self, _btn):
        idx = self._selected_index()
        if idx is not None:
            self.store.remove(idx)

    def _on_toggle_dir(self, _btn):
        idx = self._selected_index()
        if idx is None:
            return
        item = self.store.get_item(idx)
        item.ascending = not item.ascending
        self.store.items_changed(idx, 1, 1)
        self.selection.set_selected(idx)

    def _on_up(self, _btn):
        idx = self._selected_index()
        if idx is None or idx == 0:
            return
        item = self.store.get_item(idx)
        self.store.remove(idx)
        self.store.insert(idx - 1, item)
        self.selection.set_selected(idx - 1)

    def _on_down(self, _btn):
        idx = self._selected_index()
        if idx is None or idx >= self.store.get_n_items() - 1:
            return
        item = self.store.get_item(idx)
        self.store.remove(idx)
        self.store.insert(idx + 1, item)
        self.selection.set_selected(idx + 1)

    def get_spec(self):
        return [(self.store.get_item(i).field_id,
                 self.store.get_item(i).ascending)
                for i in range(self.store.get_n_items())]

    def _on_apply_clicked(self, _btn):
        spec = self.get_spec()
        self.close()
        if self._on_apply:
            self._on_apply(spec)

    def _on_clear_clicked(self, _btn):
        self.close()
        if self._on_clear:
            self._on_clear()
