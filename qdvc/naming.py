"""Naming, id, and slug helpers (pure, no GTK).

These functions build and sanitise the identifiers used throughout the model:
Bibliotheca IDs (file stems), author ids, outlet slugs, nickname file stems,
and DOI normalisation. They are grouped here so both the model layer
(`workspace.py`) and any future front-end can share them without importing the
whole workspace.
"""

import re

# Characters allowed in a file stem / bibliotheca_id (everything else stripped).
_ID_ALLOWED_RE = re.compile(r"[^A-Za-z0-9_-]+")

# An outlet nickname may contain only ASCII letters (upper/lower A-Z).
_OUTLET_NICKNAME_RE = re.compile(r"[A-Za-z]+")


def normalise_doi(doi: str | None) -> str:
    """Strip a leading ``doi.org/`` (or ``dx.doi.org/``) prefix and surrounding
    whitespace, returning the bare DOI. Returns '' for falsy input."""
    if not doi:
        return ""
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi


def sanitise_id(text: str) -> str:
    """Turn an arbitrary string into a safe file-stem / bibliotheca_id."""
    text = (text or "").strip()
    # collapse whitespace to underscores, strip disallowed characters
    text = re.sub(r"\s+", "_", text)
    text = _ID_ALLOWED_RE.sub("", text)
    return text.strip("_-")


def id_suffix(bibliotheca_id: str) -> str:
    """Return the suffix of a bibliotheca_id, i.e. the text after the last
    underscore (the convention is ``AuthorSurnamesYear_suffix``). Returns '' if
    there is no underscore or nothing follows it."""
    bid = bibliotheca_id or ""
    if "_" not in bid:
        return ""
    return bid.rsplit("_", 1)[1].strip()


def sanitise_stem(text: str) -> str:
    """Turn arbitrary text into a safe file stem, preserving case.

    Used for outlet nickname filenames ("JBIB" -> "JBIB.yml"). Spaces become
    hyphens; characters outside [A-Za-z0-9_-] are dropped.
    """
    text = (text or "").strip()
    text = re.sub(r"\s+", "-", text)
    text = _ID_ALLOWED_RE.sub("", text)
    return text.strip("-_")


def slugify_outlet(name: str) -> str:
    """Slugify an outlet name to a stable, lowercase, hyphen-joined id.

    "Journal of Bibliotheca" -> "journal-of-bibliotheca"

    Returns '' if nothing usable remains.
    """
    text = (name or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def make_author_id(surname: str, given_names: str) -> str:
    """Build a stable author id of the form SURNAME_GivenNames.

    Surname is upper-cased; given names keep their case. Non-alphanumeric
    characters (spaces, dots, hyphens inside names) are removed so the id is a
    safe filename. Returns '' if there is no surname.
    """
    surname = (surname or "").strip()
    given_names = (given_names or "").strip()
    if not surname:
        return ""
    sur = re.sub(r"[^A-Za-z0-9]+", "", surname).upper()
    giv = re.sub(r"[^A-Za-z0-9]+", "", given_names.title())
    if not sur:
        return ""
    return f"{sur}_{giv}" if giv else sur
