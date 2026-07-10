"""Dialog for building a multi-key sort specification.

The user assembles an ordered list of (field, direction) rows. Order matters:
the first row is the primary sort key, the next is the tie-breaker, and so on.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from .catalogue_tab import SORT_LABELS


class SortDialog(Gtk.Dialog):
    # store columns: field_id, field_label, direction_label, ascending(bool)
    COL_FIELD_ID = 0
    COL_FIELD_LABEL = 1
    COL_DIR_LABEL = 2
    COL_ASC = 3

    def __init__(self, parent, current_spec):
        super().__init__(title="Sort", transient_for=parent, modal=True)
        self.set_default_size(460, 320)
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("C_lear", Gtk.ResponseType.REJECT)
        self.add_button("_Apply", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        self._id_to_label = dict(SORT_LABELS)

        area = self.get_content_area()
        area.set_border_width(10)
        area.set_spacing(6)

        info = Gtk.Label(xalign=0)
        info.set_markup(
            "Sort by the first row, breaking ties by each row below it. "
            "Use the arrows to reorder.")
        info.set_line_wrap(True)
        area.pack_start(info, False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        area.pack_start(body, True, True, 0)

        # the ordered list of sort keys
        self.store = Gtk.ListStore(str, str, str, bool)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_reorderable(True)

        field_r = Gtk.CellRendererText()
        self.view.append_column(
            Gtk.TreeViewColumn("Field", field_r, text=self.COL_FIELD_LABEL))
        dir_r = Gtk.CellRendererText()
        self.view.append_column(
            Gtk.TreeViewColumn("Direction", dir_r, text=self.COL_DIR_LABEL))

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(self.view)
        sw.set_hexpand(True)
        body.pack_start(sw, True, True, 0)

        # side buttons
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        up = Gtk.Button.new_from_icon_name("go-up", Gtk.IconSize.BUTTON)
        up.set_tooltip_text("Move up (higher priority)")
        up.connect("clicked", self._on_up)
        down = Gtk.Button.new_from_icon_name("go-down", Gtk.IconSize.BUTTON)
        down.set_tooltip_text("Move down (lower priority)")
        down.connect("clicked", self._on_down)
        toggle = Gtk.Button.new_from_icon_name("view-sort-descending",
                                               Gtk.IconSize.BUTTON)
        toggle.set_tooltip_text("Toggle ascending / descending")
        toggle.connect("clicked", self._on_toggle_dir)
        remove = Gtk.Button.new_from_icon_name("list-remove",
                                               Gtk.IconSize.BUTTON)
        remove.set_tooltip_text("Remove this key")
        remove.connect("clicked", self._on_remove)
        for b in (up, down, toggle, remove):
            side.pack_start(b, False, False, 0)
        body.pack_start(side, False, False, 0)

        # add-a-key row
        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add_combo = Gtk.ComboBoxText()
        for fid, label in SORT_LABELS:
            self.add_combo.append(fid, label)
        self.add_combo.set_active(0)
        add_btn = Gtk.Button.new_from_icon_name("list-add", Gtk.IconSize.BUTTON)
        add_btn.set_label("Add sort key")
        add_btn.set_always_show_image(True)
        add_btn.connect("clicked", self._on_add)
        add_row.pack_start(self.add_combo, True, True, 0)
        add_row.pack_start(add_btn, False, False, 0)
        area.pack_start(add_row, False, False, 0)

        # seed with current spec
        for fid, asc in (current_spec or []):
            if fid in self._id_to_label:
                self._append_row(fid, asc)

        self.show_all()

    # ------------------------------------------------------------------
    def _append_row(self, field_id, ascending):
        self.store.append([field_id, self._id_to_label.get(field_id, field_id),
                           _dir_label(ascending), ascending])

    def _on_add(self, _btn):
        fid = self.add_combo.get_active_id()
        if not fid:
            return
        # avoid duplicate fields
        for row in self.store:
            if row[self.COL_FIELD_ID] == fid:
                return
        self._append_row(fid, True)

    def _selected_iter(self):
        _model, it = self.view.get_selection().get_selected()
        return it

    def _on_remove(self, _btn):
        it = self._selected_iter()
        if it:
            self.store.remove(it)

    def _on_toggle_dir(self, _btn):
        it = self._selected_iter()
        if not it:
            return
        asc = not self.store[it][self.COL_ASC]
        self.store[it][self.COL_ASC] = asc
        self.store[it][self.COL_DIR_LABEL] = _dir_label(asc)

    def _on_up(self, _btn):
        it = self._selected_iter()
        if not it:
            return
        path = self.store.get_path(it)
        idx = path.get_indices()[0]
        if idx > 0:
            prev = self.store.get_iter(idx - 1)
            self.store.move_before(it, prev)

    def _on_down(self, _btn):
        it = self._selected_iter()
        if not it:
            return
        nxt = self.store.iter_next(it)
        if nxt:
            self.store.move_after(it, nxt)

    def get_spec(self):
        """Return the ordered [(field_id, ascending_bool), ...]."""
        return [(row[self.COL_FIELD_ID], row[self.COL_ASC])
                for row in self.store]


def _dir_label(ascending):
    return "Ascending" if ascending else "Descending"
