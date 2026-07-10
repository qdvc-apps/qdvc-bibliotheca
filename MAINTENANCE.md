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

**Separation of concerns.** `workspace.py` is pure model/IO logic with no GTK
imports. All GTK code lives in the `*_tab.py`, `main_window.py`,
`preferences.py`, and `myworks_editor.py` modules. This separation is what lets
the model be unit-tested without a display (see §9).

**Lazy where it counts.** Opening a large workspace must be fast, so a cached
index holds only lightweight display fields. Full BibTeX parsing and notes
reading happen per-record, on demand.

---

## 2. Runtime requirements

- Python 3.10+ (uses `str | None` union syntax and `list[...]` generics).
- PyGObject + GTK 3 (`gi`, `gi.repository.Gtk` version "3.0").
- PyYAML (hard dependency).
- `bibtexparser` (optional; a built-in fallback parser is used when absent).

GTK 4 is **not** supported. Several deprecated-in-GTK4 idioms are used
deliberately (see §8).

---

## 3. Directory & file layout

### 3.1 Source tree

```
qdvc-bibliotheca.py        Launcher shim (adds nothing but a __main__ entry).
qdvc/
    __init__.py            Version + app constants (APP_ID, APP_NAME, __version__).
    app.py                 Gtk.Application subclass; sets prgname + icon.
    config.py              Config: load/save YAML at the XDG config location.
    workspace.py           MODEL. No GTK. Records, MyWork, Author, Workspace.
    apa.py                 BibTeX-entry -> APA 7 formatter (markup + plain).
    platform_utils.py      Launch system apps (viewer, editor, file manager).
    main_window.py         MainWindow (menubar/toolbar/notebook) + ImportDialog.
    catalogue_tab.py       Three-pane Catalogue tab (the biggest UI module).
    authors_tab.py         Authors tab (list + star toggles).
    doi_tab.py             DOI lookup tab.
    preferences.py         Preferences dialog.
    myworks_editor.py      Dialog to edit a "my work" (citations + published_as).
    sort_dialog.py         Dialog to build a multi-key sort specification.
```

### 3.2 Workspace on disk

```
(workspace root)/
    bibtex/<A..Z>/<bibliotheca_id>.bib     One entry per file. Authoritative.
    markdown/<A..Z>/<bibliotheca_id>.md    YAML frontmatter + free notes.
    my_works/*.yml                         User projects (arbitrary stems).
    authors/<SURNAME_GivenNames>.yml       Derived author records + star state.
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
published_as: SmithJones2025_MISQ   # optional
cites:
  - SmithJones2025_MISQ
  - Jones2009_JAIS
```

Loader (`_load_my_works`) is tolerant: it accepts `cites` or `citations`,
`name` or `title`, and `published_as` or `published_version`. The canonical
writer (`MyWork.save` / `to_yaml_dict`) emits `name`, `cites`, and
`published_as` (only if set).

### 4.4 authors YAML

```
id: ZUBOFF_Shoshana
surname: Zuboff
given_names: Shoshana
starred: true
```

Derived automatically (see §6). Only `starred` is user-editable state; the rest
is a stable mapping regenerated from BibTeX.

### 4.5 Index cache (`.qdvc-index.json`)

`{"version": INDEX_VERSION, "records": [ {…}, … ]}`. Each record stores only
display/index fields: `bibliotheca_id, bib_path, md_path, entrytype,
type_label, author, year, title, journal, doi, has_pdf, has_epub`.

`INDEX_VERSION` is currently **3**. **Bump it whenever the per-record schema
changes**, otherwise stale caches load with missing fields. `_load_index`
returns `False` (forcing a rescan) if the version mismatches or if any
referenced `.bib` path no longer exists.

### 4.6 Application config

`config.py` stores YAML at `$XDG_CONFIG_HOME/qdvc-bibliotheca/config.yml`
(falling back to `~/.config`). `DEFAULTS` holds `last_workspace`,
`recent_workspaces`, and `window` size. Additional keys set via
`Config.set`/`get`: `notes_font`, `file_manager`, `fulltext_library_path`,
`reopen_last`, `autosave_notes`, `toolbar_style`. When you add a preference,
add it in `preferences.py` (widget + `apply()`) and read it where used; no
schema migration is needed because `Config.get` takes a default.

---

## 5. The model: `workspace.py`

No GTK. Three dataclasses plus the `Workspace` aggregate.

### 5.1 `Record`

