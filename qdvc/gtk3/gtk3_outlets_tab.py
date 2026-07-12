"""The Outlets tab: unique publication outlets (journals and proceedings)
derived from BibTeX, with starring, per-outlet nicknames, and per-outlet
J-Flags.

Like the Authors tab, the list is derived automatically from the workspace's
journal-article and proceedings records; each outlet is backed by a YAML file
under the workspace's ``outlets/`` folder. The user can star an outlet (making
it a quick filter in the Catalogue), give it a short nickname (which also
renames its YAML file and prefaces the Catalogue's Outlet column), and attach
one or more J-Flags chosen from the presets configured in Preferences.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, GObject  # noqa: E402


class OutletsTab(Gtk.Box):
    __gsignals__ = {
        # (outlet_id) -> ask the catalogue to filter by this outlet
        "show-outlet-works": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # (outlet_id, starred) -> star state changed
        "star-changed": (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
        # a nickname or J-Flag set changed (catalogue must re-render Pane 2)
        "outlet-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    # store columns
    COL_STAR = 0     # bool
    COL_NAME = 1     # display name (full outlet title)
    COL_NICK = 2     # nickname (may be empty)
    COL_JFLAGS = 3   # comma-joined J-Flags, alphabetical
    COL_ID = 4       # outlet_id (slug, stable key)
    COL_COUNT = 5    # number of records (int)

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.workspace = None
        # list of (flag, priority) presets from config, for the J-Flags editor
        self._jflag_presets = []

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar.set_border_width(6)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Filter outlets\u2026")
        self.search.connect("search-changed", lambda _e: self.filter.refilter())
        toolbar.pack_start(self.search, True, True, 0)
        self.starred_only = Gtk.CheckButton(label="Starred only")
        self.starred_only.connect("toggled", lambda _b: self.filter.refilter())
        toolbar.pack_start(self.starred_only, False, False, 0)
        self.pack_start(toolbar, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.store = Gtk.ListStore(bool, str, str, str, str, int)
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
        name_col = Gtk.TreeViewColumn("Outlet", name_r, text=self.COL_NAME)
        name_col.set_expand(True)
        name_col.set_sort_column_id(self.COL_NAME)
        self.view.append_column(name_col)

        # nickname column
        nick_col = Gtk.TreeViewColumn("Nickname", Gtk.CellRendererText(),
                                      text=self.COL_NICK)
        nick_col.set_sort_column_id(self.COL_NICK)
        self.view.append_column(nick_col)

        # J-Flags column
        jflags_col = Gtk.TreeViewColumn("J-Flags", Gtk.CellRendererText(),
                                        text=self.COL_JFLAGS)
        jflags_col.set_sort_column_id(self.COL_JFLAGS)
        self.view.append_column(jflags_col)

        # records count
        count_col = Gtk.TreeViewColumn("Records", Gtk.CellRendererText(),
                                       text=self.COL_COUNT)
        count_col.set_sort_column_id(self.COL_COUNT)
        self.view.append_column(count_col)

        self.view.connect("row-activated", self._on_row_activated)
        sw.add(self.view)
        self.pack_start(sw, True, True, 0)

        # bottom actions
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bottom.set_border_width(6)
        self.nickname_btn = Gtk.Button(label="Set nickname\u2026")
        self.nickname_btn.set_image(Gtk.Image.new_from_icon_name(
            "document-edit", Gtk.IconSize.BUTTON))
        self.nickname_btn.set_always_show_image(True)
        self.nickname_btn.connect("clicked", self._on_set_nickname)
        bottom.pack_start(self.nickname_btn, False, False, 0)

        self.jflags_btn = Gtk.Button(label="Set J-Flags\u2026")
        self.jflags_btn.set_image(Gtk.Image.new_from_icon_name(
            "emblem-important", Gtk.IconSize.BUTTON))
        self.jflags_btn.set_always_show_image(True)
        self.jflags_btn.connect("clicked", self._on_set_jflags)
        bottom.pack_start(self.jflags_btn, False, False, 0)

        self.show_works_btn = Gtk.Button(label="Show records in Catalogue")
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

    def set_jflag_presets(self, presets):
        """presets: list of (flag, priority). Used to offer choices in the
        J-Flags editor."""
        self._jflag_presets = list(presets or [])

    def reload(self):
        self.store.clear()
        if not self.workspace:
            return
        for o in self.workspace.all_outlets():
            self.store.append([o.starred, o.display_name, o.nickname,
                               ", ".join(o.sorted_jflags()), o.outlet_id,
                               len(o.record_ids)])

    def reveal_outlet(self, outlet_id):
        """Select the row for *outlet_id* and scroll it into view. Clears any
        active text/star filter first so the row is guaranteed visible. Used
        when jumping here from the Catalogue's 'Go to outlet' action."""
        # Clear filters so the target row is present in the filtered view.
        self.search.set_text("")
        self.starred_only.set_active(False)
        self.filter.refilter()
        for row in self.filter:
            if row[self.COL_ID] == outlet_id:
                self.view.get_selection().select_iter(row.iter)
                path = row.path
                self.view.scroll_to_cell(path, None, True, 0.5, 0.0)
                self.view.set_cursor(path, None, False)
                self.view.grab_focus()
                return True
        return False

    def _visible(self, model, it, _data):
        if self.starred_only.get_active() and not model[it][self.COL_STAR]:
            return False
        needle = self.search.get_text().strip().lower()
        if not needle:
            return True
        return (needle in (model[it][self.COL_NAME] or "").lower()
                or needle in (model[it][self.COL_NICK] or "").lower())

    def _on_star_toggled(self, _renderer, filter_path):
        # map filtered path back to the child store
        child_path = self.filter.convert_path_to_child_path(
            Gtk.TreePath.new_from_string(filter_path))
        it = self.store.get_iter(child_path)
        new_val = not self.store[it][self.COL_STAR]
        self.store[it][self.COL_STAR] = new_val
        outlet_id = self.store[it][self.COL_ID]
        if self.workspace:
            self.workspace.set_outlet_starred(outlet_id, new_val)
        self.emit("star-changed", outlet_id, new_val)

    def _selected_outlet_id(self):
        model, it = self.view.get_selection().get_selected()
        if it:
            return model[it][self.COL_ID]
        return None

    def _on_row_activated(self, _view, _path, _col):
        oid = self._selected_outlet_id()
        if oid:
            self.emit("show-outlet-works", oid)

    def _on_show_works(self, _btn):
        oid = self._selected_outlet_id()
        if oid:
            self.emit("show-outlet-works", oid)

    # ------------------------------------------------------------------
    # Nickname
    # ------------------------------------------------------------------
    def _on_set_nickname(self, _btn):
        oid = self._selected_outlet_id()
        if not oid or not self.workspace:
            return
        outlet = self.workspace.outlets.get(oid)
        if not outlet:
            return
        dlg = Gtk.Dialog(title="Set outlet nickname",
                         transient_for=self.get_toplevel(), modal=True)
        dlg.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("_Save", Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        area = dlg.get_content_area()
        area.set_border_width(10)
        area.set_spacing(6)
        area.add(Gtk.Label(label=f"Nickname for '{outlet.name}':", xalign=0))
        entry = Gtk.Entry()
        entry.set_text(outlet.nickname)
        entry.set_placeholder_text("e.g. JBIB (leave blank to clear)")
        entry.set_activates_default(True)
        area.add(entry)
        hint = Gtk.Label(xalign=0)
        hint.get_style_context().add_class("dim-label")
        hint.set_markup(
            "<small>The nickname renames the outlet's YAML file and appears "
            "in bold before the outlet name in the Catalogue's Outlet "
            "column. Letters A-Z/a-z only.</small>")
        hint.set_line_wrap(True)
        area.add(hint)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            nickname = entry.get_text().strip()
            dlg.destroy()
            try:
                self.workspace.set_outlet_nickname(oid, nickname)
            except ValueError as exc:
                self._warn(str(exc))
                return
            self.reload()
            self.emit("outlet-changed")
        else:
            dlg.destroy()

    def _warn(self, message):
        dlg = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), modal=True,
            message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK,
            text="Could not set nickname")
        dlg.format_secondary_text(message)
        dlg.run()
        dlg.destroy()

    # ------------------------------------------------------------------
    # J-Flags
    # ------------------------------------------------------------------
    def _on_set_jflags(self, _btn):
        oid = self._selected_outlet_id()
        if not oid or not self.workspace:
            return
        outlet = self.workspace.outlets.get(oid)
        if not outlet:
            return
        current = set(outlet.sorted_jflags())
        # Offer every preset flag plus any flag already on the outlet that is
        # not a preset (so hand-added flags are not silently dropped).
        preset_flags = [flag for flag, _prio in self._jflag_presets]
        extra = [f for f in outlet.sorted_jflags() if f not in preset_flags]
        all_flags = preset_flags + extra

        dlg = Gtk.Dialog(title=f"J-Flags for {outlet.name}",
                         transient_for=self.get_toplevel(), modal=True)
        dlg.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("_Save", Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        area = dlg.get_content_area()
        area.set_border_width(10)
        area.set_spacing(4)
        if all_flags:
            area.add(Gtk.Label(label="Select the J-Flags for this outlet:",
                               xalign=0))
        else:
            area.add(Gtk.Label(
                label="No J-Flags are configured. Add presets in "
                      "Preferences \u2192 J-Flags.", xalign=0))
        checks = {}
        for flag in all_flags:
            cb = Gtk.CheckButton(label=flag)
            cb.set_active(flag in current)
            area.add(cb)
            checks[flag] = cb
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            chosen = [flag for flag, cb in checks.items() if cb.get_active()]
            dlg.destroy()
            self.workspace.set_outlet_jflags(oid, chosen)
            self.reload()
            self.emit("outlet-changed")
        else:
            dlg.destroy()
