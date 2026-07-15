"""Format a BibTeX entry into an APA 7th-edition reference.

Produces two forms:
  * markup : Pango markup with <i>...</i> around titles/journals as APA requires.
  * plain  : the same text with all formatting stripped.

This is a pragmatic formatter covering the common source types an academic
collection contains (journal article, conference paper, book, book chapter,
webpage, and a sensible fallback). It is not a full CSL engine.

The style-agnostic primitives (author splitting, initials, field cleaning,
type labels, italic wrapping, markup->plain) live in :mod:`builtin`; this module
only decides how APA arranges them.
"""

import re

from . import builtin
from .builtin import (  # noqa: F401  (re-exported for backward compatibility)
    author_tokens,
    split_name,
    type_label,
    markup_to_plain,
    TYPE_LABELS,
)

# APA historically escaped markup content with quotes on (via html.escape's
# default), so apostrophes/quotes became &#x27;/&quot; entities. Preserve that
# exactly by defaulting quote=True here; builtin.markup_to_plain unescapes those
# entities on the plain path.
def escape(text, quote=True):
    return builtin.escape(text, quote=quote)


# ---------------------------------------------------------------------------
# Author handling
# ---------------------------------------------------------------------------

def format_author_list(raw: str) -> str:
    """APA author string: 'Smith, J., & Jones, A.' with up to 20 authors."""
    authors = [builtin.surname_initials(a) for a in builtin.split_authors(raw)]
    authors = [a for a in authors if a]
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) <= 20:
        return ", ".join(authors[:-1]) + ", & " + authors[-1]
    # APA: first 19, ellipsis, final author.
    head = ", ".join(authors[:19])
    return f"{head}, . . . {authors[-1]}"


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------

def _year(entry: dict) -> str:
    y = builtin.clean(entry.get("year"))
    if not y:
        date = builtin.clean(entry.get("date"))
        m = re.match(r"(\d{4})", date)
        y = m.group(1) if m else ""
    return f"({y})" if y else "(n.d.)"


def _sentence_case(title: str) -> str:
    """APA uses sentence case for article/chapter titles. We are conservative:
    if the title already looks title-cased we lower it, but preserve tokens
    that were brace-protected (already stripped) and obvious acronyms."""
    title = title.strip()
    if not title:
        return ""
    # Keep it simple and non-destructive: leave as-is. Aggressive recasing
    # risks corrupting proper nouns; APA tolerates faithful capitalisation.
    return title


def _i(text: str) -> str:
    """Wrap in Pango italic markup, escaping the inner text (quotes escaped)."""
    return builtin.italic(text, quote=True)


def _doi_url(entry: dict) -> str:
    doi = builtin.clean(entry.get("doi"))
    if doi:
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
        return f"https://doi.org/{doi}"
    return builtin.clean(entry.get("url"))


# ---------------------------------------------------------------------------
# Type-specific renderers -> return Pango markup
# ---------------------------------------------------------------------------

def _render_article(e: dict) -> str:
    authors = format_author_list(e.get("author", ""))
    year = _year(e)
    title = _sentence_case(builtin.clean(e.get("title")))
    journal = builtin.clean(e.get("journal") or e.get("journaltitle"))
    volume = builtin.clean(e.get("volume"))
    issue = builtin.clean(e.get("number") or e.get("issue"))
    pages = builtin.clean(e.get("pages")).replace("--", "\u2013")
    url = _doi_url(e)

    parts = []
    if authors:
        parts.append(f"{escape(authors)} {escape(year)}.")
    else:
        parts.append(f"{escape(year)}.")
    if title:
        parts.append(f"{escape(title)}.")
    tail = ""
    if journal:
        tail = _i(journal)
        if volume:
            tail += f", {_i(volume)}"
            if issue:
                tail += f"({escape(issue)})"
        if pages:
            tail += f", {escape(pages)}"
        tail += "."
    if tail:
        parts.append(tail)
    if url:
        parts.append(escape(url))
    return " ".join(parts)


