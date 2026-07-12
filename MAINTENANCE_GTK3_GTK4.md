# MAINTENANCE_GTK3_GTK4.md

An element-by-element comparison of how **QDVC Bibliotheca**'s user interface is
built in **GTK 3** (the `qdvc/gtk3/` package) versus **GTK 4 / libadwaita** (the
`qdvc/gtk4/` package), and *why* each GTK4 choice was made. Both UIs sit on the
same GTK-free core (`qdvc/workspace.py`, `models.py`, `bibtex.py`,
`markdown_io.py`, `naming.py`, `apa.py`, `csl.py`, `catalogue_sort.py`,
`config.py`, `platform_utils.py`, and the shared `ui_prefs.py`); only the view
layer differs. Neither front-end imports the other.

It doubles as a worked example for porting a three-pane GTK3/PyGObject
reference manager to a parallel GTK4/libadwaita UI. Where a decision follows the
GNOME Human Interface Guidelines (HIG), that is called out.

> Scope note: this document is about the *view* layer. The model, YAML/BibTeX
> handling, naming rules, sort logic, APA/CSL rendering, and settings are
> unchanged and shared; neither UI reimplements them.

## Contents

- Choosing the backend (dispatcher & config)
- Application object & entry point
- Actions, accelerators & the command layer
- Menubar / toolbar → header bars, primary menu & view switcher
- Top-level views: Notebook → Adw.ViewStack
- Catalogue window layout & Pane 1 (navigation) sidebar
- Catalogue Pane 2 (record table): TreeView → ColumnView + factories
- Catalogue Pane 3 (detail): reference, CSL picker, notes
- The four secondary views (Authors / Outlets / DOI)
- Preferences window
- Dialogs & the death of run()
- Clipboard (rich copy)
- List models & data binding cheat-sheet

---

## Choosing the backend (dispatcher & config)

The toolkit is selected **before any GTK is imported**, so only the chosen
front-end is loaded. `qdvc_bibliotheca.py` is a backend-agnostic dispatcher that
resolves the backend in priority order: a `--gtk3` / `--gtk4` CLI flag; then the
`ui_backend` key in the config; then the default, `gtk3`. It preserves `argv[0]`
(GApplication expects a program name there) and, if the GTK4 import fails (e.g.
libadwaita is absent), prints a note and falls back to GTK3.

`Config.ui_backend` (in the pure `config.py`) validates and normalises the value
so a corrupt or hand-edited config can never leave the dispatcher without a
valid backend. The selector appears in **both** UIs' preferences, so a GTK3 user
can switch forward and a GTK4 user can switch back; changing it takes effect on
the next launch.

## Application object & entry point

**GTK3** (`gtk3_app.Application`): a plain `Gtk.Application` (id
`org.qdvc.Bibliotheca`, `HANDLES_OPEN`); the window is built in `do_activate`,
accelerators are attached per-widget via a `Gtk.AccelGroup` on the window.

**GTK4** (`gtk4_app.Application`): an **`Adw.Application`** — the idiomatic GNOME
entry point that also initialises libadwaita styling. It owns the app id, the
action scopes, window lifecycle, and the main loop, and registers accelerators
once via `set_accels_for_action("win.<name>", [...])` (the `ACCELS` table). The
window is built in `do_activate` and shown with `present()`.

## Actions, accelerators & the command layer

This is the most consequential difference and it ripples through the menu,
header bars, and context menus.

**GTK3** wires each widget to a handler with `connect("activate"/"clicked", …)`
and binds keys through a `Gtk.AccelGroup`. A command in both the menu and the
toolbar is connected twice, and enabling/disabling it means calling
`set_sensitive` on each widget (`_update_actions_sensitivity`).

