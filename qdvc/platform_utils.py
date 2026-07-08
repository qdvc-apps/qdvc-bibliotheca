"""Small helpers for launching the system's default applications."""

import os
import shlex
import subprocess
import sys


def open_with_default_app(path: str) -> None:
    """Open a file or folder with the OS default handler."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def open_with_text_editor(path: str) -> None:
    """Open a file with the system text editor.

    Honours $VISUAL / $EDITOR if they name a GUI editor, otherwise falls back
    to xdg-open (which uses the registered handler for the MIME type). On
    macOS/Windows it defers to the default handler.
    """
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-t", path])
        return
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    # Linux/BSD: xdg-open respects the user's default text/plain handler,
    # which is the most reliable way to get "their" editor for .md/.bib.
    subprocess.Popen(["xdg-open", path])


def reveal_in_file_manager(path: str, custom_command: str | None = None) -> None:
    """Open a folder in the file manager. `path` may be a file or a dir.

    If `custom_command` is given, {dir} and {file} placeholders are filled.
    """
    import os.path as _osp
    folder = path if _osp.isdir(path) else _osp.dirname(path)
    if custom_command:
        cmd = custom_command.replace("{dir}", folder).replace("{file}", path)
        subprocess.Popen(shlex.split(cmd))
    else:
        open_with_default_app(folder)
