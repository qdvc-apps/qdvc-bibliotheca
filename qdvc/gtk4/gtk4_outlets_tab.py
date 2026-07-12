"""The Outlets view (GTK4): journals + proceedings derived from BibTeX, with
starring, per-outlet nicknames, and per-outlet J-Flags.

Same ``Gtk.ColumnView`` + filter/selection harness as the Authors view, plus a
nickname prompt and a J-Flags checklist (both async ``Adw`` dialogs).
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, Adw, GObject  # noqa: E402

from . import gtk4_widgets as W  # noqa: E402
from . import gtk4_dialogs as dialogs  # noqa: E402


class _OutletItem(GObject.Object):
    __gtype_name__ = "QdvcOutletItem"

    def __init__(self, outlet):
        super().__init__()
        self.outlet_id = outlet.outlet_id
        self.name = outlet.display_name
        self.nickname = outlet.nickname or ""
        self.jflags = ", ".join(outlet.sorted_jflags())
        self.count = len(outlet.record_ids)
        self.starred = outlet.starred


class OutletsView(Gtk.Box):
    __gsignals__ = {
        "show-outlet-works": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "star-changed": (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
        "outlet-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, window=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.workspace = None
        self._jflag_presets = []

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for m in ("top", "bottom", "start", "end"):
            getattr(toolbar, f"set_margin_{m}")(6)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Filter outlets\u2026")
        self.search.set_hexpand(True)
        self.search.connect("search-changed", lambda _e: self._refilter())
        toolbar.append(self.search)
        self.starred_only = Gtk.CheckButton(label="Starred only")
        self.starred_only.connect("toggled", lambda _b: self._refilter())
        toolbar.append(self.starred_only)
        self.append(toolbar)

        self.store = Gio.ListStore(item_type=_OutletItem)
        self.filter = Gtk.CustomFilter.new(self._match, None)
        self.filter_model = Gtk.FilterListModel(model=self.store,
                                                filter=self.filter)
        self.selection = Gtk.SingleSelection(model=self.filter_model)

        self.column_view = Gtk.ColumnView(model=self.selection)
        self.column_view.set_vexpand(True)
        self.column_view.append_column(
            W.make_star_column("starred", self._on_star_toggled))
        self.column_view.append_column(
            W.make_text_column("Outlet", "name", expand=True, ellipsize=True))
        self.column_view.append_column(
            W.make_text_column("Nickname", "nickname"))
        self.column_view.append_column(
            W.make_text_column("J-Flags", "jflags"))
        self.column_view.append_column(
            W.make_text_column("Records", "count", xalign=1.0))
        self.column_view.connect("activate", self._on_activate)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_child(self.column_view)
        self.append(scroller)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for m in ("top", "bottom", "start", "end"):
            getattr(bottom, f"set_margin_{m}")(6)
        self.nickname_btn = Gtk.Button(label="Set nickname\u2026")
        self.nickname_btn.connect("clicked", self._on_set_nickname)
        bottom.append(self.nickname_btn)
        self.jflags_btn = Gtk.Button(label="Set J-Flags\u2026")
        self.jflags_btn.connect("clicked", self._on_set_jflags)
        bottom.append(self.jflags_btn)
        bottom.append(Gtk.Box(hexpand=True))
        self.show_works_btn = Gtk.Button(label="Show records in Catalogue")
        self.show_works_btn.connect("clicked", self._on_show_works)
        bottom.append(self.show_works_btn)
        self.append(bottom)

    # ------------------------------------------------------------------
    def set_workspace(self, workspace):
        self.workspace = workspace
        self.reload()

    def set_jflag_presets(self, presets):
        self._jflag_presets = list(presets or [])

    def reload(self):
        self.store.remove_all()
        if not self.workspace:
            return
        for o in self.workspace.all_outlets():
            self.store.append(_OutletItem(o))

    def reveal_outlet(self, outlet_id):
        """Clear filters, then select and scroll to the matching row."""
        self.search.set_text("")
        self.starred_only.set_active(False)
        self._refilter()
        n = self.filter_model.get_n_items()
        for i in range(n):
            item = self.filter_model.get_item(i)
            if item.outlet_id == outlet_id:
                self.selection.set_selected(i)
                self.column_view.scroll_to(
                    i, None, Gtk.ListScrollFlags.FOCUS, None)
                return True
        return False

    def _refilter(self):
        self.filter.changed(Gtk.FilterChange.DIFFERENT)

    def _match(self, item, _user_data=None):
        if self.starred_only.get_active() and not getattr(item, "starred",
                                                          False):
            return False
        needle = self.search.get_text().strip().lower()
        if not needle:
            return True
        return (needle in (item.name or "").lower()
                or needle in (item.nickname or "").lower())

    def _on_star_toggled(self, item, new_value):
        item.starred = new_value
        if self.workspace:
            self.workspace.set_outlet_starred(item.outlet_id, new_value)
        self.emit("star-changed", item.outlet_id, new_value)

    def _selected_outlet_id(self):
        item = self.selection.get_selected_item()
        return item.outlet_id if item else None

    def _on_activate(self, _view, _position):
        oid = self._selected_outlet_id()
        if oid:
            self.emit("show-outlet-works", oid)

    def _on_show_works(self, _btn):
        oid = self._selected_outlet_id()
        if oid:
            self.emit("show-outlet-works", oid)

    # --- nickname -----------------------------------------------------
    def _on_set_nickname(self, _btn):
        oid = self._selected_outlet_id()
        if not oid or not self.workspace:
            return
        outlet = self.workspace.outlets.get(oid)
        if not outlet:
            return

        def _apply(nickname):
            try:
                self.workspace.set_outlet_nickname(oid, nickname)
            except ValueError as exc:
                dialogs.message(self.window or self.get_root(),
                                "Could not set nickname", str(exc),
                                kind="warning")
                return
            self.reload()
            self.emit("outlet-changed")

        dialogs.prompt_text(
            self.window or self.get_root(), "Set outlet nickname", _apply,
            body=f"Nickname for '{outlet.name}' (letters A\u2013Z only; "
                 "leave blank to clear):",
            initial=outlet.nickname, ok_label="_Save",
            placeholder="e.g. JBIB")

    # --- J-Flags ------------------------------------------------------
    def _on_set_jflags(self, _btn):
        oid = self._selected_outlet_id()
        if not oid or not self.workspace:
            return
        outlet = self.workspace.outlets.get(oid)
        if not outlet:
            return
        current = set(outlet.sorted_jflags())
        preset_flags = [flag for flag, _prio in self._jflag_presets]
        extra = [f for f in outlet.sorted_jflags() if f not in preset_flags]
        all_flags = preset_flags + extra

        parent = self.window or self.get_root()
        dlg = Adw.MessageDialog(transient_for=parent, modal=True,
                                heading=f"J-Flags for {outlet.name}")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        checks = {}
        if all_flags:
            box.append(Gtk.Label(label="Select the J-Flags for this outlet:",
                                 xalign=0))
            for flag in all_flags:
                cb = Gtk.CheckButton(label=flag)
                cb.set_active(flag in current)
                box.append(cb)
                checks[flag] = cb
        else:
            box.append(Gtk.Label(
                label="No J-Flags are configured. Add presets in "
                      "Preferences \u2192 J-Flags.", xalign=0))
        dlg.set_extra_child(box)
        dlg.add_response("cancel", "_Cancel")
        dlg.add_response("save", "_Save")
        dlg.set_response_appearance("save",
                                    Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("save")
        dlg.set_close_response("cancel")

        def _resp(_d, response):
            if response != "save":
                return
            chosen = [flag for flag, cb in checks.items() if cb.get_active()]
            self.workspace.set_outlet_jflags(oid, chosen)
            self.reload()
            self.emit("outlet-changed")
        dlg.connect("response", _resp)
        dlg.present()