One catalogued work. Index fields are eager; `bib()` lazily parses the `.bib`
and caches it in `_bib`. Helpers: `apa_markup()`, `apa_plain()`,
`read_notes()`, and the `outlet` property (journal for journal articles, book
title for book chapters, em dash otherwise — drives the Outlet column).

### 5.2 `MyWork`

`name, path, cites[], published_as`. `save()` writes atomically.

### 5.3 `Author`

`author_id, surname, given_names, starred, path, record_ids[]`. `record_ids`
is populated at load, not persisted. `display_name` = `"Surname, Given"`.

### 5.4 `Workspace` — load pipeline

```
load(force_rescan=False):
    if not force_rescan and _load_index():   # fast path from cache
        _load_my_works(); _build_doi_index(); _derive_authors(); return
    _scan()                                    # slow path: read every .bib
    _load_my_works(); _build_doi_index(); _derive_authors(); _save_index()
```

- `_scan` walks `bibtex/**/*.bib`, parses each, checks the paired `.md` for
  `pdf`/`epub` frontmatter to set `has_pdf`/`has_epub`.
- `_build_doi_index` maps normalised DOI -> bibliotheca_id (for the DOI tab).
- `_derive_authors` (see §6).

### 5.5 Query API (used by the UI)

`all_records`, `records_by_type(label)`, `records_by_fulltext(which)` (which ∈
{"pdf","epub","none"}), `records_by_doi_status(has_doi)`,
`records_for_work(key)`, `records_for_author(author_id)`, `all_authors`,
`starred_authors`, `lookup_doi(doi)`, `get(bibliotheca_id)`.

### 5.6 Mutation API

- `import_bib_text(text)` / `import_bib_file(path)` — split, file each new
  entry under its shard using the citation key as the `bibliotheca_id`, skip
  existing ids, then rebuild DOI index + authors + save index.
- `rename_record(old, new)` — moves both paired files, updates in-memory
  record, rewrites every `my_works` reference (`cites` and `published_as`),
  rebuilds authors + index. Raises `ValueError` on empty/invalid/collision.
- `create_my_work(name)` — sanitises name to a file stem, de-duplicates, writes
  an empty work.
- `set_fulltext_path(id, kind, abs_path|None, storage_root)` — writes the
  `pdf`/`epub` frontmatter **relative to `storage_root`** when the file is
  inside it, else absolute; updates `has_pdf`/`has_epub`; re-saves index.
- `resolve_fulltext_path(id, kind, storage_root)` — inverse; returns an
  absolute path for opening.

### 5.7 `validate(storage_root)`

Returns a dict of problem lists: `orphan_markdown`, `key_mismatch`,
`missing_fulltext`, `dangling_citations`, `dangling_published_as`,
`duplicate_dois`. Relative full-text paths are resolved against `storage_root`
before the existence check. When you add a check, add its key here **and** a
`section(...)` line in `MainWindow._format_report`.

### 5.8 Module helpers

`make_author_id(surname, given)` → `SURNAME_GivenNames` (surname uppercased,
given-names title-cased, non-alphanumerics stripped). `_sanitise_id` for safe
file stems. `_normalise_doi` strips a `doi.org/` prefix.

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

---

## 7. APA formatting (`apa.py`)

`format_apa_markup(entry)` returns **Pango markup** (`<i>…</i>` for titles/
journals, entities escaped). `format_apa_plain(entry)` strips it to text.

- Type-specific renderers are registered in `_RENDERERS` keyed by entry type
  (article, inproceedings, book, inbook/incollection, online/misc, …), with
  `_render_online` as the fallback.
- `TYPE_LABELS` / `type_label()` map BibTeX entry types to the human labels the
  UI filters on ("Journal article", "Conference paper", "Book chapter", "Book",
  "Webpage", "Other"). **These strings are load-bearing**: the sidebar "By
  type" filter, `records_by_type`, and `Record.outlet` all compare against
  them. Change them in one place only.
- Author name handling: `split_name` handles "Surname, Given" and
  "Given Surname"; `author_tokens` returns `(surname, given)` pairs;
  `format_author_list` builds the APA `A, B., & C.` string (≤20 authors, then
  ellipsis rule).

The rich-vs-plain design exists to support the two Copy buttons and the
HTML-clipboard path in the Catalogue (see §8.2).

---

## 8. UI layer

### 8.1 Application & window bootstrap

