"""The GTK4 / libadwaita main window.

``BibliothecaWindow`` composes the action and header-bar mixins over an
``Adw.ApplicationWindow``. Layout (per the HIG):

  * top: a single ``Adw.HeaderBar`` whose title is an ``Adw.ViewSwitcher``;
  * body: an ``Adw.ViewStack`` with the four top-level views
    (Catalogue / Authors / Outlets / DOI Lookup);
  * the Catalogue view is itself an ``Adw.OverlaySplitView`` (filters sidebar +
    master/detail content), each side in an ``Adw.ToolbarView`` with its own
    header bar;
  * bottom: a slim status line.

The window owns the workspace and exposes the same helper contract the tabs
call (``set_status`` etc.), reusing the toolkit-independent logic in
``qdvc.ui_prefs``. Dialog flows are async (``qdvc.gtk4.gtk4_dialogs``).
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib  # noqa: E402

from .. import APP_NAME, __version__
from ..workspace import Workspace
from ..platform_utils import (open_with_default_app, open_with_text_editor,
                              reveal_in_file_manager)
from .. import ui_prefs
from .gtk4_actions import ActionsMixin
from .gtk4_headerbar import HeaderBarMixin
from . import gtk4_dialogs as dialogs
from .gtk4_catalogue_tab import CatalogueView
from .gtk4_authors_tab import AuthorsView
from .gtk4_outlets_tab import OutletsView
from .gtk4_doi_tab import DoiLookupView

# View ids for the Adw.ViewStack (also targeted by the win.view-* actions).
VIEW_CATALOGUE = "catalogue"
VIEW_AUTHORS = "authors"
VIEW_OUTLETS = "outlets"
VIEW_DOI = "doi"


class BibliothecaWindow(ActionsMixin, HeaderBarMixin, Adw.ApplicationWindow):
    def __init__(self, app, config):
        super().__init__(application=app)
        self.config = config
        self.workspace = None
        self.set_title(APP_NAME)

        w = self.config.window.get("width", 1100)
        h = self.config.window.get("height", 720)
        self.set_default_size(w, h)

        self._install_actions()
        self._build_ui()

        self.connect("close-request", self._on_close_request)

        self._apply_prefs_to_widgets()
        self._update_actions_sensitivity()
        self._update_title()
        self.set_status("No workspace open. Use the Open button to begin.")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        # The four views.
        self.catalogue = CatalogueView(self)
        self.catalogue.connect("selection-changed",
                               lambda _t, _b: self._update_actions_sensitivity())
        self.catalogue.connect("record-action", self._on_record_action)
        self.catalogue.connect("goto-outlet", self._on_goto_outlet)
        self.catalogue.set_style_change_callback(self._on_citation_style_chosen)

        self.authors_tab = AuthorsView(self)
        self.authors_tab.connect("show-author-works",
                                 self._on_show_author_works)
        self.authors_tab.connect("star-changed", self._on_author_star_changed)

        self.outlets_tab = OutletsView(self)
        self.outlets_tab.connect("show-outlet-works",
                                 self._on_show_outlet_works)
        self.outlets_tab.connect("star-changed", self._on_outlet_star_changed)
        self.outlets_tab.connect("outlet-changed", self._on_outlet_changed)

        self.doi_tab = DoiLookupView(self)
        self.doi_tab.connect("goto-record", self._on_goto_record)

        # View stack + switcher.
        self.view_stack = Adw.ViewStack()
        self.view_stack.add_titled_with_icon(
            self.catalogue, VIEW_CATALOGUE, "Catalogue",
            "view-list-symbolic")
        self.view_stack.add_titled_with_icon(
            self.authors_tab, VIEW_AUTHORS, "Authors",
            "system-users-symbolic")
        self.view_stack.add_titled_with_icon(
            self.outlets_tab, VIEW_OUTLETS, "Outlets",
            "emblem-documents-symbolic")
        self.view_stack.add_titled_with_icon(
            self.doi_tab, VIEW_DOI, "DOI Lookup",
            "edit-find-symbolic")
        self.view_stack.connect("notify::visible-child-name",
                                lambda *_: self._update_actions_sensitivity())

        header = self._build_main_header(self.view_stack)

        # Status line (slim toolbar-styled box).
        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status_bar.add_css_class("toolbar")
        status_bar.set_margin_start(8)
        status_bar.set_margin_end(8)
        status_bar.set_margin_top(2)
        status_bar.set_margin_bottom(2)
        status_bar.append(self.status_label)

        # Compose: ToolbarView(header on top, stack as content, status bottom).
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self.view_stack)
        toolbar.add_bottom_bar(status_bar)

        self.set_content(toolbar)

    def _select_view(self, view_id):
        self.view_stack.set_visible_child_name(view_id)

    def _current_view_id(self):
        return self.view_stack.get_visible_child_name()

    # ------------------------------------------------------------------
    # Shared helpers (the contract the tabs / mixins rely on)
    # ------------------------------------------------------------------
    def set_status(self, text):
        self.status_label.set_text(text)

    def _warn(self, message, heading="Something went wrong"):
        dialogs.message(self, heading, message, kind="warning")

    def _update_title(self):
        if self.workspace:
            self.set_title(f"{APP_NAME} \u2014 {self.workspace.root.name}")
        else:
            self.set_title(APP_NAME)

    def _update_actions_sensitivity(self):
        has_ws = self.workspace is not None
        rec = self.catalogue.current_record() if has_ws else None
        has_rec = rec is not None
        for name in ("close-workspace", "import", "refresh-workspace",
                     "validate", "sort"):
            self.set_action_enabled(name, has_ws)

        on_catalogue = (self._current_view_id() == VIEW_CATALOGUE)
        self.set_action_enabled(
            "open-pdf", bool(on_catalogue and has_rec and rec.has_pdf))
        self.set_action_enabled(
            "open-epub", bool(on_catalogue and has_rec and rec.has_epub))
        self.set_action_enabled(
            "rename-record", bool(on_catalogue and has_rec))
        # keep the Open-PDF header button in step (it mirrors the action)
        if hasattr(self, "_open_pdf_btn"):
            self._open_pdf_btn.set_visible(True)

    def _apply_prefs_to_widgets(self):
        font = self.config.get("notes_font", "Monospace 10")
        self.catalogue.set_notes_font(font)
        self.catalogue.set_autosave(self.config.get("autosave_notes", True))
        self.catalogue.set_fulltext_root(
            self.config.get("fulltext_library_path", "") or None)
        self.catalogue.set_jflag_priority(ui_prefs.jflag_priority_map(
            self.config))
        self.outlets_tab.set_jflag_presets(ui_prefs.jflag_presets(self.config))
        self.catalogue.refresh_csl_styles()
        self.catalogue.set_citation_style(
            ui_prefs.saved_citation_style(self.config, self.workspace))
        self.catalogue.set_sort_spec(ui_prefs.load_sort_spec(self.config))

    def _rebuild_recent_menu(self):
        self._recent_menu.remove_all()
        for path in self.config.recent_workspaces:
            # menu item -> parameterised win.open-recent action with the path
            item = Gio.MenuItem.new(path, None)
            item.set_action_and_target_value(
                "win.open-recent", GLib.Variant.new_string(path))
            self._recent_menu.append_item(item)

    # ------------------------------------------------------------------
    # Workspace lifecycle
    # ------------------------------------------------------------------
    def open_last_workspace_if_any(self):
        if not self.config.get("reopen_last", True):
            return
        last = self.config.last_workspace
        if last and Workspace.looks_like_workspace(last):
            self.open_path(last)

    def do_open_workspace(self):
        dialogs.choose_folder(self, "Open Workspace Folder", self.open_path)

    def open_path(self, path):
        if not path:
            return
        if not Workspace.looks_like_workspace(path):
            self._warn(f"'{path}' does not look like a QDVC workspace "
                       "(no bibtex/ or markdown/ folder).",
                       heading="Not a workspace")
            return
        try:
            ws = Workspace(path)
            ws.load()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Failed to open workspace:\n{exc}",
                       heading="Could not open")
            return
        self.workspace = ws
        self.catalogue.set_fulltext_root(
            self.config.get("fulltext_library_path", "") or None)
        self.catalogue.set_jflag_priority(ui_prefs.jflag_priority_map(
            self.config))
        self.catalogue.set_workspace(ws)
        self.catalogue.set_citation_style(
            ui_prefs.saved_citation_style(self.config, ws))
        self.authors_tab.set_workspace(ws)
        self.outlets_tab.set_jflag_presets(ui_prefs.jflag_presets(self.config))
        self.outlets_tab.set_workspace(ws)
        self.doi_tab.set_workspace(ws)
        self.config.last_workspace = path
        self.config.push_recent(path)
        self.config.save()
        self._rebuild_recent_menu()
        self._update_actions_sensitivity()
        self._update_title()
        self.set_status(f"Opened {path} \u2014 {len(ws.records)} records, "
                        f"{len(ws.my_works)} works, "
                        f"{len(ws.authors)} authors.")

    def do_close_workspace(self):
        self.catalogue.set_workspace(None)
        self.authors_tab.set_workspace(None)
        self.outlets_tab.set_workspace(None)
        self.doi_tab.set_workspace(None)
        self.workspace = None
        self.config.last_workspace = None
        self.config.save()
        self._update_actions_sensitivity()
        self._update_title()
        self.set_status("Workspace closed.")

    def do_reindex(self):
        if not self.workspace:
            return
        self.workspace.load(force_rescan=True)
        self.catalogue.set_workspace(self.workspace)
        self.catalogue.set_citation_style(
            ui_prefs.saved_citation_style(self.config, self.workspace))
        self.authors_tab.set_workspace(self.workspace)
        self.outlets_tab.set_workspace(self.workspace)
        self.doi_tab.set_workspace(self.workspace)
        self.set_status(
            f"Rescanned \u2014 {len(self.workspace.records)} records.")

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    def do_import(self):
        if not self.workspace:
            self._warn("Open a workspace first.", heading="No workspace")
            return
        preselect = None
        if self._current_view_id() == VIEW_CATALOGUE:
            preselect = self.catalogue.current_work_key()
        from .gtk4_import_dialog import ImportDialog
        ImportDialog(self, self.workspace, preselect_work_key=preselect,
                     on_import=self._do_import_text).present()

    def _do_import_text(self, text, work_key):
        if not text.strip():
            self.set_status("Nothing to import.")
            return
        try:
            imported, skipped_dois = self.workspace.import_bib_text(text)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Import failed:\n{exc}", heading="Import failed")
            return
        self.catalogue.set_workspace(self.workspace)
        self.catalogue.set_citation_style(
            ui_prefs.saved_citation_style(self.config, self.workspace))
        self.authors_tab.set_workspace(self.workspace)
        self.outlets_tab.set_workspace(self.workspace)
        allocated = 0
        if work_key and imported and work_key in self.workspace.my_works:
            try:
                allocated = self.workspace.allocate_to_work(work_key, imported)
                self._select_view(VIEW_CATALOGUE)
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
            lines = [f"\u2022 {key}: DOI {doi} already used by {existing}"
                     for key, doi, existing in skipped_dois]
            dialogs.message(
                self, "Some entries were not imported",
                "These entries share a DOI with a record already in your "
                "library, so they were skipped to avoid duplicates:\n\n"
                + "\n".join(lines))
        self.set_status(msg)

    # ------------------------------------------------------------------
    # Sort
    # ------------------------------------------------------------------
    def do_sort(self):
        from .gtk4_sort_dialog import SortDialog
        SortDialog(self, self.catalogue.get_sort_spec(),
                   on_apply=self._apply_sort_spec,
                   on_clear=self._clear_sort_spec).present()

    def _apply_sort_spec(self, spec):
        self.catalogue.set_sort_spec(spec)
        ui_prefs.save_sort_spec(self.config, spec)
        self.set_status(ui_prefs.describe_sort(spec))

    def _clear_sort_spec(self):
        self.catalogue.set_sort_spec([])
        ui_prefs.save_sort_spec(self.config, [])
        self.set_status("Sort cleared (default order).")

    # ------------------------------------------------------------------
    # Record actions / full-text
    # ------------------------------------------------------------------
    def _current_record(self):
        return self.catalogue.current_record()

    def open_fulltext(self, kind):
        rec = self._current_record()
        if not rec:
            return
        path = self.workspace.resolve_fulltext_path(
            rec.bibliotheca_id, kind,
            self.config.get("fulltext_library_path", "") or None)
        if not path:
            self._warn(f"No {kind.upper()} is set for this record.")
            return
        from pathlib import Path
        if not Path(path).exists():
            self._warn(f"The {kind.upper()} could not be found:\n{path}")
            return
        try:
            open_with_default_app(path)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not open {kind.upper()}:\n{exc}")

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
        from pathlib import Path
        target = rec.bib_path if which == "bib" else rec.md_path
        if not target or not Path(target).exists():
            self._warn(f"No {which} file exists for this record yet.")
            return
        try:
            open_with_text_editor(str(target))
        except Exception as exc:  # noqa: BLE001
            self._warn(f"Could not open text editor:\n{exc}")

    def _on_record_action(self, _tab, action):
        if action == "reveal_bib":
            self._reveal("bib")
        elif action == "reveal_md":
            self._reveal("md")
        elif action == "edit_bib":
            self._open_in_editor("bib")
        elif action == "edit_md":
            self._open_in_editor("md")
        elif action == "open_pdf":
            self.open_fulltext("pdf")
        elif action == "open_epub":
            self.open_fulltext("epub")
        elif action == "rename":
            self.do_rename_record()
        elif action == "allocate":
            rec = self._current_record()
            self._allocate_records([rec.bibliotheca_id] if rec else [])

    def _allocate_records(self, bibliotheca_ids):
        if not self.workspace or not bibliotheca_ids:
            return
        from .gtk4_allocate_dialog import AllocateDialog
        AllocateDialog(self, self.workspace, bibliotheca_ids,
                       on_done=self._after_allocation).present()

    def _after_allocation(self, total):
        self.catalogue.refresh_after_allocation()
        self.set_status(f"Made {total} allocation(s) to My Works."
                        if total else "No new allocations.")

    def do_rename_record(self):
        rec = self._current_record()
        if not rec:
            self._warn("Select a record first.")
            return
        old_id = rec.bibliotheca_id

        def _rename(new_id):
            if not new_id:
                return
            try:
                self.workspace.rename_record(old_id, new_id)
            except ValueError as exc:
                self._warn(str(exc), heading="Could not rename")
                return
            self.catalogue.set_workspace(self.workspace)
            self.catalogue.reveal_record(new_id)
            self.set_status(f"Renamed '{old_id}' \u2192 '{new_id}'.")

        dialogs.prompt_text(self, "Rename Bibliotheca ID", _rename,
                            body=f"Rename '{old_id}' to:", initial=old_id,
                            ok_label="_Rename")

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------
    def do_validate(self):
        if not self.workspace:
            return
        root = self.config.get("fulltext_library_path", "") or None
        report = self.workspace.validate(root)
        text = ui_prefs.format_validation_report(report)
        dialogs.text_report(self, "Workspace Validation", text)

    # ------------------------------------------------------------------
    # Preferences / help
    # ------------------------------------------------------------------
    def do_preferences(self):
        from .gtk4_preferences import PreferencesWindow
        PreferencesWindow(self, self.config, workspace=self.workspace,
                          on_apply=self._apply_prefs_to_widgets).present()

    def do_shortcuts(self):
        from .gtk4_shortcuts import ShortcutsWindow
        ShortcutsWindow(self).present()

    def do_about(self):
        about = Adw.AboutWindow(
            transient_for=self, application_name=APP_NAME,
            version=__version__, application_icon="accessories-dictionary",
            comments="A personal reference manager for academics.")
        about.present()

    # ------------------------------------------------------------------
    # Tab signal relays
    # ------------------------------------------------------------------
    def _on_goto_record(self, _tab, bibliotheca_id):
        self._select_view(VIEW_CATALOGUE)
        if not self.catalogue.reveal_record(bibliotheca_id):
            self.set_status(
                f"Record {bibliotheca_id} not found in current view.")

    def _on_show_author_works(self, _tab, author_id):
        self._select_view(VIEW_CATALOGUE)
        self.catalogue.show_author_works(author_id)

    def _on_author_star_changed(self, _tab, _author_id, _starred):
        self.catalogue.refresh_starred_authors()

    def _on_show_outlet_works(self, _tab, outlet_id):
        self._select_view(VIEW_CATALOGUE)
        self.catalogue.show_outlet_works(outlet_id)

    def _on_outlet_star_changed(self, _tab, _outlet_id, _starred):
        self.catalogue.refresh_starred_outlets()

    def _on_outlet_changed(self, _tab):
        self.catalogue.refresh_starred_outlets()

    def _on_goto_outlet(self, _tab, outlet_id):
        self._select_view(VIEW_OUTLETS)
        self.outlets_tab.reveal_outlet(outlet_id)

    def _on_citation_style_chosen(self, style_id):
        ui_prefs.store_citation_style(self.config, self.workspace, style_id)

    # ------------------------------------------------------------------
    # Header/action helpers referenced by the mixins
    # ------------------------------------------------------------------
    def _on_toggle_sidebar(self, button):
        self.catalogue.set_sidebar_visible(button.get_active())

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------
    def _on_close_request(self, *_a):
        self.catalogue.flush_notes()
        w, h = self.get_default_size()
        self.config.window["width"] = w
        self.config.window["height"] = h
        self.config.save()
        return False
