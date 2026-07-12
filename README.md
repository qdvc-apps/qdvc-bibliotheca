# QDVC Bibliotheca

A desktop app for academics — researchers, scholars, students — to manage a
personal collection of articles, papers, and books. Built with Python 3 and
GTK 3.

Your library lives as plain files on disk: an authoritative BibTeX file per
work (the reference data, exactly as it comes from the publisher) alongside a
Markdown file for your own notes and full-text links. Nothing is locked in a
database, so the whole collection stays portable, greppable, and friendly to
Git or Syncthing.

## What it does

- **Catalogue** — browse and filter your library in a three-pane view: pick a
  filter on the left (all works, by type, by full-text availability, by DOI
  status, by project, or by a starred author or journal — each filter showing
  the number of matching articles), scan the sortable table in the middle (with
  a J-Flags column and a nickname-prefaced Outlet), and read the APA-7 reference
  and your syntax-highlighted Markdown notes on the right. Sort by several keys
  at once (e.g. Year descending, then Author ascending). Copy references as rich
  text or plain text in one click.
- **Authors** — a list of every author, derived automatically from your
  BibTeX. Star the ones you follow and they become quick filters in the
  Catalogue.
- **Journals** — a list of every journal, derived automatically from your
  BibTeX. Star the ones you follow (they become quick filters in the
  Catalogue), give a journal a short nickname, and tag it with one or more
  J-Flags (e.g. FT50, A*) chosen from presets you configure in Preferences.
- **DOI lookup** — paste a DOI and jump straight to the matching record.
- **My works** — track your own papers/projects and which references each one
  cites. Allocate any record to one or more works straight from its right-click
  menu.
- **Full-text** — attach a PDF or EPUB to any record and open it in your
  system viewer.
- **Import** — paste BibTeX or load a `.bib` file; multi-entry files are split
  and filed automatically, and you can allocate the new records to a work in the
  same step.

## Requirements

- Python 3.10+
- PyGObject with GTK 3 (`python3-gi`, `gir1.2-gtk-3.0`)
- PyYAML
- `bibtexparser` (optional — a built-in fallback parser is used if it's absent)

## Install & run

```sh
# Debian/Ubuntu
sudo apt install python3-gi gir1.2-gtk-3.0 python3-yaml
pip install bibtexparser   # optional

python3 qdvc-bibliotheca.py
```

To add it to your application menu and taskbar, see the desktop-launcher
instructions in [MAINTENANCE.md](MAINTENANCE.md).

## Documentation

- **[MAINTENANCE.md](MAINTENANCE.md)** — architecture, module layout, data
  formats, and guidance for developing and maintaining the codebase.

## License

See the repository for license details.
