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
  - Sidebar: All articles / By type / My works (filters the table)
  - Master: sortable, filterable table of records
  - Detail: APA 7 reference (with **Copy rich** and **Copy plain text**) and an
    editable Markdown notes box (auto-saves on record change / close)
- **DOI Lookup tab** — jump straight to a record by its DOI, or see
  `Sorry, no records found for DOI = …`
- **File → Open/Close Workspace**, recent-workspaces list, and rescan
- Fast re-opening of large workspaces via a cached index
  (`.qdvc-index.json` in the workspace root)
- Config stored at `$XDG_CONFIG_HOME/qdvc-bibliotheca/config.yml`

## Notes on the cache

The index caches lightweight display fields per record. Full BibTeX parsing
and note reading happen lazily when a record is selected. If files change
outside the app, use **File → Rescan Workspace**.
