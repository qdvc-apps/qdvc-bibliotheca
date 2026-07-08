"""Preferences dialog, backed by the Config object."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402


class PreferencesDialog(Gtk.Dialog):
    def __init__(self, parent, config):
        super().__init__(title="Preferences", transient_for=parent,
                         modal=True)
        self.config = config
        self.set_default_size(480, 300)
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_border_width(12)
        self.get_content_area().add(grid)

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

        self.show_all()

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
        self.config.save()


def _right(text):
    lbl = Gtk.Label(label=text, xalign=1)
    return lbl
