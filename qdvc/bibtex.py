"""BibTeX parsing (pure, no GTK).

Uses ``bibtexparser`` when it is importable, else a small brace-aware fallback
parser that is good enough for the one-entry-per-file workspace convention.
Also provides ``split_bib_entries`` for breaking a multi-entry paste/import
into individual entries.
"""

import re
from pathlib import Path

_BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{", re.IGNORECASE)
_FIELD_RE = re.compile(r"(\w+)\s*=\s*", re.IGNORECASE)


def parse_bib_fallback(text: str) -> dict:
    """Minimal single-entry BibTeX parser used when bibtexparser is absent.

    Handles brace- and quote-delimited values and nested braces. Good enough
    for one-entry .bib files, which is the workspace convention.
    """
    m = _BIB_ENTRY_RE.search(text)
    if not m:
        return {}
    entry = {"ENTRYTYPE": m.group(1).lower()}
    i = m.end()
    # citation key up to first comma
    key_end = text.find(",", i)
    if key_end == -1:
        return entry
    entry["ID"] = text[i:key_end].strip()
    i = key_end + 1
    n = len(text)
    while i < n:
        fm = _FIELD_RE.search(text, i)
        if not fm:
            break
        fname = fm.group(1).lower()
        j = fm.end()
        while j < n and text[j] in " \t\r\n":
            j += 1
        if j >= n:
            break
        ch = text[j]
        if ch == "{":
            depth = 0
            start = j + 1
            k = j
            while k < n:
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            value = text[start:k]
            i = k + 1
        elif ch == '"':
            start = j + 1
            k = start
            while k < n and text[k] != '"':
                k += 1
            value = text[start:k]
            i = k + 1
        else:  # bare value (number, etc.)
            k = j
            while k < n and text[k] not in ",}\n":
                k += 1
            value = text[j:k].strip()
            i = k
        entry[fname] = value.strip()
        # advance past a trailing comma
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i < n and text[i] == ",":
            i += 1
        elif i < n and text[i] == "}":
            break
    return entry


def parse_bibtex(path: Path) -> dict:
    """Parse a single-entry .bib file into a normalised dict."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    try:
        import bibtexparser  # type: ignore
        from bibtexparser.bparser import BibTexParser  # type: ignore
        parser = BibTexParser(common_strings=True)
        parser.ignore_nonstandard_types = False
        db = bibtexparser.loads(text, parser=parser)
        if db.entries:
            e = dict(db.entries[0])
            # normalise key casing used elsewhere
            e.setdefault("ENTRYTYPE", e.get("entrytype", "misc"))
            return e
    except Exception:
        pass
    return parse_bib_fallback(text)


def split_bib_entries(text: str) -> list[tuple[str, str]]:
    """Split a multi-entry .bib string into (entry_text, citation_key) pairs.

    Uses brace balancing so entry bodies containing nested braces are kept
    intact. Non-entry content (comments, @string, @preamble) is skipped.
    """
    entries: list[tuple[str, str]] = []
    n = len(text)
    i = 0
    while i < n:
        at = text.find("@", i)
        if at == -1:
            break
        m = _BIB_ENTRY_RE.match(text, at)
        if not m:
            i = at + 1
            continue
        etype = m.group(1).lower()
        brace_open = m.end() - 1  # position of '{'
        # balance braces to find the end of this entry
        depth = 0
        j = brace_open
        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        entry_text = text[at:j + 1]
        i = j + 1
        if etype in ("string", "preamble", "comment"):
            continue
        # citation key: between '{' and first comma
        comma = entry_text.find(",")
        brace = entry_text.find("{")
        if comma == -1 or brace == -1:
            continue
        key = entry_text[brace + 1:comma].strip()
        entries.append((entry_text, key))
    return entries