`app.py`: `Gtk.Application` (id `org.qdvc.Bibliotheca`, `HANDLES_OPEN`).
`GLib.set_prgname("qdvc-bibliotheca")` runs at import so the X11 `WM_CLASS`
matches the `.desktop` `StartupWMClass` (needed for the MATE panel icon).
`do_startup` sets the default icon name; `do_activate` builds the single
`MainWindow`; `do_open` routes a folder argument to `_open_path`.

`main_window.py` builds a `Gtk.Box` containing menubar, toolbar, a
`Gtk.Notebook` (Catalogue / Authors / DOI Lookup, in that order — index 0/1/2,
which the Alt+1/2/3 accelerators and `_on_goto_record`/`_on_show_author_works`
depend on), and a status bar.

`_menu_item(label, icon)` builds menu items as a `Box(Image+Label)` inside a
plain `MenuItem` — deliberately **not** `Gtk.ImageMenuItem`, which is removed in
GTK4 and warns in GTK3.

Actions/sensitivity: `_update_actions_sensitivity` centralises enable/disable
based on whether a workspace is open and whether a record is selected (and,
for "Open PDF", whether that record has a PDF). It's called after open/close/
reindex and on the Catalogue's `selection-changed` signal.

### 8.2 Catalogue tab (`catalogue_tab.py`) — the big one

Three panes in nested `Gtk.Paned`:

- **Pane 1 (sidebar)** — a `Gtk.TreeStore` with columns
  `(icon_name, label, kind, key, pango_style_int)`. Node "kind" constants:
  `NODE_ALL, NODE_TYPE, NODE_WORK, NODE_WORKS_ROOT, NODE_AUTHOR, NODE_FULLTEXT,
  NODE_DOI, NODE_TEMP`. Sections: All articles / By type / By full-text
  (PDF available / EPUB available / Not available, keys `pdf`/`epub`/`none`) /
  By DOI status (DOI is set / not set, keys `set`/`unset`) / My works / Starred
  authors. Selecting a node calls `_apply_filter(kind, key)`, which repopulates
  Pane 2 and records `_active_filter` (so `refresh_current_view` can re-apply
  it).

  - **Right-click** (`_on_sidebar_button_press`): on the My-works root →
    "Add work…"; on a work → "Edit work… / Add work…". (This replaced an
    earlier +/pencil button bar.)
  - **Transient query node** (`NODE_TEMP`): when the Authors tab asks to show a
    *non-starred* author's works, `show_author_works` rebuilds the sidebar with
    an italic "Query: …" node pinned at the bottom and selects it, so Pane 1
    stays consistent with Pane 2. Selecting any other node removes it
    (`_remove_temp_node`). The italic is done via the pango-style column
    (`_pango_style_italic()`), guarded so it degrades under the test stub.

- **Pane 2 (master)** — a `Gtk.ListStore` with columns
  `(pdf_icon, bibliotheca_id, author, year, outlet, title, type)`. **Column 0
  is the PDF icon**, so every text-column index is offset by one — remember
  this if you add columns or touch `_populate_master`, `_filter_visible`
  (searches columns 1..6), `_on_master_changed` (reads col 1 for the id), or
  `reveal_record`/`_update_row_pdf_icon` (match on col 1). The Year column is
  fixed-width so 4-digit years aren't ellipsised. A `filter_new()` model backs
  the search box.

  - **Right-click** (`_on_master_button_press`): Set PDF… / Set EPUB… / Open
    PDF / Remove full-text link(s) for the row under the pointer. This is the
    only place to *attach* full-text.

- **Pane 3 (detail)** — read-only APA reference label (Pango markup), Copy
  (rich) / Copy (plain) buttons, an **Open PDF** button (shown enabled only
  when a PDF is set), the editable notes `TextView`, and a status line.

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
(in `sort_dialog.py`) is the UI: an ordered, reorderable list the user builds
with an "add key" combo, up/down/toggle-direction/remove buttons; it returns
the spec via `get_spec()`. The View → Sort menu item and the Sort toolbar
button (both workspace-sensitive) invoke it from `MainWindow._on_sort`, which
also handles the dialog's "Clear" response (empty spec = default id order).

**Notes autosave**: `_on_notes_changed` marks `_notes_dirty`; `_flush_notes`
writes on record switch, on `set_fulltext`/`clear`, on workspace change, and on
window close. Honours the `autosave` preference. Suppressed during programmatic
buffer loads via `_suppress_notes_save`.

