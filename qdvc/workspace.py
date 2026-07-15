"""Workspace model.

A workspace on disk looks like:

    (root)/
        bibtex/A..Z/<bibliotheca_id>.bib
        markdown/A..Z/<bibliotheca_id>.md
        my_works/*.yml

We build a lightweight index (bibliotheca_id -> paths + a few display fields)
and cache it as JSON at (root)/.qdvc-index.json so re-opening a large workspace
is fast. Full BibTeX parsing and Markdown reading are done lazily, per record,
only when a record is selected.

This module keeps the `Workspace` class itself. The pure building blocks it is
built from were split out into focused modules and are re-exported here so
existing imports (e.g. `from .workspace import slugify_outlet` / `Record`)
keep working unchanged:

  * bibtex.py       BibTeX parsing + multi-entry splitting.
  * markdown_io.py  Markdown/YAML-frontmatter read & write.
  * naming.py       id / slug / nickname / DOI helpers.
  * models.py       Record, MyWork, Author, Outlet dataclasses.
"""

import json
import os
from pathlib import Path

import yaml

from . import apa
from .bibtex import parse_bibtex, parse_bib_fallback, split_bib_entries
from .markdown_io import parse_markdown, write_markdown
from .models import Record, MyWork, Author, Outlet
from .naming import (
    normalise_doi,
    sanitise_id,
    id_suffix,
    sanitise_stem,
    slugify_outlet,
    make_author_id,
    _OUTLET_NICKNAME_RE,
)

# --- backward-compatible aliases ------------------------------------------
# The helpers below used to live in this module under underscore-prefixed
# names and are referenced that way inside `Workspace` (and by some callers /
# tests). Keep the old names pointing at the new public functions so nothing
# downstream has to change.
_normalise_doi = normalise_doi
_sanitise_id = sanitise_id
_id_suffix = id_suffix
_sanitise_stem = sanitise_stem
_parse_bib_fallback = parse_bib_fallback
_split_bib_entries = split_bib_entries

