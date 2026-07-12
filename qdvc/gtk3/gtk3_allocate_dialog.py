"""Dialog to allocate one or more records to the user's "my works".

Shows a checklist of existing works (with a check pre-ticked where the record
is already cited) and an option to create a new work. Used both from the
Catalogue record right-click menu and from the import flow.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


class AllocateDialog(Gtk.Dialog):
    # store columns: active(bool), work_label(str), work_key(str)
    COL_ACTIVE = 0
    COL_LABEL = 1
    COL_KEY = 2

    def __init__(self, parent, workspace, bibliotheca_ids, heading=None):
        super().__init__(title="Allocate to My Works", transient_for=parent,
                         modal=True)
        self.workspace = workspace
        self.bibliotheca_ids = list(bibliotheca_ids)
        self.set_default_size(440, 400)
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_Apply", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        area = self.get_content_area()
        area.set_border_width(10)
        area.set_spacing(6)

        if heading is None:
            if len(self.bibliotheca_ids) == 1:
                heading = (f"Allocate <b>{_esc(self.bibliotheca_ids[0])}</b> "
                           "to:")
            else:
                heading = (f"Allocate <b>{len(self.bibliotheca_ids)}</b> "
                           "records to:")
        lbl = Gtk.Label(xalign=0)
        lbl.set_markup(heading)
        lbl.set_line_wrap(True)
        area.pack_start(lbl, False, False, 0)

        # checklist of works
        self.store = Gtk.ListStore(bool, str, str)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_visible(False)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._on_toggled)
        self.view.append_column(
            Gtk.TreeViewColumn("", toggle, active=self.COL_ACTIVE))
        self.view.append_column(
            Gtk.TreeViewColumn("", Gtk.CellRendererText(),
                               text=self.COL_LABEL))
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(self.view)
        area.pack_start(sw, True, True, 0)

        self._populate()

        # create-a-new-work row
        new_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        new_row.pack_start(Gtk.Label(label="New work:"), False, False, 0)
        self.new_entry = Gtk.Entry()
        self.new_entry.set_placeholder_text("Name a new work to create\u2026")
        new_row.pack_start(self.new_entry, True, True, 0)
        area.pack_start(new_row, False, False, 0)

        note = Gtk.Label(xalign=0)
        note.get_style_context().add_class("dim-label")
        note.set_markup(
            "<small>Ticked works will include the record(s). A pre-ticked "
            "work already cites them; unticking does not remove them.</small>")
        note.set_line_wrap(True)
        area.pack_start(note, False, False, 0)

        self.show_all()

    def _populate(self):
        self.store.clear()
        # a record is "already in" a work if every selected id is cited there
        id_set = set(self.bibliotheca_ids)
        for key, work in sorted(self.workspace.my_works.items(),
                                key=lambda kv: kv[1].name.lower()):
            already = id_set.issubset(set(work.cites)) and bool(id_set)
            self.store.append([already, work.name, key])

    def _on_toggled(self, _renderer, path):
        self.store[path][self.COL_ACTIVE] = \
            not self.store[path][self.COL_ACTIVE]

    def apply(self) -> int:
        """Create the optional new work, allocate to every ticked work.

        Returns the number of (work, record) allocations performed.
        """
        # create a new work first, if named, and treat it as ticked
        new_name = self.new_entry.get_text().strip()
        target_keys = [row[self.COL_KEY] for row in self.store
                       if row[self.COL_ACTIVE]]
        if new_name:
            work = self.workspace.create_my_work(new_name)
            # find its key
            for k, w in self.workspace.my_works.items():
                if w is work:
                    target_keys.append(k)
                    break

        total = 0
        for key in target_keys:
            total += self.workspace.allocate_to_work(
                key, self.bibliotheca_ids)
        return total


def _esc(text):
    from gi.repository import GObject
    return GObject.markup_escape_text(str(text))
