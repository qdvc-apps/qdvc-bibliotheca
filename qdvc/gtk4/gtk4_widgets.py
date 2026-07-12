"""Shared GTK4 view helpers: ColumnView column factories and a small
filter/selection harness used by the Authors and Outlets lists.

GTK4 binds GObjects onto reusable row widgets via ``Gtk.SignalListItemFactory``
(setup builds the widget once; bind fills it per row). These helpers build the
common column kinds (a star toggle, a plain-text cell, a markup cell) so the
list-backed views stay short and consistent.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango  # noqa: E402


def make_text_column(title, attr, *, expand=False, ellipsize=False,
                     markup=False, xalign=0.0):
    """A ColumnView text column bound to ``item.<attr>``. When ``markup`` is
    true the attribute is treated as Pango markup."""
    factory = Gtk.SignalListItemFactory()

    def on_setup(_f, list_item):
        label = Gtk.Label(xalign=xalign)
        if ellipsize:
            label.set_ellipsize(Pango.EllipsizeMode.END)
        list_item.set_child(label)

    def on_bind(_f, list_item):
        label = list_item.get_child()
        value = getattr(list_item.get_item(), attr, "")
        if markup:
            label.set_markup(value or "")
        else:
            label.set_text(str(value) if value not in (None, "") else "")

    factory.connect("setup", on_setup)
    factory.connect("bind", on_bind)
    col = Gtk.ColumnViewColumn(title=title, factory=factory)
    col.set_expand(expand)
    return col


def make_icon_column(title, attr, *, pixel_size=16):
    """A narrow ColumnView column showing a themed icon named by
    ``item.<attr>`` (blank name ⇒ no icon)."""
    factory = Gtk.SignalListItemFactory()

    def on_setup(_f, list_item):
        image = Gtk.Image()
        image.set_pixel_size(pixel_size)
        list_item.set_child(image)

    def on_bind(_f, list_item):
        image = list_item.get_child()
        name = getattr(list_item.get_item(), attr, "") or ""
        if name:
            image.set_from_icon_name(name)
        else:
            image.clear()

    factory.connect("setup", on_setup)
    factory.connect("bind", on_bind)
    col = Gtk.ColumnViewColumn(title=title, factory=factory)
    return col


def make_star_column(attr, on_toggle):
    """A ColumnView column of toggle stars bound to the boolean ``item.<attr>``.
    ``on_toggle(item, new_value)`` is called when the user flips one."""
    factory = Gtk.SignalListItemFactory()

    def on_setup(_f, list_item):
        check = Gtk.CheckButton()
        check.add_css_class("selection-mode")  # renders check-like; fine
        list_item.set_child(check)

    def on_bind(_f, list_item):
        check = list_item.get_child()
        item = list_item.get_item()
        check.set_active(bool(getattr(item, attr, False)))

        # store the handler id so we can block it while syncing
        handler = getattr(check, "_qdvc_handler", None)
        if handler is not None:
            check.disconnect(handler)

        def _toggled(btn):
            on_toggle(item, btn.get_active())
        check._qdvc_handler = check.connect("toggled", _toggled)

    factory.connect("setup", on_setup)
    factory.connect("bind", on_bind)
    col = Gtk.ColumnViewColumn(title="\u2605", factory=factory)
    return col
