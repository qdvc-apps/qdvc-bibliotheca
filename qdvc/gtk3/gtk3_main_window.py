"""Main window: menubar + toolbar + notebook tabs."""

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Gio  # noqa: E402

from .. import APP_NAME, __version__
from ..workspace import Workspace
from .gtk3_catalogue_tab import CatalogueTab
from .gtk3_doi_tab import DoiLookupTab
from .gtk3_authors_tab import AuthorsTab
from .gtk3_outlets_tab import OutletsTab
from .gtk3_preferences import PreferencesDialog
from ..platform_utils import (open_with_default_app, open_with_text_editor,
                             reveal_in_file_manager)


def _menu_item(label, icon_name=None):
    """An image menu item built without the deprecated ImageMenuItem.

    Uses a Box with a Gtk.Image + Gtk.AccelLabel inside a plain MenuItem.
    """
    item = Gtk.MenuItem()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    if icon_name:
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
    else:
        img = Gtk.Image()
        img.set_size_request(16, 16)
    box.pack_start(img, False, False, 0)
    lbl = Gtk.Label(label=label, xalign=0)
    box.pack_start(lbl, True, True, 0)
    item.add(box)
    item._label = lbl
    return item


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title=APP_NAME)
        self.config = config
        self.workspace = None

        # Icon shown in the window frame and (with a matching StartupWMClass in
        # the .desktop file) in the MATE panel / taskbar. We use a standard
        # themed icon name directly, so it appears even before any .desktop
        # matching and without bundling an icon file.
        try:
            self.set_icon_name("accessories-dictionary")
        except Exception:  # noqa: BLE001
            pass

        w = self.config.window.get("width", 1100)
        h = self.config.window.get("height", 720)
        self.set_default_size(w, h)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self._on_close)

        self.accel_group = Gtk.AccelGroup()
        self.add_accel_group(self.accel_group)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        root.pack_start(self._build_menubar(), False, False, 0)
        root.pack_start(self._build_toolbar(), False, False, 0)

        self.notebook = Gtk.Notebook()
        root.pack_start(self.notebook, True, True, 0)

        self.catalogue = CatalogueTab()
        self.catalogue.connect("selection-changed",
                               self._on_catalogue_selection)
        self.catalogue.connect("record-action", self._on_record_action)
        self.catalogue.connect("goto-outlet", self._on_goto_outlet)
        self.catalogue.set_style_change_callback(self._on_citation_style_chosen)
        self.doi_tab = DoiLookupTab()
        self.doi_tab.connect("goto-record", self._on_goto_record)
        self.authors_tab = AuthorsTab()
        self.authors_tab.connect("show-author-works",
                                 self._on_show_author_works)
        self.authors_tab.connect("star-changed", self._on_author_star_changed)
        self.outlets_tab = OutletsTab()
        self.outlets_tab.connect("show-outlet-works",
                                 self._on_show_outlet_works)
        self.outlets_tab.connect("star-changed",
                                 self._on_outlet_star_changed)
        self.outlets_tab.connect("outlet-changed",
                                 self._on_outlet_changed)

        self.notebook.append_page(self.catalogue, Gtk.Label(label="Catalogue"))
        self.notebook.append_page(self.authors_tab, Gtk.Label(label="Authors"))
        self.notebook.append_page(self.outlets_tab,
                                   Gtk.Label(label="Outlets"))
        self.notebook.append_page(self.doi_tab, Gtk.Label(label="DOI Lookup"))
        self.notebook.connect("switch-page", self._on_tab_switched)

        self.statusbar = Gtk.Statusbar()
        self._sb_ctx = self.statusbar.get_context_id("main")
        root.pack_start(self.statusbar, False, False, 0)

        # F2 renames the selected record. The Record menu was removed (its
        # actions live in the Catalogue right-click menu), so we bind F2 at the
        # window level instead of on a menu item.
        self.accel_group.connect(
            Gdk.KEY_F2, 0, Gtk.AccelFlags.VISIBLE,
            self._accel_rename)

        self._apply_prefs_to_widgets()
        self._update_actions_sensitivity()
        self._update_title()
        self._set_status("No workspace open. Use File \u2192 Open Workspace.")

    # ==================================================================
    # Menubar
    # ==================================================================
    def _build_menubar(self):
        menubar = Gtk.MenuBar()
        menubar.append(self._file_menu())
        menubar.append(self._edit_menu())
        menubar.append(self._view_menu())
        menubar.append(self._tools_menu())
        menubar.append(self._help_menu())
        return menubar

    def _accel(self, item, key, mods):
        item.add_accelerator("activate", self.accel_group, key, mods,
                             Gtk.AccelFlags.VISIBLE)

    def _file_menu(self):
        top = Gtk.MenuItem(label="File")
        menu = Gtk.Menu()
        top.set_submenu(menu)

        self.mi_open = _menu_item("Open Workspace\u2026", "document-open")
        self.mi_open.connect("activate", self._on_open_workspace)
        self._accel(self.mi_open, Gdk.KEY_o, Gdk.ModifierType.CONTROL_MASK)
        menu.append(self.mi_open)

        self.mi_close = _menu_item("Close Workspace", "window-close")
        self.mi_close.connect("activate", self._on_close_workspace)
        menu.append(self.mi_close)

        menu.append(Gtk.SeparatorMenuItem())

        self.recent_menu_item = Gtk.MenuItem(label="Recent Workspaces")
        self.recent_submenu = Gtk.Menu()
        self.recent_menu_item.set_submenu(self.recent_submenu)
        menu.append(self.recent_menu_item)
        self._rebuild_recent_menu()

        menu.append(Gtk.SeparatorMenuItem())

        self.mi_import = _menu_item("Import .bib\u2026", "document-import")
        self.mi_import.connect("activate", self._on_import)
        self._accel(self.mi_import, Gdk.KEY_i, Gdk.ModifierType.CONTROL_MASK)
        menu.append(self.mi_import)

        self.mi_refresh_ws = _menu_item("Refresh Workspace", "view-refresh")
        self.mi_refresh_ws.connect("activate", self._on_reindex)
        menu.append(self.mi_refresh_ws)

        menu.append(Gtk.SeparatorMenuItem())

        mi_quit = _menu_item("Quit", "application-exit")
        mi_quit.connect("activate", lambda *_: self.close())
        self._accel(mi_quit, Gdk.KEY_q, Gdk.ModifierType.CONTROL_MASK)
        menu.append(mi_quit)
        return top

    def _edit_menu(self):
        top = Gtk.MenuItem(label="Edit")
        menu = Gtk.Menu()
        top.set_submenu(menu)
        mi_prefs = _menu_item("Preferences\u2026", "preferences-system")
        mi_prefs.connect("activate", self._on_preferences)
        self._accel(mi_prefs, Gdk.KEY_comma, Gdk.ModifierType.CONTROL_MASK)
        menu.append(mi_prefs)
        return top

    def _view_menu(self):
        top = Gtk.MenuItem(label="View")
        menu = Gtk.Menu()
        top.set_submenu(menu)

        self.mi_toggle_sidebar = Gtk.CheckMenuItem(label="Show Sidebar")
        self.mi_toggle_sidebar.set_active(True)
        self.mi_toggle_sidebar.connect("toggled", self._on_toggle_sidebar)
        self._accel(self.mi_toggle_sidebar, Gdk.KEY_F9, 0)
        menu.append(self.mi_toggle_sidebar)

        self.mi_toggle_detail = Gtk.CheckMenuItem(label="Show Detail Pane")
        self.mi_toggle_detail.set_active(True)
        self.mi_toggle_detail.connect("toggled", self._on_toggle_detail)
        self._accel(self.mi_toggle_detail, Gdk.KEY_F10, 0)
        menu.append(self.mi_toggle_detail)

        menu.append(Gtk.SeparatorMenuItem())

        mi_cat = _menu_item("Catalogue Tab")
        mi_cat.connect("activate", lambda *_: self.notebook.set_current_page(0))
        self._accel(mi_cat, Gdk.KEY_1, Gdk.ModifierType.MOD1_MASK)
        menu.append(mi_cat)

        mi_auth = _menu_item("Authors Tab")
        mi_auth.connect("activate",
                        lambda *_: self.notebook.set_current_page(1))
        self._accel(mi_auth, Gdk.KEY_2, Gdk.ModifierType.MOD1_MASK)
        menu.append(mi_auth)

        mi_outlets = _menu_item("Outlets Tab")
        mi_outlets.connect("activate",
                           lambda *_: self.notebook.set_current_page(2))
        self._accel(mi_outlets, Gdk.KEY_3, Gdk.ModifierType.MOD1_MASK)
        menu.append(mi_outlets)

        mi_doi = _menu_item("DOI Lookup Tab")
        mi_doi.connect("activate", lambda *_: self.notebook.set_current_page(3))
        self._accel(mi_doi, Gdk.KEY_4, Gdk.ModifierType.MOD1_MASK)
        menu.append(mi_doi)

        menu.append(Gtk.SeparatorMenuItem())

        self.mi_sort = _menu_item("Sort\u2026", "view-sort-ascending")
        self.mi_sort.connect("activate", self._on_sort)
        self._accel(self.mi_sort, Gdk.KEY_s,
                    Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
        menu.append(self.mi_sort)

        mi_refresh = _menu_item("Refresh Current View", "view-refresh")
        mi_refresh.connect("activate", self._on_refresh_view)
        self._accel(mi_refresh, Gdk.KEY_F5, 0)
        menu.append(mi_refresh)

        menu.append(Gtk.SeparatorMenuItem())

        self.mi_view_open_pdf = _menu_item("Open PDF", "application-pdf")
        self.mi_view_open_pdf.connect("activate", lambda *_: self._open_pdf())
        menu.append(self.mi_view_open_pdf)

        self.mi_view_open_epub = _menu_item("Open EPUB", "x-office-document")
        self.mi_view_open_epub.connect("activate",
                                       lambda *_: self._open_epub())
        menu.append(self.mi_view_open_epub)
        return top

    def _tools_menu(self):
        top = Gtk.MenuItem(label="Tools")
        menu = Gtk.Menu()
        top.set_submenu(menu)
        self.mi_validate = _menu_item("Validate Workspace\u2026",
                                      "emblem-important")
        self.mi_validate.connect("activate", self._on_validate)
        menu.append(self.mi_validate)
        return top

    def _help_menu(self):
        top = Gtk.MenuItem(label="Help")
        menu = Gtk.Menu()
        top.set_submenu(menu)

        mi_keys = _menu_item("Keyboard Shortcuts", "preferences-desktop-keyboard")
        mi_keys.connect("activate", self._on_shortcuts)
        self._accel(mi_keys, Gdk.KEY_question,
                    Gdk.ModifierType.CONTROL_MASK)
        menu.append(mi_keys)

        mi_about = _menu_item("About", "help-about")
        mi_about.connect("activate", self._on_about)
        menu.append(mi_about)
        return top

    def _rebuild_recent_menu(self):
        for child in self.recent_submenu.get_children():
            self.recent_submenu.remove(child)
        recents = self.config.recent_workspaces
        if not recents:
            empty = Gtk.MenuItem(label="(none)")
            empty.set_sensitive(False)
            self.recent_submenu.append(empty)
        else:
            for path in recents:
                mi = Gtk.MenuItem(label=path)
                mi.connect("activate", lambda _w, p=path: self._open_path(p))
                self.recent_submenu.append(mi)
        self.recent_submenu.show_all()

    # ==================================================================
    # Toolbar
    # ==================================================================
    def _build_toolbar(self):
        tb = Gtk.Toolbar()
        self.toolbar = tb

        self.tb_rescan = Gtk.ToolButton.new(
            Gtk.Image.new_from_icon_name("view-refresh", Gtk.IconSize.LARGE_TOOLBAR),
            "Rescan")
        self.tb_rescan.set_tooltip_text("Rescan workspace")
        self.tb_rescan.connect("clicked", self._on_reindex)
        tb.insert(self.tb_rescan, -1)

        self.tb_import = Gtk.ToolButton.new(
            Gtk.Image.new_from_icon_name("document-import", Gtk.IconSize.LARGE_TOOLBAR),
            "Import")
        self.tb_import.set_tooltip_text("Import a .bib file (Ctrl+I)")
        self.tb_import.connect("clicked", self._on_import)
        tb.insert(self.tb_import, -1)

        tb.insert(Gtk.SeparatorToolItem(), -1)

        self.tb_sort = Gtk.ToolButton.new(
            Gtk.Image.new_from_icon_name("view-sort-ascending",
                                         Gtk.IconSize.LARGE_TOOLBAR),
            "Sort")
        self.tb_sort.set_tooltip_text("Sort the current list (Ctrl+Shift+S)")
        self.tb_sort.connect("clicked", self._on_sort)
        tb.insert(self.tb_sort, -1)

        tb.insert(Gtk.SeparatorToolItem(), -1)

        self.tb_open_pdf = Gtk.ToolButton.new(
            Gtk.Image.new_from_icon_name("application-pdf",
                                         Gtk.IconSize.LARGE_TOOLBAR),
            "Open PDF")
        self.tb_open_pdf.set_tooltip_text("Open the selected record's PDF")
        self.tb_open_pdf.connect("clicked", lambda *_: self._open_pdf())
        tb.insert(self.tb_open_pdf, -1)

        self.tb_open_epub = Gtk.ToolButton.new(
            Gtk.Image.new_from_icon_name("x-office-document",
                                         Gtk.IconSize.LARGE_TOOLBAR),
            "Open EPUB")
        self.tb_open_epub.set_tooltip_text("Open the selected record's EPUB")
        self.tb_open_epub.connect("clicked", lambda *_: self._open_epub())
        tb.insert(self.tb_open_epub, -1)

        self._apply_toolbar_style()
        return tb

    def _apply_toolbar_style(self):
        """Set icons-with-labels layout per the user's preference."""
        style = self.config.get("toolbar_style", "beside")
        gtk_style = (Gtk.ToolbarStyle.BOTH_HORIZ if style == "beside"
                     else Gtk.ToolbarStyle.BOTH)
        self.toolbar.set_style(gtk_style)

    # ==================================================================
    # Workspace open/close/rescan
    # ==================================================================
    def _on_open_workspace(self, _item):
        dialog = Gtk.FileChooserDialog(
            title="Open Workspace Folder", parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("_Cancel", Gtk.ResponseType.CANCEL,
                           "_Open", Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            dialog.destroy()
            self._open_path(path)
        else:
            dialog.destroy()

    def _open_path(self, path):
        if not path:
            return
        if not Workspace.looks_like_workspace(path):
            self._warn(f"'{path}' does not look like a QDVC workspace "
                       "(no bibtex/ or markdown/ folder).")
            return
        try:
            ws = Workspace(path)
            ws.load()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Failed to open workspace:\n{exc}")
            return
        self.workspace = ws
        self.catalogue.set_fulltext_root(
            self.config.get("fulltext_library_path", "") or None)
        self.catalogue.set_jflag_priority(self._jflag_priority_map())
        self.catalogue.set_workspace(ws)
        self.catalogue.set_citation_style(self._saved_citation_style())
        self.authors_tab.set_workspace(ws)
        self.outlets_tab.set_jflag_presets(self._jflag_presets())
        self.outlets_tab.set_workspace(ws)
        self.doi_tab.set_workspace(ws)
        self.config.last_workspace = path
        self.config.push_recent(path)
        self.config.save()
        self._rebuild_recent_menu()
        self._update_actions_sensitivity()
        self._update_title()
        self._set_status(f"Opened {path} \u2014 {len(ws.records)} records, "
                         f"{len(ws.my_works)} works, "
                         f"{len(ws.authors)} authors.")

    def _on_close_workspace(self, _item):
        self.catalogue.set_workspace(None)
        self.authors_tab.set_workspace(None)
        self.outlets_tab.set_workspace(None)
        self.doi_tab.set_workspace(None)
        self.workspace = None
        self.config.last_workspace = None
        self.config.save()
        self._update_actions_sensitivity()
        self._update_title()
        self._set_status("Workspace closed.")

    def _on_reindex(self, _item):
        if not self.workspace:
            return
        self.workspace.load(force_rescan=True)
        self.catalogue.set_workspace(self.workspace)
        self.catalogue.set_citation_style(self._saved_citation_style())
        self.authors_tab.set_workspace(self.workspace)
        self.outlets_tab.set_workspace(self.workspace)
        self.doi_tab.set_workspace(self.workspace)
        self._set_status(
            f"Rescanned \u2014 {len(self.workspace.records)} records.")

    # ==================================================================
    # Import
    # ==================================================================
    def _on_import(self, _item):
        if not self.workspace:
            self._warn("Open a workspace first.")
            return
        # If the user is viewing a "my work" in the Catalogue, pre-select it.
        preselect = None
        if self.notebook.get_current_page() == 0:
            preselect = self.catalogue.current_work_key()
        dlg = ImportDialog(self, workspace=self.workspace,
                           preselect_work_key=preselect)
        resp = dlg.run()
        if resp != Gtk.ResponseType.OK:
            dlg.destroy()
            return
        text = dlg.get_bibtex_text()
        work_key = dlg.allocate_work_key()
        dlg.destroy()
        if not text.strip():
            self._set_status("Nothing to import.")
            return
        try:
            imported, skipped_dois = self.workspace.import_bib_text(text)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Import failed:\n{exc}")
            return
        self.catalogue.set_workspace(self.workspace)
        self.catalogue.set_citation_style(self._saved_citation_style())
        self.authors_tab.set_workspace(self.workspace)
        self.outlets_tab.set_workspace(self.workspace)
        # optionally allocate the freshly-imported records to the chosen work
        allocated = 0
        if work_key and imported and work_key in self.workspace.my_works:
            try:
                allocated = self.workspace.allocate_to_work(work_key, imported)
                # show that work's view so the user sees the result
                self.notebook.set_current_page(0)
                self.catalogue.show_work(work_key)
            except Exception as exc:  # noqa: BLE001
                self._warn(f"Imported, but could not allocate:\n{exc}")
        msg = f"Imported {len(imported)} record(s)."
        if allocated:
            name = self.workspace.my_works[work_key].name
            msg += f" Allocated {allocated} to '{name}'."
        if skipped_dois:
            msg += (f" Skipped {len(skipped_dois)} with a DOI already in the "
                    "catalogue.")
            self._warn_skipped_dois(skipped_dois)
        self._set_status(msg)

    def _warn_skipped_dois(self, skipped_dois):
        lines = [f"\u2022 {key}: DOI {doi} already used by {existing}"
                 for key, doi, existing in skipped_dois]
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK,
            text="Some entries were not imported")
        dlg.format_secondary_text(
            "These entries share a DOI with a record already in your library, "
            "so they were skipped to avoid duplicates:\n\n" + "\n".join(lines))
        dlg.run()
        dlg.destroy()

    # ==================================================================
    # Preferences
    # ==================================================================
    def _on_preferences(self, _item):
        dlg = PreferencesDialog(self, self.config, workspace=self.workspace)
        if dlg.run() == Gtk.ResponseType.OK:
            dlg.apply()
            self._apply_prefs_to_widgets()
        dlg.destroy()

    def _apply_prefs_to_widgets(self):
        font = self.config.get("notes_font", "Monospace 10")
        self.catalogue.set_notes_font(font)
        self.catalogue.set_autosave(self.config.get("autosave_notes", True))
        self.catalogue.set_fulltext_root(
            self.config.get("fulltext_library_path", "") or None)
        self.catalogue.set_jflag_priority(self._jflag_priority_map())
        self.outlets_tab.set_jflag_presets(self._jflag_presets())
        # a CSL file may have been added/removed; refresh the Pane 3 dropdown
        self.catalogue.refresh_csl_styles()
        self.catalogue.set_citation_style(self._saved_citation_style())
        self._apply_toolbar_style()
        self.catalogue.set_sort_spec(self._load_sort_spec())

    def _jflag_presets(self):
        """Read the J-Flag presets from config as a list of (flag, priority),
        ordered by priority then name. Stored as [{'flag': str,
        'priority': number}, ...]."""
        raw = self.config.get("jflags", []) or []
        presets = []
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
                prio = float(prio)
            except (TypeError, ValueError):
                prio = 0.0
            presets.append((flag, prio))
        presets.sort(key=lambda t: (t[1], t[0].lower()))
        return presets

    def _jflag_priority_map(self):
        """{flag: priority} derived from the configured presets."""
        return {flag: prio for flag, prio in self._jflag_presets()}

    def _load_sort_spec(self):
        """Read the persisted sort spec from config as a list of
        (field_id, ascending_bool) tuples. Stored as [[field, bool], ...]."""
        raw = self.config.get("sort_spec", []) or []
        spec = []
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            spec.append((str(item[0]), bool(item[1])))
        return spec

    def _save_sort_spec(self, spec):
        self.config.set("sort_spec", [[fid, bool(asc)] for fid, asc in spec])
        self.config.save()

    # ==================================================================
    # View toggles / refresh
    # ==================================================================
    def _on_toggle_sidebar(self, item):
        self.catalogue.set_sidebar_visible(item.get_active())

    def _on_toggle_detail(self, item):
        self.catalogue.set_detail_visible(item.get_active())

    def _on_refresh_view(self, _item):
        self.catalogue.refresh_current_view()
        self._set_status("View refreshed.")

    def _on_sort(self, _item):
        from .gtk3_sort_dialog import SortDialog
        dlg = SortDialog(self, self.catalogue.get_sort_spec())
        resp = dlg.run()
        if resp == Gtk.ResponseType.OK:
            spec = dlg.get_spec()
            self.catalogue.set_sort_spec(spec)
            self._save_sort_spec(spec)
            self._set_status(self._describe_sort(spec))
        elif resp == Gtk.ResponseType.REJECT:  # Clear
            self.catalogue.set_sort_spec([])
            self._save_sort_spec([])
            self._set_status("Sort cleared (default order).")
        dlg.destroy()

    @staticmethod
    def _describe_sort(spec):
        if not spec:
            return "Sort cleared (default order)."
        from ..catalogue_sort import SORT_LABELS
        labels = dict(SORT_LABELS)
        up, down = "\u2191", "\u2193"
        parts = [f"{labels.get(fid, fid)} {up if asc else down}"
                 for fid, asc in spec]
        return "Sorted by " + ", ".join(parts)

    # ==================================================================
    # Record actions
    # ==================================================================
    def _current_record(self):
        return self.catalogue.current_record()

    def _reveal(self, which):
        rec = self._current_record()
        if not rec:
            return
        target = rec.bib_path if which == "bib" else rec.md_path
        if not target:
            self._warn("No file path for this record.")
            return
        custom = self.config.get("file_manager", "") or None
        try:
            reveal_in_file_manager(target, custom)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not open file manager:\n{exc}")

    def _open_in_editor(self, which):
        rec = self._current_record()
        if not rec:
            return
        target = rec.bib_path if which == "bib" else rec.md_path
        if not target or not Path(target).exists():
            self._warn(f"No {which} file exists for this record yet.")
            return
        try:
            open_with_text_editor(str(target))
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not open text editor:\n{exc}")

    def _open_pdf(self):
        rec = self._current_record()
        if not rec:
            return
        path = self.workspace.resolve_fulltext_path(
            rec.bibliotheca_id, "pdf",
            self.config.get("fulltext_library_path", "") or None)
        if not path:
            self._warn("No PDF is set for this record.")
            return
        if not Path(path).exists():
            self._warn(f"The PDF could not be found:\n{path}")
            return
        try:
            open_with_default_app(path)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not open PDF:\n{exc}")

    def _open_epub(self):
        rec = self._current_record()
        if not rec:
            return
        path = self.workspace.resolve_fulltext_path(
            rec.bibliotheca_id, "epub",
            self.config.get("fulltext_library_path", "") or None)
        if not path:
            self._warn("No EPUB is set for this record.")
            return
        if not Path(path).exists():
            self._warn(f"The EPUB could not be found:\n{path}")
            return
        try:
            open_with_default_app(path)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not open EPUB:\n{exc}")

    def _on_record_action(self, _tab, action):
        """Route a record context-menu action (from the Catalogue's popup)
        to the appropriate handler, acting on the current record."""
        if action == "reveal_bib":
            self._reveal("bib")
        elif action == "reveal_md":
            self._reveal("md")
        elif action == "edit_bib":
            self._open_in_editor("bib")
        elif action == "edit_md":
            self._open_in_editor("md")
        elif action == "open_pdf":
            self._open_pdf()
        elif action == "open_epub":
            self._open_epub()
        elif action == "rename":
            self._on_rename_record(None)
        elif action == "allocate":
            self._allocate_records([self._current_record().bibliotheca_id]
                                   if self._current_record() else [])

    def _allocate_records(self, bibliotheca_ids):
        """Open the allocation dialog for one or more record ids."""
        if not self.workspace or not bibliotheca_ids:
            return
        from .gtk3_allocate_dialog import AllocateDialog
        dlg = AllocateDialog(self, self.workspace, bibliotheca_ids)
        if dlg.run() == Gtk.ResponseType.OK:
            try:
                total = dlg.apply()
            except Exception as exc:  # noqa: BLE001
                dlg.destroy()
                self._warn(f"Could not allocate:\n{exc}")
                return
            dlg.destroy()
            # refresh sidebar (works list may have gained a new work) and the
            # current view (a My-works filter may now include the record)
            self.catalogue.refresh_after_allocation()
            self._set_status(
                f"Made {total} allocation(s) to My Works."
                if total else "No new allocations.")
        else:
            dlg.destroy()

    def _accel_rename(self, _group, _accel, _keyval, _modifier):
        # only when the Catalogue tab is active and a record is selected
        if self.notebook.get_current_page() != 0:
            return False
        if not self._current_record():
            return False
        self._on_rename_record(None)
        return True

    def _on_rename_record(self, _item):
        rec = self._current_record()
        if not rec:
            self._warn("Select a record first.")
            return
        old_id = rec.bibliotheca_id
        dlg = Gtk.Dialog(title="Rename Bibliotheca ID", transient_for=self,
                         modal=True)
        dlg.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("_Rename", Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        area = dlg.get_content_area()
        area.set_border_width(10)
        area.set_spacing(6)
        area.add(Gtk.Label(label=f"Rename '{old_id}' to:", xalign=0))
        entry = Gtk.Entry()
        entry.set_text(old_id)
        entry.set_activates_default(True)
        area.add(entry)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            new_id = entry.get_text().strip()
            dlg.destroy()
            try:
                self.workspace.rename_record(old_id, new_id)
            except ValueError as exc:
                self._warn(str(exc))
                return
            self.catalogue.set_workspace(self.workspace)
            self.catalogue.reveal_record(new_id)
            self._set_status(f"Renamed '{old_id}' \u2192 '{new_id}'.")
        else:
            dlg.destroy()

    def _on_catalogue_selection(self, _tab, has_selection):
        self._update_actions_sensitivity()

    def _on_tab_switched(self, _nb, _page, _num):
        # Open PDF/EPUB depend on being on the Catalogue tab, so refresh.
        self._update_actions_sensitivity()

    # ==================================================================
    # Tools: validate
    # ==================================================================
    def _on_validate(self, _item):
        if not self.workspace:
            self._warn("Open a workspace first.")
            return
        report = self.workspace.validate(
            self.config.get("fulltext_library_path", "") or None)
        self._show_validation_report(report)

    def _show_validation_report(self, report):
        dlg = Gtk.Dialog(title="Workspace Validation", transient_for=self,
                         modal=True)
        dlg.add_button("_Close", Gtk.ResponseType.CLOSE)
        dlg.set_default_size(640, 480)
        area = dlg.get_content_area()
        area.set_border_width(8)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        # Use the user's "Notes editor font" from Preferences.
        font = self.config.get("notes_font", "Monospace 10")
        try:
            from gi.repository import Pango
            view.override_font(Pango.FontDescription.from_string(font))
        except Exception:  # noqa: BLE001
            view.set_monospace(True)
        buf = view.get_buffer()
        buf.set_text(self._format_report(report))
        sw.add(view)
        area.pack_start(sw, True, True, 0)

        dlg.show_all()
        dlg.run()
        dlg.destroy()

    @staticmethod
    def _format_report(report):
        lines = []
        total_problems = sum(len(v) for v in report.values())
        if total_problems == 0:
            return "No problems found. The workspace looks healthy."

        def section(title, items, fmt):
            if not items:
                return
            lines.append(f"{title} ({len(items)}):")
            for it in items:
                lines.append("  \u2022 " + fmt(it))
            lines.append("")

        section("Orphan Markdown files (no matching .bib)",
                 report["orphan_markdown"], lambda p: p)
        section("BibTeX key does not match Bibliotheca ID",
                report.get("key_mismatch", []),
                lambda t: f"{t[0]}  (key is '{t[1]}')")
        section("Missing full-text files",
                report["missing_fulltext"],
                lambda t: f"{t[0]} [{t[1]}] \u2192 {t[2]}")
        section("Citations to unknown records",
                report["dangling_citations"],
                lambda t: f"work '{t[0]}' cites missing '{t[1]}'")
        section("'published_as' pointing to unknown records",
                report["dangling_published_as"],
                lambda t: f"work '{t[0]}' \u2192 missing '{t[1]}'")
        section("Duplicate DOIs",
                report["duplicate_dois"],
                lambda t: f"{t[0]} \u2192 {', '.join(t[1])}")
        section("Outlet nickname set, but Bibliotheca ID has no suffix",
                report.get("nick_set_no_suffix", []),
                lambda t: f"{t[0]}  (outlet nickname is '{t[1]}')")
        section("Outlet nickname set, but Bibliotheca ID suffix differs",
                report.get("nick_set_suffix_diff", []),
                lambda t: f"{t[0]}  (suffix '{t[1]}' \u2260 nickname '{t[2]}')")
        section("Bibliotheca ID has a suffix, but no outlet nickname is set",
                report.get("suffix_no_nick", []),
                lambda t: f"{t[0]}  (suffix is '{t[1]}')")
        return "\n".join(lines).rstrip()

    # ==================================================================
    # Help
    # ==================================================================
    def _on_shortcuts(self, _item):
        rows = [
            ("Ctrl+O", "Open workspace"),
            ("Ctrl+I", "Import BibTeX"),
            ("Ctrl+Q", "Quit"),
            ("Ctrl+,", "Preferences"),
            ("F9", "Toggle sidebar"),
            ("F10", "Toggle detail pane"),
            ("Alt+1", "Catalogue tab"),
            ("Alt+2", "Authors tab"),
            ("Alt+3", "Outlets tab"),
            ("Alt+4", "DOI Lookup tab"),
            ("F5", "Refresh current view"),
            ("Ctrl+Shift+S", "Sort current list"),
            ("F2", "Rename Bibliotheca ID"),
            ("Ctrl+?", "This shortcuts list"),
        ]
        dlg = Gtk.Dialog(title="Keyboard Shortcuts", transient_for=self,
                         modal=True)
        dlg.add_button("_Close", Gtk.ResponseType.CLOSE)
        grid = Gtk.Grid(column_spacing=24, row_spacing=6)
        grid.set_border_width(14)
        for i, (keys, desc) in enumerate(rows):
            k = Gtk.Label(xalign=0)
            k.set_markup(f"<tt>{keys}</tt>")
            grid.attach(k, 0, i, 1, 1)
            grid.attach(Gtk.Label(label=desc, xalign=0), 1, i, 1, 1)
        dlg.get_content_area().add(grid)
        dlg.show_all()
        dlg.run()
        dlg.destroy()

    def _on_about(self, _item):
        about = Gtk.AboutDialog(transient_for=self, modal=True)
        about.set_program_name(APP_NAME)
        about.set_version(__version__)
        about.set_comments("A personal reference manager for academics.")
        about.set_logo_icon_name("accessories-dictionary")
        about.run()
        about.destroy()

    # ==================================================================
    # DOI goto
    # ==================================================================
    def _on_goto_record(self, _tab, bibliotheca_id):
        self.notebook.set_current_page(0)
        if not self.catalogue.reveal_record(bibliotheca_id):
            self._set_status(
                f"Record {bibliotheca_id} not found in current view.")

    def _on_show_author_works(self, _tab, author_id):
        # jump to the Catalogue tab and filter by this author
        self.notebook.set_current_page(0)
        self.catalogue.show_author_works(author_id)

    def _on_author_star_changed(self, _tab, _author_id, _starred):
        # the Catalogue sidebar's Starred Authors section must be rebuilt
        self.catalogue.refresh_starred_authors()

    def _on_show_outlet_works(self, _tab, outlet_id):
        # jump to the Catalogue tab and filter by this outlet
        self.notebook.set_current_page(0)
        self.catalogue.show_outlet_works(outlet_id)

    def _on_outlet_star_changed(self, _tab, _outlet_id, _starred):
        # the Catalogue sidebar's Starred Outlets section must be rebuilt
        self.catalogue.refresh_starred_outlets()

    def _on_outlet_changed(self, _tab):
        # a nickname or J-Flag set changed: re-render Pane 2 so the Outlet and
        # J-Flags columns reflect it.
        self.catalogue.refresh_starred_outlets()

    def _on_goto_outlet(self, _tab, outlet_id):
        # From the Catalogue record menu: switch to the Outlets tab and
        # highlight/scroll to the record's outlet.
        self.notebook.set_current_page(2)
        self.outlets_tab.reveal_outlet(outlet_id)

    def _on_citation_style_chosen(self, style_id):
        # Persist the chosen citation style per workspace (keyed by path).
        if not self.workspace:
            return
        styles = dict(self.config.get("csl_styles", {}) or {})
        styles[str(self.workspace.root)] = style_id
        self.config.set("csl_styles", styles)
        self.config.save()

    def _saved_citation_style(self):
        """The persisted citation style id for the current workspace, or the
        APA sentinel when none is stored."""
        from .gtk3_catalogue_tab import APA_STYLE_ID
        if not self.workspace:
            return APA_STYLE_ID
        styles = self.config.get("csl_styles", {}) or {}
        return styles.get(str(self.workspace.root), APA_STYLE_ID)

    # ==================================================================
    # Lifecycle / helpers
    # ==================================================================
    def open_last_workspace_if_any(self):
        if not self.config.get("reopen_last", True):
            return
        last = self.config.last_workspace
        if last and Workspace.looks_like_workspace(last):
            self._open_path(last)

    def _on_close(self, *_a):
        self.catalogue.flush_notes()
        alloc = self.get_allocation()
        self.config.window["width"] = alloc.width
        self.config.window["height"] = alloc.height
        self.config.save()
        return False

    def _update_actions_sensitivity(self):
        has_ws = self.workspace is not None
        rec = self.catalogue.current_record() if has_ws else None
        has_rec = rec is not None
        for w in (self.mi_close, self.mi_import, self.mi_refresh_ws,
                  self.mi_validate, self.mi_sort, self.tb_rescan,
                  self.tb_import, self.tb_sort):
            w.set_sensitive(has_ws)

        # Open PDF/EPUB: only on the Catalogue tab, with a record selected that
        # actually has that full-text linked.
        on_catalogue = (self.notebook.get_current_page() == 0)
        can_pdf = bool(on_catalogue and has_rec and rec.has_pdf)
        can_epub = bool(on_catalogue and has_rec and rec.has_epub)
        self.mi_view_open_pdf.set_sensitive(can_pdf)
        self.tb_open_pdf.set_sensitive(can_pdf)
        self.mi_view_open_epub.set_sensitive(can_epub)
        self.tb_open_epub.set_sensitive(can_epub)

    def _update_title(self):
        if self.workspace:
            self.set_title(f"{APP_NAME} \u2014 {self.workspace.root.name}")
        else:
            self.set_title(APP_NAME)

    def _set_status(self, text):
        self.statusbar.pop(self._sb_ctx)
        self.statusbar.push(self._sb_ctx, text)

    def _warn(self, message):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.OK, text=message)
        dlg.run()
        dlg.destroy()


class ImportDialog(Gtk.Dialog):
    """Import BibTeX either by pasting text or by choosing a .bib file.

    Choosing a file loads its contents into the text area, so the user can
    review/edit before importing; the import always uses the text area.
    """

    def __init__(self, parent, workspace=None, preselect_work_key=None):
        super().__init__(title="Import BibTeX", transient_for=parent,
                         modal=True)
        self.workspace = workspace
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.import_btn = self.add_button("_Import", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(600, 480)

        area = self.get_content_area()
        area.set_border_width(10)
        area.set_spacing(6)

        info = Gtk.Label(xalign=0)
        info.set_markup(
            "Paste BibTeX below, or load a <tt>.bib</tt> file. Multiple "
            "entries are supported; each is filed by its citation key.")
        info.set_line_wrap(True)
        area.pack_start(info, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        choose = Gtk.Button.new_from_icon_name("document-open",
                                               Gtk.IconSize.BUTTON)
        choose.set_label("Choose file\u2026")
        choose.set_always_show_image(True)
        choose.connect("clicked", self._on_choose_file)
        row.pack_start(choose, False, False, 0)
        self.file_label = Gtk.Label(xalign=0)
        self.file_label.get_style_context().add_class("dim-label")
        row.pack_start(self.file_label, True, True, 0)
        area.pack_start(row, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.textview = Gtk.TextView()
        self.textview.set_monospace(True)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.buffer = self.textview.get_buffer()
        sw.add(self.textview)
        area.pack_start(sw, True, True, 0)

        # "allocate to a work" dropdown
        alloc_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        alloc_row.pack_start(
            Gtk.Label(label="Allocate imported records to:"), False, False, 0)
        self.work_combo = Gtk.ComboBoxText()
        # id "" -> the "don't allocate" choice
        self.work_combo.append("", "(none)")
        if workspace:
            for key, work in sorted(workspace.my_works.items(),
                                    key=lambda kv: kv[1].name.lower()):
                self.work_combo.append(key, work.name)
        # preselect the work the user was viewing, else "(none)"
        if preselect_work_key and workspace \
                and preselect_work_key in workspace.my_works:
            self.work_combo.set_active_id(preselect_work_key)
        else:
            self.work_combo.set_active_id("")
        alloc_row.pack_start(self.work_combo, True, True, 0)
        area.pack_start(alloc_row, False, False, 0)

        self.show_all()

    def allocate_work_key(self):
        """The chosen work key to allocate to, or None for '(none)'."""
        key = self.work_combo.get_active_id()
        return key or None

    def _on_choose_file(self, _btn):
        dlg = Gtk.FileChooserDialog(
            title="Choose a .bib file", transient_for=self,
            action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("_Cancel", Gtk.ResponseType.CANCEL,
                        "_Open", Gtk.ResponseType.OK)
        flt = Gtk.FileFilter()
        flt.set_name("BibTeX files (*.bib)")
        flt.add_pattern("*.bib")
        dlg.add_filter(flt)
        all_flt = Gtk.FileFilter()
        all_flt.set_name("All files")
        all_flt.add_pattern("*")
        dlg.add_filter(all_flt)
        if dlg.run() == Gtk.ResponseType.OK:
            path = dlg.get_filename()
            dlg.destroy()
            try:
                text = Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                self.file_label.set_text(f"Could not read: {exc}")
                return
            self.buffer.set_text(text)
            self.file_label.set_text(Path(path).name)
        else:
            dlg.destroy()

    def get_bibtex_text(self):
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, True)
