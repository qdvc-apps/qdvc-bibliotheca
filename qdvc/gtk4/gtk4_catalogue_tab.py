"""The Catalogue view (GTK4 / libadwaita): a three-pane master-detail browser.

Layout (HIG):
  * ``Adw.OverlaySplitView`` — sidebar = Pane 1 (filter navigation), content =
    a ``Gtk.Paned`` holding Pane 2 (master ``Gtk.ColumnView``) and Pane 3
    (detail).
  * Pane 1 is a ``Gtk.ListView`` over a ``Gtk.TreeListModel`` of ``NavItem``s
    (section headers + selectable rows with an article count).
  * Pane 2 is a ``Gtk.ColumnView`` over a ``Gtk.SingleSelection(
    Gtk.FilterListModel(Gio.ListStore(RecordItem)))``. Sorting is done in the
    core (multi-key spec) and the store is filled in sorted order; the search
    box drives a ``Gtk.CustomFilter``.
  * Pane 3 renders the reference (built-in APA or a chosen CSL style), copy
    buttons, and a Markdown-highlighted notes editor.

The public method contract matches the GTK3 ``CatalogueTab`` exactly, so the
shared window code calls both identically.
"""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Gio, Pango, GObject, Adw  # noqa: E402

from ..platform_utils import open_with_default_app, open_with_text_editor
from .. import csl as csl_mod
from .. import acis as acis_mod
from ..catalogue_sort import (SORT_KEYS, count_label as _count_label,
                              order_jflags as _order_jflags,
                              markup_to_html as _markup_to_html,
                              APA_STYLE_ID, ACIS_STYLE_ID)
from .gtk4_common import (NODE_ALL, NODE_TYPE, NODE_WORK, NODE_WORKS_ROOT,
                          NODE_AUTHOR, NODE_OUTLET, NODE_FULLTEXT, NODE_DOI,
                          NODE_TEMP, NavItem, RecordItem, TextItem)
from .gtk4_md_highlight import MarkdownHighlighter
from . import gtk4_dialogs as dialogs

TYPE_ICONS = {
    "Journal article": "text-x-generic",
    "Proceedings": "presentation",
    "Book chapter": "x-office-document",
    "Book": "accessories-dictionary",
    "Webpage": "text-html",
    "Other": "emblem-documents",
}
TYPE_ORDER = ["Journal article", "Proceedings", "Book chapter", "Book",
              "Webpage", "Other"]