**Rich clipboard**: `Gtk.Clipboard.set_with_data` is not introspectable in
PyGObject (calling it crashes the interpreter), so rich copy uses a
`_ClipboardOwner` GObject held in a **module-level strong reference**
(`_clipboard_owner`) to survive GC while it owns the clipboard, offering
`text/html` + plain-text targets, with a plain-text fallback. Do not "simplify"
this back to `set_with_data`.

Public methods the main window calls: `set_workspace`, `set_fulltext_root`,
`set_notes_font`, `set_autosave`, `set_sidebar_visible`, `set_detail_visible`,
`refresh_current_view`, `refresh_starred_authors`, `show_author_works`,
`reveal_record`, `current_record`, `flush_notes`, `set_sort_spec`,
`get_sort_spec`.

### 8.3 Authors tab (`authors_tab.py`)

A `ListStore(bool, str, str, int)` = (starred, display_name, author_id,
work_count) behind a filter (text + "starred only"). The star column is a
`CellRendererToggle`; `_on_star_toggled` maps the **filter path back to the
child store** via `convert_path_to_child_path` before flipping — keep that
conversion if you touch it. Emits `star-changed(author_id, bool)` and
`show-author-works(author_id)`. The main window relays these to
`catalogue.refresh_starred_authors()` and `catalogue.show_author_works()`.

### 8.4 DOI tab (`doi_tab.py`)

Entry + Lookup button + status label. On match, emits `goto-record(id)` which
the main window routes to the Catalogue (`reveal_record`). On miss, shows
`Sorry, no records found for DOI = …`.

### 8.5 Dialogs

- `ImportDialog` (in `main_window.py`) — paste box + "Choose file…" that loads
  a `.bib` into the same box; import always uses the box text via
  `import_bib_text`.
- `PreferencesDialog` — font, file-manager command, full-text library path,
  reopen-last, autosave, toolbar style. `apply()` writes to `Config`;
  `MainWindow._apply_prefs_to_widgets` pushes values into the widgets and calls
  `_apply_toolbar_style`.
- `MyWorkEditor` — two-list citation picker + name + `published_as` combo.

### 8.6 `platform_utils.py`

`open_with_default_app` (viewer), `open_with_text_editor` (editor;
`xdg-open` on Linux, `open -t` on macOS), `reveal_in_file_manager` (honours the
`file_manager` config template with `{dir}`/`{file}`). Cross-platform via
`sys.platform` / `os.name`.

---

## 9. Testing without a display

There is no bundled GTK in many CI/sandbox environments, so two techniques are
used:

1. **Model tests** run directly — `workspace.py` and `apa.py` import no GTK, so
   you can build a temp workspace on disk and assert on `Workspace` behaviour
   (author derivation, import, rename, validate, full-text relative paths).
2. **Import smoke test** — a permissive fake `gi` package (a stub that returns a
   catch-all object for any attribute) lets every GTK module be *imported* so
   class bodies, `__gsignals__` definitions, and top-level code are exercised.
   This catches typos, bad imports, and signature errors that `py_compile`
   misses. Note the stub cannot evaluate real enum values, which is why Pango
   style ints are computed through guarded helpers rather than at class scope.

Before shipping a change, at minimum:

```sh
python3 -m py_compile qdvc/*.py qdvc-bibliotheca.py
# then the stub-import of every qdvc.* module
```

and cross-check that every `self.<tab>.<method>` call in `main_window.py` has a
matching definition, and every `.connect("signal")` has a declared
`__gsignals__` entry.

**Not testable this way** (needs a real display): actual rendering, accelerator
firing, `popup_at_pointer` (needs GTK ≥ 3.22), toggle/right-click behaviour,
and whether icon names resolve in the user's theme (missing names degrade to a
placeholder, not a crash).

---

## 10. Common maintenance tasks — where to touch

- **Add a master-table column** → `catalogue_tab._build_master` (mind the
  column-0 offset), `_populate_master`, `_filter_visible` range, and any code
  reading store columns by index.
- **Add a sidebar filter category** → add a `NODE_*` constant, build the nodes
  in `_rebuild_sidebar`, handle it in `_apply_filter`, and add the backing
  query to `Workspace`.
- **Add a validation check** → add the key + logic in `Workspace.validate`, and
  a `section(...)` line in `MainWindow._format_report`.
- **Add a sortable field** → add an entry to `SORT_KEYS` (id → key function)
  and `SORT_LABELS` (id → label, in display order) in `catalogue_tab.py`. The
  sort dialog and the sort engine pick it up automatically.
- **Add a preference** → widget + `apply()` in `preferences.py`; read via
  `config.get(key, default)`; if it affects widgets live, push it in
  `_apply_prefs_to_widgets`.
