"""Render a BibTeX entry through a CSL (Citation Style Language) file.

This is an optional feature. Real CSL processing is delegated to
``citeproc-py`` when it is importable; when it is not, ``csl_available()``
returns ``False`` and the Catalogue simply keeps the built-in APA renderer as
the only choice (the CSL dropdown still lists files but selecting one shows a
short "install citeproc-py" note rather than crashing).

The public surface mirrors the built-in formatters:

    render_markup(entry, csl_path) -> Pango markup string
    render_plain(entry, csl_path)  -> plain-text string

``entry`` is the normalised BibTeX dict used elsewhere (lowercase field names,
``ENTRYTYPE``/``ID`` keys). We convert it to a minimal CSL-JSON item before
handing it to citeproc.
"""

import re
from html import escape, unescape

from . import builtin
from . import builtin_apa7 as apa


def csl_available() -> bool:
    """True when the citeproc-py backend can be imported."""
    try:
        import citeproc  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# BibTeX entry -> CSL-JSON
# ---------------------------------------------------------------------------

# BibTeX entry type -> CSL item type (the common cases the collection holds).
_CSL_TYPE = {
    "article": "article-journal",
    "inproceedings": "paper-conference",
    "conference": "paper-conference",
    "proceedings": "paper-conference",
    "incollection": "chapter",
    "inbook": "chapter",
    "book": "book",
    "online": "webpage",
    "electronic": "webpage",
    "webpage": "webpage",
    "misc": "document",
}


def _markup_safe(value: str) -> str:
    """Escape the characters that break the downstream Pango markup label.

    citeproc-py's HTML formatter copies text-field values through verbatim
    without escaping, so a raw ``&``, ``<`` or ``>`` in (say) a journal name
    reaches ``Gtk.Label.set_markup`` unescaped and makes Pango reject the whole
    reference. We therefore escape these characters here, *before* the value is
    handed to citeproc: citeproc then emits well-formed ``&amp;``/``&lt;`` in
    its "HTML" output, which is valid Pango markup, and the plain-text path
    (``_html_to_plain``) unescapes the entities back to the original symbols.
    """
    return escape(value or "", quote=False)


def _names(raw: str) -> list[dict]:
    """Convert a BibTeX author/editor string to CSL name objects."""
    out = []
    for surname, given in builtin.author_tokens(raw or ""):
        name = {"family": _markup_safe(surname)}
        if given:
            name["given"] = _markup_safe(given)
        out.append(name)
    return out


def _year_parts(entry: dict) -> dict | None:
    y = builtin.clean(entry.get("year"))
    if not y:
        date = builtin.clean(entry.get("date"))
        m = re.match(r"(\d{4})", date)
        y = m.group(1) if m else ""
    if not y:
        return None
    digits = "".join(ch for ch in y if ch.isdigit())
    if not digits:
        return None
    return {"date-parts": [[int(digits)]]}