**GTK4** (`gtk4_actions.ActionsMixin`) uses the **`Gio.Action`** system. Every
command is a `Gio.SimpleAction` installed on the window under the `win.` scope
(`_install_actions`). Menu items and header buttons reference the action *by
name* (`win.import`, `win.sort`, …), so one action drives every surface;
`set_action_enabled(name, bool)` greys every bound item and disables its
shortcut at once. The recent-workspaces entries are a **parameterised**
`win.open-recent` action carrying the path as a string target, replacing GTK3's
per-item lambdas.

## Menubar / toolbar → header bars, primary menu & view switcher

**GTK3** (`gtk3_main_window`): a `Gtk.MenuBar` (File/Edit/View/Tools/Help) plus a
`Gtk.Toolbar`, both packed above a `Gtk.Notebook`, and a `Gtk.Statusbar` below.

**GTK4** (`gtk4_headerbar.HeaderBarMixin`): GNOME apps avoid menubars and
toolbars. Instead:

- The window's top bar is a single **`Adw.HeaderBar`** whose **title widget is
  an `Adw.ViewSwitcher`** bound to the view stack, so switching the four
  top-level views is a first-class HIG control rather than a notebook tab strip.
- A **primary menu** — a `Gtk.MenuButton` with the `open-menu-symbolic`
  hamburger and `set_primary(True)` — holds the commands that don't warrant a
  header button. Its `Gio.Menu` is split into sections (workspace actions with a
  Recent submenu; record actions; and, per the menus HIG, a **final section of
  Preferences, Keyboard Shortcuts, About**).
- The most common entry actions (Open Workspace, Import) are header buttons.
- The Catalogue's own sidebar and content sides each get a small `Adw.HeaderBar`
  inside an `Adw.ToolbarView` (Sort/Rescan on the sidebar header; the sidebar
  toggle and Open-PDF on the content header).
- A slim status line lives in the window's bottom bar (GTK4 has no
  `Gtk.Statusbar`). The GTK3 "toolbar style" preference is dropped — it is
  meaningless without a toolbar.

## Top-level views: Notebook → Adw.ViewStack

**GTK3** puts Catalogue / Authors / Outlets / DOI Lookup in a `Gtk.Notebook`;
`notebook.set_current_page(n)` switches, `switch-page` reacts.

**GTK4** uses an **`Adw.ViewStack`** (`gtk4_window`) with the same four children,
added via `add_titled_with_icon` under stable ids (`catalogue`/`authors`/
`outlets`/`doi`). The `Adw.ViewSwitcher` in the header drives it; `win.view-*`
actions (with `<Alt>1..4` accels) select programmatically; the window watches
`notify::visible-child-name` to refresh action sensitivity.

## Catalogue window layout & Pane 1 (navigation) sidebar

**GTK3** (`gtk3_catalogue_tab`): two nested `Gtk.Paned`s; Pane 1 is a
`Gtk.TreeView` over a `Gtk.TreeStore` addressed by integer columns, with a
second right-aligned count column, painted via cell attributes.

**GTK4** (`gtk4_catalogue_tab`): the view is an **`Adw.OverlaySplitView`** whose
**sidebar** is Pane 1 and whose **content** is a `Gtk.Paned` of Panes 2 and 3.
Pane 1 selects what Pane 2 lists — textbook top-level navigation — so a sidebar
(with the `.navigation-sidebar` style class) is the correct pattern, not a
utility pane. It is a **`Gtk.ListView`** over a **`Gtk.TreeListModel`** of
`NavItem` GObjects (`gtk4_common`); a `Gtk.SignalListItemFactory` builds each
row (a `Gtk.TreeExpander` wrapping icon + label + count). The node set,
grouping, and per-row article counts (`_compute_sidebar_counts`) are identical
to GTK3, including the transient italic "Query results" node used when jumping
from a non-starred author.

Work management (New / Edit / Open-YAML) moves from the GTK3 sidebar
right-click on a `Gtk.TreeView` row to a GTK4 `Gtk.GestureClick` (secondary
button) that resolves the `NavItem` under the pointer (each row is tagged in
`bind`) and shows a `Gtk.PopoverMenu` backed by a `catnav.*` action group.

