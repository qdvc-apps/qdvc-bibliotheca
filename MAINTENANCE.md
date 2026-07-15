# QDVC Bibliotheca — Maintenance & Architecture Manual

This document is for a developer (human or AI) who needs to understand, extend,
or debug the codebase. It describes the design philosophy, module layout, data
formats, control flow, and the non-obvious decisions worth knowing before you
touch anything.

---

## 1. Design philosophy

**Files are the database.** There is no SQLite, no ORM. A "workspace" is a
directory of plain-text files. The application is a viewer/editor over those
files plus a fast in-memory index. Consequences:

- Everything is portable, diffable, and Git/Syncthing friendly.
- The authoritative reference data (BibTeX) is kept strictly separate from the
  user's own data (Markdown notes, full-text links, project citations). BibTeX
  represents the work "upstream" from the publisher; the Markdown file
  represents the user's relationship with it.
- Any external change to the files is recoverable by rescanning.

**Separation of concerns.** The top-level `qdvc/` package is **pure**,
toolkit-independent logic with no GTK imports (`workspace.py`, `models.py`,
`bibtex.py`, `markdown_io.py`, `naming.py`, `apa.py`, `acis.py`, `csl.py`,
`catalogue_sort.py`, `config.py`, `platform_utils.py`). **All GTK3 code lives
in the `qdvc/gtk3/` sub-package**, where every module is prefixed `gtk3_`. This
split is what lets the model be unit-tested without a display (see §9), and it
keeps the pure layer ready for a second front-end: a future GTK4 port can live
in a sibling `qdvc/gtk4/` package (mirroring the `gtk4_` prefix convention used
in the related QDVC apps) without touching the pure modules.

**Lazy where it counts.** Opening a large workspace must be fast, so a cached
index holds only lightweight display fields. Full BibTeX parsing and notes
reading happen per-record, on demand.

---

## 2. Runtime requirements

- Python 3.10+ (uses `str | None` union syntax and `list[...]` generics).
- PyGObject, and **one** of the two UI toolkits:
  - GTK 3 (`gi.repository.Gtk` version "3.0") for the default front-end, or
  - GTK 4 + libadwaita (`gi.repository.Gtk` "4.0" and `gi.repository.Adw` "1";
    Debian/Ubuntu package `gir1.2-adw-1`) for the GTK4 front-end.
- PyYAML (hard dependency).
- `bibtexparser` (optional; a built-in fallback parser is used when absent).
- `citeproc-py` (optional; enables the CSL citation-style renderer in `csl.py`.
  Absent, the citation-style dropdown offers the built-in APA 7 and ACIS
  renderers only). `csl.py` escapes `&`/`<`/`>` in field values before handing
  them to citeproc (whose HTML formatter does not escape), so the markup it
  returns is valid Pango markup and the plain path round-trips the symbols.

Both front-ends exist in the tree and share the same pure core. The toolkit is
chosen at launch (see §3.3): the `ui_backend` config key (default `gtk3`), or a
`--gtk3` / `--gtk4` CLI flag. The GTK3 UI intentionally uses some
deprecated-in-GTK4 idioms (see §8); the GTK4 UI follows the GNOME HIG. For an
element-by-element comparison of the two view layers, see
[MAINTENANCE_GTK3_GTK4.md](MAINTENANCE_GTK3_GTK4.md).

---

## 3. Directory & file layout

### 3.1 Source tree

```
qdvc-bibliotheca.py        Launcher / backend dispatcher (see §3.3): picks
                           gtk3 or gtk4 before importing any GTK, then calls
                           the chosen front-end's main().
qdvc/                       PURE package — no GTK imports anywhere here.
    __init__.py            Version + app constants (APP_ID, APP_NAME, __version__).
    config.py              Config: load/save YAML at the XDG config location
                           (incl. the validated ui_backend accessor).
    workspace.py           MODEL aggregate. The Workspace class + INDEX_*.
                           Re-exports the names below for backward compat.
    models.py              Record, MyWork, Author, Outlet dataclasses.
    bibtex.py              BibTeX parsing (+ fallback) and multi-entry split.
    markdown_io.py         Markdown / YAML-frontmatter read & write.
    naming.py              id / slug / nickname / DOI helpers.
    apa.py                 BibTeX-entry -> APA 7 formatter (markup + plain).
    acis.py                BibTeX-entry -> ACIS formatter (reference markup +
                           plain, plus in-text citation + disambiguation).
    csl.py                 Optional CSL renderer (via citeproc-py) + fallback.
    catalogue_sort.py      Pure sort-keys, count/label + J-Flag ordering helpers,
                           and the APA_STYLE_ID sentinel.
    ui_prefs.py            Pure, toolkit-independent helpers shared by BOTH
                           front-ends: J-Flag presets/priority, sort-spec
                           load/save + describe, citation-style get/store,
                           validation-report formatting, the shortcuts table.
    platform_utils.py      Launch system apps (viewer, editor, file manager).
    gtk3/                  GTK3 front-end sub-package — all modules gtk3_*.
        __init__.py        Package marker + porting note.
        gtk3_app.py        Gtk.Application subclass; sets prgname + icon.
        gtk3_main_window.py    MainWindow (menubar/toolbar/notebook) + ImportDialog.
        gtk3_catalogue_tab.py  Three-pane Catalogue tab (the biggest UI module).
        gtk3_authors_tab.py    Authors tab (list + star toggles).
        gtk3_outlets_tab.py    Outlets tab (list + star + nickname + J-Flags).
        gtk3_doi_tab.py        DOI lookup tab.
        gtk3_preferences.py    Preferences dialog (incl. the backend selector).
        gtk3_myworks_editor.py Dialog to edit a "my work" (cites + published_as).
        gtk3_sort_dialog.py    Dialog to build a multi-key sort specification.
        gtk3_allocate_dialog.py Dialog to allocate record(s) to works.
        gtk3_md_highlight.py   Regex Markdown highlighter for the notes buffer.
        gtk3_widgets.py    Shared GTK3 helpers: icon menu item, Pango style
                           enums, rich-text clipboard setter.
    gtk4/                 GTK4 / libadwaita front-end sub-package — all gtk4_*.
        __init__.py        Package doc.
        gtk4_app.py        Adw.Application; registers accelerators (win.* scope).
        gtk4_window.py     BibliothecaWindow (Adw.ViewStack + header bar +
                           primary menu); shares helpers via ui_prefs.
        gtk4_actions.py    ActionsMixin: installs the win.* Gio.SimpleActions.
        gtk4_headerbar.py  HeaderBarMixin: header bars, primary menu, switcher.
        gtk4_common.py     Row GObjects (RecordItem, NavItem, TextItem) + the
                           shared NODE_* constants; re-exports APA_STYLE_ID.
        gtk4_dialogs.py    Async dialog helpers (message/confirm/prompt/choose/
                           text-report) — the "no run()" layer.
        gtk4_catalogue_tab.py  Adw.OverlaySplitView + Gtk.ColumnView Catalogue.
        gtk4_authors_tab.py    Authors ColumnView.
        gtk4_outlets_tab.py    Outlets ColumnView (+ nickname / J-Flags dialogs).
        gtk4_doi_tab.py        DOI lookup view.
        gtk4_widgets.py    Shared ColumnView column factories (text/icon/star).
        gtk4_import_dialog.py  Import BibTeX (Adw.Window; on_import callback).
        gtk4_sort_dialog.py    Multi-key sort (on_apply / on_clear callbacks).
        gtk4_allocate_dialog.py Allocate to works (on_done callback).
        gtk4_myworks_editor.py Two-list work editor (on_apply callback).
        gtk4_preferences.py    Adw.PreferencesWindow (live-apply + selector).
        gtk4_shortcuts.py      Shortcuts window (from ui_prefs.SHORTCUTS).
        gtk4_md_highlight.py   Markdown highlighter (GTK4 copy of the gtk3 one).
```