class CatalogueView(Gtk.Box):
    __gsignals__ = {
        "record-activated": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "selection-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
        "record-action": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "goto-outlet": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, window=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.window = window
        self.workspace = None
        self._current_record = None
        self._suppress_notes_save = False
        self._notes_dirty = False
        self._autosave = True
        self._fulltext_root = None
        self._active_filter = (NODE_ALL, "")
        self._temp_author_id = None
        self._suppress_sidebar_change = False
        self._sort_spec = []
        self._current_records = []
        self._jflag_priority = {}
        self._current_style = APA_STYLE_ID
        self._style_change_cb = None
        self._suppress_style_change = False
        self._current_frontmatter = {}

        self.split = Adw.OverlaySplitView()
        self.split.set_hexpand(True)
        self.split.set_vexpand(True)
        self.split.set_sidebar(self._build_sidebar())
        content = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        content.set_start_child(self._build_master())
        content.set_end_child(self._build_detail())
        content.set_position(620)
        content.set_resize_start_child(True)
        content.set_resize_end_child(False)
        self.split.set_content(content)
        self.split.set_min_sidebar_width(200)
        self.split.set_max_sidebar_width(320)
        self.append(self.split)

    # ==================================================================
    # Pane 1: sidebar
    # ==================================================================
    def _build_sidebar(self):
        self.nav_root = Gio.ListStore(item_type=NavItem)

        def child_model(item):
            if item.children:
                store = Gio.ListStore(item_type=NavItem)
                for c in item.children:
                    store.append(c)
                return store
            return None

        self.nav_tree = Gtk.TreeListModel.new(
            self.nav_root, False, True, child_model)
        self.nav_selection = Gtk.SingleSelection(model=self.nav_tree)
        self.nav_selection.set_autoselect(False)
        self.nav_selection.connect("notify::selected",
                                   self._on_sidebar_changed)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._nav_setup)
        factory.connect("bind", self._nav_bind)

        self.nav_view = Gtk.ListView(model=self.nav_selection,
                                     factory=factory)
        self.nav_view.add_css_class("navigation-sidebar")

        # right-click on works root / a work row -> work-management menu
        nav_gesture = Gtk.GestureClick()
        nav_gesture.set_button(Gdk.BUTTON_SECONDARY)
        nav_gesture.connect("pressed", self._on_sidebar_secondary_click)
        self.nav_view.add_controller(nav_gesture)

        self._nav_popover = Gtk.PopoverMenu()
        self._nav_popover.set_parent(self.nav_view)
        self._nav_popover.set_has_arrow(False)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_child(self.nav_view)
        return scroller

    def _nav_setup(self, _factory, list_item):
        expander = Gtk.TreeExpander()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        icon = Gtk.Image()
        label = Gtk.Label(xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_hexpand(True)
        count = Gtk.Label(xalign=1)
        count.add_css_class("dim-label")
        row.append(icon)
        row.append(label)
        row.append(count)
        expander.set_child(row)
        list_item.set_child(expander)
        # stash sub-widgets for bind
        list_item._icon = icon
        list_item._label = label
        list_item._count = count
        list_item._expander = expander

    def _nav_bind(self, _factory, list_item):
        row = list_item.get_item()          # Gtk.TreeListRow
        item = row.get_item()               # NavItem
        list_item._expander.set_list_row(row)
        # tag the row box so a right-click can recover the NavItem
        list_item._expander._qdvc_navitem = item
        if item.icon:
            list_item._icon.set_from_icon_name(item.icon)
        else:
            list_item._icon.clear()
        if item.is_header:
            list_item._label.set_markup(f"<b>{GObject.markup_escape_text(item.label)}</b>")
        else:
            list_item._label.set_text(item.label)
        list_item._count.set_text(_count_label(item.count) if not
                                  item.is_header else "")
        # headers are not selectable targets for filtering
        list_item.set_selectable(not item.is_header)

    def _rebuild_sidebar(self, temp_author_id=None):
        self._temp_author_id = temp_author_id
        counts = self._compute_sidebar_counts()
        self.nav_root.remove_all()

        self.nav_root.append(NavItem("All articles", NODE_ALL, "",
                                     "edit-select-all-symbolic",
                                     counts["all"]))

        type_children = [
            NavItem(label, NODE_TYPE, label,
                    TYPE_ICONS.get(label, "text-x-generic"),
                    counts["type"].get(label, 0))
            for label in TYPE_ORDER]
        self.nav_root.append(NavItem("By type", icon="view-list-symbolic",
                                     children=type_children, is_header=True))

        ft_children = [
            NavItem("PDF available", NODE_FULLTEXT, "pdf",
                    "application-pdf", counts["ft"].get("pdf", 0)),
            NavItem("EPUB available", NODE_FULLTEXT, "epub",
                    "x-office-document", counts["ft"].get("epub", 0)),
            NavItem("Not available", NODE_FULLTEXT, "none",
                    "window-close", counts["ft"].get("none", 0)),
        ]
        self.nav_root.append(NavItem("By full-text",
                                     icon="emblem-documents-symbolic",
                                     children=ft_children, is_header=True))

        doi_children = [
            NavItem("DOI is set", NODE_DOI, "set", "insert-link",
                    counts["doi"].get("set", 0)),
            NavItem("DOI is not set", NODE_DOI, "unset", "window-close",
                    counts["doi"].get("unset", 0)),
        ]
        self.nav_root.append(NavItem("By DOI status", icon="insert-link",
                                     children=doi_children, is_header=True))

        work_children = []
        if self.workspace:
            for key, work in sorted(self.workspace.my_works.items(),
                                    key=lambda kv: kv[1].name.lower()):
                work_children.append(
                    NavItem(work.name, NODE_WORK, key, "emblem-favorite",
                            counts["work"].get(key, 0)))
        self.nav_root.append(NavItem("My works", NODE_WORKS_ROOT, "",
                                     "folder-documents",
                                     children=work_children, is_header=True))

        author_children = []
        if self.workspace:
            for a in self.workspace.starred_authors():
                author_children.append(
                    NavItem(a.display_name, NODE_AUTHOR, a.author_id,
                            "starred", len(a.record_ids)))
        self.nav_root.append(NavItem("Starred authors", icon="starred",
                                     children=author_children,
                                     is_header=True))

        outlet_children = []
        if self.workspace:
            for j in self.workspace.starred_outlets():
                label = j.nickname or j.display_name
                outlet_children.append(
                    NavItem(label, NODE_OUTLET, j.outlet_id, "starred",
                            len(j.record_ids)))
        self.nav_root.append(NavItem("Starred outlets", icon="starred",
                                     children=outlet_children,
                                     is_header=True))

        if temp_author_id and self.workspace:
            author = self.workspace.authors.get(temp_author_id)
            label = "Query results"
            temp_count = 0
            if author:
                label = f"Query: {author.display_name}"
                temp_count = len(author.record_ids)
            self.nav_root.append(NavItem(label, NODE_TEMP, temp_author_id,
                                         "edit-find", temp_count))

    def _compute_sidebar_counts(self):
        counts = {"all": 0, "type": {}, "ft": {"pdf": 0, "epub": 0, "none": 0},
                  "doi": {"set": 0, "unset": 0}, "work": {}}
        if not self.workspace:
            return counts
        records = self.workspace.all_records()
        counts["all"] = len(records)
        for r in records:
            counts["type"][r.type_label] = counts["type"].get(
                r.type_label, 0) + 1
            has_pdf = getattr(r, "has_pdf", False)
            has_epub = getattr(r, "has_epub", False)
            if has_pdf:
                counts["ft"]["pdf"] += 1
            if has_epub:
                counts["ft"]["epub"] += 1
            if not has_pdf and not has_epub:
                counts["ft"]["none"] += 1
            counts["doi"]["set" if r.doi else "unset"] += 1
        for key in self.workspace.my_works:
            counts["work"][key] = len(self.workspace.records_for_work(key))
        return counts

    def _selected_nav_item(self):
        row = self.nav_selection.get_selected_item()
        return row.get_item() if row is not None else None

    def _on_sidebar_changed(self, *_a):
        if self._suppress_sidebar_change:
            return
        item = self._selected_nav_item()
        if item is None or item.is_header:
            return
        self._apply_filter(item.kind, item.key)

    # --- sidebar work management (right-click) ------------------------
    def _on_sidebar_secondary_click(self, _gesture, _n_press, x, y):
        if not self.workspace:
            return
        widget = self.nav_view.pick(x, y, Gtk.PickFlags.DEFAULT)
        item = self._nav_item_for_widget(widget)
        if item is None:
            return
        menu = None
        if item.kind == NODE_WORKS_ROOT:
            menu = Gio.Menu()
            menu.append("Add work\u2026", "catnav.add-work")
        elif item.kind == NODE_WORK:
            self._nav_menu_work_key = item.key
            menu = Gio.Menu()
            menu.append("Edit work\u2026", "catnav.edit-work")
            menu.append("Open YAML in Text Editor", "catnav.open-work-yaml")
            add_section = Gio.Menu()
            add_section.append("Add work\u2026", "catnav.add-work")
            menu.append_section(None, add_section)
        if menu is None:
            return
        self._ensure_nav_actions()
        self._nav_popover.set_menu_model(menu)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self._nav_popover.set_pointing_to(rect)
        self._nav_popover.popup()

    def _nav_item_for_widget(self, widget):
        """Walk up from a picked widget to the tagged TreeExpander that carries
        the row's NavItem (set in _nav_bind)."""
        w = widget
        while w is not None and w is not self.nav_view:
            item = getattr(w, "_qdvc_navitem", None)
            if item is not None:
                return item
            w = w.get_parent()
        return None

    def _ensure_nav_actions(self):
        if getattr(self, "_nav_actions_installed", False):
            return
        group = Gio.SimpleActionGroup()

        def add(name, cb):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            group.add_action(act)

        add("add-work", lambda *_: self._add_work())
        add("edit-work",
            lambda *_: self._edit_work(getattr(self, "_nav_menu_work_key",
                                               None)))
        add("open-work-yaml",
            lambda *_: self._open_work_yaml(getattr(self, "_nav_menu_work_key",
                                                    None)))
        self.insert_action_group("catnav", group)
        self._nav_actions_installed = True

    def _open_work_yaml(self, key):
        work = self.workspace.my_works.get(key) if (self.workspace and key) \
            else None
        if not work or not work.path:
            return
        if not Path(work.path).exists():
            return
        open_with_text_editor(work.path)

    def _add_work(self):
        if not self.workspace:
            return

        def _create(name):
            if not name:
                return
            work = self.workspace.create_my_work(name)
            self._rebuild_sidebar()
            self._edit_work_object(work)

        dialogs.prompt_text(self.window or self.get_root(), "New Work",
                            _create, body="Name for the new work:",
                            ok_label="_Create")

    def _edit_work(self, key):
        if not key:
            return
        work = self.workspace.my_works.get(key)
        if work:
            self._edit_work_object(work, key)

    def _edit_work_object(self, work, key=None):
        from .gtk4_myworks_editor import MyWorkEditor

        def _applied():
            self._rebuild_sidebar()
            if key and self._active_filter == (NODE_WORK, key):
                self._populate_master(self.workspace.records_for_work(key))

        MyWorkEditor(self.window or self.get_root(), self.workspace, work,
                     on_apply=_applied).present()

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
        elif kind == NODE_OUTLET:
            self._active_filter = (NODE_OUTLET, key)
            self._populate_master(self.workspace.records_for_outlet(key))

    def _select_sidebar_where(self, predicate):
        """Select the first nav row (searching one level of children) whose
        NavItem satisfies ``predicate``. Returns True if selected."""
        n = self.nav_tree.get_n_items()
        for i in range(n):
            row = self.nav_tree.get_item(i)
            item = row.get_item()
            if not item.is_header and predicate(item):
                self.nav_selection.set_selected(i)
                return True
        return False

    # ==================================================================
    # Pane 2: master ColumnView
    # ==================================================================
    def _build_master(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Filter\u2026")
        self.search.set_margin_top(4)
        self.search.set_margin_bottom(4)
        self.search.set_margin_start(4)
        self.search.set_margin_end(4)
        self.search.connect("search-changed", self._on_search)
        box.append(self.search)

        self.master_store = Gio.ListStore(item_type=RecordItem)
        self.master_filter = Gtk.CustomFilter.new(self._match_row, None)
        self.master_filter_model = Gtk.FilterListModel(
            model=self.master_store, filter=self.master_filter)
        self.master_selection = Gtk.SingleSelection(
            model=self.master_filter_model)
        self.master_selection.set_autoselect(False)
        self.master_selection.set_can_unselect(True)
        self.master_selection.connect("notify::selected",
                                      self._on_master_changed)

        self.column_view = Gtk.ColumnView(model=self.master_selection)
        self.column_view.set_vexpand(True)
        self.column_view.set_reorderable(False)
        self._add_columns()

        # right-click / menu key -> record popover
        gesture = Gtk.GestureClick()
        gesture.set_button(Gdk.BUTTON_SECONDARY)
        gesture.connect("pressed", self._on_master_secondary_click)
        self.column_view.add_controller(gesture)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        scroller.set_child(self.column_view)
        box.append(scroller)

        # a popover reused for the record context menu
        self._record_popover = Gtk.PopoverMenu()
        self._record_popover.set_parent(self.column_view)
        self._record_popover.set_has_arrow(False)
        return box

    def _add_columns(self):
        # PDF icon column
        icon_factory = Gtk.SignalListItemFactory()

        def icon_setup(_f, li):
            img = Gtk.Image()
            img.set_pixel_size(16)
            li.set_child(img)

        def icon_bind(_f, li):
            img = li.get_child()
            item = li.get_item()
            if item.has_pdf:
                img.set_from_icon_name("application-pdf")
            else:
                img.clear()
        icon_factory.connect("setup", icon_setup)
        icon_factory.connect("bind", icon_bind)
        icon_col = Gtk.ColumnViewColumn(title="", factory=icon_factory)
        icon_col.set_fixed_width(32)
        self.column_view.append_column(icon_col)

        self.column_view.append_column(
            self._text_col("Bibliotheca ID", "bibliotheca_id"))
        self.column_view.append_column(self._text_col("Author", "author"))
        self.column_view.append_column(
            self._text_col("Year", "year", ellipsize=False))
        self.column_view.append_column(self._text_col("J-Flags", "jflags",
                                                      ellipsize=False))
        self.column_view.append_column(
            self._text_col("Outlet", "outlet_markup", markup=True,
                           expand=False))
        self.column_view.append_column(
            self._text_col("Title", "title", expand=True))
        self.column_view.append_column(self._text_col("Type", "type_label"))

    def _text_col(self, title, attr, *, markup=False, expand=False,
                  ellipsize=True):
        factory = Gtk.SignalListItemFactory()

        def setup(_f, li):
            label = Gtk.Label(xalign=0)
            if ellipsize:
                label.set_ellipsize(Pango.EllipsizeMode.END)
            li.set_child(label)

        def bind(_f, li):
            label = li.get_child()
            item = li.get_item()
            label._qdvc_record_item = item
            value = getattr(item, attr, "")
            if markup:
                label.set_markup(value or "")
            else:
                label.set_text(str(value) if value not in (None, "") else "")
        factory.connect("setup", setup)
        factory.connect("bind", bind)
        col = Gtk.ColumnViewColumn(title=title, factory=factory)
        col.set_resizable(True)
        col.set_expand(expand)
        return col

    def _make_record_item(self, r):
        return RecordItem(
            r,
            jflags=self._jflags_display(r),
            outlet_markup=self._outlet_markup(r),
            has_pdf=getattr(r, "has_pdf", False))

    def _outlet_markup(self, r):
        from html import escape
        outlet_text = r.outlet or "\u2014"
        outlet = self.workspace.outlet_for_record(r) if self.workspace else None
        if outlet and outlet.nickname:
            return (f"<b>({escape(outlet.nickname)})</b> "
                    f"{escape(outlet.name)}")
        return escape(outlet_text)

    def _jflags_display(self, r):
        outlet = self.workspace.outlet_for_record(r) if self.workspace \
            else None
        if not outlet or not outlet.jflags:
            return "\u2014"
        ordered = _order_jflags(outlet.sorted_jflags(), self._jflag_priority)
        return ", ".join(ordered) if ordered else "\u2014"

    def _populate_master(self, records):
        self._current_records = list(records)
        self.master_store.remove_all()
        for r in self._sorted_records(self._current_records):
            self.master_store.append(self._make_record_item(r))

    def _sorted_records(self, records):
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
        self._sort_spec = list(spec or [])
        self.master_store.remove_all()
        for r in self._sorted_records(self._current_records):
            self.master_store.append(self._make_record_item(r))

    def get_sort_spec(self):
        return list(self._sort_spec)

    def _match_row(self, item, _user_data=None):
        needle = self.search.get_text().strip().lower()
        if not needle:
            return True
        # Mirror the GTK3 filter, which searched the visible text columns:
        # id, author, year, J-Flags, Outlet, title, type. Use the record's
        # plain outlet value (not the Pango markup) for the Outlet column.
        outlet_plain = item.record.outlet or ""
        hay = " ".join([
            item.bibliotheca_id or "", item.author or "", item.year or "",
            item.jflags or "", outlet_plain, item.title or "",
            item.type_label or ""]).lower()
        return needle in hay

    def _on_search(self, _entry):
        self.master_filter.changed(Gtk.FilterChange.DIFFERENT)

    def _on_master_changed(self, *_a):
        item = self.master_selection.get_selected_item()
        if item is None:
            self._current_record = None
            self.emit("selection-changed", False)
            return
        rec = item.record
        if rec:
            self._show_detail(rec)
            self.emit("selection-changed", True)
        else:
            self.emit("selection-changed", False)

    # ==================================================================
    # Pane 3: detail
    # ==================================================================
    def _build_detail(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        box.set_size_request(320, -1)

        ref_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ref_lbl = Gtk.Label(xalign=0)
        ref_lbl.set_markup("<b>Reference</b>")
        ref_lbl.set_hexpand(True)
        ref_head.append(ref_lbl)
        style_caption = Gtk.Label(label="Style:")
        style_caption.add_css_class("dim-label")
        ref_head.append(style_caption)
        # DropDown over TextItem strings; model rebuilt in _populate_style_combo
        self.style_model = Gio.ListStore(item_type=TextItem)
        self.style_dropdown = Gtk.DropDown(model=self.style_model)
        self.style_dropdown.set_tooltip_text(
            "Citation style: the built-in APA 7 renderer, or a custom CSL "
            "file from the workspace's csl/ folder")
        self._setup_style_dropdown_factory()
        self.style_dropdown.connect("notify::selected", self._on_style_changed)
        ref_head.append(self.style_dropdown)
        box.append(ref_head)

        ref_sw = Gtk.ScrolledWindow()
        ref_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        ref_sw.set_min_content_height(90)
        self.ref_label = Gtk.Label(xalign=0, yalign=0)
        self.ref_label.set_wrap(True)
        self.ref_label.set_selectable(True)
        self.ref_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        ref_sw.set_child(self.ref_label)
        box.append(ref_sw)

        # In-text citation row (shown only for styles that define one, i.e. the
        # built-in ACIS style): both parenthetical and narrative forms.
        self.intext_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                  spacing=6)
        intext_caption = Gtk.Label(xalign=0)
        intext_caption.set_markup("<b>In-text</b>")
        self.intext_box.append(intext_caption)
        self.intext_label = Gtk.Label(xalign=0)
        self.intext_label.set_wrap(True)
        self.intext_label.set_selectable(True)
        self.intext_box.append(self.intext_label)
        self.intext_box.set_visible(False)
        box.append(self.intext_box)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_margin_top(4)
        btn_box.set_margin_bottom(4)
        self.copy_rich_btn = Gtk.Button(label="Copy (rich)")
        self.copy_plain_btn = Gtk.Button(label="Copy (plain text)")
        self.copy_rich_btn.connect("clicked", self._copy_rich)
        self.copy_plain_btn.connect("clicked", self._copy_plain)
        btn_box.append(self.copy_rich_btn)
        btn_box.append(self.copy_plain_btn)
        self.open_pdf_btn = Gtk.Button(label="Open PDF")
        self.open_pdf_btn.set_tooltip_text(
            "Open the PDF with your system viewer")
        self.open_pdf_btn.connect("clicked", lambda _b: self._open_pdf())
        btn_box.append(self.open_pdf_btn)
        box.append(btn_box)

        notes_lbl = Gtk.Label(xalign=0)
        notes_lbl.set_markup("<b>My notes (Markdown)</b>")
        box.append(notes_lbl)

        notes_sw = Gtk.ScrolledWindow()
        notes_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        notes_sw.set_vexpand(True)
        self.notes_view = Gtk.TextView()
        self.notes_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.notes_view.set_monospace(True)
        self.notes_buffer = self.notes_view.get_buffer()
        self.notes_buffer.connect("changed", self._on_notes_changed)
        self.highlighter = MarkdownHighlighter(self.notes_buffer)
        notes_sw.set_child(self.notes_view)
        box.append(notes_sw)

        self.detail_status = Gtk.Label(xalign=0)
        self.detail_status.add_css_class("dim-label")
        box.append(self.detail_status)

        self._set_detail_sensitive(False)
        return box

    def _setup_style_dropdown_factory(self):
        factory = Gtk.SignalListItemFactory()

        def setup(_f, li):
            li.set_child(Gtk.Label(xalign=0))

        def bind(_f, li):
            item = li.get_item()
            li.get_child().set_text(item.text if item else "")
        factory.connect("setup", setup)
        factory.connect("bind", bind)
        self.style_dropdown.set_factory(factory)

    def _set_detail_sensitive(self, on):
        for w in (self.copy_rich_btn, self.copy_plain_btn, self.notes_view):
            w.set_sensitive(on)
        if not on:
            self.open_pdf_btn.set_sensitive(False)

    def _active_csl_path(self):
        if self._current_style in (APA_STYLE_ID, ACIS_STYLE_ID) \
                or not self.workspace:
            return None
        p = self.workspace.csl_path(self._current_style)
        return str(p) if p else None

    def _acis_disambiguator(self, rec):
        if not self.workspace:
            return ""
        return self.workspace.acis_disambiguator(rec)

    def _reference_markup(self, rec):
        if self._current_style == ACIS_STYLE_ID:
            return rec.acis_markup(self._acis_disambiguator(rec))
        csl_path = self._active_csl_path()
        if csl_path:
            return csl_mod.render_markup(rec.bib(), csl_path)
        return rec.apa_markup()

    def _reference_plain(self, rec):
        if self._current_style == ACIS_STYLE_ID:
            return rec.acis_plain(self._acis_disambiguator(rec))
        csl_path = self._active_csl_path()
        if csl_path:
            return csl_mod.render_plain(rec.bib(), csl_path)
        return rec.apa_plain()

    def _render_reference(self, rec):
        try:
            self.ref_label.set_markup(self._reference_markup(rec))
        except Exception:  # noqa: BLE001
            self.ref_label.set_text(self._reference_plain(rec))
        self._render_intext(rec)

    def _render_intext(self, rec):
        """Show the in-text citation row for styles that define one (ACIS):
        both the parenthetical and narrative forms."""
        if self._current_style != ACIS_STYLE_ID:
            self.intext_box.set_visible(False)
            return
        dis = self._acis_disambiguator(rec)
        paren = rec.acis_in_text_plain(dis, narrative=False)
        narrative = rec.acis_in_text_plain(dis, narrative=True)
        self.intext_label.set_text(f"{paren}    {narrative}")
        self.intext_box.set_visible(True)

    def _style_ids(self):
        """Ordered list of style ids currently in the dropdown model."""
        return [self.style_model.get_item(i).key
                for i in range(self.style_model.get_n_items())]

    def _populate_style_combo(self):
        self._suppress_style_change = True
        self.style_model.remove_all()
        self.style_model.append(TextItem("APA 7 (built-in)", APA_STYLE_ID))
        self.style_model.append(TextItem("ACIS (built-in)", ACIS_STYLE_ID))
        files = self.workspace.list_csl_files() if self.workspace else []
        for name in files:
            self.style_model.append(TextItem(name, name))
        if self._current_style not in (APA_STYLE_ID, ACIS_STYLE_ID) and \
                self._current_style not in files:
            self._current_style = APA_STYLE_ID
        ids = self._style_ids()
        if self._current_style in ids:
            self.style_dropdown.set_selected(ids.index(self._current_style))
        self._suppress_style_change = False

    def _on_style_changed(self, *_a):
        if self._suppress_style_change:
            return
        idx = self.style_dropdown.get_selected()
        ids = self._style_ids()
        if idx < 0 or idx >= len(ids):
            return
        self._current_style = ids[idx]
        if self._style_change_cb:
            self._style_change_cb(self._current_style)
        if self._current_record:
            self._render_reference(self._current_record)

    def _show_detail(self, rec):
        self._flush_notes()
        self._current_record = rec
        self._render_reference(rec)
        fm, body = rec.read_notes()
        self._current_frontmatter = fm
        self._suppress_notes_save = True
        self.notes_buffer.set_text(body)
        self._suppress_notes_save = False
        self.highlighter.highlight()
        self._set_detail_sensitive(True)
        self._refresh_detail_status(rec)

    def _refresh_detail_status(self, rec):
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
        self.open_pdf_btn.set_sensitive(bool(fm.get("pdf")))

    def _on_notes_changed(self, _buf):
        if self._suppress_notes_save or not self._current_record:
            return
        self._notes_dirty = True
        self.highlighter.highlight()

    def _flush_notes(self):
        rec = self._current_record
        if not rec or not self._notes_dirty:
            self._notes_dirty = False
            return
        if not self._autosave:
            return
        start, end = self.notes_buffer.get_bounds()
        body = self.notes_buffer.get_text(start, end, True)
        from .. import markdown_io
        md_path = Path(rec.md_path) if rec.md_path \
            else self.workspace.md_path_for(rec.bibliotheca_id)
        fm = getattr(self, "_current_frontmatter", {}) or {}
        markdown_io.write_markdown(md_path, fm, body)
        rec.md_path = str(md_path)
        self._notes_dirty = False

    def _copy_rich(self, _btn):
        if not self._current_record:
            return
        plain = self._reference_plain(self._current_record)
        html = _markup_to_html(self._reference_markup(self._current_record))
        self._set_clipboard_rich(plain, html)

    def _copy_plain(self, _btn):
        if not self._current_record:
            return
        text = self._reference_plain(self._current_record)
        self.get_clipboard().set(text)

    def _set_clipboard_rich(self, plain_text, html):
        # GTK4: provide text/html plus a plain-text fallback via a
        # ContentProvider union; fall back to plain text on any error.
        try:
            html_bytes = GLib_bytes(html)
            html_provider = Gdk.ContentProvider.new_for_bytes(
                "text/html", html_bytes)
            text_provider = Gdk.ContentProvider.new_for_value(plain_text)
            provider = Gdk.ContentProvider.new_union(
                [html_provider, text_provider])
            self.get_clipboard().set_content(provider)
        except Exception:  # noqa: BLE001
            self.get_clipboard().set(plain_text)

    # ==================================================================
    # Record context menu (Gio.Menu + PopoverMenu)
    # ==================================================================
    def _on_master_secondary_click(self, gesture, _n_press, x, y):
        # find the record cell under the pointer, select its row, show the menu
        picked = self.column_view.pick(x, y, Gtk.PickFlags.DEFAULT)
        record_item = self._record_item_for_widget(picked)
        if record_item is not None:
            # select the corresponding row so the menu acts on it
            n = self.master_filter_model.get_n_items()
            for i in range(n):
                if self.master_filter_model.get_item(i) is record_item:
                    self.master_selection.set_selected(i)
                    break
        rec = self._current_record
        if rec is None:
            return
        self._present_record_menu(rec, x, y)

    def _record_item_for_widget(self, widget):
        w = widget
        while w is not None and w is not self.column_view:
            item = getattr(w, "_qdvc_record_item", None)
            if item is not None:
                return item
            w = w.get_parent()
        return None

    def _present_record_menu(self, rec, x, y):
        menu = self._build_record_menu(rec)
        self._record_popover.set_menu_model(menu)
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        self._record_popover.set_pointing_to(rect)
        self._record_popover.popup()

    def _build_record_menu(self, rec):
        fm, _ = rec.read_notes()
        has_pdf = bool(fm.get("pdf"))
        has_epub = bool(fm.get("epub"))
        self._ensure_menu_actions()

        menu = Gio.Menu()
        reveal = Gio.Menu()
        reveal.append("Reveal .bib in File Manager", "cat.reveal-bib")
        reveal.append("Reveal .md in File Manager", "cat.reveal-md")
        menu.append_section(None, reveal)

        edit = Gio.Menu()
        edit.append("Open .bib in Text Editor", "cat.edit-bib")
        edit.append("Open .md in Text Editor", "cat.edit-md")
        if has_pdf:
            edit.append("Open PDF", "cat.open-pdf")
        if has_epub:
            edit.append("Open EPUB", "cat.open-epub")
        menu.append_section(None, edit)

        if self.workspace and self.workspace.outlet_for_record(rec):
            goto = Gio.Menu()
            goto.append("Go to outlet", "cat.goto-outlet")
            menu.append_section(None, goto)

        idsec = Gio.Menu()
        idsec.append("Copy Bibliotheca ID", "cat.copy-id")
        idsec.append("Rename Bibliotheca ID\u2026", "cat.rename")
        idsec.append("Allocate to My Works\u2026", "cat.allocate")
        menu.append_section(None, idsec)

        ftsec = Gio.Menu()
        ftsec.append("Set PDF\u2026", "cat.set-pdf")
        ftsec.append("Set EPUB\u2026", "cat.set-epub")
        if has_pdf or has_epub:
            ftsec.append("Remove full-text link(s)", "cat.clear-ft")
        menu.append_section(None, ftsec)
        return menu

    def _ensure_menu_actions(self):
        if getattr(self, "_menu_actions_installed", False):
            return
        group = Gio.SimpleActionGroup()

        def add(name, cb):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            group.add_action(act)

        add("reveal-bib", lambda *_: self.emit("record-action", "reveal_bib"))
        add("reveal-md", lambda *_: self.emit("record-action", "reveal_md"))
        add("edit-bib", lambda *_: self.emit("record-action", "edit_bib"))
        add("edit-md", lambda *_: self.emit("record-action", "edit_md"))
        add("open-pdf", lambda *_: self.emit("record-action", "open_pdf"))
        add("open-epub", lambda *_: self.emit("record-action", "open_epub"))
        add("goto-outlet", self._menu_goto_outlet)
        add("copy-id", lambda *_: self._copy_bibliotheca_id(
            self._current_record))
        add("rename", lambda *_: self.emit("record-action", "rename"))
        add("allocate", lambda *_: self.emit("record-action", "allocate"))
        add("set-pdf", lambda *_: self._set_fulltext(self._current_record,
                                                     "pdf"))
        add("set-epub", lambda *_: self._set_fulltext(self._current_record,
                                                      "epub"))
        add("clear-ft", lambda *_: self._clear_fulltext(self._current_record))
        self.insert_action_group("cat", group)
        self._menu_actions_installed = True

    def _menu_goto_outlet(self, *_a):
        rec = self._current_record
        if not rec or not self.workspace:
            return
        outlet = self.workspace.outlet_for_record(rec)
        if outlet:
            self.emit("goto-outlet", outlet.outlet_id)

    def _copy_bibliotheca_id(self, rec):
        if rec:
            self.get_clipboard().set(rec.bibliotheca_id)

    # ==================================================================
    # Full-text set/clear/open
    # ==================================================================
    def _set_fulltext(self, rec, kind):
        if not rec or not self.workspace:
            return
        self._flush_notes()
        label = kind.upper()
        filters = [(f"{label} files", [f"*.{kind}"]), ("All files", ["*"])]

        def _chosen(path):
            outside = False
            if self._fulltext_root:
                try:
                    Path(path).resolve().relative_to(
                        Path(self._fulltext_root).resolve())
                except ValueError:
                    outside = True
            self.workspace.set_fulltext_path(rec.bibliotheca_id, kind, path,
                                             self._fulltext_root)
            self._after_fulltext_change(rec)
            if outside:
                dialogs.message(
                    self.window or self.get_root(),
                    f"The {label} is outside your full-text library folder.",
                    "Its absolute path was stored instead of a relative one. "
                    "To keep paths portable, place full-text files inside the "
                    "library folder set in Preferences.")

        dialogs.choose_file(self.window or self.get_root(),
                            f"Select {label} for {rec.bibliotheca_id}",
                            _chosen, initial=self._fulltext_root,
                            filters=filters)

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
            dialogs.message(self.window or self.get_root(),
                            "The file could not be found.", str(path),
                            kind="warning")
            return
        open_with_default_app(path)

    def _after_fulltext_change(self, rec):
        if self._current_record and \
                self._current_record.bibliotheca_id == rec.bibliotheca_id:
            self._refresh_detail_status(rec)
        self._update_row_pdf_icon(rec)

    def _update_row_pdf_icon(self, rec):
        n = self.master_store.get_n_items()
        for i in range(n):
            item = self.master_store.get_item(i)
            if item.bibliotheca_id == rec.bibliotheca_id:
                item.has_pdf = getattr(rec, "has_pdf", False)
                self.master_store.items_changed(i, 1, 1)
                break

    # ==================================================================
    # Public API (matches the GTK3 CatalogueTab contract)
    # ==================================================================
    def set_workspace(self, workspace):
        self._flush_notes()
        self.workspace = workspace
        self._current_record = None
        self._notes_dirty = False
        self._active_filter = (NODE_ALL, "")
        self._populate_style_combo()
        self._rebuild_sidebar()
        if workspace:
            self._populate_master(workspace.all_records())
        else:
            self.master_store.remove_all()
        self.ref_label.set_text("")
        self.intext_box.set_visible(False)
        self._suppress_notes_save = True
        self.notes_buffer.set_text("")
        self._suppress_notes_save = False
        self.detail_status.set_text("")
        self._set_detail_sensitive(False)
        self.emit("selection-changed", False)

    def reveal_record(self, bibliotheca_id):
        self._active_filter = (NODE_ALL, "")
        self._populate_master(self.workspace.all_records())
        n = self.master_filter_model.get_n_items()
        for i in range(n):
            item = self.master_filter_model.get_item(i)
            if item.bibliotheca_id == bibliotheca_id:
                self.master_selection.set_selected(i)
                self.column_view.scroll_to(
                    i, None, Gtk.ListScrollFlags.FOCUS, None)
                return True
        return False

    def current_record(self):
        return self._current_record

    def flush_notes(self):
        self._flush_notes()

    def refresh_current_view(self):
        kind, key = self._active_filter
        self._apply_filter(kind, key)

    def set_sidebar_visible(self, visible):
        self.split.set_show_sidebar(visible)

    def set_detail_visible(self, visible):
        # Pane 3 lives in the content Gtk.Paned; toggle its end child.
        content = self.split.get_content()
        end = content.get_end_child()
        if end is not None:
            end.set_visible(visible)

    def set_notes_font(self, font_str):
        try:
            self.highlighter.set_code_font(font_str)
        except Exception:  # noqa: BLE001
            pass

    def set_autosave(self, on):
        self._autosave = bool(on)

    def set_jflag_priority(self, priority_map):
        self._jflag_priority = dict(priority_map or {})
        self.set_sort_spec(self._sort_spec)

    def set_fulltext_root(self, path):
        self._fulltext_root = path or None

    def set_style_change_callback(self, cb):
        self._style_change_cb = cb

    def set_citation_style(self, style_id):
        self._current_style = style_id or APA_STYLE_ID
        self._suppress_style_change = True
        ids = self._style_ids()
        if self._current_style in ids:
            self.style_dropdown.set_selected(ids.index(self._current_style))
        else:
            self._current_style = APA_STYLE_ID
            if APA_STYLE_ID in ids:
                self.style_dropdown.set_selected(ids.index(APA_STYLE_ID))
        self._suppress_style_change = False
        if self._current_record:
            self._render_reference(self._current_record)

    def refresh_csl_styles(self):
        self._populate_style_combo()
        if self._current_record:
            self._render_reference(self._current_record)

    def refresh_starred_authors(self):
        self._rebuild_sidebar()

    def refresh_starred_outlets(self):
        self._rebuild_sidebar()
        self.set_sort_spec(self._sort_spec)

    def refresh_after_allocation(self):
        active = self._active_filter
        self._rebuild_sidebar()
        kind, key = active
        if kind and kind not in (NODE_TEMP,):
            self._apply_filter(kind, key)

    def current_work_key(self):
        kind, key = self._active_filter
        return key if kind == NODE_WORK else None

    def show_author_works(self, author_id):
        if not self.workspace:
            return
        author = self.workspace.authors.get(author_id)
        is_starred = bool(author and author.starred)
        if is_starred:
            self._rebuild_sidebar()
            if not self._select_sidebar_where(
                    lambda it: it.kind == NODE_AUTHOR and it.key == author_id):
                self._apply_filter(NODE_AUTHOR, author_id)
        else:
            self._rebuild_sidebar(temp_author_id=author_id)
            if not self._select_sidebar_where(
                    lambda it: it.kind == NODE_TEMP and it.key == author_id):
                self._apply_filter(NODE_TEMP, author_id)

    def show_outlet_works(self, outlet_id):
        if not self.workspace:
            return
        self._rebuild_sidebar()
        if not self._select_sidebar_where(
                lambda it: it.kind == NODE_OUTLET and it.key == outlet_id):
            self._apply_filter(NODE_OUTLET, outlet_id)

    def show_work(self, work_key):
        if not self.workspace:
            return
        self._rebuild_sidebar()
        if not self._select_sidebar_where(
                lambda it: it.kind == NODE_WORK and it.key == work_key):
            self._apply_filter(NODE_WORK, work_key)


def GLib_bytes(text):
    """Small helper: UTF-8 GLib.Bytes for the clipboard HTML payload."""
    from gi.repository import GLib
    return GLib.Bytes.new(text.encode("utf-8"))
