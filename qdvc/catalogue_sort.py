"""Pure helpers for the Catalogue's master list (no GTK).

The sort-key definitions, the sidebar count formatter, the J-Flag display
ordering, and the reference-markup-to-HTML wrapper are all plain data
transformations with no GTK dependency, so they live here where both the GTK3
front-end and any future front-end (or tests) can use them.
"""


def year_key(r):
    """Numeric year when possible (so 2009 < 2025), else 0, then raw string."""
    y = (r.year or "").strip()
    digits = "".join(ch for ch in y if ch.isdigit())
    return (int(digits) if digits else 0, y.lower())


# Sentinel id for the built-in APA renderer in the citation-style dropdown.
# Lives here (pure) so both front-ends and ui_prefs share one definition.
APA_STYLE_ID = "__apa__"


# Multi-key sort: maps a stable sort-key id to a callable producing a
# comparison key from a Record. Order of this dict is the order shown to the
# user in the sort dialog.
SORT_KEYS = {
    "bibliotheca_id": lambda r: r.bibliotheca_id.lower(),
    "author": lambda r: (r.author or "").lower(),
    "year": year_key,
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


def count_label(n) -> str:
    """Format a sidebar row count: '(N)' when positive, '' when zero, so rows
    that would surface no articles show a blank count column."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    return f"({n})" if n > 0 else ""


def order_jflags(jflags, priority_map):
    """Order J-Flags for display by their configured priority number (lower
    first). Flags without a configured priority sort after those with one,
    then alphabetically as a tie-breaker."""
    priority_map = priority_map or {}

    def sort_key(flag):
        if flag in priority_map:
            try:
                return (0, float(priority_map[flag]), flag.lower())
            except (TypeError, ValueError):
                return (0, 0.0, flag.lower())
        return (1, 0.0, flag.lower())

    return sorted(jflags, key=sort_key)


def markup_to_html(markup: str) -> str:
    """Wrap Pango reference markup as a minimal HTML document for the rich
    clipboard. Pango's ``<i>``/``<b>`` are already valid HTML."""
    return f"<html><body>{markup}</body></html>"
