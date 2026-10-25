"""Layer 1: the only package that knows file formats (ARCHITECTURE §10).

- ``manifest``  provenance JSON + atomic writes
- ``stack``     StackStore (Zarr v3): SLC / interferogram / coherence / geometry cubes
- ``state``     StateStore (HDF5 with a declared schema): processing-engine state
- ``points``    PointStore (GeoParquet) and TimeSeriesStore (long-format Parquet)
- ``raster``    RasterStore (Cloud-Optimized GeoTIFF)
"""
