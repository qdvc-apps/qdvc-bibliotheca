"""Import BibTeX dialog (GTK4): paste text or load a .bib file, optionally
allocating the imported records to a chosen work.

An ``Adw.Window`` with Cancel/Import in the header bar (modern dialog action
placement). Because GTK4 has no ``run()``, the result is delivered through an
``on_import(text, work_key)`` callback fired when Import is clicked.
"""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, Adw  # noqa: E402

from . import gtk4_dialogs as dialogs  # noqa: E402
from .gtk4_common import TextItem  # noqa: E402


class ImportDialog(Adw.Window):
    def __init__(self, parent, workspace=None, preselect_work_key=None,
                 on_import=None):
        super().__init__(transient_for=parent, modal=True,
                         title="Import BibTeX")
        self.workspace = workspace
        self._on_import = on_import
        self.set_default_size(600, 520)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel)
        import_btn = Gtk.Button(label="Import")
        import_btn.add_css_class("suggested-action")
        import_btn.connect("clicked", self._on_import_clicked)
        header.pack_end(import_btn)
        toolbar.add_top_bar(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ("top", "bottom", "start", "end"):
            getattr(body, f"set_margin_{m}")(10)

        info = Gtk.Label(xalign=0)
        info.set_markup(
            "Paste BibTeX below, or load a <tt>.bib</tt> file. Multiple "
            "entries are supported; each is filed by its citation key.")
        info.set_wrap(True)
        body.append(info)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        choose = Gtk.Button(label="Choose file\u2026")
        choose.connect("clicked", self._on_choose_file)
        row.append(choose)
        self.file_label = Gtk.Label(xalign=0)
        self.file_label.add_css_class("dim-label")
        self.file_label.set_hexpand(True)
        row.append(self.file_label)
        body.append(row)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_vexpand(True)
        self.textview = Gtk.TextView()
        self.textview.set_monospace(True)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.buffer = self.textview.get_buffer()
        sw.set_child(self.textview)
        body.append(sw)

        alloc_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        alloc_row.append(Gtk.Label(label="Allocate imported records to:"))
        self._work_model = Gio.ListStore(item_type=TextItem)
        self._work_model.append(TextItem("(none)", ""))
        preselect_index = 0
        if workspace:
            for i, (key, work) in enumerate(sorted(
                    workspace.my_works.items(),
                    key=lambda kv: kv[1].name.lower()), start=1):
                self._work_model.append(TextItem(work.name, key))
                if key == preselect_work_key:
                    preselect_index = i
        self.work_dropdown = Gtk.DropDown(model=self._work_model)
        self._setup_work_factory()
        self.work_dropdown.set_selected(preselect_index)
        self.work_dropdown.set_hexpand(True)
        alloc_row.append(self.work_dropdown)
        body.append(alloc_row)

        toolbar.set_content(body)
        self.set_content(toolbar)

    def _setup_work_factory(self):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup",
                        lambda _f, li: li.set_child(Gtk.Label(xalign=0)))

        def bind(_f, li):
            item = li.get_item()
            li.get_child().set_text(item.text if item else "")
        factory.connect("bind", bind)
        self.work_dropdown.set_factory(factory)

    def allocate_work_key(self):
        item = self.work_dropdown.get_selected_item()
        return (item.key or None) if item else None

    def get_bibtex_text(self):
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, True)

    def _on_choose_file(self, _btn):
        def _chosen(path):
            try:
                text = Path(path).read_text(encoding="utf-8",
                                            errors="replace")
            except OSError as exc:
                self.file_label.set_text(f"Could not read: {exc}")
                return
            self.buffer.set_text(text)
            self.file_label.set_text(Path(path).name)

        dialogs.choose_file(self, "Choose a .bib file", _chosen,
                            filters=[("BibTeX files (*.bib)", ["*.bib"]),
                                     ("All files", ["*"])])

    def _on_import_clicked(self, _btn):
        text = self.get_bibtex_text()
        work_key = self.allocate_work_key()
        self.close()
        if self._on_import:
            self._on_import(text, work_key)
