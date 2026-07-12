"""Header bars, primary menu, and the top-level view switcher (GTK4).

GNOME apps avoid menubars and toolbars; commands live on header bars with the
content they affect, plus a single primary (hamburger) menu whose final section
is Preferences / Keyboard Shortcuts / About, per the HIG. The four top-level
views (Catalogue / Authors / Outlets / DOI Lookup) are an ``Adw.ViewStack``
driven by an ``Adw.ViewSwitcher`` in the main header bar's title area.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, Adw  # noqa: E402

from .. import APP_NAME  # noqa: E402


class HeaderBarMixin:
    """Builds the main header bar (with view switcher + primary menu) and the
    small per-pane header bars used inside the Catalogue split view."""

    def _build_primary_menu(self):
        """The hamburger menu model. Command items reference win.* actions by
        name, so they share sensitivity/accels with everything else."""
        menu = Gio.Menu()

        workspace_section = Gio.Menu()
        workspace_section.append("Open Workspace\u2026", "win.open-workspace")
        # Recent submenu is rebuilt dynamically (see _rebuild_recent_menu).
        self._recent_menu = Gio.Menu()
        workspace_section.append_submenu("Open Recent", self._recent_menu)
        workspace_section.append("Close Workspace", "win.close-workspace")
        workspace_section.append("Import BibTeX\u2026", "win.import")
        workspace_section.append("Rescan Workspace", "win.refresh-workspace")
        menu.append_section(None, workspace_section)

        record_section = Gio.Menu()
        record_section.append("Sort\u2026", "win.sort")
        record_section.append("Rename Bibliotheca ID\u2026",
                              "win.rename-record")
        record_section.append("Validate Workspace\u2026", "win.validate")
        menu.append_section(None, record_section)

        # Final section, HIG order: Preferences, Keyboard Shortcuts, About.
        final = Gio.Menu()
        final.append("Preferences", "win.preferences")
        final.append("Keyboard Shortcuts", "win.shortcuts")
        final.append(f"About {APP_NAME}", "win.about")
        menu.append_section(None, final)
        return menu

    def _build_main_header(self, view_switcher_stack):
        """The window's top header bar: primary menu at the start, an
        Adw.ViewSwitcher (bound to the view stack) as the title, and the
        Open-Workspace + Import buttons at the end."""
        header = Adw.HeaderBar()

        switcher = Adw.ViewSwitcher()
        switcher.set_stack(view_switcher_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Primary menu (end)
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_primary(True)
        menu_btn.set_menu_model(self._build_primary_menu())
        menu_btn.set_tooltip_text("Main menu")
        header.pack_end(menu_btn)

        # Open workspace (start) — the most common entry action.
        open_btn = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        open_btn.set_tooltip_text("Open a workspace")
        open_btn.set_action_name("win.open-workspace")
        header.pack_start(open_btn)

        # Import (start)
        import_btn = Gtk.Button.new_from_icon_name("document-import-symbolic")
        import_btn.set_tooltip_text("Import BibTeX")
        import_btn.set_action_name("win.import")
        header.pack_start(import_btn)

        self._main_header = header
        self._view_switcher = switcher
        return header

    def _build_catalogue_sidebar_header(self):
        """Header bar for the Catalogue sidebar (Pane 1): holds the Rescan and
        Sort controls, which act on the whole catalogue."""
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        header.set_title_widget(Gtk.Label(label="Filters"))

        sort_btn = Gtk.Button.new_from_icon_name("view-sort-descending-symbolic")
        sort_btn.set_tooltip_text("Sort the catalogue\u2026")
        sort_btn.set_action_name("win.sort")
        header.pack_start(sort_btn)

        rescan_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        rescan_btn.set_tooltip_text("Rescan the workspace from disk")
        rescan_btn.set_action_name("win.refresh-workspace")
        header.pack_end(rescan_btn)
        return header

    def _build_catalogue_content_header(self):
        """Header bar for the Catalogue content side (Panes 2+3): the sidebar
        toggle and the Open-PDF/EPUB actions for the selected record."""
        header = Adw.HeaderBar()

        # Toggle the sidebar (the OverlaySplitView collapse).
        toggle = Gtk.ToggleButton()
        toggle.set_icon_name("sidebar-show-symbolic")
        toggle.set_active(True)
        toggle.set_tooltip_text("Show or hide the filters sidebar")
        toggle.connect("toggled", self._on_toggle_sidebar)
        header.pack_start(toggle)
        self._sidebar_toggle = toggle

        open_pdf = Gtk.Button.new_from_icon_name("application-pdf-symbolic")
        open_pdf.set_tooltip_text("Open the linked PDF")
        open_pdf.set_action_name("win.open-pdf")
        header.pack_end(open_pdf)
        self._open_pdf_btn = open_pdf

        return header
