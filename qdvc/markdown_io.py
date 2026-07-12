"""Markdown + YAML frontmatter IO (pure, no GTK).

A note file is YAML frontmatter delimited by ``---`` lines, followed by a free
Markdown body. These helpers read and write that structure atomically.
"""

import os
import re
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def parse_markdown(path: Path) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_markdown)."""
    if not path.exists():
        return {}, ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, ""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, m.group(2)


def write_markdown(path: Path, frontmatter: dict, body: str) -> None:
    """Write frontmatter + body atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = yaml.safe_dump(frontmatter or {}, sort_keys=True,
                             allow_unicode=True).strip()
    content = f"---\n{fm_text}\n---\n{body}"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