**Pure vs. front-end rule of thumb.** If a module imports `gi`, it belongs in a
front-end sub-package (`qdvc/gtk3/` named `gtk3_*`, or `qdvc/gtk4/` named
`gtk4_*`). If it doesn't, it stays in the top-level `qdvc/` package. Intra-package
imports follow from this: front-end modules reach pure modules with `from ..`
(e.g. `from ..workspace import Workspace`, `from .. import ui_prefs`) and reach
their siblings with `from .gtk3_x` / `from .gtk4_x`. The two front-ends never
import each other.

**Backward-compatible re-exports.** `workspace.py` was split into `models.py`,
`bibtex.py`, `markdown_io.py`, and `naming.py`, but it still imports and
re-exports every moved name — including the old underscore-prefixed private
aliases (`_sanitise_id`, `_id_suffix`, `_sanitise_stem`, `_normalise_doi`,
`_split_bib_entries`, `_parse_bib_fallback`) — so existing imports such as
`from qdvc.workspace import Workspace, slugify_outlet, Record` keep working
unchanged.

### 3.3 Backend selection (dispatcher)

`qdvc-bibliotheca.py` chooses the UI toolkit **before importing any GTK**, so
only the selected front-end is loaded. Priority: a `--gtk3` / `--gtk4` CLI flag;
then `Config.ui_backend`; then the default `gtk3`. It preserves `argv[0]` for
GApplication and, if the GTK4 import fails (e.g. libadwaita absent), prints a
note to stderr and falls back to GTK3. The selector is written from either UI's
Preferences and takes effect on the next launch. `Config.ui_backend` validates
and lower-cases the value, falling back to `gtk3` for anything unrecognised.

### 3.2 Workspace on disk

```
(workspace root)/
    bibtex/<A..Z>/<bibliotheca_id>.bib     One entry per file. Authoritative.
    markdown/<A..Z>/<bibliotheca_id>.md    YAML frontmatter + free notes.
    my_works/*.yml                         User projects (arbitrary stems).
    authors/<SURNAME_GivenNames>.yml       Derived author records + star state.
    outlets/<nickname-or-slug>.yml         Derived outlet records (journals +
                                           proceedings) + star, nickname,
                                           and J-Flags.
    csl/*.csl                              Optional custom CSL citation styles.
    .qdvc-index.json                       Cache (safe to delete; regenerated).
```

The `<A..Z>` shard is the uppercased first letter of the `bibliotheca_id`
(non-alphabetic falls back to `_`). See `Workspace._shard`.

**`bibliotheca_id`** is the file stem and the app's primary key. Convention:
`AuthorSurnamesYear_suffix` (e.g. `SmithJones2025_MISQ`). It is *independent*
of the BibTeX citation key inside the `.bib` file — they may differ, and
`validate()` reports mismatches, but the app always keys off the filename.

---

## 4. Data formats

### 4.1 BibTeX (`bibtex/.../*.bib`)

One entry per file, by convention. Parsing is in `workspace.parse_bibtex`:

1. If `bibtexparser` is importable, use it.
2. Otherwise fall back to `_parse_bib_fallback`, a hand-rolled single-entry
   parser that balances braces and handles quote- or brace-delimited values.

Parsed entries are normalised to a dict with an `ENTRYTYPE` key (lowercased)
and lowercase field names, plus `ID` for the citation key. Multi-entry text
(used by import) is split by `_split_bib_entries`, which brace-balances each
`@type{...}` block and skips `@string`/`@preamble`/`@comment`.

### 4.2 Markdown (`markdown/.../*.md`)

```
---
pdf: S/SmithJones2025.pdf     # relative to the full-text library path
epub: S/SmithJones2025.epub   # (absolute path if outside that folder)
my_works:
  - project1
---
Free-form Markdown notes.
```

`parse_markdown` returns `(frontmatter_dict, body_str)`. `write_markdown`
writes atomically (temp file + `os.replace`) and always re-emits the
frontmatter, so callers must pass the full frontmatter they want preserved.

**Critical ordering rule:** editing notes and editing frontmatter both rewrite
the same file. Before any frontmatter write (e.g. setting a PDF path), the
Catalogue flushes pending notes first (`_flush_notes`) so the two writes don't
clobber each other. Preserve this ordering if you add frontmatter writers.

### 4.3 my_works YAML

```
name: My Dissertation
cites:
  - Jones2009_JAIS
  - SmithJones2025_MISQ
published_as: SmithJones2025_MISQ   # optional
```

Loader (`_load_my_works`) is tolerant on read: it accepts `cites` or
`citations`, `name` or `title`, and `published_as` or `published_version`.

**Canonical form (enforced on write and on load):** `name` first, then `cites`,
then optional `published_as`. `cites` is de-duplicated and sorted
case-insensitively by Bibliotheca ID. `MyWork.to_yaml_dict` builds the dict in
that key order and `MyWork.save` dumps with `sort_keys=False`
(`MyWork.sorted_cites` does the de-dup/sort, and `save` also rewrites the
in-memory `cites` to match). On load, `_load_my_works` compares each file's
raw text against its canonical serialisation and rewrites the file in place if
they differ (`_canonicalise_work_file`), so any hand-edited or legacy file is
normalised the first time the app touches it. `records_for_work` returns
records in `sorted_cites()` order. The **Edit Work** dialog keeps its cited
list alphabetical and inserts newly-added references at their sorted slot
(`_insert_cited_sorted`).

### 4.4 authors YAML

```
id: ZUBOFF_Shoshana
surname: Zuboff
given_names: Shoshana
starred: true
```

Derived automatically (see §6). Only `starred` is user-editable state; the rest
is a stable mapping regenerated from BibTeX.

### 4.4b outlets YAML

```
name: Journal of Bibliotheca
nickname: JBIB
starred: true
jflags:
  - A*
  - FT50
```

