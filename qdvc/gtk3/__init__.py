"""GTK3 front-end package for QDVC Bibliotheca.

Every module here is GTK3-specific and prefixed ``gtk3_`` so a future GTK4 port
can live beside it (e.g. a sibling ``qdvc/gtk4/`` package) without collisions.
Pure, toolkit-independent logic lives in the top-level ``qdvc`` package
(``workspace``, ``models``, ``apa``, ``csl``, ``bibtex``, ``markdown_io``,
``naming``, ``catalogue_sort``, ``config``, ``platform_utils``).
"""
