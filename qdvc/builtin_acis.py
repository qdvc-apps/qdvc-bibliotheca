"""Format a BibTeX entry into an ACIS-style reference and in-text citation.

ACIS (the reference style used by the *Australasian Conference on Information
Systems* and kindred IS outlets) differs from APA in several visible ways:

  * The year follows the authors with no parentheses and a trailing period,
    and carries a lower-case disambiguation letter when an author/year pair is
    reused (``2025a``, ``2025b``).
  * Article/chapter titles are wrapped in curly quotation marks, with the
    following comma placed *inside* the closing quote.
  * The author list joins the final author with ", and" and keeps every author
    in "Surname, Initials" order (it is never inverted back to initials-first).
  * Journal articles show volume and issue as ``(vol:iss)`` and, where present,
    a DOI as ``(doi:…)`` in place of a page range.

Like :mod:`builtin_apa7`, this is a pragmatic formatter (not a full CSL engine)
that produces two forms:

  * markup : Pango markup with ``<i>…</i>`` around titles/journals.
  * plain  : the same text with formatting stripped.

It also exposes an in-text citation renderer (``in_text_markup`` /
``in_text_plain``) for the parenthetical and narrative forms:

    (Thompson et al. 2026)          parenthetical, 3+ authors
    (Smith and Jones 2026)          parenthetical, 2 authors
    Smith and Jones (2025a)         narrative (year only in parentheses)

The disambiguation letter is supplied by the caller (the workspace knows which
records share an author/year), so this module stays pure and stateless. The
style-agnostic primitives live in :mod:`builtin`.
"""

import re

from . import builtin

# ACIS escapes markup content with quotes off, so apostrophes/straight quotes
# stay literal (matters for names like "O'Brien" and for a clean plain-text
# round-trip via builtin.markup_to_plain).
escape = builtin.escape

# ---------------------------------------------------------------------------
# Author handling
# ---------------------------------------------------------------------------

def format_author_list(raw: str) -> str:
    """ACIS author string: 'Smith, A., Jones, B. C., and Carter, D.'.

    Every author is surname-first; the final author is joined with ', and'.
    """
    authors = [builtin.surname_initials(a)
               for a in builtin.split_authors(raw)]
    authors = [a for a in authors if a]
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    return ", ".join(authors[:-1]) + ", and " + authors[-1]


def _surnames(raw: str) -> list[str]:
    """Surnames only, in order, for in-text citations."""
    return [surname for surname, _ in builtin.author_tokens(raw or "")]


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def _year_bare(entry: dict) -> str:
    """The four-digit year with no parentheses (empty string if unknown)."""
    y = builtin.clean(entry.get("year"))
    if not y:
        date = builtin.clean(entry.get("date"))
        m = re.match(r"(\d{4})", date)
        y = m.group(1) if m else ""
    return y


def _accessed_date(entry: dict) -> str:
    """Format an ISO ``urldate``/``accessed`` value as '10 July 2026'.

    Falls back to the raw value when it is not an ISO ``YYYY-MM-DD`` date.
    """
    raw = builtin.clean(entry.get("urldate") or entry.get("accessed"))
    if not raw:
        return ""
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if not m:
        return raw
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1 <= month <= 12:
        return f"{day} {_MONTHS[month - 1]} {year}"
    return raw


def _i(text: str) -> str:
    """Wrap in Pango italic markup, escaping the inner text."""
    return builtin.italic(text, quote=False)


def _doi(entry: dict) -> str:
    doi = builtin.clean(entry.get("doi"))
    if doi:
        return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi,
                      flags=re.IGNORECASE)
    return ""


def _quoted_title(title: str, closing: str = ",") -> str:
    """Curly-quote a title with the trailing punctuation inside the closing
    quote (ACIS convention). ``closing`` is ',' before a journal/container and
    '.' when the title is the last element."""
    if not title:
        return ""
    return f"\u201c{escape(title, quote=False)}{closing}\u201d"


# ---------------------------------------------------------------------------
# Type-specific renderers -> return Pango markup
# ---------------------------------------------------------------------------