Derived automatically from the outlet field (`journal`/`booktitle`) of
**journal-article and proceedings** records only (plain book-chapter
booktitles never appear here — see §6). `name` is the verbatim outlet title and
is regenerated from BibTeX; `nickname`, `starred`, and `jflags` are
user-editable state preserved across rescans. `jflags` is de-duplicated and
stored **alphabetically** (canonical form via `Outlet.sorted_jflags`); the
display order in the Catalogue's J-Flags column is by configured priority, not
alphabetical. The **file stem** is the nickname when one is set (`JBIB.yml`),
else the slug of the full name (`journal-of-bibliotheca.yml`);
`Workspace.outlet_path_for` decides. The in-memory key (`outlet_id`) is always
the slug, so state survives a nickname change. `Outlet.to_yaml_dict` builds the
dict as name, nickname (if any), starred, jflags, and `save` dumps with
`sort_keys=False`. A nickname may contain **only ASCII letters** (`A-Za-z`) and
must be unique (case-insensitively) across outlets; `set_outlet_nickname` raises
`ValueError` on an invalid character or a collision, so YAML filenames never
clash.

`{"version": INDEX_VERSION, "records": [ {…}, … ]}`. Each record stores only
display/index fields: `bibliotheca_id, bib_path, md_path, entrytype,
type_label, author, year, title, journal, doi, has_pdf, has_epub`.

`INDEX_VERSION` is currently **4**. **Bump it whenever the per-record schema
changes**, otherwise stale caches load with missing fields. `_load_index`
returns `False` (forcing a rescan) if the version mismatches or if any
referenced `.bib` path no longer exists.

### 4.6 Application config

