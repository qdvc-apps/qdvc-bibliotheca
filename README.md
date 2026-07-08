# QDVC Bibliotheca

A GTK 3 desktop application for academics to manage a personal collection of
articles, papers, and books.

## Requirements

- Python 3.10+
- PyGObject with GTK 3 (`python3-gi`, `gir1.2-gtk-3.0`)
- PyYAML
- (optional) `bibtexparser` — improves BibTeX parsing; a built-in fallback
  parser is used if it is absent.

### Install dependencies

Debian/Ubuntu:

    sudo apt install python3-gi gir1.2-gtk-3.0 python3-yaml
    pip install bibtexparser   # optional

Fedora:

    sudo dnf install python3-gobject gtk3 python3-pyyaml
    pip install bibtexparser   # optional

## Run

    python3 qdvc-bibliotheca.py

## Desktop launcher (Linux)

To make QDVC Bibliotheca appear in your application menu and show its own icon
in the MATE panel / taskbar (not a generic window icon), install a `.desktop`
file **and** an icon, and make sure the launcher's `StartupWMClass` matches the
running window.

### 1. Install an icon

The app asks the icon theme for an icon named `qdvc-bibliotheca`. Install your
own PNG/SVG under that name so both the window and the panel can find it:

    # a 256x256 PNG works well; SVG is even better
    mkdir -p ~/.local/share/icons/hicolor/256x256/apps
    cp my-icon.png ~/.local/share/icons/hicolor/256x256/apps/qdvc-bibliotheca.png

    # (for SVG, use .../scalable/apps/qdvc-bibliotheca.svg instead)
    gtk-update-icon-cache ~/.local/share/icons/hicolor 2>/dev/null || true

If you skip this, the app falls back to a themed stock icon, but the panel may
then show a generic icon.

### 2. Create the .desktop file

Create `~/.local/share/applications/qdvc-bibliotheca.desktop` (single user) or
`/usr/share/applications/qdvc-bibliotheca.desktop` (system-wide), adjusting the
paths to where you placed the program:

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

The two lines that make the **panel icon** correct:

- `Icon=qdvc-bibliotheca` — must match the icon file name you installed in
  step 1 (and the name the app sets internally). This is what the launcher and
  the panel display.
