"""Main window: menu bar (File > Open/Close Workspace) + notebook tabs."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio  # noqa: E402

from . import APP_NAME
from .workspace import Workspace
from .catalogue_tab import CatalogueTab
from .doi_tab import DoiLookupTab


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app, title=APP_NAME)
        self.config = config
        self.workspace = None

        w = self.config.window.get("width", 1100)
        h = self.config.window.get("height", 720)
        self.set_default_size(w, h)
        self.connect("delete-event", self._on_close)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)
        root.pack_start(self._build_menubar(), False, False, 0)

        self.notebook = Gtk.Notebook()
        root.pack_start(self.notebook, True, True, 0)

        self.catalogue = CatalogueTab()
        self.doi_tab = DoiLookupTab()
        self.doi_tab.connect("goto-record", self._on_goto_record)

        self.notebook.append_page(self.catalogue, Gtk.Label(label="Catalogue"))
        self.notebook.append_page(self.doi_tab, Gtk.Label(label="DOI Lookup"))

        self.statusbar = Gtk.Statusbar()
        self._sb_ctx = self.statusbar.get_context_id("main")
        root.pack_start(self.statusbar, False, False, 0)

        self._update_title()
        self._set_status("No workspace open. Use File \u2192 Open Workspace.")

    # ------------------------------------------------------------------
    def _build_menubar(self):
        menubar = Gtk.MenuBar()
        file_item = Gtk.MenuItem(label="File")
        file_menu = Gtk.Menu()
        file_item.set_submenu(file_menu)

        self.mi_open = Gtk.MenuItem(label="Open Workspace\u2026")
        self.mi_open.connect("activate", self._on_open_workspace)
        file_menu.append(self.mi_open)

        self.mi_close = Gtk.MenuItem(label="Close Workspace")
        self.mi_close.connect("activate", self._on_close_workspace)
        self.mi_close.set_sensitive(False)
        file_menu.append(self.mi_close)

        file_menu.append(Gtk.SeparatorMenuItem())

        self.recent_menu_item = Gtk.MenuItem(label="Recent Workspaces")
        self.recent_submenu = Gtk.Menu()
        self.recent_menu_item.set_submenu(self.recent_submenu)
        file_menu.append(self.recent_menu_item)
        self._rebuild_recent_menu()

        file_menu.append(Gtk.SeparatorMenuItem())

        mi_reindex = Gtk.MenuItem(label="Rescan Workspace")
        mi_reindex.connect("activate", self._on_reindex)
        file_menu.append(mi_reindex)

        mi_quit = Gtk.MenuItem(label="Quit")
        mi_quit.connect("activate", lambda *_: self.close())
        file_menu.append(mi_quit)

        menubar.append(file_item)
        return menubar

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
                mi.connect("activate",
                           lambda _w, p=path: self._open_path(p))
                self.recent_submenu.append(mi)
        self.recent_submenu.show_all()

    # ------------------------------------------------------------------
    def _on_open_workspace(self, _item):
        dialog = Gtk.FileChooserDialog(
            title="Open Workspace Folder", parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL,
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
            self._warn(
                f"'{path}' does not look like a QDVC workspace "
                "(no bibtex/ or markdown/ folder).")
            return
        try:
            ws = Workspace(path)
            ws.load()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Failed to open workspace:\n{exc}")
            return
        self.workspace = ws
        self.catalogue.set_workspace(ws)
        self.doi_tab.set_workspace(ws)
        self.mi_close.set_sensitive(True)
        self.config.last_workspace = path
        self.config.push_recent(path)
        self.config.save()
        self._rebuild_recent_menu()
        self._update_title()
        self._set_status(
            f"Opened {path} \u2014 {len(ws.records)} records, "
            f"{len(ws.my_works)} works.")

    def _on_close_workspace(self, _item):
        self.catalogue.set_workspace(None)
        self.doi_tab.set_workspace(None)
        self.workspace = None
        self.mi_close.set_sensitive(False)
        self.config.last_workspace = None
        self.config.save()
        self._update_title()
        self._set_status("Workspace closed.")

    def _on_reindex(self, _item):
        if not self.workspace:
            return
        self.workspace.load(force_rescan=True)
        self.catalogue.set_workspace(self.workspace)
        self.doi_tab.set_workspace(self.workspace)
        self._set_status(
            f"Rescanned \u2014 {len(self.workspace.records)} records.")

    def _on_goto_record(self, _tab, bibliotheca_id):
        self.notebook.set_current_page(0)
        if not self.catalogue.reveal_record(bibliotheca_id):
            self._set_status(
                f"Record {bibliotheca_id} not found in current view.")

    # ------------------------------------------------------------------
    def open_last_workspace_if_any(self):
        last = self.config.last_workspace
        if last and Workspace.looks_like_workspace(last):
            self._open_path(last)

    def _on_close(self, *_a):
        # persist notes + window size
        self.catalogue._flush_notes()
        alloc = self.get_allocation()
        self.config.window["width"] = alloc.width
        self.config.window["height"] = alloc.height
        self.config.save()
        return False

    # ------------------------------------------------------------------
    def _update_title(self):
        if self.workspace:
            self.set_title(f"{APP_NAME} \u2014 {self.workspace.root.name}")
        else:
            self.set_title(APP_NAME)

    def _set_status(self, text):
        self.statusbar.pop(self._sb_ctx)
        self.statusbar.push(self._sb_ctx, text)

    def _warn(self, message):
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK, text=message)
        dlg.run()
        dlg.destroy()