## Catalogue Pane 2 (record table): TreeView → ColumnView + factories

**GTK3**: a multi-column `Gtk.TreeView` over a `Gtk.ListStore` wrapped in a
`Gtk.TreeModelFilter`; columns addressed by index; the Outlet cell uses the
`markup=` attribute so a nickname can be bold.

**GTK4**: a **`Gtk.ColumnView`** — the right widget for a genuine data table —
over a `Gtk.SingleSelection(Gtk.FilterListModel(Gio.ListStore(RecordItem)))`.
Each of the eight columns (PDF icon + Bibliotheca ID, Author, Year, J-Flags,
Outlet, Title, Type) is a `Gtk.ColumnViewColumn` with a
`Gtk.SignalListItemFactory`; the Outlet column binds Pango markup, the icon
column a themed `Gtk.Image`. The derived cells (J-Flags string,
nickname-prefaced Outlet markup) are computed once when building each
`RecordItem`. Search is a `Gtk.CustomFilter` re-run with `filter.changed(...)`
(matching the same visible fields as GTK3). **Sorting stays in the core**: every
fill runs the records through the multi-key `_sorted_records` and splices the
store — it is not a sortable-model feature. Selection → detail is
`SingleSelection`'s `notify::selected`. The right-click record menu is a
`Gtk.GestureClick` + `Gtk.PopoverMenu` over a `cat.*` action group (with a
parameter-free action per command, emitting the same `record-action` strings the
window already handles), replacing GTK3's `Gtk.Menu` of lambda-connected
`Gtk.ImageMenuItem`s.

## Catalogue Pane 3 (detail): reference, CSL picker, notes

The layout is the same in both: a Reference area with a citation-style picker, a
rich/plain copy pair and an Open-PDF button, then a Markdown notes editor and a
status line. GTK4 changes only the mechanics:

- The style picker is a **`Gtk.DropDown`** over a `Gio.ListStore` of `TextItem`s
  (APA sentinel + each workspace CSL filename) instead of a `Gtk.ComboBoxText`;
  selection is by index, so the tab keeps an ordered id list to map between the
  two.
- Notes use a `Gtk.TextView` + the shared `MarkdownHighlighter`
  (`gtk4_md_highlight`, a near-verbatim copy — the `Gtk.TextBuffer` tag APIs are
  identical across GTK3/4). Auto-save on record change is unchanged.
- The reference label uses `set_wrap`/`set_wrap_mode` (GTK4 spelling) and the
  APA-or-CSL rendering is the shared core (`apa` / `csl`).

## The four secondary views (Authors / Outlets / DOI)

**GTK3**: each is a `Gtk.Box` with a `Gtk.TreeView`.

**GTK4** (`gtk4_authors_tab`, `gtk4_outlets_tab`, `gtk4_doi_tab`): Authors and
Outlets are `Gtk.ColumnView`s over a `Gtk.SingleSelection(Gtk.FilterListModel(
Gio.ListStore))` with a shared column-factory helper (`gtk4_widgets`: text,
icon, and toggle-star columns). Search + "starred only" drive a
`Gtk.CustomFilter`; row activation and the bottom button emit the same
`show-*-works` signals; the star toggle persists via the workspace and emits
`star-changed`. Outlets keeps its nickname prompt and J-Flags checklist as async
`Adw` dialogs, and `reveal_outlet` selects + `scroll_to`s the row. The DOI view
is a near-direct translation (`append`, `set_wrap`).

## Preferences window

**GTK3** (`gtk3_preferences`): a `Gtk.Dialog` with a `Gtk.Notebook`
(General / J-Flags / CSL), Save/Cancel.

**GTK4** (`gtk4_preferences`): an **`Adw.PreferencesWindow`** — the standard
GNOME container. Each GTK3 tab becomes an `Adw.PreferencesPage` of
`Adw.PreferencesGroup`s and rows (`Adw.EntryRow`, `Adw.SwitchRow`,
`Adw.ComboRow`, `Adw.ActionRow` + `Gtk.FontButton`). Two deliberate behavioural
changes, both HIG-driven:

