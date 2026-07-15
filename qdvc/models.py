"""Model dataclasses (pure, no GTK).

`Record`, `MyWork`, `Author`, and `Outlet` are the persistent entities the
workspace manages. They know how to render/serialise themselves but contain no
UI code, so they can be shared across any front-end.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import apa
from . import acis
from .bibtex import parse_bibtex
from .markdown_io import parse_markdown


@dataclass
class Record:
    bibliotheca_id: str
    bib_path: str
    md_path: str | None = None
    # cached-index display fields:
    entrytype: str = "misc"
    type_label: str = "Other"
    author: str = ""
    year: str = ""
    title: str = ""
    journal: str = ""
    doi: str = ""
    # full-text presence, cached in the index (paths live in the .md file):
    has_pdf: bool = False
    has_epub: bool = False
    # lazily populated:
    _bib: dict | None = field(default=None, repr=False)

    def bib(self) -> dict:
        if self._bib is None:
            self._bib = parse_bibtex(Path(self.bib_path))
        return self._bib

    def apa_markup(self) -> str:
        return apa.format_apa_markup(self.bib())

    def apa_plain(self) -> str:
        return apa.format_apa_plain(self.bib())

    def acis_markup(self, disambiguator: str = "") -> str:
        return acis.format_acis_markup(self.bib(), disambiguator)

    def acis_plain(self, disambiguator: str = "") -> str:
        return acis.format_acis_plain(self.bib(), disambiguator)

    def acis_in_text_markup(self, disambiguator: str = "",
                            narrative: bool = False) -> str:
        return acis.in_text_markup(self.bib(), disambiguator, narrative)

    def acis_in_text_plain(self, disambiguator: str = "",
                           narrative: bool = False) -> str:
        return acis.in_text_plain(self.bib(), disambiguator, narrative)

    @property
    def outlet(self) -> str:
        """Display value for the 'Outlet' column: the journal for journal
        articles, the book/proceedings title for chapters and proceedings, an
        em dash otherwise."""
        if self.type_label in ("Journal article", "Book chapter",
                               "Proceedings"):
            return self.journal or "\u2014"
        return "\u2014"

    def read_notes(self) -> tuple[dict, str]:
        if self.md_path:
            return parse_markdown(Path(self.md_path))
        return {}, ""


@dataclass
class MyWork:
    name: str
    path: str
    cites: list[str] = field(default_factory=list)
    published_as: str | None = None

    def sorted_cites(self) -> list[str]:
        """Cited Bibliotheca IDs, de-duplicated and alphabetically ordered
        (case-insensitive)."""
        seen = set()
        unique = []
        for c in self.cites:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return sorted(unique, key=str.lower)

    def to_yaml_dict(self) -> dict:
        # Order matters: `name` first, then `cites`, then optional extras.
        # Python dicts preserve insertion order and we dump with
        # sort_keys=False so this ordering is what lands on disk.
        data: dict = {"name": self.name, "cites": self.sorted_cites()}
        if self.published_as:
            data["published_as"] = self.published_as
        return data

    def save(self) -> None:
        # keep the in-memory list canonicalised too, so callers that read
        # `cites` after a save see the same order that was written
        self.cites = self.sorted_cites()
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(self.to_yaml_dict(), sort_keys=False,
                              allow_unicode=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)


@dataclass
class Author:
    author_id: str            # SURNAME_GivenNames
    surname: str
    given_names: str
    starred: bool = False
    path: str = ""            # authors/<author_id>.yml
    # populated at load time, not persisted:
    record_ids: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if self.given_names:
            return f"{self.surname}, {self.given_names}"
        return self.surname

    def to_yaml_dict(self) -> dict:
        return {
            "id": self.author_id,
            "surname": self.surname,
            "given_names": self.given_names,
            "starred": bool(self.starred),
        }

    def save(self) -> None:
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(self.to_yaml_dict(), sort_keys=True,
                              allow_unicode=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)


@dataclass
class Outlet:
    """A publication outlet (journal or proceedings) derived from the outlet
    field of journal-article and proceedings records.

    `outlet_id` is a stable in-memory key (the slug of the full name); it does
    not change when a nickname is set. The on-disk file stem, however, is the
    nickname when one is set, else the slug (see `Workspace.outlet_path_for`).
    Only `starred`, `nickname`, and `jflags` are user-editable; `name` is the
    verbatim outlet title as it appears in the BibTeX.
    """

    outlet_id: str            # slug of the full name (stable key)
    name: str                 # full outlet title, verbatim
    nickname: str = ""        # optional short label, e.g. "JBIB"
    starred: bool = False
    jflags: list[str] = field(default_factory=list)
    path: str = ""            # outlets/<nickname-or-slug>.yml
    # populated at load time, not persisted:
    record_ids: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.name

    def sorted_jflags(self) -> list[str]:
        """J-Flags de-duplicated and stored in alphabetical order (the on-disk
        canonical form). Display ordering by priority is a UI concern handled
        elsewhere."""
        seen = set()
        unique = []
        for f in self.jflags:
            f = str(f).strip()
            if f and f not in seen:
                seen.add(f)
                unique.append(f)
        return sorted(unique, key=str.lower)

    def to_yaml_dict(self) -> dict:
        data: dict = {"name": self.name}
        if self.nickname:
            data["nickname"] = self.nickname
        data["starred"] = bool(self.starred)
        data["jflags"] = self.sorted_jflags()
        return data

    def save(self) -> None:
        # keep the in-memory list canonicalised too
        self.jflags = self.sorted_jflags()
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(self.to_yaml_dict(), sort_keys=False,
                              allow_unicode=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)