- **Add a BibTeX entry type / tweak APA** → `apa._RENDERERS`, `TYPE_LABELS`.
  If you add a new human label, update `Record.outlet` and any By-type list.
- **Change the cached record schema** → update `Record`, `_scan`, `_load_index`,
  `_save_index`, and **bump `INDEX_VERSION`**.
- **Add a menu/toolbar action** → the relevant `_*_menu`/`_build_toolbar`
  builder in `main_window.py`; wire sensitivity into
  `_update_actions_sensitivity`.

---

## 11. Deployment: desktop launcher & icon

The app ships a fallback icon at `qdvc/data/qdvc-bibliotheca.svg`.
`app.install_default_icon()` (called from `do_startup`) prefers a themed icon
named `qdvc-bibliotheca` if the system icon theme has one, otherwise loads the
bundled SVG directly from disk at several sizes via
`Gtk.Window.set_default_icon_list`. `MainWindow` also sets the icon on its own
window. `GLib.set_prgname("qdvc-bibliotheca")` (run at import in `app.py`) fixes
the X11 `WM_CLASS`.

For the **MATE panel** to show the app icon rather than a generic one, the
running window's `WM_CLASS` must match the launcher's `StartupWMClass`. Install
`~/.local/share/applications/qdvc-bibliotheca.desktop`:

```
[Desktop Entry]
Type=Application
Name=QDVC Bibliotheca
Comment=Manage your personal collection of articles, papers and books
Exec=python3 /full/path/to/qdvc-bibliotheca.py %U
Path=/full/path/to
Icon=qdvc-bibliotheca
Terminal=false
Categories=Office;Education;Literature;
StartupNotify=true
StartupWMClass=qdvc-bibliotheca
Keywords=bibliography;references;bibtex;citations;research;
```

- `StartupWMClass=qdvc-bibliotheca` is the load-bearing line for the panel
  icon; it must equal the value passed to `set_prgname`.
- `Icon=qdvc-bibliotheca` is used by the launcher/menu. For it to resolve
  outside the app, install the icon into the theme:
  ```
  mkdir -p ~/.local/share/icons/hicolor/scalable/apps
  cp qdvc/data/qdvc-bibliotheca.svg \
     ~/.local/share/icons/hicolor/scalable/apps/qdvc-bibliotheca.svg
  gtk-update-icon-cache ~/.local/share/icons/hicolor 2>/dev/null || true
  ```
  (The *window/taskbar* icon works from the bundled SVG even without this; the
  theme install is what makes the *menu/launcher* entry show it too.)
- Verify with `xprop WM_CLASS` (click the window) — both strings should be
  `qdvc-bibliotheca`. If the panel still shows the old icon, log out/in; MATE
  caches launcher↔WM-class associations per session.
- Refresh + validate:
  ```
  update-desktop-database ~/.local/share/applications
  desktop-file-validate ~/.local/share/applications/qdvc-bibliotheca.desktop
  ```

Packaging note: `qdvc/data/*.svg` must be included as package data (it is
loaded by filesystem path relative to `app.py`, so a zipimport/egg that doesn't
extract data files would break the bundled-icon fallback — ship it unzipped or
adjust the loader to use `importlib.resources`).

---

## 12. Persisted state (config keys)

Beyond the §4.6 list, note `sort_spec` — the multi-key sort, stored as
`[[field_id, ascending_bool], ...]` and round-tripped by
`MainWindow._load_sort_spec` / `_save_sort_spec`. It is applied to the
Catalogue in `_apply_prefs_to_widgets` at startup (before any workspace is
open, which is fine — it's applied again on populate) and saved whenever the
Sort dialog is accepted or cleared. Unknown field ids load harmlessly:
`_sorted_records` skips any key absent from `SORT_KEYS`.

---

## 13. Known constraints & gotchas

- **GTK 3 only.** A GTK 4 port would need: `ImageMenuItem` replacement (already
  done), `Gtk.Toolbar` (removed in 4), `override_font` (removed), and the
  clipboard API (rewritten around `Gdk.Clipboard`).
- **`WM_CLASS` / panel icon**: the app now ships a fallback icon and sets it
  explicitly (see §11), so the window/taskbar icon should render even without a
  themed icon installed. The MATE *launcher* association still relies on
  `set_prgname` matching the `.desktop` `StartupWMClass`. Under Wayland, window
  placement and some class matching are compositor-controlled.
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