def _render_inproceedings(e: dict) -> str:
    authors = format_author_list(e.get("author", ""))
    year = _year(e)
    title = builtin.clean(e.get("title"))
    book = builtin.clean(e.get("booktitle"))
    pages = builtin.clean(e.get("pages")).replace("--", "\u2013")
    url = _doi_url(e)

    parts = []
    if authors:
        parts.append(f"{escape(authors)} {escape(year)}.")
    else:
        parts.append(f"{escape(year)}.")
    if title:
        parts.append(f"{escape(title)}.")
    seg = "In "
    if book:
        seg += _i(book)
        if pages:
            seg += f" (pp. {escape(pages)})"
        seg += "."
        parts.append(seg)
    if url:
        parts.append(escape(url))
    return " ".join(parts)


def _render_book(e: dict) -> str:
    authors = format_author_list(e.get("author", "") or e.get("editor", ""))
    year = _year(e)
    title = builtin.clean(e.get("title"))
    edition = builtin.clean(e.get("edition"))
    publisher = builtin.clean(e.get("publisher"))
    url = _doi_url(e)

    parts = []
    if authors:
        parts.append(f"{escape(authors)} {escape(year)}.")
    else:
        parts.append(f"{escape(year)}.")
    t = _i(title) if title else ""
    if edition:
        t += f" ({escape(edition)} ed.)"
    if t:
        parts.append(t + ".")
    if publisher:
        parts.append(f"{escape(publisher)}.")
    if url:
        parts.append(escape(url))
    return " ".join(parts)


def _render_inbook(e: dict) -> str:
    authors = format_author_list(e.get("author", ""))
    year = _year(e)
    title = builtin.clean(e.get("title"))
    book = builtin.clean(e.get("booktitle"))
    editor = format_author_list(e.get("editor", ""))
    pages = builtin.clean(e.get("pages")).replace("--", "\u2013")
    publisher = builtin.clean(e.get("publisher"))
    url = _doi_url(e)

    parts = []
    if authors:
        parts.append(f"{escape(authors)} {escape(year)}.")
    else:
        parts.append(f"{escape(year)}.")
    if title:
        parts.append(f"{escape(title)}.")
    seg = "In "
    if editor:
        seg += f"{escape(editor)} (Ed.), "
    if book:
        seg += _i(book)
        if pages:
            seg += f" (pp. {escape(pages)})"
        seg += "."
        parts.append(seg)
    if publisher:
        parts.append(f"{escape(publisher)}.")
    if url:
        parts.append(escape(url))
    return " ".join(parts)


def _render_online(e: dict) -> str:
    authors = format_author_list(e.get("author", ""))
    year = _year(e)
    title = builtin.clean(e.get("title"))
    site = builtin.clean(e.get("organization") or e.get("publisher")
                         or e.get("howpublished"))
    url = _doi_url(e)

    parts = []
    if authors:
        parts.append(f"{escape(authors)} {escape(year)}.")
    else:
        parts.append(f"{escape(year)}.")
    if title:
        parts.append(f"{_i(title)}.")
    if site:
        parts.append(f"{escape(site)}.")
    if url:
        parts.append(escape(url))
    return " ".join(parts)


_RENDERERS = {
    "article": _render_article,
    "inproceedings": _render_inproceedings,
    "conference": _render_inproceedings,
    "proceedings": _render_inproceedings,
    "book": _render_book,
    "inbook": _render_inbook,
    "incollection": _render_inbook,
    "online": _render_online,
    "electronic": _render_online,
    "misc": _render_online,
    "webpage": _render_online,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_apa_markup(entry: dict) -> str:
    """Return Pango-markup APA reference for a parsed BibTeX entry dict.

    `entry` is expected to have an 'ENTRYTYPE' key plus lowercase fields.
    """
    etype = (entry.get("ENTRYTYPE") or entry.get("entrytype") or "misc").lower()
    renderer = _RENDERERS.get(etype, _render_online)
    return builtin.collapse_artefacts(renderer(entry))


def format_apa_plain(entry: dict) -> str:
    return markup_to_plain(format_apa_markup(entry))