def entry_to_csl_json(entry: dict) -> dict:
    """Build a minimal CSL-JSON item dict from a normalised BibTeX entry."""
    et = (entry.get("ENTRYTYPE") or entry.get("entrytype") or "misc").lower()
    booktitle = builtin.clean(entry.get("booktitle"))
    csl_type = _CSL_TYPE.get(et, "document")
    if et == "incollection" and booktitle.lower().startswith("proceedings of"):
        csl_type = "paper-conference"

    item: dict = {"id": entry.get("ID") or entry.get("id") or "ITEM-1",
                  "type": csl_type}
    title = _markup_safe(builtin.clean(entry.get("title")))
    if title:
        item["title"] = title
    authors = _names(entry.get("author"))
    if authors:
        item["author"] = authors
    editors = _names(entry.get("editor"))
    if editors:
        item["editor"] = editors
    container = _markup_safe(builtin.clean(entry.get("journal")
                                        or entry.get("journaltitle")
                                        or booktitle))
    if container:
        item["container-title"] = container
    publisher = _markup_safe(builtin.clean(entry.get("publisher")))
    if publisher:
        item["publisher"] = publisher
    vol = builtin.clean(entry.get("volume"))
    if vol:
        item["volume"] = vol
    issue = builtin.clean(entry.get("number") or entry.get("issue"))
    if issue:
        item["issue"] = issue
    pages = builtin.clean(entry.get("pages"))
    if pages:
        item["page"] = pages.replace("--", "-")
    doi = builtin.clean(entry.get("doi"))
    if doi:
        item["DOI"] = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi,
                             flags=re.IGNORECASE)
    url = builtin.clean(entry.get("url"))
    if url:
        item["URL"] = url
    issued = _year_parts(entry)
    if issued:
        item["issued"] = issued
    return item


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render(entry: dict, csl_path: str) -> str:
    """Return citeproc HTML output for one entry, or raise on failure."""
    from citeproc import CitationStylesStyle, CitationStylesBibliography
    from citeproc import Citation, CitationItem, formatter
    from citeproc.source.json import CiteProcJSON

    item = entry_to_csl_json(entry)
    item_id = str(item["id"])
    source = CiteProcJSON([item])
    style = CitationStylesStyle(str(csl_path), validate=False)
    bib = CitationStylesBibliography(style, source, formatter.html)
    bib.register(Citation([CitationItem(item_id)]))
    rendered = bib.bibliography()
    if not rendered:
        return ""
    return str(rendered[0])


# Pango understands a small subset of HTML-like tags. Map the inline styling
# citeproc emits (<i>, <b>, <span style="font-style:italic">) onto that subset,
# and drop anything else.
_ITALIC_SPAN_RE = re.compile(
    r'<span[^>]*font-style:\s*italic[^>]*>(.*?)</span>', re.IGNORECASE | re.S)
_BOLD_SPAN_RE = re.compile(
    r'<span[^>]*font-weight:\s*bold[^>]*>(.*?)</span>', re.IGNORECASE | re.S)
_SMALLCAPS_SPAN_RE = re.compile(r'<span[^>]*>(.*?)</span>',
                                re.IGNORECASE | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_pango(html: str) -> str:
    text = _ITALIC_SPAN_RE.sub(r"<i>\1</i>", html)
    text = _BOLD_SPAN_RE.sub(r"<b>\1</b>", text)
    # normalise <em>/<strong>
    text = re.sub(r"</?em>", lambda m: "<i>" if "/" not in m.group(0)
                  else "</i>", text)
    text = re.sub(r"</?strong>", lambda m: "<b>" if "/" not in m.group(0)
                  else "</b>", text)
    # drop any remaining spans but keep their content
    text = _SMALLCAPS_SPAN_RE.sub(r"\1", text)
    # strip any other stray tags except the i/b we introduced
    text = re.sub(r"</?(?!/?[ib]>)[a-zA-Z][^>]*>", "", text)
    return text.strip()


def _html_to_plain(html: str) -> str:
    return unescape(_TAG_RE.sub("", html)).strip()


def render_markup(entry: dict, csl_path: str) -> str:
    """Pango markup for the reference, rendered via the given CSL file.

    Falls back to the built-in APA markup if citeproc is unavailable or the
    render fails."""
    if not csl_available():
        return apa.format_apa_markup(entry)
    try:
        html = _render(entry, csl_path)
    except Exception:  # noqa: BLE001
        return apa.format_apa_markup(entry)
    if not html:
        return apa.format_apa_markup(entry)
    return _html_to_pango(html)


def render_plain(entry: dict, csl_path: str) -> str:
    """Plain-text reference rendered via the given CSL file, with APA
    fallback."""
    if not csl_available():
        return apa.format_apa_plain(entry)
    try:
        html = _render(entry, csl_path)
    except Exception:  # noqa: BLE001
        return apa.format_apa_plain(entry)
    if not html:
        return apa.format_apa_plain(entry)
    return _html_to_plain(html)