def _lead(e: dict, disambiguator: str) -> str:
    """The '{authors} {year}{disambig}.' opening shared by every type."""
    authors = format_author_list(e.get("author", "") or e.get("editor", ""))
    year = _year_bare(e)
    stamp = f"{year}{disambiguator}" if year else "n.d."
    if authors:
        return f"{escape(authors)} {escape(stamp)}."
    return f"{escape(stamp)}."


def _render_article(e: dict, disambiguator: str) -> str:
    title = builtin.clean(e.get("title"))
    journal = builtin.clean(e.get("journal") or e.get("journaltitle"))
    volume = builtin.clean(e.get("volume"))
    issue = builtin.clean(e.get("number") or e.get("issue"))
    pages = builtin.clean(e.get("pages")).replace("--", "-")
    doi = _doi(e)

    parts = [_lead(e, disambiguator)]
    if title:
        parts.append(_quoted_title(title, ","))
    tail = ""
    if journal:
        tail = _i(journal)
        if volume:
            vi = escape(volume)
            if issue:
                vi += f":{escape(issue)}"
            tail += f" ({vi})"
        if doi:
            tail += f" (doi:{escape(doi)})"
        elif pages:
            tail += f", pp. {escape(pages)}."
        else:
            tail += "."
    if tail:
        parts.append(tail)
    return " ".join(parts)


def _render_inproceedings(e: dict, disambiguator: str) -> str:
    title = builtin.clean(e.get("title"))
    book = builtin.clean(e.get("booktitle"))
    address = builtin.clean(e.get("address") or e.get("location"))

    parts = [_lead(e, disambiguator)]
    if title:
        parts.append(_quoted_title(title, ","))
    if book:
        parts.append(f"{_i(book)}.")
    if address:
        parts.append(f"{escape(address)}.")
    return " ".join(parts)


def _render_book(e: dict, disambiguator: str) -> str:
    title = builtin.clean(e.get("title"))
    edition = builtin.clean(e.get("edition"))
    publisher = builtin.clean(e.get("publisher"))
    address = builtin.clean(e.get("address") or e.get("location"))

    parts = [_lead(e, disambiguator)]
    t = _i(title) if title else ""
    if edition:
        t += f" ({escape(edition)} ed.)"
    if t:
        parts.append(t + ".")
    if address and publisher:
        parts.append(f"{escape(address)}: {escape(publisher)}.")
    elif publisher:
        parts.append(f"{escape(publisher)}.")
    elif address:
        parts.append(f"{escape(address)}.")
    return " ".join(parts)


def _render_inbook(e: dict, disambiguator: str) -> str:
    title = builtin.clean(e.get("title"))
    book = builtin.clean(e.get("booktitle"))
    editor = format_author_list(e.get("editor", ""))
    pages = builtin.clean(e.get("pages")).replace("--", "-")
    publisher = builtin.clean(e.get("publisher"))
    address = builtin.clean(e.get("address") or e.get("location"))

    parts = [_lead(e, disambiguator)]
    if title:
        parts.append(_quoted_title(title, ","))
    seg = "in "
    if editor:
        seg += f"{escape(editor)} (ed.), "
    if book:
        seg += _i(book)
        if pages:
            seg += f", pp. {escape(pages)}"
        seg += "."
        parts.append(seg)
    if address and publisher:
        parts.append(f"{escape(address)}: {escape(publisher)}.")
    elif publisher:
        parts.append(f"{escape(publisher)}.")
    return " ".join(parts)


def _render_online(e: dict, disambiguator: str) -> str:
    title = builtin.clean(e.get("title"))
    url = builtin.clean(e.get("url")) or builtin.clean(e.get("howpublished"))
    accessed = _accessed_date(e)

    parts = [_lead(e, disambiguator)]
    if title:
        # No container follows, so the closing punctuation is a period.
        parts.append(_quoted_title(title, "."))
    if url:
        inner = escape(url)
        if accessed:
            inner += f", accessed {escape(accessed)}"
        parts.append(f"({inner}).")
    elif accessed:
        parts.append(f"(accessed {escape(accessed)}).")
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


