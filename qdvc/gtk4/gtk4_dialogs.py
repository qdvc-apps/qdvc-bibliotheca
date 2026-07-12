"""Async dialog helpers for the GTK4 front-end.

GTK4 has no ``dialog.run()``; every dialog is asynchronous with a continuation
callback. These wrap the common cases (message, confirm, text prompt, folder
chooser, scrollable text report) so the window/handlers can express
"call dialog, act in the callback" concisely.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, Adw  # noqa: E402


def message(parent, heading, body="", *, kind="info"):
    """Show a simple acknowledgement dialog (OK). ``kind`` may be
    'info'/'warning'/'error' — only affects the default response styling."""
    dlg = Adw.MessageDialog(transient_for=parent, modal=True,
                            heading=heading, body=body)
    dlg.add_response("ok", "_OK")
    dlg.set_default_response("ok")
    dlg.set_close_response("ok")
    dlg.present()


def confirm(parent, heading, body, on_confirm, *,
            confirm_label="_OK", destructive=False):
    """Confirm/cancel dialog; calls ``on_confirm()`` only if confirmed."""
    dlg = Adw.MessageDialog(transient_for=parent, modal=True,
                            heading=heading, body=body)
    dlg.add_response("cancel", "_Cancel")
    dlg.add_response("confirm", confirm_label)
    if destructive:
        dlg.set_response_appearance(
            "confirm", Adw.ResponseAppearance.DESTRUCTIVE)
    else:
        dlg.set_response_appearance(
            "confirm", Adw.ResponseAppearance.SUGGESTED)
    dlg.set_default_response("confirm")
    dlg.set_close_response("cancel")

    def _resp(_d, response):
        if response == "confirm":
            on_confirm()
    dlg.connect("response", _resp)
    dlg.present()


def prompt_text(parent, heading, on_ok, *, body="", initial="",
                ok_label="_OK", placeholder=""):
    """Text-entry prompt. Calls ``on_ok(text)`` with the stripped entry text
    when the user confirms. The entry is the dialog's extra child, and Enter
    activates the default (OK) response."""
    dlg = Adw.MessageDialog(transient_for=parent, modal=True,
                            heading=heading, body=body)
    entry = Gtk.Entry()
    entry.set_text(initial)
    if placeholder:
        entry.set_placeholder_text(placeholder)
    entry.set_activates_default(True)
    entry.set_margin_top(6)
    entry.set_margin_bottom(6)
    entry.set_margin_start(6)
    entry.set_margin_end(6)
    dlg.set_extra_child(entry)
    dlg.add_response("cancel", "_Cancel")
    dlg.add_response("ok", ok_label)
    dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dlg.set_default_response("ok")
    dlg.set_close_response("cancel")

    def _resp(_d, response):
        if response == "ok":
            on_ok(entry.get_text().strip())
    dlg.connect("response", _resp)
    dlg.present()


def choose_folder(parent, title, on_chosen, *, initial=None):
    """Async folder chooser using Gtk.FileDialog; calls ``on_chosen(path)``."""
    dialog = Gtk.FileDialog()
    dialog.set_title(title)
    dialog.set_modal(True)
    if initial:
        try:
            dialog.set_initial_folder(Gio.File.new_for_path(str(initial)))
        except Exception:  # noqa: BLE001
            pass

    def _done(dlg, result):
        try:
            folder = dlg.select_folder_finish(result)
        except Exception:  # noqa: BLE001
            return  # cancelled or error
        if folder is not None:
            on_chosen(folder.get_path())
    dialog.select_folder(parent, None, _done)


def choose_file(parent, title, on_chosen, *, initial=None, filters=None):
    """Async open-file chooser; calls ``on_chosen(path)``. ``filters`` is an
    optional list of (name, [patterns]) tuples."""
    dialog = Gtk.FileDialog()
    dialog.set_title(title)
    dialog.set_modal(True)
    if filters:
        store = Gio.ListStore.new(Gtk.FileFilter)
        for name, patterns in filters:
            f = Gtk.FileFilter()
            f.set_name(name)
            for pat in patterns:
                f.add_pattern(pat)
            store.append(f)
        dialog.set_filters(store)
    if initial:
        try:
            dialog.set_initial_folder(Gio.File.new_for_path(str(initial)))
        except Exception:  # noqa: BLE001
            pass

    def _done(dlg, result):
        try:
            gfile = dlg.open_finish(result)
        except Exception:  # noqa: BLE001
            return
        if gfile is not None:
            on_chosen(gfile.get_path())
    dialog.open(parent, None, _done)


def text_report(parent, title, text):
    """Show a scrollable, monospaced, read-only text report in a dialog window
    (used for the validation report). Async; user closes it."""
    win = Adw.Window(transient_for=parent, modal=True, title=title)
    win.set_default_size(560, 480)

    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    toolbar.add_top_bar(header)

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroller.set_vexpand(True)
    view = Gtk.TextView()
    view.set_editable(False)
    view.set_cursor_visible(False)
    view.set_monospace(True)
    view.set_left_margin(10)
    view.set_right_margin(10)
    view.set_top_margin(8)
    view.set_bottom_margin(8)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.get_buffer().set_text(text)
    scroller.set_child(view)
    toolbar.set_content(scroller)

    win.set_content(toolbar)
    win.present()
