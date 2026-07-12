"""Shared GTK4 view types and constants.

GTK4's list widgets (`Gtk.ColumnView`, `Gtk.ListView`, `Gtk.TreeListModel`)
bind **GObjects**, not integer-indexed store columns, so the row data is wrapped
in small `GObject.Object` subclasses here. The sidebar node-kind constants and
the APA sentinel are the same logical values the GTK3 view uses; they are
defined once here so the GTK4 modules can never disagree about what a nav row
means.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject  # noqa: E402

from ..catalogue_sort import APA_STYLE_ID  # noqa: F401  (re-exported)


# --- sidebar node kinds (mirror the GTK3 view's semantics) -----------------
NODE_ALL = "all"
NODE_TYPE = "type"
NODE_WORK = "work"
NODE_WORKS_ROOT = "works_root"
NODE_AUTHOR = "author"
NODE_OUTLET = "outlet"
NODE_FULLTEXT = "fulltext"   # key in {"pdf","epub","none"}
NODE_DOI = "doi"             # key in {"set","unset"}
NODE_TEMP = "temp"           # transient "query results" node


class RecordItem(GObject.Object):
    """A row in the Catalogue's ColumnView, wrapping a model ``Record``.

    The columns read plain attributes off this object (that is how GTK4 binds
    list rows), so the derived display cells — the J-Flags string and the
    nickname-prefaced Outlet markup — are computed once by the tab and stored
    here alongside the raw record.
    """

    __gtype_name__ = "QdvcRecordItem"

    def __init__(self, record, jflags="", outlet_markup="", has_pdf=False):
        super().__init__()
        self.record = record
        self.bibliotheca_id = record.bibliotheca_id
        self.author = record.author or ""
        self.year = record.year or ""
        self.title = record.title or ""
        self.type_label = record.type_label or ""
        self.jflags = jflags
        self.outlet_markup = outlet_markup
        self.has_pdf = has_pdf


class NavItem(GObject.Object):
    """A node in the sidebar navigation tree.

    ``kind``/``key`` carry the same meaning as the GTK3 tree's hidden columns
    (see the NODE_* constants). ``children`` is a Python list of NavItems used
    to build a ``Gtk.TreeListModel``; leaf rows have an empty list. ``count`` is
    the article count shown right-aligned (0 ⇒ blank).
    """

    __gtype_name__ = "QdvcNavItem"

    def __init__(self, label, kind="", key="", icon="", count=0,
                 children=None, is_header=False):
        super().__init__()
        self.label = label
        self.kind = kind
        self.key = key
        self.icon = icon
        self.count = count
        self.children = children if children is not None else []
        self.is_header = is_header


class TextItem(GObject.Object):
    """A trivial string wrapper for simple GTK4 list/dropdown models (e.g. the
    citation-style dropdown, allocate-to-works list)."""

    __gtype_name__ = "QdvcTextItem"

    def __init__(self, text, key=None):
        super().__init__()
        self.text = text
        self.key = key if key is not None else text
