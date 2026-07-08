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

To make QDVC Bibliotheca appear in your application menu and dock, install a
`.desktop` file. Create `~/.local/share/applications/qdvc-bibliotheca.desktop`
(for a single user) or `/usr/share/applications/qdvc-bibliotheca.desktop`
(system-wide) with the following contents, adjusting the paths to where you
placed the program:

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
    Keywords=bibliography;references;bibtex;citations;research;

Notes:

- `Exec` must use an absolute path. The trailing `%U` lets you open a workspace
  folder by passing it on the command line or dropping it onto the launcher.
- `Path` sets the working directory so the `qdvc` package is importable; set it
  to the directory that *contains* both `qdvc-bibliotheca.py` and the `qdvc/`
  folder.
- `Icon` can be a named icon from your theme (as above) or an absolute path to
  your own `.png`/`.svg`.
- If you prefer a wrapper, make `qdvc-bibliotheca.py` executable
  (`chmod +x qdvc-bibliotheca.py`, keeping its `#!/usr/bin/env python3` shebang)
  and point `Exec` straight at it.

After creating the file, refresh the desktop database so it shows up
immediately:

    update-desktop-database ~/.local/share/applications

You can validate the entry with:

    desktop-file-validate ~/.local/share/applications/qdvc-bibliotheca.desktop

## Workspace layout

    (workspace root)/
        bibtex/A..Z/<bibliotheca_id>.bib     authoritative reference data
        markdown/A..Z/<bibliotheca_id>.md    your notes + YAML frontmatter
        my_works/*.yml                       your own projects

`bibliotheca_id` follows `AuthorSurnamesYear_suffix`
(e.g. `SmithJones2025_MISQ`).

### Markdown frontmatter

    ---
    pdf: /path/to/fulltext.pdf
    epub: /path/to/fulltext.epub
    my_works:
      - project1
    ---
    Free-form Markdown notes go here.

### my_works YAML

    name: My Dissertation
    published_as: SmithJones2025_MISQ   # optional
    cites:
      - SmithJones2025_MISQ
      - Jones2009_JAIS

## Features

- **Catalogue tab** — three-pane master/detail:
  - Sidebar (with icons): All articles / By type / My works (filters the
    table). Double-click a work — or use the +/edit buttons at the bottom — to
    manage it.
  - Master: sortable, filterable table of records
  - Detail: APA 7 reference (with **Copy rich** and **Copy plain text**) and an
    editable Markdown notes box (auto-saves on record change / close)
- **DOI Lookup tab** — jump straight to a record by its DOI, or see
  `Sorry, no records found for DOI = …`
- **My works editing** — add/remove cited records with a two-list picker and
  set the published version, written back to the work's YAML file.
- **Menubar**
  - *File*: Open / Close / Recent workspaces, Import `.bib`, Quit
  - *Edit*: Preferences (editor font, file-manager command, startup + autosave)
  - *View*: toggle sidebar (F9) / detail pane (F10), switch tabs (Alt+1/Alt+2),
    refresh current view (F5)
  - *Record*: reveal `.bib`/`.md` in the file manager, rename Bibliotheca ID
    (F2) — renames both paired files and updates all `my_works` references
  - *Tools*: Validate workspace (orphan notes, missing full-text, dangling
    citations, duplicate DOIs)
  - *Help*: Keyboard shortcuts, About
- **Toolbar** — Rescan and Import, with icons.
- **Import** — a `.bib` file may contain multiple entries; each is filed under
  the correct `bibtex/<shard>/` folder using its citation key as the
  `bibliotheca_id`. Existing IDs are never overwritten.
- Fast re-opening of large workspaces via a cached index
  (`.qdvc-index.json` in the workspace root)
- Config stored at `$XDG_CONFIG_HOME/qdvc-bibliotheca/config.yml`

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+O   | Open workspace |
| Ctrl+I   | Import `.bib` |
| Ctrl+Q   | Quit |
| Ctrl+,   | Preferences |
| F9 / F10 | Toggle sidebar / detail pane |
| Alt+1 / Alt+2 | Catalogue / DOI Lookup tab |
| F5       | Refresh current view |
| F2       | Rename Bibliotheca ID |
| Ctrl+?   | Shortcuts list |

## Notes on the cache

The index caches lightweight display fields per record. Full BibTeX parsing
and note reading happen lazily when a record is selected. If files change
outside the app, use the Rescan toolbar button (or **View → Refresh** to
re-apply the current sidebar filter without a full disk rescan).
