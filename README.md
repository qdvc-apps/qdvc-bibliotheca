# QDVC Bibliotheca

A desktop app for academics — researchers, scholars, students — to manage a
personal collection of articles, papers, and books. Built with Python 3 and
GTK, with a choice of two interfaces: a classic **GTK 3** UI (the default) and a
modern **GTK 4 / libadwaita** UI.

Your library lives as plain files on disk: an authoritative BibTeX file per
work (the reference data, exactly as it comes from the publisher) alongside a
Markdown file for your own notes and full-text links. Nothing is locked in a
database, so the whole collection stays portable, greppable, and friendly to
Git or Syncthing.

## What it does

- **Catalogue** — browse and filter your library in a three-pane view: pick a
  filter on the left (all works, by type — including Proceedings — by full-text
  availability, by DOI status, by project, or by a starred author or outlet,
  each filter showing the number of matching articles), scan the sortable table
  in the middle (with a J-Flags column and a nickname-prefaced Outlet), and read
  the reference — rendered with a built-in style (APA 7 or ACIS) or a custom
  CSL style you pick from a dropdown; the ACIS style also shows the matching
  in-text citation (both parenthetical and narrative forms) — alongside your
  syntax-highlighted Markdown notes on
  the right. Sort by several keys at once (e.g. Year descending, then Author
  ascending). Copy references as rich text or plain text in one click.
  Right-click a record (or press the Menu key) for actions including "Go to
  outlet", which jumps to the Outlets tab and highlights that outlet.
- **Authors** — a list of every author, derived automatically from your
  BibTeX. Star the ones you follow and they become quick filters in the
  Catalogue.
- **Outlets** — a list of every publication outlet (journals and proceedings),
  derived automatically from your BibTeX. Star the ones you follow (they become
  quick filters in the Catalogue), give an outlet a short nickname, and tag it
  with one or more J-Flags (e.g. FT50, A*) chosen from presets you configure in
  Preferences.
- **DOI lookup** — paste a DOI and jump straight to the matching record.
- **My works** — track your own papers/projects and which references each one
  cites. Allocate any record to one or more works straight from its right-click
  menu.
- **Full-text** — attach a PDF or EPUB to any record and open it in your
  system viewer.
- **Import** — paste BibTeX or load a `.bib` file; multi-entry files are split
  and filed automatically, entries whose DOI already exists are skipped to
  avoid duplicates, and you can allocate the new records to a work in the same
  step.

## Requirements

- Python 3.10+
- PyGObject, plus **one** of the two toolkits:
  - GTK 3 (`python3-gi`, `gir1.2-gtk-3.0`) — the default interface, or
  - GTK 4 + libadwaita (`gir1.2-gtk-4.0`, `gir1.2-adw-1`) — the modern interface
- PyYAML
- `bibtexparser` (optional — a built-in fallback parser is used if it's absent)
- `citeproc-py` (optional — enables rendering references with custom CSL
  styles; without it the built-in APA 7 and ACIS renderers are the only options)

## Install & run

```sh
# Debian/Ubuntu — GTK 3 (default)
sudo apt install python3-gi gir1.2-gtk-3.0 python3-yaml
pip install bibtexparser   # optional
pip install citeproc-py    # optional (custom CSL citation styles)

python3 qdvc-bibliotheca.py
```

To use the GTK 4 / libadwaita interface, also install its runtime and either
pass `--gtk4` or set the interface in Preferences (it takes effect on the next
launch):

```sh
sudo apt install gir1.2-gtk-4.0 gir1.2-adw-1

python3 qdvc-bibliotheca.py --gtk4    # or --gtk3 to force the classic UI
```

The chosen interface is remembered in the config (`ui_backend`); the default is
GTK 3. Either UI's Preferences window can switch to the other.

To add it to your application menu and taskbar, see the desktop-launcher
instructions in [MAINTENANCE.md](MAINTENANCE.md).

## Documentation

- **[MAINTENANCE.md](MAINTENANCE.md)** — architecture, module layout, data
  formats, and guidance for developing and maintaining the codebase.
- **[MAINTENANCE_GTK3_GTK4.md](MAINTENANCE_GTK3_GTK4.md)** — an element-by-element
  comparison of the GTK 3 and GTK 4 / libadwaita interfaces.

## License

See the repository for license details.
