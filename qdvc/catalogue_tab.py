"""The Catalogue tab: a three-pane master-detail view."""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GObject  # noqa: E402


# Sidebar node kinds
NODE_ALL = "all"
NODE_TYPE = "type"
NODE_WORK = "work"


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
        # (kind, key) describing the active sidebar filter, for refresh.
        self._active_filter = (NODE_ALL, "")

        self.paned_outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned_inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(self.paned_outer, True, True, 0)

        self.sidebar_widget = self._build_sidebar()
        self.detail_widget = self._build_detail()
        self.paned_outer.pack1(self.sidebar_widget, False, False)
        self.paned_outer.pack2(self.paned_inner, True, False)
        self.paned_inner.pack1(self._build_master(), True, False)
        self.paned_inner.pack2(self.detail_widget, True, False)

        self.paned_outer.set_position(220)
        self.paned_inner.set_position(430)

    # ------------------------------------------------------------------
    # Pane 1: sidebar
    # ------------------------------------------------------------------
    def _build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        # columns: icon-name, label, kind, key
        self.side_store = Gtk.TreeStore(str, str, str, str)
        self.side_view = Gtk.TreeView(model=self.side_store)
        self.side_view.set_headers_visible(False)
        col = Gtk.TreeViewColumn("")
        icon_r = Gtk.CellRendererPixbuf()
        text_r = Gtk.CellRendererText()
        col.pack_start(icon_r, False)
        col.pack_start(text_r, True)
        col.add_attribute(icon_r, "icon-name", 0)
        col.add_attribute(text_r, "text", 1)
        self.side_view.append_column(col)
        self.side_view.get_selection().connect("changed",
                                               self._on_sidebar_changed)
        self.side_view.connect("row-activated", self._on_sidebar_activated)
        sw.add(self.side_view)
        box.pack_start(sw, True, True, 0)

        # small action bar for My works management
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.add_work_btn = Gtk.Button.new_from_icon_name(
            "list-add", Gtk.IconSize.SMALL_TOOLBAR)
        self.add_work_btn.set_tooltip_text("New work\u2026")
        self.add_work_btn.connect("clicked", self._on_add_work)
        self.edit_work_btn = Gtk.Button.new_from_icon_name(
            "document-edit", Gtk.IconSize.SMALL_TOOLBAR)
        self.edit_work_btn.set_tooltip_text("Edit selected work\u2026")
        self.edit_work_btn.connect("clicked", self._on_edit_selected_work)
        bar.pack_start(self.add_work_btn, False, False, 0)
        bar.pack_start(self.edit_work_btn, False, False, 0)
        box.pack_start(bar, False, False, 0)

        box.set_size_request(200, -1)
        return box

    def _rebuild_sidebar(self):
        self.side_store.clear()
        self.side_store.append(
            None, ["edit-select-all", "All articles", NODE_ALL, ""])
        by_type = self.side_store.append(
            None, ["view-list-symbolic", "By type", "", ""])
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
                          label, NODE_TYPE, label])
        works = self.side_store.append(
            None, ["folder-documents", "My works", "", ""])
        if self.workspace:
            for key, work in sorted(self.workspace.my_works.items(),
                                    key=lambda kv: kv[1].name.lower()):
                self.side_store.append(
                    works, ["emblem-favorite", work.name, NODE_WORK, key])
        self.side_view.expand_all()

    def _on_sidebar_changed(self, selection):
        model, it = selection.get_selected()
        if not it:
            return
        kind = model[it][2]
        key = model[it][3]
        self._apply_filter(kind, key)

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

    def _on_sidebar_activated(self, _view, path, _col):
        it = self.side_store.get_iter(path)
        if self.side_store[it][2] == NODE_WORK:
            self._edit_work(self.side_store[it][3])

    def _selected_work_key(self):
        model, it = self.side_view.get_selection().get_selected()
        if it and model[it][2] == NODE_WORK:
            return model[it][3]
        return None

    def _on_edit_selected_work(self, _btn):
        key = self._selected_work_key()
        if key:
            self._edit_work(key)

    def _on_add_work(self, _btn):
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
        # columns: bibliotheca_id, author, year, title, type
        self.master_store = Gtk.ListStore(str, str, str, str, str)
        self.master_filter = self.master_store.filter_new()
        self.master_filter.set_visible_func(self._filter_visible)
        self.master_view = Gtk.TreeView(model=self.master_filter)
        for i, title in enumerate(
                ["Bibliotheca ID", "Author", "Year", "Title", "Type"]):
            r = Gtk.CellRendererText()
            r.set_property("ellipsize", Pango.EllipsizeMode.END)
            c = Gtk.TreeViewColumn(title, r, text=i)
            c.set_resizable(True)
            c.set_sort_column_id(i)
            if title == "Title":
                c.set_expand(True)
            self.master_view.append_column(c)
        self.master_view.get_selection().connect("changed",
                                                  self._on_master_changed)
        sw.add(self.master_view)
        box.pack_start(sw, True, True, 0)
        return box

    def _populate_master(self, records):
        self.master_store.clear()
        for r in records:
            self.master_store.append(
                [r.bibliotheca_id, r.author, r.year, r.title, r.type_label])

    def _filter_visible(self, model, it, _data):
        needle = self.search.get_text().strip().lower()
        if not needle:
            return True
        for col in range(5):
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
        bid = model[it][0]
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
            if row[0] == bibliotheca_id:
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


# ----------------------------------------------------------------------
# clipboard helpers
# ----------------------------------------------------------------------

def _markup_to_html(markup: str) -> str:
    # Pango uses <i>, which is already valid HTML. Wrap for completeness.
    return f"<html><body>{markup}</body></html>"


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
