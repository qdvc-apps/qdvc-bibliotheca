"""The Catalogue tab: a three-pane master-detail view."""

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GObject  # noqa: E402

from .platform_utils import open_with_default_app  # noqa: E402


# Sidebar node kinds
NODE_ALL = "all"
NODE_TYPE = "type"
NODE_WORK = "work"
NODE_WORKS_ROOT = "works_root"
NODE_AUTHOR = "author"
NODE_FULLTEXT = "fulltext"   # key in {"pdf","epub","none"}
NODE_DOI = "doi"             # key in {"set","unset"}
NODE_TEMP = "temp"  # transient "query results" node at the bottom


def _year_key(r):
    """Numeric year when possible (so 2009 < 2025), else 0, then raw string."""
    y = (r.year or "").strip()
    digits = "".join(ch for ch in y if ch.isdigit())
    return (int(digits) if digits else 0, y.lower())


# Multi-key sort: maps a stable sort-key id to a callable producing a
# comparison key from a Record. Order of this dict is the order shown to the
# user in the sort dialog.
SORT_KEYS = {
    "bibliotheca_id": lambda r: r.bibliotheca_id.lower(),
    "author": lambda r: (r.author or "").lower(),
    "year": _year_key,
    "outlet": lambda r: (r.outlet or "").lower(),
    "title": lambda r: (r.title or "").lower(),
    "type": lambda r: (r.type_label or "").lower(),
}

# Human labels for the sort-key ids, in display order.
SORT_LABELS = [
    ("bibliotheca_id", "Bibliotheca ID"),
    ("author", "Author"),
    ("year", "Year"),
    ("outlet", "Outlet"),
    ("title", "Title"),
    ("type", "Type"),
]


