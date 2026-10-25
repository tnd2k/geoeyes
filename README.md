# GeoEyes

InSAR time-series processing, from raw SAR scenes to versioned displacement products and reports.

- **Sensors**: Sentinel-1 IW (bursts from ASF), COSMO-SkyMed and Capella stripmap; native coregistration (no SNAP).
- **Methods**: StaMPS-type persistent scatterers (`psi`), phase linking with distributed scatterers (`psds`),
  `ps_lite` for short Capella stacks; ERA5 / GACOS atmospheric correction.
- **Outputs**: immutable products (GeoParquet points and time series, COG rasters, STAC item), GIS exports
  (GeoPackage styled for QGIS, PMTiles), scientific PDF reports, corner reflector identification reports, a
  workspace catalog (STAC + DuckDB).
- **Web app**: project tree, map of millions of points, time series, comparison of products, map images,
  monitoring (next Sentinel-1 acquisitions, scheduled runs, deformation alerts).

## Install

```
conda create -n geoeyes python=3.11 gdal rasterio geopandas -c conda-forge
conda activate geoeyes
pip install -e .[era5,web,dev]
copy .env.example .env      # then set GEOEYES_WORKSPACE (and EARTHDATA_TOKEN for Sentinel-1)
```

## Use

A project is a folder `<workspace>/projects/<name>/` with a `project.toml` (sensor preset + overrides).
How to declare a project and where the raw data go: [docs/guide/projects-and-data.md](docs/guide/projects-and-data.md).

```
geoeyes check  <project>        # environment and configuration
geoeyes plan   <project>        # what would run: new data, changed parameters, phases up to date
geoeyes run    <project>        # acquire -> build_stack -> [phase_linking] -> ps -> build_product -> export -> report
geoeyes status <project>
geoeyes report <project>        # rebuild the PDF report of the latest product
geoeyes cr-report <project>     # corner reflector identification (Sentinel-1)
geoeyes catalog search --bbox W,S,E,N    # products of every project over an area
geoeyes serve --open            # web app on http://localhost:8765
```

Phases re-run only when their inputs or parameters change; new acquisitions extend the stack incrementally
(a new reference date rebuilds it).

## Layout

| Path | Content |
|---|---|
| `src/geoeyes/` | the package: `config`, `controller`, `sensors`, `geometry`, `processing`, `products`, `export`, `report`, `validation`, `catalog`, `ancillary`, `api` (web back end), `io`, `workspace`, `cli` |
| `tests/unit` | fast tests (`pytest tests/unit`) |
| `tests/parity` | per-step comparison of the PS engine with the legacy StaMPS runs (needs the legacy outputs) |
| `tests/golden` | end-to-end runs against stored references (needs `GEOEYES_TEST_DATA`) |
| `docs/guide` | user guide: declaring projects and data |
| `docs/architecture` | architecture, decisions (ADR), migration map |
| `docs/refactor/TODO.md` | refactor plan and progress; `webapp-plan.md`: the web app |
| `webapp/` | web app front end (React + TypeScript), built into `src/geoeyes/api/static`; run with `geoeyes serve` |

Product language is English (ADR-015). The license is to be defined by the project owner (ADR-019).
