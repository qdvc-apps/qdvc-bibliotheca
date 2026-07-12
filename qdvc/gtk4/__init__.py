"""GTK4 / libadwaita front-end package for QDVC Bibliotheca.

Every module here is GTK4-specific and prefixed ``gtk4_``. It is a sibling of
``qdvc/gtk3/`` and sits on the exact same pure core (``qdvc.workspace``,
``qdvc.models``, ``qdvc.apa``, ``qdvc.csl``, ``qdvc.catalogue_sort``,
``qdvc.config``, ``qdvc.platform_utils`` …). Neither front-end imports the
other; the launcher (`qdvc_bibliotheca.py`) picks one at startup based on the
``ui_backend`` config key (or a ``--gtk4`` CLI flag).

Design follows the GNOME Human Interface Guidelines: an ``Adw.Application``
entry point, header bars + a primary menu instead of a menubar/toolbar, an
``Adw.OverlaySplitView`` sidebar, ``Gtk.ColumnView`` for the catalogue table,
``Adw.ViewStack``/``Adw.ViewSwitcher`` for the top-level views, an
``Adw.PreferencesWindow`` with live-apply, and async dialogs (no ``run()``).
"""
