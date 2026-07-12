"""Allocate record(s) to "my works" (GTK4).

A checklist of existing works (pre-ticked where the record is already cited)
plus an optional new-work entry. Apply/Cancel in the header bar; the result is
applied on Apply and reported via ``on_done(total)``.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, GObject, Adw  # noqa: E402


class _WorkCheckItem(GObject.Object):
    __gtype_name__ = "QdvcWorkCheckItem"

    def __init__(self, active, label, key):
        super().__init__()
        self.active = active
        self.label = label
        self.key = key


class AllocateDialog(Adw.Window):
    def __init__(self, parent, workspace, bibliotheca_ids, on_done=None):
        super().__init__(transient_for=parent, modal=True,
                         title="Allocate to My Works")
        self.workspace = workspace
        self.bibliotheca_ids = list(bibliotheca_ids)
        self._on_done = on_done
        self.set_default_size(440, 420)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel)
        apply_btn = Gtk.Button(label="Apply")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_clicked)
        header.pack_end(apply_btn)
        toolbar.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ("top", "bottom", "start", "end"):
            getattr(body, f"set_margin_{m}")(10)

        if len(self.bibliotheca_ids) == 1:
            heading = (f"Allocate <b>{_esc(self.bibliotheca_ids[0])}</b> to:")
        else:
            heading = (f"Allocate <b>{len(self.bibliotheca_ids)}</b> "
                       "records to:")
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup(heading)
        lbl.set_wrap(True)
        body.append(lbl)

        self.store = Gio.ListStore(item_type=_WorkCheckItem)
        self.selection = Gtk.NoSelection(model=self.store)
        self.column_view = Gtk.ColumnView(model=self.selection)
        self.column_view.set_vexpand(True)
        self.column_view.append_column(self._check_column())
        self.column_view.append_column(self._label_column())
        self.column_view.set_show_column_separators(False)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True)
        sw.set_child(self.column_view)
        body.append(sw)

        self._populate()

        new_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        new_row.append(Gtk.Label(label="New work:"))
        self.new_entry = Gtk.Entry()
        self.new_entry.set_hexpand(True)
        self.new_entry.set_placeholder_text("Name a new work to create\u2026")
        new_row.append(self.new_entry)
        body.append(new_row)

        note = Gtk.Label(xalign=0)
        note.add_css_class("dim-label")
        note.set_markup(
            "<small>Ticked works will include the record(s). A pre-ticked "
            "work already cites them; unticking does not remove them.</small>")
        note.set_wrap(True)
        body.append(note)

        toolbar.set_content(body)
        self.set_content(toolbar)

    def _check_column(self):
        factory = Gtk.SignalListItemFactory()

        def setup(_f, li):
            li.set_child(Gtk.CheckButton())

        def bind(_f, li):
            check = li.get_child()
            item = li.get_item()
            check.set_active(item.active)
            handler = getattr(check, "_qdvc_handler", None)
            if handler is not None:
                check.disconnect(handler)

            def _toggled(btn):
                item.active = btn.get_active()
            check._qdvc_handler = check.connect("toggled", _toggled)
        factory.connect("setup", setup)
        factory.connect("bind", bind)
        col = Gtk.ColumnViewColumn(title="", factory=factory)
        col.set_fixed_width(40)
        return col

    def _label_column(self):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup",
                        lambda _f, li: li.set_child(Gtk.Label(xalign=0)))

        def bind(_f, li):
            li.get_child().set_text(li.get_item().label)
        factory.connect("bind", bind)
        col = Gtk.ColumnViewColumn(title="", factory=factory)
        col.set_expand(True)
        return col

    def _populate(self):
        self.store.remove_all()
        id_set = set(self.bibliotheca_ids)
        for key, work in sorted(self.workspace.my_works.items(),
                                key=lambda kv: kv[1].name.lower()):
            already = bool(id_set) and id_set.issubset(set(work.cites))
            self.store.append(_WorkCheckItem(already, work.name, key))

    def apply(self) -> int:
        new_name = self.new_entry.get_text().strip()
        target_keys = [self.store.get_item(i).key
                       for i in range(self.store.get_n_items())
                       if self.store.get_item(i).active]
        if new_name:
            work = self.workspace.create_my_work(new_name)
            for k, w in self.workspace.my_works.items():
                if w is work:
                    target_keys.append(k)
                    break
        total = 0
        for key in target_keys:
            total += self.workspace.allocate_to_work(key, self.bibliotheca_ids)
        return total

    def _on_apply_clicked(self, _btn):
        try:
            total = self.apply()
        except Exception:  # noqa: BLE001
            total = 0
        self.close()
        if self._on_done:
            self._on_done(total)


def _esc(text):
    return GObject.markup_escape_text(str(text))