- **Live-apply, no Save/Cancel.** Each control writes its setting and calls the
  window's `on_apply` immediately; the config persists on change. The GTK3
  snapshot/save machinery is gone.
- **The toolbar-style control is dropped** (no toolbar). Every other persisted
  preference remains, and the GTK3/GTK4 **backend selector** is present as an
  `Adw.ComboRow` with a "takes effect after restart" subtitle.

The J-Flags preset table is an editable `Gtk.ColumnView` (an entry + a spin
button per row, committing on change); the CSL page is an informational list of
the workspace's style files.

## Dialogs & the death of run()

**`dialog.run()` is gone in GTK4.** Every GTK3 modal flow
(`resp = dlg.run(); dlg.destroy()`) becomes **asynchronous** with a continuation
callback:

- Confirms/messages/text-prompts use **`Adw.MessageDialog`** with
  `add_response(...)` + a `response` handler (`gtk4_dialogs.message` /
  `confirm` / `prompt_text`).
- File/folder selection uses **`Gtk.FileDialog`** with `open`/`select_folder`
  and a finish-in-callback (`gtk4_dialogs.choose_file` / `choose_folder`).
- The structured dialogs (Import, Sort, Allocate, Edit Work) are `Adw.Window`s
  with Cancel/confirm buttons in an `Adw.HeaderBar` (modern action placement)
  and deliver their result through an `on_*` callback rather than a return
  value. The window's handlers are written as "open dialog, act in the
  callback".

## Clipboard (rich copy)

**GTK3** puts `text/html` + plain text on the `Gtk.Clipboard` singleton via a
kept-alive owner (working around a PyGObject `set_with_data` crash).

**GTK4** uses `widget.get_clipboard()`: plain copy is `clipboard.set(text)`;
rich copy builds a `Gdk.ContentProvider` union of an HTML provider
(`new_for_bytes("text/html", …)`) and a plain-text provider, falling back to
plain text on any error. The HTML is produced by the shared
`catalogue_sort.markup_to_html`.

## List models & data binding cheat-sheet

| Concern | GTK3 | GTK4 |
| --- | --- | --- |
| List store | `Gtk.ListStore` (typed columns) | `Gio.ListStore` of a GObject row (`RecordItem`, `_AuthorItem`, …) |
| Tree store | `Gtk.TreeStore` | `Gio.ListStore` + `Gtk.TreeListModel` over a `children` list (`NavItem`) |
| Row addressing | integer column index | object attribute (`item.author`) |
| Rendering | `Gtk.TreeViewColumn` + `set_cell_data_func` / attributes | `Gtk.SignalListItemFactory` (`setup` + `bind`) |
| Multi-column table | `Gtk.TreeView` | `Gtk.ColumnView` + `Gtk.ColumnViewColumn` |
| Expander | `Gtk.TreeView` built-in | `Gtk.TreeExpander` in the row |
| Filtering | `Gtk.TreeModelFilter` + visible-func + `refilter()` | `Gtk.FilterListModel` + `Gtk.CustomFilter` + `filter.changed(...)` |
| Selection | `tree.get_selection()` `changed` | `Gtk.SingleSelection` `notify::selected` |
| Activation | `row-activated` | `Gtk.ColumnView`/`ListView::activate` |
| In-place row refresh | rewrite store cells | mutate object + `items_changed(i, 1, 1)` |
| Context menu | `Gtk.Menu` + `popup_at_pointer` | `Gtk.GestureClick` + `Gtk.PopoverMenu` + action group |
| Dialog result | `dlg.run()` return value | `on_*` callback continuation |

The guiding principle: in GTK3 you *paint* a model's cells on demand; in GTK4
you *bind* model GObjects onto reusable row widgets, and most "refresh" logic
becomes a property set plus a targeted `items_changed` or a factory re-set.
