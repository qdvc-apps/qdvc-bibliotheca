"""The command layer: Gio.Actions + handlers (GTK4).

Every command is a ``Gio.SimpleAction`` in the ``win.`` scope, installed on the
window. Menu items and header buttons reference actions *by name*, so a single
action drives every surface and one ``set_enabled`` greys them all (and disables
the shortcut). Stateful/parameterised actions back the recent-workspaces list
and view navigation.

Handlers here are thin: they call methods defined on the window
(``open_path``, ``do_import``, ``set_status`` …). The dialog-bearing ones use
the async helpers in ``gtk4_dialogs`` (no ``run()`` in GTK4).
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402


class ActionsMixin:
    """Installs win.* actions and holds their handlers. Mixed into the window,
    so ``self`` is the Adw.ApplicationWindow."""

    def _install_actions(self):
        self._actions = {}

        def add(name, handler, param_type=None):
            if param_type is not None:
                action = Gio.SimpleAction.new(name, param_type)
            else:
                action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)
            self._actions[name] = action
            return action

        # workspace / import
        add("open-workspace", self._act_open_workspace)
        add("close-workspace", self._act_close_workspace)
        add("import", self._act_import)
        add("refresh-workspace", self._act_refresh_workspace)
        # view / records
        add("refresh-view", self._act_refresh_view)
        add("sort", self._act_sort)
        add("rename-record", self._act_rename_record)
        add("validate", self._act_validate)
        add("open-pdf", self._act_open_pdf)
        add("open-epub", self._act_open_epub)
        # app-level
        add("preferences", self._act_preferences)
        add("shortcuts", self._act_shortcuts)
        add("about", self._act_about)
        add("quit", self._act_quit)

        # parameterised: open a specific recent workspace (path as string)
        add("open-recent", self._act_open_recent,
            GLib.VariantType.new("s"))

        # view navigation (switch the Adw.ViewStack). Parameterised by view id.
        add("view-catalogue",
            lambda *_: self._select_view("catalogue"))
        add("view-authors", lambda *_: self._select_view("authors"))
        add("view-outlets", lambda *_: self._select_view("outlets"))
        add("view-doi", lambda *_: self._select_view("doi"))

    def set_action_enabled(self, name, enabled):
        action = self._actions.get(name)
        if action is not None:
            action.set_enabled(bool(enabled))

    # --- handlers (thin; real work lives on the window) ------------------
    def _act_open_workspace(self, *_a):
        self.do_open_workspace()

    def _act_close_workspace(self, *_a):
        self.do_close_workspace()

    def _act_import(self, *_a):
        self.do_import()

    def _act_refresh_workspace(self, *_a):
        self.do_reindex()

    def _act_refresh_view(self, *_a):
        if self.workspace:
            self.catalogue.refresh_current_view()

    def _act_sort(self, *_a):
        self.do_sort()

    def _act_rename_record(self, *_a):
        self.do_rename_record()

    def _act_validate(self, *_a):
        self.do_validate()

    def _act_open_pdf(self, *_a):
        self.open_fulltext("pdf")

    def _act_open_epub(self, *_a):
        self.open_fulltext("epub")

    def _act_preferences(self, *_a):
        self.do_preferences()

    def _act_shortcuts(self, *_a):
        self.do_shortcuts()

    def _act_about(self, *_a):
        self.do_about()

    def _act_quit(self, *_a):
        self.close()

    def _act_open_recent(self, _action, param):
        path = param.get_string()
        if path:
            self.open_path(path)
