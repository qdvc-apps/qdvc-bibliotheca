"""Toolkit-independent helpers shared by both front-ends (pure, no GTK).

These read/normalise config values and format the validation report — logic
that is identical whether the view is GTK3 or GTK4, so it lives once here and
both windows call it. Keeping it out of the view modules also means it can be
unit-tested without a display.
"""

from .catalogue_sort import SORT_LABELS, APA_STYLE_ID  # noqa: F401


def jflag_presets(config):
    """Config J-Flag presets as a list of (flag, priority) ordered by priority
    then name. Stored as [{'flag': str, 'priority': number}, ...]."""
    raw = config.get("jflags", []) or []
    presets = []
    for item in raw:
        if isinstance(item, dict):
            flag = str(item.get("flag", "")).strip()
            prio = item.get("priority", 0)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            flag, prio = str(item[0]).strip(), item[1]
        else:
            continue
        if not flag:
            continue
        try:
            prio = float(prio)
        except (TypeError, ValueError):
            prio = 0.0
        presets.append((flag, prio))
    presets.sort(key=lambda t: (t[1], t[0].lower()))
    return presets


def jflag_priority_map(config):
    """{flag: priority} derived from the configured presets."""
    return {flag: prio for flag, prio in jflag_presets(config)}


def load_sort_spec(config):
    """Persisted sort spec as a list of (field_id, ascending_bool)."""
    raw = config.get("sort_spec", []) or []
    spec = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        spec.append((str(item[0]), bool(item[1])))
    return spec


def save_sort_spec(config, spec):
    config.set("sort_spec", [[fid, bool(asc)] for fid, asc in spec])
    config.save()


def describe_sort(spec):
    """One-line human summary of a sort spec (for the status line)."""
    if not spec:
        return "Sort cleared (default order)."
    labels = dict(SORT_LABELS)
    up, down = "\u2191", "\u2193"
    parts = [f"{labels.get(fid, fid)} {up if asc else down}"
             for fid, asc in spec]
    return "Sorted by " + ", ".join(parts)


def saved_citation_style(config, workspace):
    """Persisted citation style id for the workspace, or the APA sentinel."""
    if not workspace:
        return APA_STYLE_ID
    styles = config.get("csl_styles", {}) or {}
    return styles.get(str(workspace.root), APA_STYLE_ID)


def store_citation_style(config, workspace, style_id):
    """Persist the chosen citation style for the workspace (keyed by path)."""
    if not workspace:
        return
    styles = dict(config.get("csl_styles", {}) or {})
    styles[str(workspace.root)] = style_id
    config.set("csl_styles", styles)
    config.save()


def format_validation_report(report):
    """Render a validate() report dict as plain text. Shared verbatim between
    the GTK3 and GTK4 windows."""
    total_problems = sum(len(v) for v in report.values())
    if total_problems == 0:
        return "No problems found. The workspace looks healthy."

    lines = []

    def section(title, items, fmt):
        if not items:
            return
        lines.append(f"{title} ({len(items)}):")
        for it in items:
            lines.append("  \u2022 " + fmt(it))
        lines.append("")

    section("Orphan Markdown files (no matching .bib)",
            report["orphan_markdown"], lambda p: p)
    section("BibTeX key does not match Bibliotheca ID",
            report.get("key_mismatch", []),
            lambda t: f"{t[0]}  (key is '{t[1]}')")
    section("Missing full-text files",
            report["missing_fulltext"],
            lambda t: f"{t[0]} [{t[1]}] \u2192 {t[2]}")
    section("Citations to unknown records",
            report["dangling_citations"],
            lambda t: f"work '{t[0]}' cites missing '{t[1]}'")
    section("'published_as' pointing to unknown records",
            report["dangling_published_as"],
            lambda t: f"work '{t[0]}' \u2192 missing '{t[1]}'")
    section("Duplicate DOIs",
            report["duplicate_dois"],
            lambda t: f"{t[0]} \u2192 {', '.join(t[1])}")
    section("Outlet nickname set, but Bibliotheca ID has no suffix",
            report.get("nick_set_no_suffix", []),
            lambda t: f"{t[0]}  (outlet nickname is '{t[1]}')")
    section("Outlet nickname set, but Bibliotheca ID suffix differs",
            report.get("nick_set_suffix_diff", []),
            lambda t: f"{t[0]}  (suffix '{t[1]}' \u2260 nickname '{t[2]}')")
    section("Bibliotheca ID has a suffix, but no outlet nickname is set",
            report.get("suffix_no_nick", []),
            lambda t: f"{t[0]}  (suffix is '{t[1]}')")
    return "\n".join(lines).rstrip()


# Keyboard-shortcut rows, shared by both front-ends' shortcuts window.
SHORTCUTS = [
    ("Ctrl+O", "Open workspace"),
    ("Ctrl+I", "Import BibTeX"),
    ("Ctrl+Q", "Quit"),
    ("Ctrl+,", "Preferences"),
    ("Alt+1", "Catalogue"),
    ("Alt+2", "Authors"),
    ("Alt+3", "Outlets"),
    ("Alt+4", "DOI Lookup"),
    ("F5", "Refresh current view"),
    ("Ctrl+Shift+S", "Sort current list"),
    ("F2", "Rename Bibliotheca ID"),
]
