"""Preferences dialog, backed by the Config object.

The settings are split across tabs in a Gtk.Notebook:

  * General  — fonts, file manager, full-text library, startup, toolbar.
  * J-Flags  — the preset flag/priority table used by the Outlets feature.
  * CSL      — lists the custom CSL style files detected in the workspace's
               csl/ folder (by filename). This tab is informational: the
               active style is chosen per-record in the Catalogue's Pane 3.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402


class PreferencesDialog(Gtk.Dialog):
    def __init__(self, parent, config, workspace=None):
        super().__init__(title="Preferences", transient_for=parent,
                         modal=True)
        self.config = config
        self.workspace = workspace
        self.set_default_size(520, 420)
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        notebook = Gtk.Notebook()
        notebook.set_border_width(8)
        self.get_content_area().add(notebook)

        notebook.append_page(self._build_general_tab(config),
                             Gtk.Label(label="General"))
        notebook.append_page(self._build_jflags_tab(config),
                             Gtk.Label(label="J-Flags"))
        notebook.append_page(self._build_csl_tab(),
                             Gtk.Label(label="CSL"))

        self.show_all()

    # ------------------------------------------------------------------
    # General tab
    # ------------------------------------------------------------------
    def _build_general_tab(self, config):
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_border_width(12)

        # Notes editor font
        grid.attach(_right("Notes editor font:"), 0, 0, 1, 1)
        self.font_btn = Gtk.FontButton()
        self.font_btn.set_font(config.get("notes_font", "Monospace 10"))
        grid.attach(self.font_btn, 1, 0, 1, 1)

        # File manager command
        grid.attach(_right("File-manager command:"), 0, 1, 1, 1)
        self.fm_entry = Gtk.Entry()
        self.fm_entry.set_placeholder_text("auto (xdg-open)")
        self.fm_entry.set_text(config.get("file_manager", "") or "")
        self.fm_entry.set_tooltip_text(
            "Command used to reveal files. Leave blank to use xdg-open. "
            "Use {dir} as a placeholder for the folder, e.g. 'nautilus {dir}'.")
        grid.attach(self.fm_entry, 1, 1, 1, 1)

        # Full-text library path (PDFs and EPUBs)
        grid.attach(_right("Full-text library path:"), 0, 2, 1, 1)
        lib_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.lib_entry = Gtk.Entry()
        self.lib_entry.set_hexpand(True)
        self.lib_entry.set_text(config.get("fulltext_library_path", "") or "")
        self.lib_entry.set_tooltip_text(
            "Base folder where your PDF and EPUB files live. Full-text paths "
            "are stored relative to this folder.")
        lib_browse = Gtk.Button(label="Browse\u2026")
        lib_browse.connect("clicked", self._on_browse_library)
        lib_row.pack_start(self.lib_entry, True, True, 0)
        lib_row.pack_start(lib_browse, False, False, 0)
        grid.attach(lib_row, 1, 2, 1, 1)

        # Reopen last workspace
        grid.attach(_right("On startup:"), 0, 3, 1, 1)
        self.reopen_check = Gtk.CheckButton(label="Reopen last workspace")
        self.reopen_check.set_active(config.get("reopen_last", True))
        grid.attach(self.reopen_check, 1, 3, 1, 1)

        # Autosave notes
        grid.attach(_right("Notes:"), 0, 4, 1, 1)
        self.autosave_check = Gtk.CheckButton(
            label="Auto-save on switching records")
        self.autosave_check.set_active(config.get("autosave_notes", True))
        grid.attach(self.autosave_check, 1, 4, 1, 1)

        # Toolbar style
        grid.attach(_right("Toolbar style:"), 0, 5, 1, 1)
        self.toolbar_combo = Gtk.ComboBoxText()
        # id -> label
        self._toolbar_styles = [("beside", "Labels beside icons"),
                                ("below", "Labels below icons")]
        for style_id, label in self._toolbar_styles:
            self.toolbar_combo.append(style_id, label)
        self.toolbar_combo.set_active_id(
            config.get("toolbar_style", "beside"))
        grid.attach(self.toolbar_combo, 1, 5, 1, 1)

        # UI toolkit backend (GTK3 / GTK4). Changing it takes effect on the
        # next launch, since the toolkit is chosen before any GTK is imported.
        grid.attach(_right("Interface (needs restart):"), 0, 6, 1, 1)
        self.backend_combo = Gtk.ComboBoxText()
        self._backends = [("gtk3", "GTK 3 (classic)"),
                          ("gtk4", "GTK 4 (libadwaita)")]
        for backend_id, label in self._backends:
            self.backend_combo.append(backend_id, label)
        self.backend_combo.set_active_id(config.ui_backend)
        self.backend_combo.set_tooltip_text(
            "Which UI toolkit to use. Takes effect after you restart the "
            "application.")
        grid.attach(self.backend_combo, 1, 6, 1, 1)

        return grid

    # ------------------------------------------------------------------
    # J-Flags tab
    # ------------------------------------------------------------------
    def _build_jflags_tab(self, config):
        # J-Flags presets (flag + priority number). Priority orders how flags
        # are shown in the Catalogue's J-Flags column (lower = first).
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(12)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(200)
        # columns: flag(str), priority(int)
        self.jflags_store = Gtk.ListStore(str, int)
        for flag, prio in self._load_jflags(config):
            self.jflags_store.append([flag, prio])
        self.jflags_view = Gtk.TreeView(model=self.jflags_store)
        self.jflags_view.set_headers_visible(True)

        flag_r = Gtk.CellRendererText()
        flag_r.set_property("editable", True)
        flag_r.connect("edited", self._on_flag_edited)
        flag_col = Gtk.TreeViewColumn("Flag", flag_r, text=0)
        flag_col.set_expand(True)
        self.jflags_view.append_column(flag_col)

        prio_r = Gtk.CellRendererText()
        prio_r.set_property("editable", True)
        prio_r.connect("edited", self._on_priority_edited)
        prio_col = Gtk.TreeViewColumn("Priority", prio_r, text=1)
        self.jflags_view.append_column(prio_col)

        sw.add(self.jflags_view)
        box.pack_start(sw, True, True, 0)
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self._on_add_jflag)
        del_btn = Gtk.Button(label="Remove")
        del_btn.connect("clicked", self._on_remove_jflag)
        btns.pack_start(add_btn, False, False, 0)
        btns.pack_start(del_btn, False, False, 0)
        box.pack_start(btns, False, False, 0)
        hint = Gtk.Label(xalign=0)
        hint.get_style_context().add_class("dim-label")
        hint.set_markup(
            "<small>Lower priority numbers are displayed first in the "
            "Catalogue's J-Flags column (e.g. FT50 before A*).</small>")
        hint.set_line_wrap(True)
        box.pack_start(hint, False, False, 0)
        return box

    # ------------------------------------------------------------------
    # CSL tab
    # ------------------------------------------------------------------
    def _build_csl_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(12)

        intro = Gtk.Label(xalign=0)
        intro.set_line_wrap(True)
        intro.set_markup(
            "Custom citation styles are read from the <tt>csl/</tt> folder in "
            "the current workspace. Files below are listed by filename; choose "
            "the active style per record in the Catalogue's reference pane.")
        box.pack_start(intro, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(200)
        self.csl_store = Gtk.ListStore(str)
        files = self.workspace.list_csl_files() if self.workspace else []
        for name in files:
            self.csl_store.append([name])
        view = Gtk.TreeView(model=self.csl_store)
        view.set_headers_visible(True)
        col = Gtk.TreeViewColumn("CSL file", Gtk.CellRendererText(), text=0)
        col.set_expand(True)
        view.append_column(col)
        sw.add(view)
        box.pack_start(sw, True, True, 0)

        status = Gtk.Label(xalign=0)
        status.get_style_context().add_class("dim-label")
        try:
            from .. import csl as _csl
            backend_ok = _csl.csl_available()
        except Exception:  # noqa: BLE001
            backend_ok = False
        if not self.workspace:
            status.set_markup("<small>Open a workspace to see its CSL "
                              "files.</small>")
        elif not files:
            status.set_markup(
                "<small>No .csl files found in this workspace's csl/ "
                "folder.</small>")
        elif not backend_ok:
            status.set_markup(
                "<small>Found CSL files, but the 'citeproc-py' package is not "
                "installed, so custom styles cannot be rendered yet.</small>")
        else:
            status.set_markup(f"<small>{len(files)} CSL file(s) "
                              "available.</small>")
        status.set_line_wrap(True)
        box.pack_start(status, False, False, 0)
        return box

    # ------------------------------------------------------------------
    # J-Flags helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _load_jflags(config):
        """Return the configured J-Flags as a list of (flag, priority-int),
        tolerant of dict or [flag, priority] list forms."""
        raw = config.get("jflags", []) or []
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

    def _on_flag_edited(self, _renderer, path, new_text):
        self.jflags_store[path][0] = new_text.strip()

    def _on_priority_edited(self, _renderer, path, new_text):
        try:
            self.jflags_store[path][1] = int(new_text.strip())
        except ValueError:
            pass

    def _on_add_jflag(self, _btn):
        self.jflags_store.append(["NEW", 0])

    def _on_remove_jflag(self, _btn):
        model, it = self.jflags_view.get_selection().get_selected()
        if it:
            model.remove(it)

    def _on_browse_library(self, _btn):
        dlg = Gtk.FileChooserDialog(
            title="Select full-text library folder", parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        dlg.add_buttons("_Cancel", Gtk.ResponseType.CANCEL,
                        "_Select", Gtk.ResponseType.OK)
        current = self.lib_entry.get_text().strip()
        if current:
            dlg.set_current_folder(current)
        if dlg.run() == Gtk.ResponseType.OK:
            self.lib_entry.set_text(dlg.get_filename())
        dlg.destroy()

    def apply(self):
        self.config.set("notes_font", self.font_btn.get_font())
        self.config.set("file_manager", self.fm_entry.get_text().strip())
        self.config.set("fulltext_library_path",
                        self.lib_entry.get_text().strip())
        self.config.set("reopen_last", self.reopen_check.get_active())
        self.config.set("autosave_notes", self.autosave_check.get_active())
        self.config.set("toolbar_style",
                        self.toolbar_combo.get_active_id() or "beside")
        self.config.ui_backend = self.backend_combo.get_active_id() or "gtk3"
        jflags = []
        for row in self.jflags_store:
            flag = (row[0] or "").strip()
            if flag:
                jflags.append({"flag": flag, "priority": int(row[1])})
        self.config.set("jflags", jflags)
        self.config.save()


def _right(text):
    lbl = Gtk.Label(label=text, xalign=1)
    return lbl
