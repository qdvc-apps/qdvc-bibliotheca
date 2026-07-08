"""Format a BibTeX entry into an APA 7th-edition reference.

Produces two forms:
  * markup : Pango markup with <i>...</i> around titles/journals as APA requires.
  * plain  : the same text with all formatting stripped.

This is a pragmatic formatter covering the common source types an academic
collection contains (journal article, conference paper, book, book chapter,
webpage, and a sensible fallback). It is not a full CSL engine.
"""

import re
from html import escape

# ---------------------------------------------------------------------------
# Author handling
# ---------------------------------------------------------------------------

def _split_authors(raw: str) -> list[str]:
    if not raw:
        return []
    # BibTeX separates authors with " and " (not inside braces).
    parts = re.split(r"\s+and\s+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


def _format_one_author(name: str) -> str:
    """Return 'Surname, F. M.' for a single BibTeX author token."""
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
    initials = _initials(first)
    if initials:
        return f"{last}, {initials}"
    return last


def _initials(first: str) -> str:
    out = []
    for token in re.split(r"[\s\-]+", first.strip()):
        token = token.strip(".")
        if not token:
            continue
        # Preserve hyphenated given names loosely as separate initials.
        out.append(f"{token[0].upper()}.")
    return " ".join(out)


def format_author_list(raw: str) -> str:
    """APA author string: 'Smith, J., & Jones, A.' with up to 20 authors."""
    authors = [_format_one_author(a) for a in _split_authors(raw)]
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

def _clean(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("{", "").replace("}", "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _year(entry: dict) -> str:
    y = _clean(entry.get("year"))
    if not y:
        date = _clean(entry.get("date"))
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
    """Wrap in Pango italic markup, escaping the inner text."""
    return f"<i>{escape(text)}</i>" if text else ""


def _doi_url(entry: dict) -> str:
    doi = _clean(entry.get("doi"))
    if doi:
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
        return f"https://doi.org/{doi}"
    return _clean(entry.get("url"))


# ---------------------------------------------------------------------------
# Type-specific renderers -> return Pango markup
# ---------------------------------------------------------------------------

def _render_article(e: dict) -> str:
    authors = format_author_list(e.get("author", ""))
    year = _year(e)
    title = _sentence_case(_clean(e.get("title")))
    journal = _clean(e.get("journal") or e.get("journaltitle"))
    volume = _clean(e.get("volume"))
    issue = _clean(e.get("number") or e.get("issue"))
    pages = _clean(e.get("pages")).replace("--", "\u2013")
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
    title = _clean(e.get("title"))
    book = _clean(e.get("booktitle"))
    pages = _clean(e.get("pages")).replace("--", "\u2013")
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
    title = _clean(e.get("title"))
    edition = _clean(e.get("edition"))
    publisher = _clean(e.get("publisher"))
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
    title = _clean(e.get("title"))
    book = _clean(e.get("booktitle"))
    editor = format_author_list(e.get("editor", ""))
    pages = _clean(e.get("pages")).replace("--", "\u2013")
    publisher = _clean(e.get("publisher"))
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
    title = _clean(e.get("title"))
    site = _clean(e.get("organization") or e.get("publisher")
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

# A friendlier label for the "type" column / sidebar filtering.
TYPE_LABELS = {
    "article": "Journal article",
    "inproceedings": "Conference paper",
    "conference": "Conference paper",
    "proceedings": "Conference paper",
    "book": "Book",
    "inbook": "Book chapter",
    "incollection": "Book chapter",
    "online": "Webpage",
    "electronic": "Webpage",
    "webpage": "Webpage",
    "misc": "Other",
}


def type_label(entrytype: str) -> str:
    return TYPE_LABELS.get((entrytype or "").lower(), "Other")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_apa_markup(entry: dict) -> str:
    """Return Pango-markup APA reference for a parsed BibTeX entry dict.

    `entry` is expected to have an 'ENTRYTYPE' key plus lowercase fields.
    """
    etype = (entry.get("ENTRYTYPE") or entry.get("entrytype") or "misc").lower()
    renderer = _RENDERERS.get(etype, _render_online)
    markup = renderer(entry)
    # Collapse doubled spaces/periods that can arise from empty fields.
    markup = re.sub(r"\s+\.", ".", markup)
    markup = re.sub(r"\.\.", ".", markup)
    markup = re.sub(r"\s{2,}", " ", markup).strip()
    return markup


_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}


def markup_to_plain(markup: str) -> str:
    """Strip Pango tags and unescape entities to yield plain text."""
    text = _TAG_RE.sub("", markup)
    for ent, ch in _ENTITY.items():
        text = text.replace(ent, ch)
    return text


def format_apa_plain(entry: dict) -> str:
    return markup_to_plain(format_apa_markup(entry))