class CatalogueTab(Gtk.Box):
    __gsignals__ = {
        # emitted when the user wants to programmatically reveal a record
        "record-activated": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # emitted (bool has_selection) when the master selection changes
        "selection-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.workspace = None
        self._current_record = None
        self._suppress_notes_save = False
        self._autosave = True
        self._fulltext_root = None
        # (kind, key) describing the active sidebar filter, for refresh.
        self._active_filter = (NODE_ALL, "")
        # transient "query results" sidebar node state
        self._temp_author_id = None
        self._temp_iter = None
        self._suppress_sidebar_change = False
        # Multi-key sort: ordered list of (sort_key, ascending_bool).
        # Empty means default order (by bibliotheca_id, ascending).
        self._sort_spec = []
        # cache of the records currently shown (post-filter, pre-sort source)
        self._current_records = []

        self.paned_outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned_inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(self.paned_outer, True, True, 0)

        self.sidebar_widget = self._build_sidebar()
        self.detail_widget = self._build_detail()
        self.paned_outer.pack1(self.sidebar_widget, False, False)
        self.paned_outer.pack2(self.paned_inner, True, False)
        # Master pane gets the resize weight so extra width goes to the table,
        # not the detail pane (which only needs enough room to read a
        # reference and notes).
        self.paned_inner.pack1(self._build_master(), True, False)
        self.paned_inner.pack2(self.detail_widget, False, False)

        self.paned_outer.set_position(220)
        self.paned_inner.set_position(620)
        # Keep the detail pane compact by default.
        self.detail_widget.set_size_request(320, -1)

    # ------------------------------------------------------------------
    # Pane 1: sidebar
    # ------------------------------------------------------------------
    def _build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        # columns: icon-name, label, kind, key, pango-style(int)
        self.side_store = Gtk.TreeStore(str, str, str, str, int)
        self.side_view = Gtk.TreeView(model=self.side_store)
        self.side_view.set_headers_visible(False)
        col = Gtk.TreeViewColumn("")
        icon_r = Gtk.CellRendererPixbuf()
        text_r = Gtk.CellRendererText()
        col.pack_start(icon_r, False)
        col.pack_start(text_r, True)
        col.add_attribute(icon_r, "icon-name", 0)
        col.add_attribute(text_r, "text", 1)
        col.add_attribute(text_r, "style", 4)
        self.side_view.append_column(col)
        self.side_view.get_selection().connect("changed",
                                               self._on_sidebar_changed)
        self.side_view.connect("row-activated", self._on_sidebar_activated)
        self.side_view.connect("button-press-event",
                               self._on_sidebar_button_press)
        sw.add(self.side_view)
        box.pack_start(sw, True, True, 0)
        box.set_size_request(200, -1)
        return box

    def _rebuild_sidebar(self, temp_author_id=None):
        self.side_store.clear()
        self._temp_author_id = temp_author_id
        n = _pango_style_normal()
        self.side_store.append(
            None, ["edit-select-all", "All articles", NODE_ALL, "", n])
        by_type = self.side_store.append(
            None, ["view-list-symbolic", "By type", "", "", n])
        type_icons = {
            "Journal article": "text-x-generic",
            "Conference paper": "presentation",
            "Book chapter": "x-office-document",
            "Book": "accessories-dictionary",
            "Webpage": "text-html",
            "Other": "emblem-documents",
        }
        for label in ["Journal article", "Conference paper", "Book chapter",
                      "Book", "Webpage", "Other"]:
            self.side_store.append(
                by_type, [type_icons.get(label, "text-x-generic"),
                          label, NODE_TYPE, label, n])

        by_ft = self.side_store.append(
            None, ["emblem-documents", "By full-text", "", "", n])
        self.side_store.append(
            by_ft, ["application-pdf", "PDF available", NODE_FULLTEXT,
                    "pdf", n])
        self.side_store.append(
            by_ft, ["x-office-document", "EPUB available", NODE_FULLTEXT,
                    "epub", n])
        self.side_store.append(
            by_ft, ["window-close", "Not available", NODE_FULLTEXT,
                    "none", n])

        by_doi = self.side_store.append(
            None, ["insert-link", "By DOI status", "", "", n])
        self.side_store.append(
            by_doi, ["insert-link", "DOI is set", NODE_DOI, "set", n])
        self.side_store.append(
            by_doi, ["window-close", "DOI is not set", NODE_DOI,
                     "unset", n])

        works = self.side_store.append(
            None, ["folder-documents", "My works", NODE_WORKS_ROOT, "", n])
        if self.workspace:
            for key, work in sorted(self.workspace.my_works.items(),
                                    key=lambda kv: kv[1].name.lower()):
                self.side_store.append(
                    works, ["emblem-favorite", work.name, NODE_WORK, key, n])

        starred_root = self.side_store.append(
            None, ["starred", "Starred authors", "", "", n])
        if self.workspace:
            for a in self.workspace.starred_authors():
                self.side_store.append(
                    starred_root, ["starred", a.display_name,
                                   NODE_AUTHOR, a.author_id, n])

        # transient "query results" node pinned at the very bottom
        if temp_author_id and self.workspace:
            author = self.workspace.authors.get(temp_author_id)
            label = "Query results"
            if author:
                label = f"Query: {author.display_name}"
            self._temp_iter = self.side_store.append(
                None, ["edit-find", label, NODE_TEMP, temp_author_id,
                       _pango_style_italic()])
        else:
            self._temp_iter = None
        self.side_view.expand_all()

    def _on_sidebar_changed(self, selection):
        if self._suppress_sidebar_change:
            return
        model, it = selection.get_selected()
        if not it:
            return
        kind = model[it][2]
        key = model[it][3]
        # Selecting anything other than the transient node clears it.
        if kind != NODE_TEMP and self._temp_iter is not None:
            self._remove_temp_node()
        if kind in ("", NODE_WORKS_ROOT):
            # section headers: no filter action
            return
        self._apply_filter(kind, key)

    def _remove_temp_node(self):
        if self._temp_iter is not None:
            try:
                self.side_store.remove(self._temp_iter)
            except Exception:  # noqa: BLE001
                pass
        self._temp_iter = None
        self._temp_author_id = None

    def _apply_filter(self, kind, key):
        if not self.workspace:
            return
        if kind == NODE_ALL:
            self._active_filter = (NODE_ALL, "")
            self._populate_master(self.workspace.all_records())
        elif kind == NODE_TYPE:
            self._active_filter = (NODE_TYPE, key)
            self._populate_master(self.workspace.records_by_type(key))
        elif kind == NODE_WORK:
            self._active_filter = (NODE_WORK, key)
            self._populate_master(self.workspace.records_for_work(key))
        elif kind == NODE_FULLTEXT:
            self._active_filter = (NODE_FULLTEXT, key)
            self._populate_master(self.workspace.records_by_fulltext(key))
        elif kind == NODE_DOI:
            self._active_filter = (NODE_DOI, key)
            self._populate_master(
                self.workspace.records_by_doi_status(key == "set"))
        elif kind in (NODE_AUTHOR, NODE_TEMP):
            self._active_filter = (kind, key)
            self._populate_master(self.workspace.records_for_author(key))

    def _on_sidebar_activated(self, _view, path, _col):
        it = self.side_store.get_iter(path)
        if self.side_store[it][2] == NODE_WORK:
            self._edit_work(self.side_store[it][3])

    def _on_sidebar_button_press(self, _view, event):
        # right-click (button 3) -> context menu on the row under the pointer
        if event.button != 3:
            return False
        pathinfo = self.side_view.get_path_at_pos(int(event.x), int(event.y))
        if not pathinfo:
            return False
        path = pathinfo[0]
        self.side_view.get_selection().select_path(path)
        it = self.side_store.get_iter(path)
        kind = self.side_store[it][2]
        key = self.side_store[it][3]
        menu = None
        if kind == NODE_WORKS_ROOT:
            menu = Gtk.Menu()
            mi = Gtk.MenuItem(label="Add work\u2026")
            mi.connect("activate", lambda *_: self._add_work())
            menu.append(mi)
        elif kind == NODE_WORK:
            menu = Gtk.Menu()
            mi_edit = Gtk.MenuItem(label="Edit work\u2026")
            mi_edit.connect("activate", lambda *_: self._edit_work(key))
            menu.append(mi_edit)
            mi_add = Gtk.MenuItem(label="Add work\u2026")
            mi_add.connect("activate", lambda *_: self._add_work())
            menu.append(mi_add)
        if menu:
            menu.show_all()
            menu.popup_at_pointer(event)
            return True
        return False

    def _selected_work_key(self):
        model, it = self.side_view.get_selection().get_selected()
        if it and model[it][2] == NODE_WORK:
            return model[it][3]
        return None

    def _add_work(self):
        if not self.workspace:
            return
        dlg = Gtk.Dialog(title="New Work", transient_for=self.get_toplevel(),
                         modal=True)
        dlg.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("_Create", Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        area = dlg.get_content_area()
        area.set_border_width(10)
        area.add(Gtk.Label(label="Name for the new work:", xalign=0))
        entry = Gtk.Entry()
        entry.set_activates_default(True)
        area.add(entry)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            dlg.destroy()
            if name:
                work = self.workspace.create_my_work(name)
                self._rebuild_sidebar()
                self._edit_work_object(work)
        else:
            dlg.destroy()

    def _edit_work(self, key):
        work = self.workspace.my_works.get(key)
        if work:
            self._edit_work_object(work, key)

    def _edit_work_object(self, work, key=None):
        from .myworks_editor import MyWorkEditor
        dlg = MyWorkEditor(self.get_toplevel(), self.workspace, work)
        if dlg.run() == Gtk.ResponseType.OK:
            dlg.apply()
            self._rebuild_sidebar()
            # if we are currently viewing this work, refresh the master list
            if key and self._active_filter == (NODE_WORK, key):
                self._populate_master(self.workspace.records_for_work(key))
        dlg.destroy()

    # ------------------------------------------------------------------
    # Pane 2: master table
    # ------------------------------------------------------------------
    def _build_master(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Filter\u2026")
        self.search.connect("search-changed", self._on_search)
        box.pack_start(self.search, False, False, 2)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        # columns: pdf_icon, bibliotheca_id, author, year, outlet, title, type
        self.master_store = Gtk.ListStore(str, str, str, str, str, str, str)
        self.master_filter = self.master_store.filter_new()
        self.master_filter.set_visible_func(self._filter_visible)
        self.master_view = Gtk.TreeView(model=self.master_filter)
        self.master_view.connect("button-press-event",
                                 self._on_master_button_press)

        # PDF indicator column (icon only)
        pdf_r = Gtk.CellRendererPixbuf()
        pdf_col = Gtk.TreeViewColumn("", pdf_r, icon_name=0)
        pdf_col.set_fixed_width(28)
        pdf_col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.master_view.append_column(pdf_col)

        text_cols = ["Bibliotheca ID", "Author", "Year", "Outlet", "Title",
                     "Type"]
        for offset, title in enumerate(text_cols):
            i = offset + 1  # store column (0 is the icon)
            r = Gtk.CellRendererText()
            r.set_property("ellipsize", Pango.EllipsizeMode.END)
            c = Gtk.TreeViewColumn(title, r, text=i)
            c.set_resizable(True)
            c.set_sort_column_id(i)
            if title == "Year":
                # wide enough for a 4-digit year (plus a little breathing room)
                c.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
                c.set_fixed_width(60)
                c.set_min_width(60)
                r.set_property("ellipsize", Pango.EllipsizeMode.NONE)
            elif title == "Title":
                c.set_expand(True)
            elif title == "Outlet":
                c.set_min_width(120)
            self.master_view.append_column(c)
        self.master_view.get_selection().connect("changed",
                                                  self._on_master_changed)
        sw.add(self.master_view)
        box.pack_start(sw, True, True, 0)
        return box

    def _populate_master(self, records):
        self._current_records = list(records)
        self.master_store.clear()
        for r in self._sorted_records(self._current_records):
            icon = "application-pdf" if getattr(r, "has_pdf", False) else ""
            self.master_store.append(
                [icon, r.bibliotheca_id, r.author, r.year, r.outlet, r.title,
                 r.type_label])

    def _sorted_records(self, records):
        """Return records ordered by the current multi-key sort spec.

        Applied as a stable sort from the least-significant key up to the
        most-significant, which yields correct multi-column precedence.
        """
        if not self._sort_spec:
            return records
        result = list(records)
        for key, ascending in reversed(self._sort_spec):
            keyfunc = SORT_KEYS.get(key)
            if not keyfunc:
                continue
            result.sort(key=keyfunc, reverse=not ascending)
        return result

    def set_sort_spec(self, spec):
        """spec: list of (sort_key, ascending_bool). Repopulates the view."""
        self._sort_spec = list(spec or [])
        # re-render the currently shown records with the new order
        self.master_store.clear()
        for r in self._sorted_records(self._current_records):
            icon = "application-pdf" if getattr(r, "has_pdf", False) else ""
            self.master_store.append(
                [icon, r.bibliotheca_id, r.author, r.year, r.outlet, r.title,
                 r.type_label])

    def get_sort_spec(self):
        return list(self._sort_spec)

    def _filter_visible(self, model, it, _data):
        needle = self.search.get_text().strip().lower()
        if not needle:
            return True
        # search only the text columns (skip the icon column 0)
        for col in range(1, 7):
            val = model[it][col] or ""
            if needle in val.lower():
                return True
        return False

    def _on_search(self, _entry):
        self.master_filter.refilter()

    def _on_master_changed(self, selection):
        model, it = selection.get_selected()
        if not it:
            self._current_record = None
            self.emit("selection-changed", False)
            return
        bid = model[it][1]
        rec = self.workspace.get(bid) if self.workspace else None
        if rec:
            self._show_detail(rec)
            self.emit("selection-changed", True)
        else:
            self.emit("selection-changed", False)

    # ------------------------------------------------------------------
    # Pane 3: detail
    # ------------------------------------------------------------------
    def _build_detail(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_border_width(6)

        ref_lbl = Gtk.Label(xalign=0)
        ref_lbl.set_markup("<b>Reference (APA 7)</b>")
        box.pack_start(ref_lbl, False, False, 2)

        ref_sw = Gtk.ScrolledWindow()
        ref_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        ref_sw.set_min_content_height(90)
        self.ref_label = Gtk.Label(xalign=0, yalign=0)
        self.ref_label.set_line_wrap(True)
        self.ref_label.set_selectable(True)
        self.ref_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        ref_sw.add(self.ref_label)
        box.pack_start(ref_sw, False, True, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.copy_rich_btn = Gtk.Button(label="Copy (rich)")
        self.copy_plain_btn = Gtk.Button(label="Copy (plain text)")
        self.copy_rich_btn.connect("clicked", self._copy_rich)
        self.copy_plain_btn.connect("clicked", self._copy_plain)
        btn_box.pack_start(self.copy_rich_btn, False, False, 0)
        btn_box.pack_start(self.copy_plain_btn, False, False, 0)

        # Open PDF button (uses the PDF icon); shown only when a PDF is set.
        self.open_pdf_btn = Gtk.Button(label="Open PDF")
        self.open_pdf_btn.set_image(Gtk.Image.new_from_icon_name(
            "application-pdf", Gtk.IconSize.BUTTON))
        self.open_pdf_btn.set_always_show_image(True)
        self.open_pdf_btn.set_tooltip_text(
            "Open the PDF with your system viewer")
        self.open_pdf_btn.connect("clicked", lambda _b: self._open_pdf())
        btn_box.pack_start(self.open_pdf_btn, False, False, 0)
        box.pack_start(btn_box, False, False, 4)

        notes_lbl = Gtk.Label(xalign=0)
        notes_lbl.set_markup("<b>My notes (Markdown)</b>")
        box.pack_start(notes_lbl, False, False, 2)

        notes_sw = Gtk.ScrolledWindow()
        notes_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.notes_view = Gtk.TextView()
        self.notes_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.notes_view.set_monospace(True)
        self.notes_buffer = self.notes_view.get_buffer()
        self.notes_buffer.connect("changed", self._on_notes_changed)
        notes_sw.add(self.notes_view)
        box.pack_start(notes_sw, True, True, 0)

        self.detail_status = Gtk.Label(xalign=0)
        self.detail_status.get_style_context().add_class("dim-label")
        box.pack_start(self.detail_status, False, False, 2)

        self._set_detail_sensitive(False)
        return box

    def _set_detail_sensitive(self, on):
        for w in (self.copy_rich_btn, self.copy_plain_btn, self.notes_view):
            w.set_sensitive(on)
        if not on:
            self.open_pdf_btn.set_sensitive(False)

    def _show_detail(self, rec):
        # persist any pending notes for the previous record first
        self._flush_notes()
        self._current_record = rec
        markup = rec.apa_markup()
        try:
            self.ref_label.set_markup(markup)
        except Exception:
            self.ref_label.set_text(rec.apa_plain())

        fm, body = rec.read_notes()
        self._current_frontmatter = fm
        self._suppress_notes_save = True
        self.notes_buffer.set_text(body)
        self._suppress_notes_save = False
        self._set_detail_sensitive(True)

        self._refresh_detail_status(rec)

    def _refresh_detail_status(self, rec):
        """Update the status line under the notes box from the record's
        current frontmatter (re-read from disk so it reflects recent writes)."""
        fm, _ = rec.read_notes()
        self._current_frontmatter = fm
        extras = []
        if fm.get("pdf"):
            extras.append("PDF")
        if fm.get("epub"):
            extras.append("EPUB")
        works = fm.get("my_works") or []
        detail = f"ID: {rec.bibliotheca_id}"
        if extras:
            detail += "   \u2022 Full-text: " + ", ".join(extras)
        if works:
            detail += f"   \u2022 Cited in {len(works)} of my works"
        self.detail_status.set_text(detail)
        # Open PDF button only enabled when a PDF is on file
        self.open_pdf_btn.set_sensitive(bool(fm.get("pdf")))

    def _on_notes_changed(self, _buf):
        if self._suppress_notes_save or not self._current_record:
            return
        # debounce-lite: save on focus-out / record change; mark dirty here.
        self._notes_dirty = True

    def _flush_notes(self):
        rec = getattr(self, "_current_record", None)
        if not rec or not getattr(self, "_notes_dirty", False):
            return
        if not self._autosave:
            return
        start, end = self.notes_buffer.get_bounds()
        body = self.notes_buffer.get_text(start, end, True)
        from pathlib import Path
        from . import workspace as ws_mod
        md_path = Path(rec.md_path) if rec.md_path \
            else self.workspace.md_path_for(rec.bibliotheca_id)
        fm = getattr(self, "_current_frontmatter", {}) or {}
        ws_mod.write_markdown(md_path, fm, body)
        rec.md_path = str(md_path)
        self._notes_dirty = False

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------
    def _copy_rich(self, _btn):
        if not self._current_record:
            return
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        # Pango markup isn't a clipboard format; provide the visible rich text
        # via the label's selection semantics by copying plain with markup
        # intent. For true rich copy we emit both plain and a simple HTML.
        plain = self._current_record.apa_plain()
        html = _markup_to_html(self._current_record.apa_markup())
        _set_clipboard_rich(clip, plain, html)

    def _copy_plain(self, _btn):
        if not self._current_record:
            return
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clip.set_text(self._current_record.apa_plain(), -1)
        clip.store()

    # ------------------------------------------------------------------
    # Full-text (PDF/EPUB)
    # ------------------------------------------------------------------
    def _on_master_button_press(self, _view, event):
        if event.button != 3:  # right-click only
            return False
        pathinfo = self.master_view.get_path_at_pos(int(event.x), int(event.y))
        if not pathinfo:
            return False
        path = pathinfo[0]
        self.master_view.get_selection().select_path(path)
        it = self.master_filter.get_iter(path)
        bid = self.master_filter[it][1]
        rec = self.workspace.get(bid) if self.workspace else None
        if not rec:
            return False

        fm, _ = rec.read_notes()
        menu = Gtk.Menu()

        mi_pdf = Gtk.MenuItem(label="Set PDF\u2026")
        mi_pdf.connect("activate", lambda *_: self._set_fulltext(rec, "pdf"))
        menu.append(mi_pdf)

        mi_epub = Gtk.MenuItem(label="Set EPUB\u2026")
        mi_epub.connect("activate", lambda *_: self._set_fulltext(rec, "epub"))
        menu.append(mi_epub)

        if fm.get("pdf") or fm.get("epub"):
            menu.append(Gtk.SeparatorMenuItem())
            if fm.get("pdf"):
                mi_open = Gtk.MenuItem(label="Open PDF")
                mi_open.connect("activate", lambda *_: self._open_pdf(rec))
                menu.append(mi_open)
            mi_clear = Gtk.MenuItem(label="Remove full-text link(s)")
            mi_clear.connect("activate",
                             lambda *_: self._clear_fulltext(rec))
            menu.append(mi_clear)

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _set_fulltext(self, rec, kind):
        if not rec or not self.workspace:
            return
        # persist any pending notes-body edits first, so the fulltext write
        # (which rewrites the frontmatter) does not clobber unsaved notes.
        self._flush_notes()
        label = kind.upper()
        dlg = Gtk.FileChooserDialog(
            title=f"Select {label} for {rec.bibliotheca_id}",
            transient_for=self.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("_Cancel", Gtk.ResponseType.CANCEL,
                        "_Select", Gtk.ResponseType.OK)
        # open at the full-text library by default
        if self._fulltext_root and Path(self._fulltext_root).is_dir():
            dlg.set_current_folder(self._fulltext_root)
        flt = Gtk.FileFilter()
        flt.set_name(f"{label} files")
        flt.add_pattern(f"*.{kind}")
        dlg.add_filter(flt)
        all_flt = Gtk.FileFilter()
        all_flt.set_name("All files")
        all_flt.add_pattern("*")
        dlg.add_filter(all_flt)

        if dlg.run() != Gtk.ResponseType.OK:
            dlg.destroy()
            return
        chosen = dlg.get_filename()
        dlg.destroy()

        outside = False
        if self._fulltext_root:
            try:
                Path(chosen).resolve().relative_to(
                    Path(self._fulltext_root).resolve())
            except ValueError:
                outside = True

        self.workspace.set_fulltext_path(rec.bibliotheca_id, kind, chosen,
                                         self._fulltext_root)
        self._after_fulltext_change(rec)
        if outside:
            self._warn_outside_library(label)

    def _clear_fulltext(self, rec):
        if not rec or not self.workspace:
            return
        self._flush_notes()
        for kind in ("pdf", "epub"):
            self.workspace.set_fulltext_path(rec.bibliotheca_id, kind, None,
                                             self._fulltext_root)
        self._after_fulltext_change(rec)

    def _open_pdf(self, rec=None):
        rec = rec or self._current_record
        if not rec or not self.workspace:
            return
        path = self.workspace.resolve_fulltext_path(
            rec.bibliotheca_id, "pdf", self._fulltext_root)
        if not path:
            return
        if not Path(path).exists():
            self._warn_missing_file(path)
            return
        open_with_default_app(path)

    def _after_fulltext_change(self, rec):
        # refresh detail status (if this is the shown record) + master icon
        if self._current_record and \
                self._current_record.bibliotheca_id == rec.bibliotheca_id:
            self._refresh_detail_status(rec)
        self._update_row_pdf_icon(rec)

    def _update_row_pdf_icon(self, rec):
        icon = "application-pdf" if rec.has_pdf else ""
        for row in self.master_store:
            if row[1] == rec.bibliotheca_id:
                row[0] = icon
                break

    def _warn_outside_library(self, label):
        dlg = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), modal=True,
            message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK,
            text=f"The {label} is outside your full-text library folder.")
        dlg.format_secondary_text(
            "Its absolute path was stored instead of a relative one. To keep "
            "paths portable, place full-text files inside the library folder "
            "set in Preferences.")
        dlg.run()
        dlg.destroy()

    def _warn_missing_file(self, path):
        dlg = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), modal=True,
            message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK,
            text="The file could not be found.")
        dlg.format_secondary_text(str(path))
        dlg.run()
        dlg.destroy()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def set_workspace(self, workspace):
        self._flush_notes()
        self.workspace = workspace
        self._current_record = None
        self._notes_dirty = False
        self._active_filter = (NODE_ALL, "")
        self._rebuild_sidebar()
        if workspace:
            self._populate_master(workspace.all_records())
        else:
            self.master_store.clear()
        self.ref_label.set_text("")
        self._suppress_notes_save = True
        self.notes_buffer.set_text("")
        self._suppress_notes_save = False
        self.detail_status.set_text("")
        self._set_detail_sensitive(False)
        self.emit("selection-changed", False)

    def reveal_record(self, bibliotheca_id):
        """Select a record in the master table by id (used by DOI lookup)."""
        # Ensure "All articles" is the active filter so the row is present.
        self._active_filter = (NODE_ALL, "")
        self._populate_master(self.workspace.all_records())
        for row in self.master_filter:
            if row[1] == bibliotheca_id:
                self.master_view.get_selection().select_iter(row.iter)
                path = row.path
                self.master_view.scroll_to_cell(path, None, True, 0.5, 0)
                return True
        return False

    # --- public API used by the main window ---------------------------
    def current_record(self):
        return self._current_record

    def flush_notes(self):
        self._flush_notes()

    def refresh_current_view(self):
        kind, key = self._active_filter
        self._apply_filter(kind, key)

    def set_sidebar_visible(self, visible):
        self.sidebar_widget.set_no_show_all(not visible)
        self.sidebar_widget.set_visible(visible)

    def set_detail_visible(self, visible):
        self.detail_widget.set_no_show_all(not visible)
        self.detail_widget.set_visible(visible)

    def set_notes_font(self, font_str):
        try:
            self.notes_view.override_font(
                Pango.FontDescription.from_string(font_str))
        except Exception:  # noqa: BLE001
            pass

    def set_autosave(self, on):
        self._autosave = bool(on)

    def set_fulltext_root(self, path):
        self._fulltext_root = path or None

    def refresh_starred_authors(self):
        """Rebuild the sidebar so the Starred Authors section reflects
        changes made in the Authors tab."""
        self._rebuild_sidebar()

    def show_author_works(self, author_id):
        """Filter the master list to a given author's works. If the author is
        starred, select their node in the sidebar; otherwise add a transient
        italic 'Query results' node at the bottom and select that, so Pane 1
        stays consistent with Pane 2."""
        if not self.workspace:
            return
        author = self.workspace.authors.get(author_id)
        is_starred = bool(author and author.starred)

        if is_starred:
            # ensure no stale temp node lingers
            if self._temp_iter is not None:
                self._remove_temp_node()
            self._rebuild_sidebar()
            selected = False
            for row in self.side_store:
                if self._select_author_row(row, author_id):
                    selected = True
                    break
            if not selected:
                self._apply_filter(NODE_AUTHOR, author_id)
        else:
            # rebuild with a transient node pinned at the bottom, and select it
            self._rebuild_sidebar(temp_author_id=author_id)
            if self._temp_iter is not None:
                self.side_view.get_selection().select_iter(self._temp_iter)
            else:
                self._apply_filter(NODE_TEMP, author_id)

    def _select_author_row(self, parent_row, author_id):
        for child in parent_row.iterchildren():
            if child[2] == NODE_AUTHOR and child[3] == author_id:
                self.side_view.get_selection().select_iter(child.iter)
                return True
        return False


# ----------------------------------------------------------------------
# clipboard helpers
# ----------------------------------------------------------------------

def _markup_to_html(markup: str) -> str:
    # Pango uses <i>, which is already valid HTML. Wrap for completeness.
    return f"<html><body>{markup}</body></html>"


def _pango_style_normal() -> int:
    try:
        return int(Pango.Style.NORMAL)
    except Exception:  # noqa: BLE001
        return 0


def _pango_style_italic() -> int:
    try:
        return int(Pango.Style.ITALIC)
    except Exception:  # noqa: BLE001
        return 2


# text/html target info id used in the target table below.
_TARGET_HTML = 0
_TARGET_TEXT = 1

# Keep a strong reference to the owner so it is not garbage-collected while it
# owns the clipboard; otherwise the "get" callback fires on freed memory
# (which is what produced the `free(): invalid pointer` crash).
_clipboard_owner = None


class _ClipboardOwner(GObject.Object):
    """A GObject that owns the clipboard and serves target data on request."""

    def __init__(self, plain_text: str, html: str):
        super().__init__()
        self.plain_text = plain_text
        self.html_bytes = html.encode("utf-8")

    def get_func(self, _clipboard, selection_data, info, _user_data=None):
        if info == _TARGET_HTML:
            selection_data.set(
                Gdk.Atom.intern("text/html", False), 8, self.html_bytes)
        else:
            selection_data.set_text(self.plain_text, -1)

    def clear_func(self, _clipboard, _user_data=None):
        pass


def _set_clipboard_rich(clip, plain_text: str, html: str) -> None:
    """Put both text/plain and text/html on the clipboard.

    PyGObject does not expose ``Gtk.Clipboard.set_with_data`` (calling it
    crashes the interpreter), so we use ``set_with_owner`` with a GObject we
    keep alive, and fall back to plain text if that is unavailable.
    """
    global _clipboard_owner

    targets = [
        Gtk.TargetEntry.new("text/html", 0, _TARGET_HTML),
        Gtk.TargetEntry.new("UTF8_STRING", 0, _TARGET_TEXT),
        Gtk.TargetEntry.new("text/plain;charset=utf-8", 0, _TARGET_TEXT),
        Gtk.TargetEntry.new("text/plain", 0, _TARGET_TEXT),
        Gtk.TargetEntry.new("STRING", 0, _TARGET_TEXT),
    ]

    owner = _ClipboardOwner(plain_text, html)
    ok = False
    set_with_owner = getattr(clip, "set_with_owner", None)
    if set_with_owner is not None:
        try:
            ok = set_with_owner(
                targets, owner.get_func, owner.clear_func, owner)
        except Exception:  # noqa: BLE001
            ok = False

    if ok:
        # Retain the owner; releasing it would invalidate the callbacks.
        _clipboard_owner = owner
    else:
        # Reliable fallback: plain text only (better than crashing).
        clip.set_text(plain_text, -1)
        clip.store()
