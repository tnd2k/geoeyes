"""Open-data hub: search the open SAR STAC catalogs for interferometric stacks and fetch them into the archive.

    sources   the catalogs (ICEYE, Capella, Umbra open data on AWS) and how their items map to one scene record
    crawl     walk a static STAC catalog (child / item links), threaded
    index     ``<workspace>/cache/opendata/<source>.json``: the scenes of each source, refreshed by ``sync``
              (items are immutable: only new item URLs are fetched)
    stacks    group the scenes into repeat-pass stacks (same satellite or repeat ground track, pass, look side,
              incidence, overlapping footprints)
    fetch     download a stack into ``<archive>/<sensor>/<track>/YYYYMMDD/``, cut to the AOI when the format
              allows ranged reads (ICEYE SLC-COG), ready for ``build_stack``

Used by ``geoeyes opendata`` (CLI), ``/api/opendata`` and the ``acquire`` phase (``[acquire] opendata``).
"""
from geoeyes.opendata.index import load, search, sync
from geoeyes.opendata.sources import SOURCES
from geoeyes.opendata.stacks import find_stacks

__all__ = ["SOURCES", "find_stacks", "load", "search", "sync"]