INDEX_FILENAME = ".qdvc-index.json"
INDEX_VERSION = 4


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.records: dict[str, Record] = {}
        self.my_works: dict[str, MyWork] = {}
        self.authors: dict[str, Author] = {}
        self.outlets: dict[str, Outlet] = {}
        self._doi_index: dict[str, str] = {}  # doi(lower) -> bibliotheca_id
        # author_id -> list of bibliotheca_ids
        self._author_records: dict[str, list[str]] = {}
        # outlet_id -> list of bibliotheca_ids
        self._outlet_records: dict[str, list[str]] = {}

    # --- paths -----------------------------------------------------------
    @property
    def bibtex_dir(self) -> Path:
        return self.root / "bibtex"

    @property
    def markdown_dir(self) -> Path:
        return self.root / "markdown"

    @property
    def my_works_dir(self) -> Path:
        return self.root / "my_works"

    @property
    def authors_dir(self) -> Path:
        return self.root / "authors"

    @property
    def outlets_dir(self) -> Path:
        return self.root / "outlets"

    @property
    def csl_dir(self) -> Path:
        return self.root / "csl"

    def list_csl_files(self) -> list[str]:
        """Return the file names (not paths) of the CSL style files in the
        workspace's ``csl/`` folder, sorted case-insensitively. Files are
        listed by filename; no metadata inside the CSL is read."""
        d = self.csl_dir
        if not d.is_dir():
            return []
        names = [f.name for f in d.glob("*.csl") if f.is_file()]
        return sorted(names, key=str.lower)

    def csl_path(self, filename: str) -> Path | None:
        """Resolve a CSL filename (as returned by list_csl_files) to its path,
        or None if it is not present."""
        if not filename:
            return None
        p = self.csl_dir / filename
        return p if p.is_file() else None

    def acis_disambiguator(self, record) -> str:
        """The ACIS year-disambiguation letter for ``record`` ('' when the
        author/year pair is unique in this workspace).

        Records sharing an author/year get 'a', 'b', … (title order). The map
        is computed lazily across all cached records and rebuilt whenever the
        record set changes (tracked by identity of the ``records`` dict), so it
        stays cheap for repeated Pane-3 lookups without going stale after an
        import or rescan.
        """
        from . import acis
        cache = getattr(self, "_acis_disambig_cache", None)
        stamp = len(self.records)
        if cache is None or cache[0] != stamp:
            cache = (stamp, acis.disambiguator_map(self.records.values()))
            self._acis_disambig_cache = cache
        bid = getattr(record, "bibliotheca_id", "")
        return cache[1].get(bid, "")

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_FILENAME

    def _shard(self, bibliotheca_id: str) -> str:
        c = bibliotheca_id[:1].upper()
        return c if c.isalpha() else "_"

    def md_path_for(self, bibliotheca_id: str) -> Path:
        return self.markdown_dir / self._shard(bibliotheca_id) / \
            f"{bibliotheca_id}.md"

    def bib_path_for(self, bibliotheca_id: str) -> Path:
        return self.bibtex_dir / self._shard(bibliotheca_id) / \
            f"{bibliotheca_id}.bib"

    def outlet_path_for(self, outlet: "Outlet") -> Path:
        """The on-disk .yml path for an outlet: the nickname when set,
        otherwise the slug of the full name."""
        stem = _sanitise_stem(outlet.nickname) if outlet.nickname \
            else outlet.outlet_id
        stem = stem or "outlet"
        return self.outlets_dir / f"{stem}.yml"

    # --- validation ------------------------------------------------------
    @staticmethod
    def looks_like_workspace(root: str | Path) -> bool:
        root = Path(root)
        return (root / "bibtex").is_dir() or (root / "markdown").is_dir()

    # --- loading ---------------------------------------------------------
    def load(self, force_rescan: bool = False) -> None:
        if not force_rescan and self._load_index():
            self._load_my_works()
            self._build_doi_index()
            self._derive_authors()
            self._derive_outlets()
            return
        self._scan()
        self._load_my_works()
        self._build_doi_index()
        self._derive_authors()
        self._derive_outlets()
        self._save_index()

    def _scan(self) -> None:
        self.records.clear()
        bib_root = self.bibtex_dir
        if not bib_root.is_dir():
            return
        for bib_file in bib_root.rglob("*.bib"):
            bid = bib_file.stem
            md = self.md_path_for(bid)
            e = parse_bibtex(bib_file)
            has_pdf = has_epub = False
            if md.exists():
                fm, _ = parse_markdown(md)
                has_pdf = bool(fm.get("pdf"))
                has_epub = bool(fm.get("epub"))
            rec = Record(
                bibliotheca_id=bid,
                bib_path=str(bib_file),
                md_path=str(md) if md.exists() else str(md),
                entrytype=(e.get("ENTRYTYPE") or "misc").lower(),
                type_label=apa.type_label(e.get("ENTRYTYPE") or "misc",
                                          e.get("booktitle")),
                author=apa._clean(e.get("author") or e.get("editor")),
                year=apa._clean(e.get("year")),
                title=apa._clean(e.get("title")),
                journal=apa._clean(e.get("journal") or e.get("journaltitle")
                                   or e.get("booktitle")),
                doi=_normalise_doi(e.get("doi")),
                has_pdf=has_pdf,
                has_epub=has_epub,
            )
            rec._bib = e
            self.records[bid] = rec

    def _load_index(self) -> bool:
        p = self.index_path
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if data.get("version") != INDEX_VERSION:
            return False
        self.records.clear()
        for item in data.get("records", []):
            bib_path = item.get("bib_path", "")
            if not bib_path or not Path(bib_path).exists():
                # index is stale; trigger a rescan
                return False
            rec = Record(
                bibliotheca_id=item["bibliotheca_id"],
                bib_path=bib_path,
                md_path=item.get("md_path"),
                entrytype=item.get("entrytype", "misc"),
                type_label=item.get("type_label", "Other"),
                author=item.get("author", ""),
                year=item.get("year", ""),
                title=item.get("title", ""),
                journal=item.get("journal", ""),
                doi=item.get("doi", ""),
                has_pdf=bool(item.get("has_pdf", False)),
                has_epub=bool(item.get("has_epub", False)),
            )
            self.records[rec.bibliotheca_id] = rec
        return bool(self.records)

    def _save_index(self) -> None:
        data = {
            "version": INDEX_VERSION,
            "records": [
                {
                    "bibliotheca_id": r.bibliotheca_id,
                    "bib_path": r.bib_path,
                    "md_path": r.md_path,
                    "entrytype": r.entrytype,
                    "type_label": r.type_label,
                    "author": r.author,
                    "year": r.year,
                    "title": r.title,
                    "journal": r.journal,
                    "doi": r.doi,
                    "has_pdf": r.has_pdf,
                    "has_epub": r.has_epub,
                }
                for r in self.records.values()
            ],
        }
        try:
            self.index_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=0),
                encoding="utf-8")
        except OSError:
            pass

    def _load_my_works(self) -> None:
        self.my_works.clear()
        d = self.my_works_dir
        if not d.is_dir():
            return
        for f in sorted(d.glob("*.yml")) + sorted(d.glob("*.yaml")):
            raw_text = ""
            try:
                raw_text = f.read_text(encoding="utf-8")
                data = yaml.safe_load(raw_text) or {}
            except (OSError, yaml.YAMLError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            cites = data.get("cites") or data.get("citations") or []
            if not isinstance(cites, list):
                cites = []
            name = data.get("name") or data.get("title") or f.stem
            work = MyWork(
                name=str(name),
                path=str(f),
                cites=[str(c) for c in cites],
                published_as=data.get("published_as")
                or data.get("published_version"),
            )
            self.my_works[f.stem] = work
            # Ensure the file on disk is in canonical form (name before cites,
            # cites alphabetised, canonical key names). Rewrite only if needed.
            self._canonicalise_work_file(work, raw_text)

    @staticmethod
    def _canonicalise_work_file(work: "MyWork", raw_text: str) -> None:
        try:
            canonical = yaml.safe_dump(work.to_yaml_dict(), sort_keys=False,
                                       allow_unicode=True)
        except Exception:  # noqa: BLE001
            return
        if raw_text != canonical:
            try:
                work.save()
            except OSError:
                pass

    def _build_doi_index(self) -> None:
        self._doi_index.clear()
        for bid, rec in self.records.items():
            if rec.doi:
                self._doi_index[rec.doi.lower()] = bid

    # --- authors ---------------------------------------------------------
    def _load_author_files(self) -> dict[str, Author]:
        """Load persisted author records (id -> Author), if any."""
        loaded: dict[str, Author] = {}
        d = self.authors_dir
        if not d.is_dir():
            return loaded
        for f in sorted(d.glob("*.yml")) + sorted(d.glob("*.yaml")):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                data = {}
            if not isinstance(data, dict):
                continue
            aid = str(data.get("id") or f.stem)
            loaded[aid] = Author(
                author_id=aid,
                surname=str(data.get("surname", "")),
                given_names=str(data.get("given_names", "")),
                starred=bool(data.get("starred", False)),
                path=str(f),
            )
        return loaded

    def _derive_authors(self) -> None:
        """Derive unique authors from records, merge with persisted records,
        persist any newly-discovered authors, and build the author->records
        index. Starred state from existing files is preserved."""
        persisted = self._load_author_files()
        self.authors = {}
        self._author_records = {}

        for bid, rec in self.records.items():
            seen_in_this_record = set()
            for surname, given in apa.author_tokens(rec.author):
                aid = make_author_id(surname, given)
                if not aid:
                    continue
                if aid not in self.authors:
                    existing = persisted.get(aid)
                    if existing is not None:
                        author = existing
                    else:
                        author = Author(
                            author_id=aid,
                            surname=surname,
                            given_names=given,
                            starred=False,
                            path=str(self.authors_dir / f"{aid}.yml"),
                        )
                    self.authors[aid] = author
                    self._author_records[aid] = []
                # avoid double-counting a record if an author appears twice
                if bid not in seen_in_this_record:
                    self._author_records[aid].append(bid)
                    seen_in_this_record.add(aid)

        # persist any authors that do not yet have a file on disk
        for aid, author in self.authors.items():
            if not author.path:
                author.path = str(self.authors_dir / f"{aid}.yml")
            if not Path(author.path).exists():
                try:
                    author.save()
                except OSError:
                    pass
            author.record_ids = sorted(self._author_records.get(aid, []),
                                       key=str.lower)

    def all_authors(self) -> list[Author]:
        return sorted(self.authors.values(),
                      key=lambda a: (a.surname.lower(),
                                     a.given_names.lower()))

    def starred_authors(self) -> list[Author]:
        return [a for a in self.all_authors() if a.starred]

    def set_author_starred(self, author_id: str, starred: bool) -> None:
        author = self.authors.get(author_id)
        if not author:
            return
        author.starred = bool(starred)
        if not author.path:
            author.path = str(self.authors_dir / f"{author_id}.yml")
        author.save()

    # --- outlets ---------------------------------------------------------
    # The record types that count as a publication "outlet": journal articles
    # and proceedings. Book chapters, books, webpages, etc. are excluded.
    OUTLET_TYPES = ("Journal article", "Proceedings")

    def _load_outlet_files(self) -> dict[str, Outlet]:
        """Load persisted outlet records (outlet_id -> Outlet), if any.

        The outlet_id is always recomputed from the stored full `name` so it
        stays stable regardless of the file stem (which follows the nickname).
        """
        loaded: dict[str, Outlet] = {}
        d = self.outlets_dir
        if not d.is_dir():
            return loaded
        for f in sorted(d.glob("*.yml")) + sorted(d.glob("*.yaml")):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                data = {}
            if not isinstance(data, dict):
                continue
            name = str(data.get("name", "")).strip()
            if not name:
                continue
            oid = slugify_outlet(name)
            if not oid:
                continue
            jflags = data.get("jflags") or []
            if not isinstance(jflags, list):
                jflags = []
            loaded[oid] = Outlet(
                outlet_id=oid,
                name=name,
                nickname=str(data.get("nickname", "")).strip(),
                starred=bool(data.get("starred", False)),
                jflags=[str(x) for x in jflags],
                path=str(f),
            )
        return loaded

    def _derive_outlets(self) -> None:
        """Derive unique outlets from journal-article and proceedings records,
        merge with persisted files, persist any newly-discovered outlets, and
        build the outlet->records index. Starred/nickname/jflags state is
        preserved.

        Only records whose type is in OUTLET_TYPES contribute an outlet, so
        book-chapter booktitles never appear here.
        """
        persisted = self._load_outlet_files()
        self.outlets = {}
        self._outlet_records = {}

        for bid, rec in self.records.items():
            if rec.type_label not in self.OUTLET_TYPES:
                continue
            name = (rec.journal or "").strip()
            if not name:
                continue
            oid = slugify_outlet(name)
            if not oid:
                continue
            if oid not in self.outlets:
                existing = persisted.get(oid)
                if existing is not None:
                    outlet = existing
                    # keep the display name in sync with the current BibTeX
                    outlet.name = name
                else:
                    outlet = Outlet(outlet_id=oid, name=name)
                    outlet.path = str(self.outlet_path_for(outlet))
                self.outlets[oid] = outlet
                self._outlet_records[oid] = []
            self._outlet_records[oid].append(bid)

        # persist any outlets that do not yet have a file on disk
        for oid, outlet in self.outlets.items():
            if not outlet.path:
                outlet.path = str(self.outlet_path_for(outlet))
            if not Path(outlet.path).exists():
                try:
                    outlet.save()
                except OSError:
                    pass
            outlet.record_ids = sorted(self._outlet_records.get(oid, []),
                                       key=str.lower)

    def all_outlets(self) -> list[Outlet]:
        return sorted(self.outlets.values(),
                      key=lambda o: o.name.lower())

    def starred_outlets(self) -> list[Outlet]:
        return [o for o in self.all_outlets() if o.starred]

    def set_outlet_starred(self, outlet_id: str, starred: bool) -> None:
        outlet = self.outlets.get(outlet_id)
        if not outlet:
            return
        outlet.starred = bool(starred)
        if not outlet.path:
            outlet.path = str(self.outlet_path_for(outlet))
        outlet.save()

    def set_outlet_jflags(self, outlet_id: str, jflags: list[str]) -> None:
        outlet = self.outlets.get(outlet_id)
        if not outlet:
            return
        outlet.jflags = [str(f) for f in (jflags or [])]
        if not outlet.path:
            outlet.path = str(self.outlet_path_for(outlet))
        outlet.save()

    def set_outlet_nickname(self, outlet_id: str, nickname: str) -> None:
        """Set (or clear) an outlet's nickname, renaming its .yml file to the
        nickname (or back to the slug when cleared).

        Raises ValueError if the nickname contains anything other than A-Z/a-z
        letters, or if it collides with another outlet's nickname or that
        outlet's on-disk .yml stem (to prevent YAML filename collisions).
        """
        outlet = self.outlets.get(outlet_id)
        if not outlet:
            return
        nickname = (nickname or "").strip()
        if nickname:
            if not _OUTLET_NICKNAME_RE.fullmatch(nickname):
                raise ValueError(
                    "A nickname may contain only the letters A-Z and a-z.")
            # collision check: no other outlet may already use this nickname,
            # and the resulting file stem must not clash with another outlet's.
            new_stem = nickname.lower()
            for other_id, other in self.outlets.items():
                if other_id == outlet_id:
                    continue
                if other.nickname and other.nickname.lower() == new_stem:
                    raise ValueError(
                        f"The nickname '{nickname}' is already used by "
                        f"'{other.name}'.")
                other_stem = (_sanitise_stem(other.nickname)
                              if other.nickname else other.outlet_id)
                if other_stem.lower() == _sanitise_stem(nickname).lower():
                    raise ValueError(
                        f"The nickname '{nickname}' collides with an existing "
                        f"outlet file.")
        old_path = Path(outlet.path) if outlet.path else None
        outlet.nickname = nickname
        new_path = self.outlet_path_for(outlet)
        # Write the new file first, then remove the stale one if it differs.
        outlet.path = str(new_path)
        outlet.save()
        if old_path and old_path.exists() and \
                old_path.resolve() != new_path.resolve():
            try:
                old_path.unlink()
            except OSError:
                pass

    def outlet_for_record(self, rec: "Record") -> Outlet | None:
        """Return the Outlet a record belongs to, or None when the record is
        not a journal article / proceedings (or its outlet is unknown)."""
        if rec.type_label not in self.OUTLET_TYPES:
            return None
        name = (rec.journal or "").strip()
        if not name:
            return None
        return self.outlets.get(slugify_outlet(name))

    def records_for_outlet(self, outlet_id: str) -> list["Record"]:
        ids = self._outlet_records.get(outlet_id, [])
        recs = [self.records[i] for i in ids if i in self.records]
        return sorted(recs, key=lambda r: r.bibliotheca_id.lower())

    def records_for_author(self, author_id: str) -> list["Record"]:
        ids = self._author_records.get(author_id, [])
        recs = [self.records[i] for i in ids if i in self.records]
        return sorted(recs, key=lambda r: r.bibliotheca_id.lower())

    # --- queries ---------------------------------------------------------
    def all_records(self) -> list[Record]:
        return sorted(self.records.values(),
                      key=lambda r: r.bibliotheca_id.lower())

    def records_by_type(self, label: str) -> list[Record]:
        return [r for r in self.all_records() if r.type_label == label]

    def records_by_fulltext(self, which: str) -> list[Record]:
        """`which` is 'pdf', 'epub', or 'none' (neither PDF nor EPUB)."""
        out = []
        for r in self.all_records():
            if which == "pdf" and r.has_pdf:
                out.append(r)
            elif which == "epub" and r.has_epub:
                out.append(r)
            elif which == "none" and not r.has_pdf and not r.has_epub:
                out.append(r)
        return out

    def records_by_doi_status(self, has_doi: bool) -> list[Record]:
        return [r for r in self.all_records() if bool(r.doi) == has_doi]

    def records_for_work(self, work_key: str) -> list[Record]:
        work = self.my_works.get(work_key)
        if not work:
            return []
        return [self.records[c] for c in work.sorted_cites()
                if c in self.records]

    def lookup_doi(self, doi: str) -> str | None:
        return self._doi_index.get(_normalise_doi(doi).lower())

    def get(self, bibliotheca_id: str) -> Record | None:
        return self.records.get(bibliotheca_id)

    # --- mutations -------------------------------------------------------
    def import_bib_file(self, source: str | Path) -> list[str]:
        """Import a .bib file that may contain one or more entries."""
        text = Path(source).read_text(encoding="utf-8", errors="replace")
        return self.import_bib_text(text)

    def import_bib_text(self, text: str) -> tuple[list[str], list[tuple]]:
        """Import BibTeX from a raw string that may contain several entries.

        Each entry is filed under bibtex/<shard>/<bibliotheca_id>.bib using
        its citation key as the bibliotheca_id. Entries whose id already exists
        are skipped, and entries whose DOI matches an already-catalogued record
        are refused (never written). Returns ``(imported_ids,
        skipped_dois)`` where ``skipped_dois`` is a list of
        ``(citation_key, doi, existing_bibliotheca_id)`` tuples for the
        DOI-collision refusals.
        """
        entries = _split_bib_entries(text or "")
        imported: list[str] = []
        skipped_dois: list[tuple] = []
        for raw_entry, key in entries:
            if not key:
                continue
            bid = _sanitise_id(key)
            dest = self.bib_path_for(bid)
            if dest.exists() or bid in self.records:
                continue
            # Refuse an entry whose DOI is already in the catalogue, so we do
            # not create a duplicate of an existing article.
            entry_doi = _normalise_doi(_parse_bib_fallback(raw_entry).get("doi"))
            if entry_doi:
                existing = self._doi_index.get(entry_doi.lower())
                if existing:
                    skipped_dois.append((key, entry_doi, existing))
                    continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(raw_entry.strip() + "\n", encoding="utf-8")
            e = parse_bibtex(dest)
            rec = Record(
                bibliotheca_id=bid,
                bib_path=str(dest),
                md_path=str(self.md_path_for(bid)),
                entrytype=(e.get("ENTRYTYPE") or "misc").lower(),
                type_label=apa.type_label(e.get("ENTRYTYPE") or "misc",
                                          e.get("booktitle")),
                author=apa._clean(e.get("author") or e.get("editor")),
                year=apa._clean(e.get("year")),
                title=apa._clean(e.get("title")),
                journal=apa._clean(e.get("journal") or e.get("journaltitle")
                                   or e.get("booktitle")),
                doi=_normalise_doi(e.get("doi")),
            )
            rec._bib = e
            self.records[bid] = rec
            imported.append(bid)
            # keep the DOI index current within this same import batch so two
            # incoming entries that share a DOI don't both slip through.
            if rec.doi:
                self._doi_index[rec.doi.lower()] = bid
        if imported:
            self._build_doi_index()
            self._derive_authors()
            self._derive_outlets()
            self._save_index()
        return imported, skipped_dois

    def rename_record(self, old_id: str, new_id: str) -> None:
        """Rename a record: move paired .bib/.md files and update my_works.

        Raises ValueError on invalid input or collision.
        """
        new_id = new_id.strip()
        if not new_id:
            raise ValueError("New Bibliotheca ID must not be empty.")
        if new_id == old_id:
            return
        if _sanitise_id(new_id) != new_id:
            raise ValueError(
                "Bibliotheca ID may only contain letters, digits, "
                "hyphen and underscore.")
        if new_id in self.records:
            raise ValueError(f"A record named '{new_id}' already exists.")
        rec = self.records.get(old_id)
        if not rec:
            raise ValueError(f"No record named '{old_id}'.")

        new_bib = self.bib_path_for(new_id)
        new_bib.parent.mkdir(parents=True, exist_ok=True)
        old_bib = Path(rec.bib_path)
        if old_bib.exists():
            os.replace(old_bib, new_bib)

        old_md = Path(rec.md_path) if rec.md_path else None
        new_md = self.md_path_for(new_id)
        if old_md and old_md.exists():
            new_md.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old_md, new_md)

        # update in-memory record
        del self.records[old_id]
        rec.bibliotheca_id = new_id
        rec.bib_path = str(new_bib)
        rec.md_path = str(new_md)
        self.records[new_id] = rec

        # update my_works references
        for work in self.my_works.values():
            changed = False
            if old_id in work.cites:
                work.cites = [new_id if c == old_id else c
                              for c in work.cites]
                changed = True
            if work.published_as == old_id:
                work.published_as = new_id
                changed = True
            if changed:
                work.save()

        self._build_doi_index()
        self._derive_authors()
        self._save_index()

    def create_my_work(self, name: str) -> "MyWork":
        stem = _sanitise_id(name) or "work"
        candidate = stem
        i = 2
        while candidate in self.my_works or \
                (self.my_works_dir / f"{candidate}.yml").exists():
            candidate = f"{stem}_{i}"
            i += 1
        self.my_works_dir.mkdir(parents=True, exist_ok=True)
        work = MyWork(name=name,
                      path=str(self.my_works_dir / f"{candidate}.yml"))
        work.save()
        self.my_works[candidate] = work
        return work

    def allocate_to_work(self, work_key: str,
                         bibliotheca_ids: list[str]) -> int:
        """Add one or more records to a work's citation list.

        The work file is kept canonical (name-first, cites de-duplicated and
        alphabetised) by MyWork.save. Returns the number of ids newly added.
        """
        work = self.my_works.get(work_key)
        if not work:
            raise ValueError(f"No work named '{work_key}'.")
        existing = set(work.cites)
        added = 0
        for bid in bibliotheca_ids:
            if bid and bid not in existing:
                work.cites.append(bid)
                existing.add(bid)
                added += 1
        if added:
            work.save()
        return added

    # --- full-text (PDF/EPUB) --------------------------------------------
    def set_fulltext_path(self, bibliotheca_id: str, kind: str,
                          abs_path: str | None,
                          storage_root: str | None) -> None:
        """Store a full-text path for a record in its markdown frontmatter.

        `kind` is 'pdf' or 'epub'. The path is stored relative to
        `storage_root` when the file lies inside it; otherwise the absolute
        path is stored (with a warning left to the caller). Passing
        abs_path=None clears the entry.
        """
        kind = kind.lower()
        if kind not in ("pdf", "epub"):
            raise ValueError("kind must be 'pdf' or 'epub'")
        rec = self.records.get(bibliotheca_id)
        if not rec:
            raise ValueError(f"No record named '{bibliotheca_id}'.")

        md_path = Path(rec.md_path) if rec.md_path \
            else self.md_path_for(bibliotheca_id)
        fm, body = parse_markdown(md_path) if md_path.exists() else ({}, "")

        if abs_path:
            stored = abs_path
            if storage_root:
                try:
                    rel = Path(abs_path).resolve().relative_to(
                        Path(storage_root).resolve())
                    stored = str(rel)
                except ValueError:
                    # file is outside the storage root; keep absolute
                    stored = str(Path(abs_path).resolve())
            fm[kind] = stored
        else:
            fm.pop(kind, None)

        write_markdown(md_path, fm, body)
        rec.md_path = str(md_path)
        if kind == "pdf":
            rec.has_pdf = bool(abs_path)
        else:
            rec.has_epub = bool(abs_path)
        self._save_index()

    def resolve_fulltext_path(self, bibliotheca_id: str, kind: str,
                              storage_root: str | None) -> str | None:
        """Return the absolute path of a record's full-text file, if set."""
        rec = self.records.get(bibliotheca_id)
        if not rec or not rec.md_path:
            return None
        fm, _ = parse_markdown(Path(rec.md_path))
        stored = fm.get(kind.lower())
        if not stored:
            return None
        p = Path(stored)
        if p.is_absolute():
            return str(p)
        if storage_root:
            return str((Path(storage_root) / p).resolve())
        return str(p)

    # --- validation ------------------------------------------------------
    def validate(self, storage_root: str | None = None) -> dict:
        """Return a report of workspace integrity problems."""
        report = {
            "orphan_markdown": [],       # .md without matching .bib
            "missing_fulltext": [],      # (id, kind, path)
            "dangling_citations": [],    # (work_name, id)
            "dangling_published_as": [],  # (work_name, id)
            "duplicate_dois": [],        # (doi, [ids])
            "key_mismatch": [],          # (bibliotheca_id, bibtex_key)
            # outlet nickname vs. bibliotheca_id suffix conventions:
            "nick_set_no_suffix": [],    # (id, nickname) nickname but no suffix
            "nick_set_suffix_diff": [],  # (id, suffix, nickname) both, differ
            "suffix_no_nick": [],        # (id, suffix) suffix but no nickname
        }

        # BibTeX citation key differs from the Bibliotheca ID (file stem)
        for bid, rec in self.records.items():
            entry = rec.bib()
            key = (entry.get("ID") or entry.get("id") or "").strip()
            if key and key != bid:
                report["key_mismatch"].append((bid, key))

        # orphan markdown: any .md whose stem is not a known record
        md_root = self.markdown_dir
        if md_root.is_dir():
            for md_file in md_root.rglob("*.md"):
                if md_file.stem not in self.records:
                    report["orphan_markdown"].append(str(md_file))

        # missing full-text files referenced in frontmatter
        for bid, rec in self.records.items():
            if not rec.md_path or not Path(rec.md_path).exists():
                continue
            fm, _ = parse_markdown(Path(rec.md_path))
            for kind in ("pdf", "epub"):
                stored = fm.get(kind)
                if not stored:
                    continue
                p = Path(stored)
                if not p.is_absolute() and storage_root:
                    p = Path(storage_root) / p
                if not p.exists():
                    report["missing_fulltext"].append(
                        (bid, kind.upper(), stored))

        # dangling my_works citations / published_as
        for work in self.my_works.values():
            for c in work.cites:
                if c not in self.records:
                    report["dangling_citations"].append((work.name, c))
            if work.published_as and work.published_as not in self.records:
                report["dangling_published_as"].append(
                    (work.name, work.published_as))

        # duplicate DOIs
        by_doi: dict[str, list[str]] = {}
        for bid, rec in self.records.items():
            if rec.doi:
                by_doi.setdefault(rec.doi.lower(), []).append(bid)
        for doi, ids in by_doi.items():
            if len(ids) > 1:
                report["duplicate_dois"].append((doi, sorted(ids)))

        # outlet nickname vs. bibliotheca_id suffix conventions.
        # The suffix is the text after the last underscore in the id (the
        # convention is AuthorSurnamesYear_suffix). Only records that belong
        # to an outlet (journal article / proceedings) are checked, since only
        # outlets carry nicknames.
        for bid, rec in self.records.items():
            outlet = self.outlet_for_record(rec)
            if outlet is None:
                continue
            suffix = _id_suffix(bid)
            nickname = (outlet.nickname or "").strip()
            if nickname:
                if not suffix:
                    # (1) nickname set, but the id has no suffix at all
                    report["nick_set_no_suffix"].append((bid, nickname))
                elif suffix != nickname:
                    # (2)/(4) nickname set and id has a suffix, but they differ
                    report["nick_set_suffix_diff"].append(
                        (bid, suffix, nickname))
            else:
                if suffix:
                    # (3) id has a suffix, but no outlet nickname is set
                    report["suffix_no_nick"].append((bid, suffix))

        return report