- `StartupWMClass=qdvc-bibliotheca` — this is the crucial one for MATE. The app
  sets its program name (and therefore the window's `WM_CLASS`) to
  `qdvc-bibliotheca`; MATE's window list matches the running window to this
  launcher by that class. Without a matching `StartupWMClass`, MATE cannot tell
  that the window belongs to the launcher and falls back to the generic window
  icon.

You can confirm the running window's class with:

    xprop WM_CLASS      # then click the QDVC window

Both strings it prints should be `qdvc-bibliotheca`.

Other notes:

- `Exec` must use an absolute path. The trailing `%U` lets you open a workspace
  folder by passing it on the command line or dropping it onto the launcher.
- `Path` sets the working directory so the `qdvc` package is importable; set it
  to the directory that *contains* both `qdvc-bibliotheca.py` and the `qdvc/`
  folder.
- If you prefer a wrapper, make `qdvc-bibliotheca.py` executable
  (`chmod +x qdvc-bibliotheca.py`, keeping its `#!/usr/bin/env python3` shebang)
  and point `Exec` straight at it.

### 3. Refresh and validate

    update-desktop-database ~/.local/share/applications
    desktop-file-validate ~/.local/share/applications/qdvc-bibliotheca.desktop

If the panel still shows the old icon, log out and back in (MATE caches
launcher/WM-class associations for the session).

## Workspace layout

    (workspace root)/
        bibtex/A..Z/<bibliotheca_id>.bib     authoritative reference data
        markdown/A..Z/<bibliotheca_id>.md    your notes + YAML frontmatter
        my_works/*.yml                       your own projects
        authors/<SURNAME_GivenNames>.yml     derived author records + stars

`bibliotheca_id` follows `AuthorSurnamesYear_suffix`
(e.g. `SmithJones2025_MISQ`).

### Markdown frontmatter

    ---
    pdf: S/SmithJones2025.pdf     # relative to the full-text library path
    epub: S/SmithJones2025.epub   # (absolute if outside that folder)
    my_works:
      - project1
    ---
    Free-form Markdown notes go here.

The `pdf` / `epub` values are written by the **Set PDF / Set EPUB** buttons and
are stored relative to the "Full-text library path" set in Preferences.

### authors YAML

    id: ZUBOFF_Shoshana
    surname: Zuboff
    given_names: Shoshana
    starred: true

Author records are derived automatically from the BibTeX on load; new ones are
written the first time an author is seen. Editing the `starred` flag is done
from the Authors tab, but the files are plain YAML you can also edit by hand.

### my_works YAML

    name: My Dissertation
    published_as: SmithJones2025_MISQ   # optional
    cites:
      - SmithJones2025_MISQ
      - Jones2009_JAIS

## Features

- **Catalogue tab** — three-pane master/detail:
  - Sidebar (with icons): All articles / By type / My works / Starred authors,
    each filtering the table. Right-click **My works** to add a work;
    right-click a work to edit it (or double-click it). When you view a
    non-starred author's works (from the Authors tab), a transient italic
    *"Query"* item appears at the very bottom and is selected, so Pane 1 stays
    consistent with Pane 2; it disappears as soon as you pick anything else.
  - Master: sortable, filterable table with columns *(PDF) / Bibliotheca ID /
    Author / Year / Outlet / Title / Type*. The **Outlet** column shows the
    journal for journal articles, the book title for book chapters, and an em
    dash otherwise. Articles with a PDF on file show a PDF icon in the first
    column. **Right-click a row** to Set PDF / Set EPUB, Open PDF, or remove
    the full-text link(s).
  - Detail: APA 7 reference (with **Copy rich** and **Copy plain text**), an
    editable Markdown notes box (auto-saves on record change / close), and an
    **Open PDF** button (PDF icon) shown when a PDF is attached.
- **Authors tab** — a unique list of authors derived from your BibTeX. Each
  author gets a stable id of the form `SURNAME_GivenNames` (e.g.
  `ZUBOFF_Shoshana`) and a persisted record at `authors/<id>.yml`. Toggle the
  star column to mark favourites; starred authors appear in the Catalogue
  sidebar. Double-click an author (or use *Show works in Catalogue*, which has
  a magnifier icon) to filter the catalogue to that author's works.
- **DOI Lookup tab** — jump straight to a record by its DOI, or see
  `Sorry, no records found for DOI = …`
- **My works editing** — add/remove cited records with a two-list picker and
  set the published version, written back to the work's YAML file.
- **Full-text library** — set a base folder in Preferences ("Full-text library
  path"). When you attach a PDF/EPUB, the file picker opens there by default
  and the path saved into the article's Markdown frontmatter is stored
  *relative* to that folder (falling back to an absolute path, with a notice,
  if the file is outside it). This keeps a workspace portable. Attached PDFs
  can be opened with the system viewer from the detail pane, the row's
  right-click menu, or the Record menu.
- **Menubar**
  - *File*: Open / Close / Recent workspaces, Import BibTeX, Refresh Workspace,
    Quit
  - *Edit*: Preferences (editor font, file-manager command, full-text library
    path, startup + autosave, and toolbar label placement)
  - *View*: toggle sidebar (F9) / detail pane (F10), switch tabs
    (Alt+1/2/3), refresh current view (F5)
  - *Record*: reveal `.bib`/`.md` in the file manager, open `.bib`/`.md` in the
    system text editor, open the PDF in the system viewer, rename Bibliotheca
    ID (F2) — renaming moves both paired files and updates all `my_works`
    references
  - *Tools*: Validate workspace (orphan notes, BibTeX-key ≠ Bibliotheca-ID
    mismatches, missing full-text, dangling citations, duplicate DOIs); the
    report uses your Notes editor font
  - *Help*: Keyboard shortcuts, About
- **Toolbar** — Rescan and Import, with icons; choose labels-beside or
  labels-below icons in Preferences.
- **Import** — a pop-up lets you either paste BibTeX text directly or load a
  `.bib` file into the editor for review before importing. Multiple entries
  are supported; each is filed under the correct `bibtex/<shard>/` folder using
  its citation key as the `bibliotheca_id`. Existing IDs are never overwritten.
- Fast re-opening of large workspaces via a cached index
  (`.qdvc-index.json` in the workspace root)
- Config stored at `$XDG_CONFIG_HOME/qdvc-bibliotheca/config.yml`

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+O   | Open workspace |
| Ctrl+I   | Import BibTeX |
| Ctrl+Q   | Quit |
| Ctrl+,   | Preferences |
| F9 / F10 | Toggle sidebar / detail pane |
| Alt+1 / Alt+2 / Alt+3 | Catalogue / Authors / DOI Lookup tab |
| F5       | Refresh current view |
| F2       | Rename Bibliotheca ID |
| Ctrl+?   | Shortcuts list |

## Notes on the cache

The index caches lightweight display fields per record (including whether a
PDF/EPUB is attached, so the PDF column renders without re-reading every notes
file). Full BibTeX parsing and note reading happen lazily when a record is
selected. If files change outside the app, use the Rescan toolbar button (or
**View → Refresh** to re-apply the current sidebar filter without a full disk
rescan).
