"""Landslide susceptibility from inventories, with rainfall and InSAR (docs/en/research/landslide-susceptibility.md).

A study is a folder ``<workspace>/studies/<name>/`` with ``study.toml``; every step writes its outputs and a manifest
in a subfolder of it:

    inventory   ``inventory.py``  the workspace inventories (reported events, mapped polygons), footprints   L0
    labels      ``labels.py``     initiation-zone positives and footprint negatives on a 30 m grid            L1
    layers      ``terrain.py``, ``predictors.py``  terrain derivatives, lithology, soil, roads, forest      L2
    aspect      ``aspect.py``     is the aspect signal the slopes' or the mapping's?                         L2a
    verify      ``verify.py``     the inventories against Landsat (Hansen) and Sentinel-1                     L2b
    scars       ``scars.py``      new scars between Sentinel-2 composites: a later event as independent test  L3b
    fit         ``model.py``      susceptibility models, spatial / transfer validation, pooled model, test  L3 / L3b

Separate from ``geoeyes.hazard`` (zoning of slow motion from InSAR) and ``geoeyes.ml.susceptibility`` (labels from
InSAR cells): here the labels come from landslide inventories.
"""
