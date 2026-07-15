"""Shared building blocks for the built-in reference formatters (pure, no GTK).

Both built-in styles — APA 7 (:mod:`builtin_apa7`) and ACIS
(:mod:`builtin_acis`) — need the same primitives: split a BibTeX author string
into tokens, turn given names into initials, clean brace/whitespace noise out of
field values, map an entry type to a human label, wrap text as Pango italic, and
strip finished markup back to plain text. Those live here so the two style
modules stay focused on *how each style arranges* those pieces rather than
re-implementing the pieces themselves.

Nothing in here is style-specific: the differences between APA and ACIS (author
joining, year placement, quotation, in-text citations, disambiguation) belong in
the style modules.
"""

import re
from html import escape as _html_escape

# ---------------------------------------------------------------------------
# Author handling
# ---------------------------------------------------------------------------

def split_authors(raw: str) -> list[str]:
    """Split a BibTeX author/editor string into individual author tokens."""
    if not raw:
        return []
    # BibTeX separates authors with " and " (not inside braces).
    parts = re.split(r"\s+and\s+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


def split_name(name: str) -> tuple[str, str]:
    """Split a single BibTeX author token into (surname, given_names).

    Handles both "Surname, Given Names" and "Given Names Surname" forms.
    Returns given_names as a space-joined string (may be empty).
    """
    name = name.replace("{", "").replace("}", "").strip()
    if not name:
        return "", ""
    if "," in name:
        last, _, first = name.partition(",")
        return last.strip(), first.strip()
    bits = name.split()
    if len(bits) == 1:
        return bits[0], ""
    return bits[-1], " ".join(bits[:-1])


def author_tokens(raw: str) -> list[tuple[str, str]]:
    """Return a list of (surname, given_names) for every author in `raw`."""
    out = []
    for tok in split_authors(raw):
        surname, given = split_name(tok)
        if surname:
            out.append((surname, given))
    return out


def initials(first: str) -> str:
    """Turn a run of given names into spaced initials, e.g. 'B. C.'."""
    out = []
    for token in re.split(r"[\s\-]+", first.strip()):
        token = token.strip(".")
        if not token:
            continue
        # Preserve hyphenated given names loosely as separate initials.
        out.append(f"{token[0].upper()}.")
    return " ".join(out)


def surname_initials(name: str) -> str:
    """Return 'Surname, F. M.' for a single BibTeX author token.

    This surname-first, initialised form is the shape APA uses for every
    author and ACIS uses for every author, so it lives here.
    """
    name = name.replace("{", "").replace("}", "").strip()
    if not name:
        return ""
    if "," in name:
        last, _, first = name.partition(",")
        last, first = last.strip(), first.strip()
    else:
        bits = name.split()
        last = bits[-1]
        first = " ".join(bits[:-1])
    inits = initials(first)
    if inits:
        return f"{last}, {inits}"
    return last


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------

def clean(value: str | None) -> str:
    """Strip braces and collapse whitespace in a raw BibTeX field value."""
    if not value:
        return ""
    value = value.replace("{", "").replace("}", "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def escape(text, quote=False):
    """HTML-escape for Pango markup *content*.

    Pango only requires ``&``, ``<`` and ``>`` to be escaped inside markup
    text. ``quote`` is exposed so a caller can also escape ``'`` and ``"`` when
    it wants to (APA's historical behaviour); the default leaves them literal so
    that plain-text round-tripping via :func:`markup_to_plain` is exact.
    """
    return _html_escape(text or "", quote=quote)


def italic(text, quote=False):
    """Wrap ``text`` in Pango italic markup, escaping the inner text."""
    return f"<i>{escape(text, quote=quote)}</i>" if text else ""


# ---------------------------------------------------------------------------
# Entry-type labels (load-bearing UI strings — change in one place only)
# ---------------------------------------------------------------------------

# A friendlier label for the "type" column / sidebar filtering.
TYPE_LABELS = {
    "article": "Journal article",
    "inproceedings": "Proceedings",
    "conference": "Proceedings",
    "proceedings": "Proceedings",
    "book": "Book",
    "inbook": "Book chapter",
    "incollection": "Book chapter",
    "online": "Webpage",
    "electronic": "Webpage",
    "webpage": "Webpage",
    "misc": "Other",
}


def type_label(entrytype: str, booktitle: str | None = None) -> str:
    """Map a BibTeX entry type to a human label.

    An ``incollection`` whose ``booktitle`` begins with "Proceedings of" is
    treated as "Proceedings" rather than "Book chapter", so conference material
    filed as a collection chapter is grouped with the other proceedings.
    """
    et = (entrytype or "").lower()
    if et == "incollection" and booktitle:
        if clean(booktitle).lower().startswith("proceedings of"):
            return "Proceedings"
    return TYPE_LABELS.get(et, "Other")


# ---------------------------------------------------------------------------
# Markup -> plain text
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
           "&#39;": "'", "&#x27;": "'"}


def markup_to_plain(markup: str) -> str:
    """Strip Pango tags and unescape entities to yield plain text."""
    text = _TAG_RE.sub("", markup)
    for ent, ch in _ENTITY.items():
        text = text.replace(ent, ch)
    return text


def collapse_artefacts(markup: str) -> str:
    """Tidy the artefacts empty fields leave behind (doubled spaces/periods)."""
    markup = re.sub(r"\s+\.", ".", markup)
    markup = re.sub(r"\.\.", ".", markup)
    markup = re.sub(r"\s{2,}", " ", markup).strip()
    return markup
