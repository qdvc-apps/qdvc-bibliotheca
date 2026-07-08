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
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import apa

INDEX_FILENAME = ".qdvc-index.json"
INDEX_VERSION = 2

_BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{", re.IGNORECASE)
_FIELD_RE = re.compile(r"(\w+)\s*=\s*", re.IGNORECASE)


# ---------------------------------------------------------------------------
# BibTeX parsing (uses bibtexparser if present, else a small fallback)
# ---------------------------------------------------------------------------

def _parse_bib_fallback(text: str) -> dict:
    """Minimal single-entry BibTeX parser used when bibtexparser is absent.

    Handles brace- and quote-delimited values and nested braces. Good enough
    for one-entry .bib files, which is the workspace convention.
    """
    m = _BIB_ENTRY_RE.search(text)
    if not m:
        return {}
    entry = {"ENTRYTYPE": m.group(1).lower()}
    i = m.end()
    # citation key up to first comma
    key_end = text.find(",", i)
    if key_end == -1:
        return entry
    entry["ID"] = text[i:key_end].strip()
    i = key_end + 1
    n = len(text)
    while i < n:
        fm = _FIELD_RE.search(text, i)
        if not fm:
            break
        fname = fm.group(1).lower()
        j = fm.end()
        while j < n and text[j] in " \t\r\n":
            j += 1
        if j >= n:
            break
        ch = text[j]
        if ch == "{":
            depth = 0
            start = j + 1
            k = j
            while k < n:
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            value = text[start:k]
            i = k + 1
        elif ch == '"':
            start = j + 1
            k = start
            while k < n and text[k] != '"':
                k += 1
            value = text[start:k]
            i = k + 1
        else:  # bare value (number, etc.)
            k = j
            while k < n and text[k] not in ",}\n":
                k += 1
            value = text[j:k].strip()
            i = k
        entry[fname] = value.strip()
        # advance past a trailing comma
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i < n and text[i] == ",":
            i += 1
        elif i < n and text[i] == "}":
            break
    return entry


def parse_bibtex(path: Path) -> dict:
    """Parse a single-entry .bib file into a normalised dict."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    try:
        import bibtexparser  # type: ignore
        from bibtexparser.bparser import BibTexParser  # type: ignore
        parser = BibTexParser(common_strings=True)
        parser.ignore_nonstandard_types = False
        db = bibtexparser.loads(text, parser=parser)
        if db.entries:
            e = dict(db.entries[0])
            # normalise key casing used elsewhere
            e.setdefault("ENTRYTYPE", e.get("entrytype", "misc"))
            return e
    except Exception:
        pass
    return _parse_bib_fallback(text)


# ---------------------------------------------------------------------------
# Markdown + YAML frontmatter
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def parse_markdown(path: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_markdown)."""
    if not path.exists():
        return {}, ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, ""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, m.group(2)


def write_markdown(path: Path, frontmatter: dict, body: str) -> None:
    """Write frontmatter + body atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = yaml.safe_dump(frontmatter or {}, sort_keys=True,
                             allow_unicode=True).strip()
    content = f"---\n{fm_text}\n---\n{body}"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

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

    def to_yaml_dict(self) -> dict:
        data: dict = {"name": self.name, "cites": list(self.cites)}
        if self.published_as:
            data["published_as"] = self.published_as
        return data

    def save(self) -> None:
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(self.to_yaml_dict(), sort_keys=True,
                              allow_unicode=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.records: dict[str, Record] = {}
        self.my_works: dict[str, MyWork] = {}
        self._doi_index: dict[str, str] = {}  # doi(lower) -> bibliotheca_id

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
            return
        self._scan()
        self._load_my_works()
        self._build_doi_index()
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
            rec = Record(
                bibliotheca_id=bid,
                bib_path=str(bib_file),
                md_path=str(md) if md.exists() else str(md),
                entrytype=(e.get("ENTRYTYPE") or "misc").lower(),
                type_label=apa.type_label(e.get("ENTRYTYPE") or "misc"),
                author=apa._clean(e.get("author") or e.get("editor")),
                year=apa._clean(e.get("year")),
                title=apa._clean(e.get("title")),
                journal=apa._clean(e.get("journal") or e.get("journaltitle")
                                   or e.get("booktitle")),
                doi=_normalise_doi(e.get("doi")),
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
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            cites = data.get("cites") or data.get("citations") or []
            if not isinstance(cites, list):
                cites = []
            name = data.get("name") or data.get("title") or f.stem
            self.my_works[f.stem] = MyWork(
                name=str(name),
                path=str(f),
                cites=[str(c) for c in cites],
                published_as=data.get("published_as")
                or data.get("published_version"),
            )

    def _build_doi_index(self) -> None:
        self._doi_index.clear()
        for bid, rec in self.records.items():
            if rec.doi:
                self._doi_index[rec.doi.lower()] = bid

    # --- queries ---------------------------------------------------------
    def all_records(self) -> list[Record]:
        return sorted(self.records.values(),
                      key=lambda r: r.bibliotheca_id.lower())

    def records_by_type(self, label: str) -> list[Record]:
        return [r for r in self.all_records() if r.type_label == label]

    def records_for_work(self, work_key: str) -> list[Record]:
        work = self.my_works.get(work_key)
        if not work:
            return []
        return [self.records[c] for c in work.cites if c in self.records]

    def lookup_doi(self, doi: str) -> str | None:
        return self._doi_index.get(_normalise_doi(doi).lower())

    def get(self, bibliotheca_id: str) -> Record | None:
        return self.records.get(bibliotheca_id)

    # --- mutations -------------------------------------------------------
    def import_bib_file(self, source: str | Path) -> list[str]:
        """Import a .bib file that may contain one or more entries.

        Each entry is filed under bibtex/<shard>/<bibliotheca_id>.bib using
        its citation key as the bibliotheca_id. Returns the list of imported
        ids. Existing ids are skipped (not overwritten).
        """
        source = Path(source)
        text = source.read_text(encoding="utf-8", errors="replace")
        entries = _split_bib_entries(text)
        imported: list[str] = []
        for raw_entry, key in entries:
            if not key:
                continue
            bid = _sanitise_id(key)
            dest = self.bib_path_for(bid)
            if dest.exists() or bid in self.records:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(raw_entry.strip() + "\n", encoding="utf-8")
            e = parse_bibtex(dest)
            rec = Record(
                bibliotheca_id=bid,
                bib_path=str(dest),
                md_path=str(self.md_path_for(bid)),
                entrytype=(e.get("ENTRYTYPE") or "misc").lower(),
                type_label=apa.type_label(e.get("ENTRYTYPE") or "misc"),
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
        if imported:
            self._build_doi_index()
            self._save_index()
        return imported

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

    # --- validation ------------------------------------------------------
    def validate(self) -> dict:
        """Return a report of workspace integrity problems."""
        report = {
            "orphan_markdown": [],       # .md without matching .bib
            "missing_fulltext": [],      # (id, kind, path)
            "dangling_citations": [],    # (work_name, id)
            "dangling_published_as": [],  # (work_name, id)
            "duplicate_dois": [],        # (doi, [ids])
        }

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
                p = fm.get(kind)
                if p and not Path(p).exists():
                    report["missing_fulltext"].append((bid, kind.upper(), p))

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

        return report


def _normalise_doi(doi: str | None) -> str:
    if not doi:
        return ""
    doi = doi.strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi


_ID_ALLOWED_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitise_id(text: str) -> str:
    """Turn an arbitrary string into a safe file-stem / bibliotheca_id."""
    text = (text or "").strip()
    # collapse whitespace to underscores, strip disallowed characters
    text = re.sub(r"\s+", "_", text)
    text = _ID_ALLOWED_RE.sub("", text)
    return text.strip("_-")


def _split_bib_entries(text: str) -> list[tuple[str, str]]:
    """Split a multi-entry .bib string into (entry_text, citation_key) pairs.

    Uses brace balancing so entry bodies containing nested braces are kept
    intact. Non-entry content (comments, @string, @preamble) is skipped.
    """
    entries: list[tuple[str, str]] = []
    n = len(text)
    i = 0
    while i < n:
        at = text.find("@", i)
        if at == -1:
            break
        m = _BIB_ENTRY_RE.match(text, at)
        if not m:
            i = at + 1
            continue
        etype = m.group(1).lower()
        brace_open = m.end() - 1  # position of '{'
        # balance braces to find the end of this entry
        depth = 0
        j = brace_open
        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        entry_text = text[at:j + 1]
        i = j + 1
        if etype in ("string", "preamble", "comment"):
            continue
        # citation key: between '{' and first comma
        comma = entry_text.find(",")
        brace = entry_text.find("{")
        if comma == -1 or brace == -1:
            continue
        key = entry_text[brace + 1:comma].strip()
        entries.append((entry_text, key))
    return entries
