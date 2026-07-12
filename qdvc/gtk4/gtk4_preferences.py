"""Preferences (GTK4): an ``Adw.PreferencesWindow`` with live-apply.

Following the GNOME HIG, settings apply immediately and persist — there is no
Save/Cancel/revert. Each control writes its config value and calls the
``on_apply`` callback so the running UI updates at once, and the window persists
on close. Pages: General (fonts, paths, startup, backend selector), J-Flags
(the preset table), and CSL (informational list of workspace style files).

The GTK3 "toolbar style" control is dropped here (there is no toolbar in the
GTK4 UI); every other persisted preference remains reachable. The GTK3/GTK4
backend selector is present, with a note that it takes effect on restart.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, GObject, Adw  # noqa: E402

from . import gtk4_dialogs as dialogs  # noqa: E402


class _JFlagItem(GObject.Object):
    __gtype_name__ = "QdvcJFlagItem"

    def __init__(self, flag, priority):
        super().__init__()
        self.flag = flag
        self.priority = priority


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, parent, config, workspace=None, on_apply=None):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.config = config
        self.workspace = workspace
        self._on_apply = on_apply
        self.set_search_enabled(False)
        self.set_default_size(560, 520)

        self.add(self._general_page())
        self.add(self._jflags_page())
        self.add(self._csl_page())

    # ------------------------------------------------------------------
    def _apply(self):
        self.config.save()
        if self._on_apply:
            self._on_apply()

    # ------------------------------------------------------------------
    # General page
    # ------------------------------------------------------------------
    def _general_page(self):
        page = Adw.PreferencesPage(title="General",
                                   icon_name="preferences-system-symbolic")

        fonts = Adw.PreferencesGroup(title="Editing")
        # Notes font
        font_row = Adw.ActionRow(title="Notes editor font")
        self.font_btn = Gtk.FontButton()
        self.font_btn.set_valign(Gtk.Align.CENTER)
        self.font_btn.set_font(self.config.get("notes_font", "Monospace 10"))
        self.font_btn.connect("font-set", self._on_font_set)
        font_row.add_suffix(self.font_btn)
        fonts.add(font_row)

        # Autosave
        self.autosave_row = Adw.SwitchRow(
            title="Auto-save notes",
            subtitle="Save notes when switching records")
        self.autosave_row.set_active(self.config.get("autosave_notes", True))
        self.autosave_row.connect("notify::active", self._on_autosave)
        fonts.add(self.autosave_row)
        page.add(fonts)

        paths = Adw.PreferencesGroup(title="Files")
        # File manager command
        fm_row = Adw.EntryRow(title="File-manager command")
        fm_row.set_text(self.config.get("file_manager", "") or "")
        fm_row.connect("changed", self._on_fm_changed)
        self.fm_row = fm_row
        paths.add(fm_row)

        # Full-text library path (+ browse)
        lib_row = Adw.EntryRow(title="Full-text library path")
        lib_row.set_text(self.config.get("fulltext_library_path", "") or "")
        lib_row.connect("changed", self._on_lib_changed)
        browse = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        browse.set_valign(Gtk.Align.CENTER)
        browse.set_tooltip_text("Browse\u2026")
        browse.connect("clicked", self._on_browse_library)
        lib_row.add_suffix(browse)
        self.lib_row = lib_row
        paths.add(lib_row)
        page.add(paths)

        startup = Adw.PreferencesGroup(title="Startup & interface")
        self.reopen_row = Adw.SwitchRow(title="Reopen last workspace")
        self.reopen_row.set_active(self.config.get("reopen_last", True))
        self.reopen_row.connect("notify::active", self._on_reopen)
        startup.add(self.reopen_row)

        # backend selector (needs restart)
        self._backend_ids = ["gtk3", "gtk4"]
        model = Gtk.StringList.new(["GTK 3 (classic)", "GTK 4 (libadwaita)"])
        self.backend_row = Adw.ComboRow(
            title="Interface", subtitle="Takes effect after restart")
        self.backend_row.set_model(model)
        self.backend_row.set_selected(
            self._backend_ids.index(self.config.ui_backend)
            if self.config.ui_backend in self._backend_ids else 0)
        self.backend_row.connect("notify::selected", self._on_backend)
        startup.add(self.backend_row)
        page.add(startup)
        return page

    def _on_font_set(self, _btn):
        self.config.set("notes_font", self.font_btn.get_font())
        self._apply()

    def _on_autosave(self, *_a):
        self.config.set("autosave_notes", self.autosave_row.get_active())
        self._apply()

    def _on_fm_changed(self, _row):
        self.config.set("file_manager", self.fm_row.get_text().strip())
        self._apply()

    def _on_lib_changed(self, _row):
        self.config.set("fulltext_library_path", self.lib_row.get_text().strip())
        self._apply()

    def _on_reopen(self, *_a):
        self.config.set("reopen_last", self.reopen_row.get_active())
        self._apply()

    def _on_backend(self, *_a):
        idx = self.backend_row.get_selected()
        if 0 <= idx < len(self._backend_ids):
            self.config.ui_backend = self._backend_ids[idx]
            self.config.save()  # persist; no live effect (needs restart)

    def _on_browse_library(self, _btn):
        def _chosen(path):
            self.lib_row.set_text(path)
        current = self.lib_row.get_text().strip() or None
        dialogs.choose_folder(self, "Select full-text library folder",
                              _chosen, initial=current)

    # ------------------------------------------------------------------
    # J-Flags page
    # ------------------------------------------------------------------
    def _jflags_page(self):
        page = Adw.PreferencesPage(title="J-Flags",
                                   icon_name="starred-symbolic")
        group = Adw.PreferencesGroup(
            title="Preset J-Flags",
            description="Lower priority numbers are displayed first in the "
                        "Catalogue's J-Flags column (e.g. FT50 before A*).")

        self.jflags_store = Gio.ListStore(item_type=_JFlagItem)
        for flag, prio in self._load_jflags():
            self.jflags_store.append(_JFlagItem(flag, prio))

        selection = Gtk.NoSelection(model=self.jflags_store)
        self.jflags_view = Gtk.ColumnView(model=selection)
        self.jflags_view.append_column(self._jflag_flag_column())
        self.jflags_view.append_column(self._jflag_prio_column())
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(220)
        sw.set_child(self.jflags_view)
        list_row = Adw.PreferencesGroup()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(sw)
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self._on_add_jflag)
        del_btn = Gtk.Button(label="Remove selected")
        del_btn.connect("clicked", self._on_remove_jflag)
        btns.append(add_btn)
        btns.append(del_btn)
        box.append(btns)
        list_row.add(box)

        group.add(box)
        page.add(group)
        return page

    def _jflag_flag_column(self):
        factory = Gtk.SignalListItemFactory()

        def setup(_f, li):
            entry = Gtk.Entry()
            li.set_child(entry)

        def bind(_f, li):
            entry = li.get_child()
            item = li.get_item()
            entry.set_text(item.flag)
            handler = getattr(entry, "_qdvc_handler", None)
            if handler is not None:
                entry.disconnect(handler)

            def _changed(e):
                item.flag = e.get_text().strip()
                self._commit_jflags()
            entry._qdvc_handler = entry.connect("changed", _changed)
        factory.connect("setup", setup)
        factory.connect("bind", bind)
        col = Gtk.ColumnViewColumn(title="Flag", factory=factory)
        col.set_expand(True)
        return col

    def _jflag_prio_column(self):
        factory = Gtk.SignalListItemFactory()

        def setup(_f, li):
            spin = Gtk.SpinButton.new_with_range(-999, 999, 1)
            li.set_child(spin)

        def bind(_f, li):
            spin = li.get_child()
            item = li.get_item()
            spin.set_value(item.priority)
            handler = getattr(spin, "_qdvc_handler", None)
            if handler is not None:
                spin.disconnect(handler)

            def _changed(s):
                item.priority = int(s.get_value())
                self._commit_jflags()
            spin._qdvc_handler = spin.connect("value-changed", _changed)
        factory.connect("setup", setup)
        factory.connect("bind", bind)
        col = Gtk.ColumnViewColumn(title="Priority", factory=factory)
        return col

    def _load_jflags(self):
        raw = self.config.get("jflags", []) or []
        out = []
        for item in raw:
            if isinstance(item, dict):
                flag = str(item.get("flag", "")).strip()
                prio = item.get("priority", 0)
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                flag, prio = str(item[0]).strip(), item[1]
            else:
                continue
            if not flag:
                continue
            try:
                prio = int(prio)
            except (TypeError, ValueError):
                prio = 0
            out.append((flag, prio))
        return out

    def _commit_jflags(self):
        jflags = []
        for i in range(self.jflags_store.get_n_items()):
            item = self.jflags_store.get_item(i)
            flag = (item.flag or "").strip()
            if flag:
                jflags.append({"flag": flag, "priority": int(item.priority)})
        self.config.set("jflags", jflags)
        self._apply()

    def _on_add_jflag(self, _btn):
        self.jflags_store.append(_JFlagItem("NEW", 0))
        self._commit_jflags()

    def _on_remove_jflag(self, _btn):
        # remove the last row (NoSelection has no current row); a simple,
        # predictable behaviour for a small preset list.
        n = self.jflags_store.get_n_items()
        if n:
            self.jflags_store.remove(n - 1)
            self._commit_jflags()

    # ------------------------------------------------------------------
    # CSL page (informational)
    # ------------------------------------------------------------------
    def _csl_page(self):
        page = Adw.PreferencesPage(title="CSL",
                                   icon_name="emblem-documents-symbolic")
        group = Adw.PreferencesGroup(
            title="Citation styles",
            description="Custom citation styles are read from the csl/ folder "
                        "in the current workspace. Choose the active style per "
                        "record in the Catalogue's reference pane.")
        files = self.workspace.list_csl_files() if self.workspace else []
        if not self.workspace:
            group.add(_dim_row("Open a workspace to see its CSL files."))
        elif not files:
            group.add(_dim_row("No .csl files found in this workspace's csl/ "
                               "folder."))
        else:
            for name in files:
                group.add(Adw.ActionRow(title=name))
            try:
                from .. import csl as _csl
                backend_ok = _csl.csl_available()
            except Exception:  # noqa: BLE001
                backend_ok = False
            if not backend_ok:
                group.add(_dim_row("Found CSL files, but 'citeproc-py' is not "
                                   "installed, so custom styles cannot be "
                                   "rendered yet."))
        page.add(group)
        return page


def _dim_row(text):
    row = Adw.ActionRow(title=text)
    row.add_css_class("dim-label")
    return row
