"""Small GTK3 widget and clipboard helpers.

These are toolkit-specific building blocks shared by the GTK3 tabs: an
icon+label menu item that avoids the deprecated ``Gtk.ImageMenuItem``, Pango
style-enum accessors that degrade gracefully under the test stub, and a
rich-text (text/html + text/plain) clipboard setter that works around a
PyGObject crash. Kept separate so the individual tab modules stay focused and
a future GTK4 port has an obvious place to provide equivalents.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GObject  # noqa: E402


def img_menu_item(label, icon_name):
    """A menu item with a leading icon, built without deprecated
    Gtk.ImageMenuItem (removed in GTK4)."""
    item = Gtk.MenuItem()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
    box.pack_start(img, False, False, 0)
    box.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0)
    item.add(box)
    return item


def pango_style_normal() -> int:
    try:
        return int(Pango.Style.NORMAL)
    except Exception:  # noqa: BLE001
        return 0


def pango_style_italic() -> int:
    try:
        return int(Pango.Style.ITALIC)
    except Exception:  # noqa: BLE001
        return 2


# text/html target info id used in the target table below.
_TARGET_HTML = 0
_TARGET_TEXT = 1

# Keep a strong reference to the owner so it is not garbage-collected while it
# owns the clipboard; otherwise the "get" callback fires on freed memory
# (which is what produced the `free(): invalid pointer` crash).
_clipboard_owner = None


class _ClipboardOwner(GObject.Object):
    """A GObject that owns the clipboard and serves target data on request."""

    def __init__(self, plain_text: str, html: str):
        super().__init__()
        self.plain_text = plain_text
        self.html_bytes = html.encode("utf-8")

    def get_func(self, _clipboard, selection_data, info, _user_data=None):
        if info == _TARGET_HTML:
            selection_data.set(
                Gdk.Atom.intern("text/html", False), 8, self.html_bytes)
        else:
            selection_data.set_text(self.plain_text, -1)

    def clear_func(self, _clipboard, _user_data=None):
        pass


def set_clipboard_rich(clip, plain_text: str, html: str) -> None:
    """Put both text/plain and text/html on the clipboard.

    PyGObject does not expose ``Gtk.Clipboard.set_with_data`` (calling it
    crashes the interpreter), so we use ``set_with_owner`` with a GObject we
    keep alive, and fall back to plain text if that is unavailable.
    """
    global _clipboard_owner

    targets = [
        Gtk.TargetEntry.new("text/html", 0, _TARGET_HTML),
        Gtk.TargetEntry.new("UTF8_STRING", 0, _TARGET_TEXT),
        Gtk.TargetEntry.new("text/plain;charset=utf-8", 0, _TARGET_TEXT),
        Gtk.TargetEntry.new("text/plain", 0, _TARGET_TEXT),
        Gtk.TargetEntry.new("STRING", 0, _TARGET_TEXT),
    ]

    owner = _ClipboardOwner(plain_text, html)
    ok = False
    set_with_owner = getattr(clip, "set_with_owner", None)
    if set_with_owner is not None:
        try:
            ok = set_with_owner(
                targets, owner.get_func, owner.clear_func, owner)
        except Exception:  # noqa: BLE001
            ok = False

    if ok:
        # Retain the owner; releasing it would invalidate the callbacks.
        _clipboard_owner = owner
    else:
        # Reliable fallback: plain text only (better than crashing).
        clip.set_text(plain_text, -1)
        clip.store()