`config.py` stores YAML at `$XDG_CONFIG_HOME/qdvc-bibliotheca/config.yml`
(falling back to `~/.config`). `DEFAULTS` holds `last_workspace`,
`recent_workspaces`, and `window` size. Additional keys set via
`Config.set`/`get`: `notes_font`, `file_manager`, `fulltext_library_path`,
`reopen_last`, `autosave_notes`, `toolbar_style`, `jflags`, `csl_styles`. The
`jflags` key is a list of `{flag, priority}` dicts — the J-Flag presets and
their priority numbers (lower = shown first in the Catalogue's J-Flags column);
read via `MainWindow._jflag_presets`/`_jflag_priority_map`. The `csl_styles`
key is a `{workspace_root_path: style_id}` map persisting the chosen citation
style per workspace (`style_id` is the `APA_STYLE_ID` or `ACIS_STYLE_ID`
sentinel, or a CSL filename); read via `MainWindow._saved_citation_style` and
written by
`_on_citation_style_chosen`. When you add a preference, add it in
`gtk3/gtk3_preferences.py` (widget + `apply()`) and read it where used; no schema
migration is needed because `Config.get` takes a default.

---

## 5. The model (pure, no GTK)

The model is spread across small pure modules, all re-exported from
`workspace.py` for backward compatibility:

- **`models.py`** — the four dataclasses (`Record`, `MyWork`, `Author`,
  `Outlet`); §5.1–5.3b.
- **`bibtex.py`** — `parse_bibtex`, `parse_bib_fallback`, `split_bib_entries`.
- **`markdown_io.py`** — `parse_markdown`, `write_markdown`.
- **`naming.py`** — `normalise_doi`, `sanitise_id`, `id_suffix`,
  `sanitise_stem`, `slugify_outlet`, `make_author_id` (§5.8). Underscore-named
  aliases (`_sanitise_id` etc.) are re-exported from `workspace.py`.
- **`workspace.py`** — the `Workspace` aggregate itself plus `INDEX_FILENAME`
  / `INDEX_VERSION`.

### 5.1 `Record`

One catalogued work. Index fields are eager; `bib()` lazily parses the `.bib`
and caches it in `_bib`. Helpers: `apa_markup()`, `apa_plain()`,
`acis_markup(disambiguator)`, `acis_plain(disambiguator)`,
`acis_in_text_markup/plain(disambiguator, narrative)`, `read_notes()`, and the
`outlet` property (journal for journal articles, book/proceedings title for
chapters and proceedings, em dash otherwise — drives the Outlet column). The
ACIS disambiguator letter is supplied by the caller (the workspace computes it
— see §7.1), keeping `Record` stateless.

### 5.2 `MyWork`

`name, path, cites[], published_as`. `save()` writes atomically.

### 5.3 `Author`

`author_id, surname, given_names, starred, path, record_ids[]`. `record_ids`
is populated at load, not persisted. `display_name` = `"Surname, Given"`.

### 5.3b `Outlet`

`outlet_id, name, nickname, starred, jflags[], path, record_ids[]`.
`outlet_id` is the slug of the full `name` (stable in-memory key; does **not**
change when a nickname is set). `record_ids` is populated at load, not
persisted. `display_name` = the full `name`. `sorted_jflags()` gives the
de-duplicated, alphabetical (canonical, on-disk) J-Flag order; the UI reorders
by priority for display. `save()` writes atomically to `path` (the
nickname-or-slug file — see §4.4b). An outlet represents a journal *or* a
proceedings (see `Workspace.OUTLET_TYPES`).

### 5.4 `Workspace` — load pipeline

```
load(force_rescan=False):
    if not force_rescan and _load_index():   # fast path from cache
        _load_my_works(); _build_doi_index()
        _derive_authors(); _derive_outlets(); return
    _scan()                                    # slow path: read every .bib
    _load_my_works(); _build_doi_index()
    _derive_authors(); _derive_outlets(); _save_index()
```

- `_scan` walks `bibtex/**/*.bib`, parses each, checks the paired `.md` for
  `pdf`/`epub` frontmatter to set `has_pdf`/`has_epub`.
- `_build_doi_index` maps normalised DOI -> bibliotheca_id (for the DOI tab).
- `_derive_authors` (see §6).
- `_derive_outlets` (see §6). Outlets, like authors, are derived on every
  load from records + `outlets/*.yml`; they are **not** cached in the index,
  so `INDEX_VERSION` is unaffected by these features.

### 5.5 Query API (used by the UI)

`all_records`, `records_by_type(label)`, `records_by_fulltext(which)` (which ∈
{"pdf","epub","none"}), `records_by_doi_status(has_doi)`,
`records_for_work(key)`, `records_for_author(author_id)`, `all_authors`,
`starred_authors`, `all_outlets`, `starred_outlets`,
`records_for_outlet(outlet_id)`, `outlet_for_record(rec)` (None when the
record is not a journal article / proceedings), `lookup_doi(doi)`,
`get(bibliotheca_id)`, `list_csl_files()` (CSL filenames in `csl/`, sorted),
`csl_path(filename)`, `acis_disambiguator(record)` (the ACIS year letter for a
record — see §7.1).

### 5.6 Mutation API

- `import_bib_text(text)` / `import_bib_file(path)` — split, file each new
  entry under its shard using the citation key as the `bibliotheca_id`, skip
  existing ids, and **refuse** any entry whose DOI already appears in the
  catalogue (guarding against duplicates), then rebuild DOI index + authors +
  outlets + save index. Returns `(imported_ids, skipped_dois)`, where
  `skipped_dois` is a list of `(citation_key, doi, existing_id)` tuples;
  `MainWindow._on_import` surfaces those in a dialog.
- `rename_record(old, new)` — moves both paired files, updates in-memory
  record, rewrites every `my_works` reference (`cites` and `published_as`),
  rebuilds authors + index. Raises `ValueError` on empty/invalid/collision.
- `create_my_work(name)` — sanitises name to a file stem, de-duplicates, writes
  an empty work.
- `allocate_to_work(work_key, bibliotheca_ids)` — adds one or more records to a
  work's `cites`, skipping ids already present; saves (canonicalising) only if
  something was added; returns the count added. Used by the record "Allocate to
  My Works…" flow and the allocate-after-import option.
- `set_outlet_starred(outlet_id, bool)` / `set_outlet_jflags(outlet_id,
  flags)` — flip the flag / replace the J-Flag list and re-save that one
  outlet file. `set_outlet_nickname(outlet_id, nickname)` sets or clears the
  nickname, writing the new (nickname-or-slug) file first and deleting the stale
  one.
- `set_fulltext_path(id, kind, abs_path|None, storage_root)` — writes the
  `pdf`/`epub` frontmatter **relative to `storage_root`** when the file is
  inside it, else absolute; updates `has_pdf`/`has_epub`; re-saves index.
- `resolve_fulltext_path(id, kind, storage_root)` — inverse; returns an
  absolute path for opening.

### 5.7 `validate(storage_root)`

Returns a dict of problem lists: `orphan_markdown`, `key_mismatch`,
`missing_fulltext`, `dangling_citations`, `dangling_published_as`,
`duplicate_dois`, and the outlet-nickname/suffix checks `nick_set_no_suffix`
(nickname set but the id has no `_suffix`), `nick_set_suffix_diff` (id suffix
≠ nickname), and `suffix_no_nick` (id has a suffix but the outlet has no
nickname) — each computed only for records that belong to an outlet, using
`_id_suffix(id)` (text after the last underscore). Relative full-text paths are
resolved against `storage_root` before the existence check. When you add a
check, add its key here **and** a `section(...)` line in
`MainWindow._format_report`.

### 5.8 Module helpers (`naming.py`)

These live in `naming.py` and are re-exported from `workspace.py` (both under
their public names and the legacy underscore aliases). `make_author_id(surname,
given)` → `SURNAME_GivenNames` (surname uppercased, given-names title-cased,
non-alphanumerics stripped). `sanitise_id` (`_sanitise_id`) for safe file
stems. `id_suffix(id)` (`_id_suffix`) returns the text after the last
underscore (the `AuthorSurnamesYear_suffix` convention). `normalise_doi`
(`_normalise_doi`) strips a `doi.org/` prefix. `slugify_outlet(name)` →
lowercase hyphen-joined slug (the stable `outlet_id`, e.g. "Journal of
Bibliotheca" → `journal-of-bibliotheca`). `sanitise_stem` (`_sanitise_stem`)
makes a safe file stem **preserving case** (used for nickname filenames like
`JBIB.yml`).

---

## 6. Author derivation (`_derive_authors`)

This is the subtle part. On every load:

1. Load any existing `authors/*.yml` into a `persisted` map (this preserves the
   user's `starred` flags and the long-term id→name mapping).
2. Walk all records; for each author token (via `apa.author_tokens`) compute
   `make_author_id`. Reuse the persisted `Author` if present, else create a new
   one.
3. Build `_author_records: author_id -> [bibliotheca_id]` (guarding against an
   author appearing twice in the same record).
4. Persist any author that has no file yet.
5. Populate each `Author.record_ids`.

So stars survive rescans, and new authors get a file the first time they're
seen. `set_author_starred` flips the flag and re-saves that one file.

### 6.1 Outlet derivation (`_derive_outlets`)

Mirrors author derivation, with two twists:

1. Load any existing `outlets/*.yml` into a `persisted` map keyed by the slug
   of each file's stored `name` (so the key is stable regardless of the file
   stem, which follows the nickname). This preserves `starred`, `nickname`, and
   `jflags`.
2. Walk records but **only** those whose `type_label` is in
   `Workspace.OUTLET_TYPES` (`"Journal article"`, `"Proceedings"`); compute the
   `outlet_id` with `slugify_outlet(rec.journal)`. Plain book-chapter
   booktitles never create an outlet. Reuse the persisted `Outlet` if present
   (refreshing its `name` from the current BibTeX), else create a new one.
3. Build `_outlet_records: outlet_id -> [bibliotheca_id]`.
4. Persist any outlet that has no file yet (at its nickname-or-slug path).
5. Populate each `Outlet.record_ids`.

---

## 7. APA formatting (`apa.py`)

`format_apa_markup(entry)` returns **Pango markup** (`<i>…</i>` for titles/
journals, entities escaped). `format_apa_plain(entry)` strips it to text.

- Type-specific renderers are registered in `_RENDERERS` keyed by entry type
  (article, inproceedings, book, inbook/incollection, online/misc, …), with
  `_render_online` as the fallback.
- `TYPE_LABELS` / `type_label()` map BibTeX entry types to the human labels the
  UI filters on ("Journal article", "Proceedings", "Book chapter", "Book",
  "Webpage", "Other"). **These strings are load-bearing**: the sidebar "By
  type" filter, `records_by_type`, and `Record.outlet` all compare against
  them. Change them in one place only. `type_label(entrytype, booktitle=None)`
  takes an optional booktitle so an `incollection` whose `booktitle` begins
  with "Proceedings of" is classed as "Proceedings" rather than "Book chapter";
  callers in `workspace._scan`/`import_bib_text` pass `e.get("booktitle")`.
- Author name handling: `split_name` handles "Surname, Given" and
  "Given Surname"; `author_tokens` returns `(surname, given)` pairs;
  `format_author_list` builds the APA `A, B., & C.` string (≤20 authors, then
  ellipsis rule).

The rich-vs-plain design exists to support the two Copy buttons and the
HTML-clipboard path in the Catalogue (see §8.2).

### 7.1 ACIS formatting (`acis.py`)

A second built-in style, parallel to `apa.py`, selected via the `ACIS_STYLE_ID`
sentinel (`"__acis__"`, defined in `catalogue_sort.py` beside `APA_STYLE_ID`).
It differs from APA in visible ways: the year follows the authors with no
parentheses and a trailing period; article/chapter titles are curly-quoted with
the following comma *inside* the closing quote; every author stays
surname-first and the final author is joined with ", and"; journal
volume/issue render as `(vol:iss)`; a DOI renders as `(doi:…)` in place of a
page range; and `@online` uses an `(url, accessed <D Month YYYY>)` tail.

- `format_acis_markup(entry, disambiguator="")` / `format_acis_plain(...)`
  return the reference-list form (Pango markup / plain). Renderers are keyed by
  entry type in `_RENDERERS`, with the same "Proceedings of" `incollection`
  special-case as APA (`_pick_renderer`).
- `in_text_markup(entry, disambiguator="", narrative=False)` /
  `in_text_plain(...)` return the in-text citation: parenthetical
  `(Smith and Jones 2026)` / `(Thompson et al. 2026)` (three+ authors collapse
  to "et al."), or narrative `Smith and Jones (2026)` when `narrative=True`.
- `escape()` is wrapped to default `quote=False`, so apostrophes/quotes stay
  literal in markup content and survive the `markup_to_plain` round-trip.

**Disambiguation.** When two records share an author list and year, ACIS
appends a letter (`2025a`, `2025b`). `acis.disambiguator_map(records)` groups by
`(surnames, year)` using only the cached `Record` fields (no BibTeX parse) and
assigns letters in title order. `Workspace.acis_disambiguator(record)` caches
that map (keyed by record count, so it rebuilds after import/rescan) and returns
the letter for one record; the Catalogue passes it into the `Record.acis_*`
helpers so the reference and in-text forms stay consistent.

---

## 8. UI layer

### 8.1 Application & window bootstrap

`gtk3/gtk3_app.py`: `Gtk.Application` (id `org.qdvc.Bibliotheca`, `HANDLES_OPEN`).
`GLib.set_prgname("qdvc-bibliotheca")` runs at import so the X11 `WM_CLASS`
matches the `.desktop` `StartupWMClass` (needed for the MATE panel icon).
`do_startup` sets the default icon name; `do_activate` builds the single
`MainWindow`; `do_open` routes a folder argument to `_open_path`.

`gtk3/gtk3_main_window.py` builds a `Gtk.Box` containing menubar, toolbar, a
`Gtk.Notebook` (Catalogue / Authors / Outlets / DOI Lookup, in that order —
index 0/1/2/3, which the Alt+1/2/3/4 accelerators and
`_on_goto_record`/`_on_show_author_works`/`_on_show_outlet_works` depend on),
and a status bar.

`_menu_item(label, icon)` builds menu items as a `Box(Image+Label)` inside a
plain `MenuItem` — deliberately **not** `Gtk.ImageMenuItem`, which is removed in
GTK4 and warns in GTK3.

Actions/sensitivity: `_update_actions_sensitivity` centralises enable/disable.
Workspace-scoped items (Close, Import, Refresh, Validate, Sort, and their
toolbar peers) track whether a workspace is open. **Open PDF** and **Open
EPUB** (in the View menu and toolbar) are enabled only when the Catalogue tab
is active *and* a record is selected *and* that record has the corresponding
full-text linked — so it's recomputed on the notebook `switch-page` signal
(`_on_tab_switched`) as well as on open/close/reindex and the Catalogue's
`selection-changed` signal. There is no longer a menubar **Record** menu; its
actions moved to the Catalogue's row right-click menu (see §8.2), and F2
(rename) is bound at the window level via `accel_group.connect` →
`_accel_rename`, which fires only on the Catalogue tab with a record selected.

### 8.2 Catalogue tab (`gtk3/gtk3_catalogue_tab.py`) — the big one

Three panes in nested `Gtk.Paned`:

- **Pane 1 (sidebar)** — a `Gtk.TreeStore` with columns
  `(icon_name, label, kind, key, pango_style_int, count_str)`. Node "kind"
  constants: `NODE_ALL, NODE_TYPE, NODE_WORK, NODE_WORKS_ROOT, NODE_AUTHOR,
  NODE_OUTLET, NODE_FULLTEXT, NODE_DOI, NODE_TEMP`. Sections: All articles / By
  type (Journal article / Proceedings / Book chapter / Book / Webpage / Other)
  / By full-text (PDF available / EPUB available / Not available, keys
  `pdf`/`epub`/`none`) / By DOI status (DOI is set / not set, keys
  `set`/`unset`) / My works / Starred authors / Starred outlets (each starred
  outlet is labelled by its nickname where one is set, else the full name).
  Selecting a node calls `_apply_filter(kind, key)`, which repopulates Pane 2
  and records `_active_filter` (so `refresh_current_view` can re-apply it). A
  second, right-aligned column shows the number of articles each filter row
  would surface (`(N)`, blank when zero); the counts are precomputed by
  `_compute_sidebar_counts` and formatted by the module-level `_count_label`
  (author/outlet rows read straight from `record_ids`).

  - **Right-click** (`_on_sidebar_button_press`): on the My-works root →
    "Add work…"; on a work → "Edit work… / Open YAML in Text Editor / Add
    work…" (`_open_work_yaml` launches the work's `.yml` via
    `open_with_text_editor`). Items use `_img_menu_item` for icons. (This
    replaced an earlier +/pencil button bar.)
  - **Transient query node** (`NODE_TEMP`): when the Authors tab asks to show a
    *non-starred* author's works, `show_author_works` rebuilds the sidebar with
    an italic "Query: …" node pinned at the bottom and selects it, so Pane 1
    stays consistent with Pane 2. Selecting any other node removes it
    (`_remove_temp_node`). The italic is done via the pango-style column
    (`_pango_style_italic()`), guarded so it degrades under the test stub. The
    Outlets tab's `show_outlet_works` selects a starred outlet's node when it
    has one, else applies the `NODE_OUTLET` filter directly (no transient
    node).

- **Pane 2 (master)** — a `Gtk.ListStore` with columns
  `(pdf_icon, bibliotheca_id, author, year, jflags, outlet, title, type)`.
  **Column 0 is the PDF icon**, so every text-column index is offset by one —
  remember this if you add columns or touch `_populate_master`/`_master_row`,
  `_filter_visible` (searches columns 1..7), `_on_master_changed` (reads col 1
  for the id), or `reveal_record`/`_update_row_pdf_icon` (match on col 1). The
  **J-Flags** column (store col 4, before Outlet) is rendered plain text via
  `_jflags_display` (outlet's flags ordered by configured priority through the
  module-level `_order_jflags`; an em dash when the record has no outlet or the
  outlet has no flags). The **Outlet** column (store col 5) is
  rendered as **Pango markup** (`markup=` attribute, not `text=`) via
  `_outlet_markup`, so an outlet's nickname can be shown in bold brackets before
  the full name (e.g. `<b>(JBIB)</b> Journal of Bibliotheca`); the nickname is a
  display-only preface and never enters the Pane 3 APA reference. The Year
  column is fixed-width so 4-digit years aren't ellipsised. A `filter_new()`
  model backs the search box.

  - **Record menu** (`_build_record_menu(rec)`): the primary record menu,
    shared by the mouse **right-click** (`_on_master_button_press`) and the
    keyboard **Menu key / Shift+F10** (`_on_master_popup_menu`, connected to the
    TreeView's `popup-menu` signal; it anchors the menu to the selected row's
    rectangle). It carries, top to bottom (all via `_img_menu_item`, so all have
    icons): Reveal .bib / Reveal .md in File Manager; Open .bib / Open .md in
    Text Editor; Open PDF; Open EPUB (the last two disabled when that full-text
    is absent); **Go to outlet** (disabled unless the record is a journal
    article or proceedings with a known outlet — emits
    `goto-outlet(outlet_id)`); Copy
    Bibliotheca ID; Rename Bibliotheca ID…; Allocate to My Works…; then the
    full-text management block Set PDF… / Set EPUB… / Remove full-text link(s).
    The "reveal/edit/open/rename/allocate" items don't act locally — they call
    `self.emit("record-action", <name>)`, and `MainWindow._on_record_action`
    routes each to the existing handler acting on the current record. This is
    the successor to the old menubar **Record** menu, which has been removed.
    Copy Bibliotheca ID (`_copy_bibliotheca_id`) and the Set/Remove full-text
    items are handled inside the tab. This menu is the only place to *attach*
    full-text.

- **Pane 3 (detail)** — a header row with a **citation-style dropdown**
  (`style_combo`: "APA 7 (built-in)", "ACIS (built-in)", plus every CSL file
  from the workspace's `csl/` folder, listed by filename), the reference label
  (Pango markup), an **in-text citation row** (`intext_box`/`intext_label`,
  shown only for styles that define one — currently ACIS — with both the
  parenthetical and narrative forms), Copy (rich) / Copy (plain) buttons, an
  **Open PDF** button (shown enabled only when a PDF is set), the editable notes
  `TextView`, and a status line.
  `_render_reference`/`_reference_markup`/`_reference_plain` route through the
  built-in APA renderer when the style is `APA_STYLE_ID`, the built-in ACIS
  renderer (with the year letter from `workspace.acis_disambiguator`) when it is
  `ACIS_STYLE_ID`, else through `csl.render_markup`/`render_plain` with the
  selected CSL file. `_render_intext` fills (and shows/hides) the in-text row.
  Changing the dropdown fires `_on_style_changed`, which re-renders and calls
  the `_style_change_cb` so the main window persists the choice per workspace.

**Multi-key sorting**: sorting is done in the model layer, not via GTK's
single-column `set_sort_column_id`. The tab holds `_sort_spec`, an ordered list
of `(sort_key, ascending_bool)`, and `_current_records`, the unsorted source
list last handed to `_populate_master`. `_sorted_records` applies the spec as a
*stable sort from least- to most-significant key* (iterating `reversed(spec)`),
which yields correct multi-column precedence. The sort persists across sidebar
filter changes because every populate path runs through `_populate_master`
(which re-applies it) and `set_sort_spec` re-renders `_current_records` in
place. The available keys and their comparison functions live in the
module-level `SORT_KEYS` dict; `SORT_LABELS` gives their display order and human
names. Year sorts numerically via `_year_key` (so 2009 < 2025). `SortDialog`
(in `gtk3/gtk3_sort_dialog.py`) is the UI: an ordered, reorderable list the user builds
with an "add key" combo, up/down/toggle-direction/remove buttons; it returns
the spec via `get_spec()`. The View → Sort menu item and the Sort toolbar
button (both workspace-sensitive) invoke it from `MainWindow._on_sort`, which
also handles the dialog's "Clear" response (empty spec = default id order).

**Notes autosave**: `_on_notes_changed` marks `_notes_dirty`; `_flush_notes`
writes on record switch, on `set_fulltext`/`clear`, on workspace change, and on
window close. Honours the `autosave` preference. Suppressed during programmatic
buffer loads via `_suppress_notes_save`.

**Notes syntax highlighting**: the notes `TextBuffer` is wrapped by a
`MarkdownHighlighter` (`gtk3/gtk3_md_highlight.py`, ported from the QDVC Markdown Notebook
project). It applies colour/weight/style tags — no font-size variation — so the
notes read as highlighted Markdown while staying plain, editable text.
`highlight()` runs after a record's notes load (in `_show_detail`, where the
`_suppress_notes_save` guard skips the `changed` handler) and again inside
`_on_notes_changed` on every edit. `set_notes_font` keeps the highlighter's
code-span font in step with the notes font.

**Rich clipboard**: `Gtk.Clipboard.set_with_data` is not introspectable in
PyGObject (calling it crashes the interpreter), so rich copy uses a
`_ClipboardOwner` GObject held in a **module-level strong reference**
(`_clipboard_owner`) to survive GC while it owns the clipboard, offering
`text/html` + plain-text targets, with a plain-text fallback. Do not "simplify"
this back to `set_with_data`.

Public methods the main window calls: `set_workspace`, `set_fulltext_root`,
`set_notes_font`, `set_autosave`, `set_jflag_priority`, `set_sidebar_visible`,
`set_detail_visible`, `set_style_change_callback`, `set_citation_style`,
`refresh_csl_styles`, `refresh_current_view`, `refresh_starred_authors`,
`refresh_starred_outlets`, `show_author_works`, `show_outlet_works`,
`reveal_record`, `current_record`, `flush_notes`, `set_sort_spec`,
`get_sort_spec`.

### 8.3 Authors tab (`gtk3/gtk3_authors_tab.py`)

A `ListStore(bool, str, str, int)` = (starred, display_name, author_id,
work_count) behind a filter (text + "starred only"). The star column is a
`CellRendererToggle`; `_on_star_toggled` maps the **filter path back to the
child store** via `convert_path_to_child_path` before flipping — keep that
conversion if you touch it. Emits `star-changed(author_id, bool)` and
`show-author-works(author_id)`. The main window relays these to
`catalogue.refresh_starred_authors()` and `catalogue.show_author_works()`.

### 8.3b Outlets tab (`gtk3/gtk3_outlets_tab.py`)

A `ListStore(bool, str, str, str, str, int)` = (starred, name, nickname,
jflags_joined, outlet_id, record_count) behind a filter (text + "starred
only"). Same `CellRendererToggle` + `convert_path_to_child_path` star pattern as
the Authors tab. Two extra actions at the bottom: **Set nickname…**
(`_on_set_nickname` → `Workspace.set_outlet_nickname`, which renames the YAML
file; a `ValueError` from the model — invalid character or a collision — is
caught and shown via `_warn`) and **Set J-Flags…** (`_on_set_jflags` — a
checklist of the presets from `set_jflag_presets`, plus any non-preset flag
already on the outlet so hand-added flags aren't dropped →
`Workspace.set_outlet_jflags`). Emits `star-changed(outlet_id, bool)`,
`show-outlet-works(outlet_id)`, and `outlet-changed()`. The main window
relays these to `catalogue.refresh_starred_outlets()`,
`catalogue.show_outlet_works()`, and (for `outlet-changed`)
`catalogue.refresh_starred_outlets()` again so the Catalogue's Outlet/J-Flags
columns re-render. `set_jflag_presets` is pushed from
`MainWindow._jflag_presets()` on workspace open and on preference changes.
`reveal_outlet(outlet_id)` clears any active filter, then selects and
scrolls the matching row into view — used by the Catalogue's "Go to outlet"
(`MainWindow._on_goto_outlet` switches to this tab first).

### 8.4 DOI tab (`gtk3/gtk3_doi_tab.py`)

Entry + Lookup button + status label. On match, emits `goto-record(id)` which
the main window routes to the Catalogue (`reveal_record`). On miss, shows
`Sorry, no records found for DOI = …`.

### 8.5 Dialogs

- `ImportDialog` (in `gtk3/gtk3_main_window.py`) — paste box + "Choose file…" that loads
  a `.bib` into the same box; import always uses the box text via
  `import_bib_text`. Carries an "Allocate imported records to:" dropdown
  (`allocate_work_key` → work key or None) listing every work plus "(none)".
  `_on_import` passes the workspace and a preselect key: when the user is
  viewing a "my work" in the Catalogue (`catalogue.current_work_key()`), that
  work is pre-selected. After a successful import, if a work was chosen the
  imported ids are allocated to it and the Catalogue navigates to that work's
  view (`catalogue.show_work`).
- `AllocateDialog` (`gtk3/gtk3_allocate_dialog.py`) — a checklist of existing works
  (pre-ticked where every selected record is already cited) plus a "new work"
  entry. `apply()` optionally creates the new work, then calls
  `Workspace.allocate_to_work` for each ticked work and the new one; returns the
  total allocations. Invoked from `MainWindow._allocate_records`, which then
  calls `catalogue.refresh_after_allocation()` (rebuild sidebar + re-apply the
  active filter). Used both from the record right-click "Allocate to My Works…"
  and the allocate-after-import path.
- `PreferencesDialog` — a `Gtk.Notebook` with three tabs: **General** (font,
  file-manager command, full-text library path, reopen-last, autosave, toolbar
  style); **J-Flags** (an editable `flag`/`priority` list with Add/Remove,
  persisted to the `jflags` config key as `{flag, priority}` dicts); and
  **CSL** (a read-only list of the `.csl` files in the workspace's `csl/`
  folder, by filename, with a status line noting whether `citeproc-py` is
  installed). It takes an optional `workspace=` so the CSL tab can list files.
  `apply()` writes to `Config`; `MainWindow._apply_prefs_to_widgets` pushes
  values into the widgets, calls `_apply_toolbar_style`, pushes the J-Flag
  priority map into the Catalogue and the presets into the Outlets tab, and
  calls `catalogue.refresh_csl_styles()` + `set_citation_style(...)` in case a
  CSL file was added or removed.
- `MyWorkEditor` (`gtk3/gtk3_myworks_editor.py`) — two-list citation picker +
  name + `published_as` combo; keeps its cited list alphabetical and inserts
  additions at their sorted slot.

### 8.6 `platform_utils.py`

`open_with_default_app` (viewer), `open_with_text_editor` (editor;
`xdg-open` on Linux, `open -t` on macOS), `reveal_in_file_manager` (honours the
`file_manager` config template with `{dir}`/`{file}`). Cross-platform via
`sys.platform` / `os.name`.

---

## 9. Testing without a display

There is no bundled GTK in many CI/sandbox environments, so two techniques are
used:

1. **Model tests** run directly — the entire pure layer (`workspace.py`,
   `models.py`, `bibtex.py`, `markdown_io.py`, `naming.py`, `apa.py`, `csl.py`,
   `catalogue_sort.py`) imports no GTK, so you can build a temp workspace on
   disk and assert on `Workspace` behaviour (author/outlet derivation, import,
   rename, validate, full-text relative paths) without a display.
2. **Import smoke test** — a permissive fake `gi` package (a stub that returns a
   catch-all object for any attribute) lets every GTK module under `qdvc/gtk3/`
   be *imported* so class bodies, `__gsignals__` definitions, and top-level code
   are exercised. This catches typos, bad imports, and signature errors that
   `py_compile` misses. Note the stub cannot evaluate real enum values, which is
   why Pango style ints are computed through guarded helpers (in
   `gtk3/gtk3_widgets.py`) rather than at class scope.

Before shipping a change, at minimum:

```sh
python3 -m py_compile qdvc/*.py qdvc/gtk3/*.py qdvc-bibliotheca.py
# then the stub-import of every qdvc.* and qdvc.gtk3.* module
```

and cross-check that every `self.<tab>.<method>` call in `gtk3/gtk3_main_window.py` has a
matching definition, and every `.connect("signal")` has a declared
`__gsignals__` entry.

**Not testable this way** (needs a real display): actual rendering, accelerator
firing, `popup_at_pointer` (needs GTK ≥ 3.22), toggle/right-click behaviour,
and whether icon names resolve in the user's theme (missing names degrade to a
placeholder, not a crash).

---

## 10. Common maintenance tasks — where to touch

- **Add a master-table column** → `catalogue_tab._build_master` (mind the
  column-0 offset and that Outlet is a `markup=` column), `_master_row`,
  `_filter_visible` range (currently 1..7), and any code reading store columns
  by index.
- **Add a sidebar filter category** → add a `NODE_*` constant, build the nodes
  in `_rebuild_sidebar` (remember the trailing count-string column; use
  `_count_label`), extend `_compute_sidebar_counts` if the count isn't already
  available, handle it in `_apply_filter`, and add the backing query to
  `Workspace`.
- **Add a validation check** → add the key + logic in `Workspace.validate`, and
  a `section(...)` line in `MainWindow._format_report`.
- **Add a sortable field** → add an entry to `SORT_KEYS` (id → key function)
  and `SORT_LABELS` (id → label, in display order) in the pure
  `catalogue_sort.py`. The sort dialog (`gtk3/gtk3_sort_dialog.py`) and the sort
  engine in `gtk3/gtk3_catalogue_tab.py` pick it up automatically.
- **Add a preference** → widget + `apply()` in the relevant tab of
  `gtk3/gtk3_preferences.py` (General / J-Flags / CSL); read via
  `config.get(key, default)`; if it affects widgets live, push it in
  `_apply_prefs_to_widgets`.
- **Tweak outlets / J-Flags / nicknames** → the `Outlet` dataclass and
  `_derive_outlets`/`set_outlet_*` in `workspace.py` (model, including
  `OUTLET_TYPES` for which record types count); the display in
  `catalogue_tab._outlet_markup`/`_jflags_display`/`_order_jflags`; the editors
  in `gtk3/gtk3_outlets_tab.py`; the presets in `gtk3/gtk3_preferences.py` + `MainWindow`'s
  `_jflag_presets`/`_jflag_priority_map`.
- **Tweak CSL rendering** → `csl.py` (`entry_to_csl_json` for the BibTeX→CSL-JSON
  mapping — text fields pass through `_markup_safe` there, so a raw `&`/`<`/`>`
  cannot break the Pango label; `_html_to_pango`/`_html_to_plain` for output);
  the dropdown + rendering in `catalogue_tab` (`_populate_style_combo`,
  `_reference_markup`); persistence in
  `MainWindow._saved_citation_style`/`_on_citation_style_chosen`.
- **Add a BibTeX entry type / tweak APA** → `apa._RENDERERS`, `TYPE_LABELS`,
  and `type_label` (which also inspects `booktitle` for the Proceedings case).
  If you add a new human label, update `Record.outlet` and any By-type list.
- **Tweak ACIS or its in-text citation** → `acis.py` (`_RENDERERS` /
  `_pick_renderer` for the reference forms, `in_text_plain`/`_author_label` for
  the in-text forms, `disambiguator_map` for the year letters). The `Record`
  helpers (`acis_*`) and `Workspace.acis_disambiguator` are the integration
  points; the Pane-3 wiring (`_reference_markup`, `_render_intext`,
  `_populate_style_combo`) lives in both `gtk3_catalogue_tab.py` and
  `gtk4_catalogue_tab.py`. Add any new built-in style id beside `ACIS_STYLE_ID`
  in `catalogue_sort.py`.
- **Change the cached record schema** → update `Record`, `_scan`, `_load_index`,
  `_save_index`, and **bump `INDEX_VERSION`**.
- **Add a menu/toolbar action** → the relevant `_*_menu`/`_build_toolbar`
  builder in `gtk3/gtk3_main_window.py`; wire sensitivity into
  `_update_actions_sensitivity`.
- **Add a new module** → if it imports `gi` it goes in `qdvc/gtk3/` with a
  `gtk3_` prefix; otherwise it stays in the pure top-level `qdvc/` package.
  GTK3 modules import pure ones with `from ..` and siblings with
  `from .gtk3_x`.
- **Extract pure logic from a GTK module** → move the toolkit-independent
  function/constant into a pure module (e.g. a new `*_sort.py`-style helper or
  `naming.py`), import it back with `from ..`, and — if callers used a private
  name — alias on import (`from ..x import y as _y`) so the GTK class body is
  unchanged. This is exactly how `catalogue_sort.py`, `naming.py`, and the
  `models`/`bibtex`/`markdown_io` split were done.
- **Work on the GTK4 UI** → it lives in `qdvc/gtk4/` (all `gtk4_*`), reuses the
  entire pure layer unchanged, and follows the GNOME HIG. The launcher already
  dispatches to `qdvc.gtk4.gtk4_app:main` when `ui_backend`/`--gtk4` selects it.
  For the GTK3↔GTK4 element map (which widget replaces which, and why), see
  [MAINTENANCE_GTK3_GTK4.md](MAINTENANCE_GTK3_GTK4.md).
- **Add a UI feature to both front-ends** → implement the view change in the
  matching `gtk3_*` and `gtk4_*` module, and put any toolkit-independent
  logic (config reads, formatting, spec parsing) in `ui_prefs.py` so both call
  one implementation. If a command is involved, add it to the GTK3 menu/toolbar
  *and* install a `win.*` `Gio.SimpleAction` in `gtk4_actions` (referencing it
  by name from the menu/header).

---

## 11. Deployment: desktop launcher & icon

The app uses a **standard freedesktop themed icon** — `accessories-dictionary`
— present on a typical GNOME/MATE install, so no icon file is bundled or needs
installing. `gtk3/gtk3_app.py` defines `ICON_NAME = "accessories-dictionary"`;
`do_startup` calls `Gtk.Window.set_default_icon_name(ICON_NAME)` and
`MainWindow.__init__` calls `self.set_icon_name("accessories-dictionary")`, so
the icon shows even before any `.desktop` matching.
`GLib.set_prgname("qdvc-bibliotheca")` (run at import in `gtk3/gtk3_app.py`) fixes the
X11 `WM_CLASS` so the MATE panel can associate the running window with the
launcher.

For the **MATE panel** to show the icon rather than a generic one, the running
window's `WM_CLASS` must match the launcher's `StartupWMClass`. Install
`~/.local/share/applications/qdvc-bibliotheca.desktop`:

```
[Desktop Entry]
Type=Application
Name=QDVC Bibliotheca
Comment=Manage your personal collection of articles, papers and books
Exec=python3 /full/path/to/qdvc-bibliotheca.py %U
Path=/full/path/to
Icon=accessories-dictionary
Terminal=false
Categories=Office;Education;Literature;
StartupNotify=true
StartupWMClass=qdvc-bibliotheca
Keywords=bibliography;references;bibtex;citations;research;
```

- `StartupWMClass=qdvc-bibliotheca` is the load-bearing line for the panel
  icon; it must equal the value passed to `set_prgname`.
- `Icon=accessories-dictionary` is a standard themed icon, so the launcher/menu
  entry resolves it without any extra install step. To use custom artwork
  instead, point `Icon=` at an absolute path to a `.png`/`.svg` and change
  `ICON_NAME` in `gtk3/gtk3_app.py` (and the `set_icon_name` call in `gtk3/gtk3_main_window.py`) to
  match.
- `Exec` must be an absolute path; `Path` must be the directory containing both
  `qdvc-bibliotheca.py` and the `qdvc/` package. `%U` lets you drop a workspace
  folder on the launcher.
- Verify with `xprop WM_CLASS` (click the window) — a string should be
  `qdvc-bibliotheca`. If the panel still shows the old icon, log out/in; MATE
  caches launcher↔WM-class associations per session.
- Refresh + validate:
  ```
  update-desktop-database ~/.local/share/applications
  desktop-file-validate ~/.local/share/applications/qdvc-bibliotheca.desktop
  ```

---

## 12. Persisted state (config keys)

Beyond the §4.6 list:

- `sort_spec` — the multi-key sort, stored as `[[field_id, ascending_bool],
  ...]` and round-tripped by the shared `ui_prefs.load_sort_spec` /
  `save_sort_spec`. It is applied to the Catalogue in `_apply_prefs_to_widgets`
  at startup (before any workspace is open, which is fine — it's applied again
  on populate) and saved whenever the Sort dialog is accepted or cleared.
  Unknown field ids load harmlessly: `_sorted_records` skips any key absent from
  `SORT_KEYS`.
- `csl_styles` — a `{workspace_root_path: style_id}` map persisting the chosen
  citation style per workspace (`style_id` is the `APA_STYLE_ID` or
  `ACIS_STYLE_ID` sentinel, or a CSL filename), read/written by
  `ui_prefs.saved_citation_style` / `store_citation_style` in both front-ends.
- `ui_backend` — `"gtk3"` (default) or `"gtk4"`, chosen from either UI's
  Preferences and read by the launcher (§3.3). `Config.ui_backend` validates it.

The reusable, toolkit-independent readers/formatters for these (J-Flag presets,
sort spec, citation style, and the validation-report text) live in the pure
`ui_prefs.py` so the GTK3 and GTK4 windows share one implementation.

---

## 13. Known constraints & gotchas

- **Two front-ends.** The GTK3 UI (`qdvc/gtk3/`) is the default; a full GTK4 /
  libadwaita UI (`qdvc/gtk4/`) is selectable via `ui_backend` or `--gtk4`. The
  GTK3 UI deliberately uses some deprecated-in-GTK4 idioms (`Gtk.Toolbar`,
  `override_font`, the `Gtk.Clipboard` owner trick); the GTK4 UI replaces each
  with its modern equivalent (header bars, `MarkdownHighlighter` font tag,
  `Gdk.ContentProvider`). When adding a UI feature, add it to **both** front-ends
  (or deliberately note why not) and keep any toolkit-independent logic in
  `ui_prefs.py`. See [MAINTENANCE_GTK3_GTK4.md](MAINTENANCE_GTK3_GTK4.md).
- **`WM_CLASS` / panel icon**: the app sets a standard themed icon
  (`accessories-dictionary`) as both the default and per-window icon, so the
  window/taskbar icon renders without any icon file being installed. The MATE
  *launcher* association still relies on `set_prgname` matching the `.desktop`
  `StartupWMClass` (see §11). Under Wayland, window placement and some class
  matching are compositor-controlled.
- **Notes vs frontmatter writes** must be ordered (flush notes before
  frontmatter writes) — see §4.2.
- **Column-0 offset** in the master table is a recurring source of off-by-one
  bugs — see §8.2.
- **Single-entry `.bib` assumption** for the on-disk convention; the fallback
  parser is single-entry, though import handles multi-entry text by splitting
  first.
- The **index is disposable**: deleting `.qdvc-index.json` or using Rescan
  forces a clean rebuild. When debugging "stale data" reports, suspect the
  cache first.