def _pick_renderer(entry: dict):
    """Choose a renderer, treating an ``incollection`` whose ``booktitle``
    begins with 'Proceedings of' as a conference paper (mirroring
    ``builtin.type_label``)."""
    etype = (entry.get("ENTRYTYPE") or entry.get("entrytype") or "misc").lower()
    if etype == "incollection":
        booktitle = builtin.clean(entry.get("booktitle"))
        if booktitle.lower().startswith("proceedings of"):
            return _render_inproceedings
    return _RENDERERS.get(etype, _render_online)


# ---------------------------------------------------------------------------
# Public API — reference list
# ---------------------------------------------------------------------------

def format_acis_markup(entry: dict, disambiguator: str = "") -> str:
    """Return Pango-markup ACIS reference for a parsed BibTeX entry dict.

    ``disambiguator`` is the lower-case letter appended to the year when an
    author/year pair is shared by several records (``"a"``, ``"b"``, …); pass
    an empty string when the reference is unambiguous.
    """
    renderer = _pick_renderer(entry)
    return builtin.collapse_artefacts(renderer(entry, disambiguator or ""))


def format_acis_plain(entry: dict, disambiguator: str = "") -> str:
    return builtin.markup_to_plain(format_acis_markup(entry, disambiguator))


# ---------------------------------------------------------------------------
# Public API — in-text citation
# ---------------------------------------------------------------------------

def _disambig_key(author: str, year: str) -> tuple:
    """Grouping key for disambiguation: the ordered surnames plus the year.

    Two records with the same authors (in the same order) and the same year
    collide and must be told apart with a trailing letter."""
    surnames = tuple(s.lower() for s in _surnames(author))
    return (surnames, (year or "").strip())


def disambiguator_map(records) -> dict:
    """Map ``bibliotheca_id`` -> disambiguation letter for a set of records.

    ``records`` is any iterable of objects exposing ``bibliotheca_id``,
    ``author``, ``year`` and ``title`` (the cached :class:`Record` fields are
    enough — no BibTeX parsing needed). Records that share an author/year pair
    get sequential lower-case letters ('a', 'b', …) assigned in title order;
    records with a unique author/year get an empty string.
    """
    groups: dict[tuple, list] = {}
    for rec in records:
        author = getattr(rec, "author", "") or ""
        year = getattr(rec, "year", "") or ""
        if not year.strip():
            continue
        groups.setdefault(_disambig_key(author, year), []).append(rec)

    out: dict = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        # Deterministic, human-sensible order: by title, then id as tie-break.
        members.sort(key=lambda r: ((getattr(r, "title", "") or "").lower(),
                                    getattr(r, "bibliotheca_id", "")))
        for offset, rec in enumerate(members):
            out[getattr(rec, "bibliotheca_id", "")] = _letter(offset)
    return out


def _letter(n: int) -> str:
    """0 -> 'a', 1 -> 'b', … 25 -> 'z', 26 -> 'aa', …"""
    letters = ""
    n += 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("a") + rem) + letters
    return letters


def _author_label(entry: dict) -> str:
    """The author portion of an in-text citation.

    One author → 'Smith'; two → 'Smith and Jones'; three or more →
    'Thompson et al.'. Falls back to a short title when there is no author.
    """
    surnames = _surnames(entry.get("author", "") or entry.get("editor", ""))
    if not surnames:
        title = builtin.clean(entry.get("title"))
        return title.split()[0] if title else ""
    if len(surnames) == 1:
        return surnames[0]
    if len(surnames) == 2:
        return f"{surnames[0]} and {surnames[1]}"
    return f"{surnames[0]} et al."


def in_text_plain(entry: dict, disambiguator: str = "",
                  narrative: bool = False) -> str:
    """Plain-text ACIS in-text citation.

    ``narrative=False`` → '(Smith and Jones 2026)'.
    ``narrative=True``  → 'Smith and Jones (2025a)' (year parenthesised).
    """
    label = _author_label(entry)
    year = _year_bare(entry)
    stamp = f"{year}{disambiguator}" if year else "n.d."
    if not label:
        return f"({stamp})"
    if narrative:
        return f"{label} ({stamp})"
    return f"({label} {stamp})"


def in_text_markup(entry: dict, disambiguator: str = "",
                   narrative: bool = False) -> str:
    """Pango-markup form of the in-text citation (escaped; no italics)."""
    return escape(in_text_plain(entry, disambiguator, narrative))
