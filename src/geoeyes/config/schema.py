"""``project.toml`` schema (ARCHITECTURE §14.1). The validated ``ProjectConfig`` is immutable and is
the only configuration object passed down the pipeline; no module reads config files itself.

Engine parameter tables (``[ps]`` = StaMPS engine, ``[ps_lite]`` = Capella workflow) keep the
parameter names of the algorithms they come from, so results stay traceable to the literature and
to the legacy code. ``[legacy.*]`` holds keys of the old in.json/control.json that have no home in
the new schema yet; it is carried along unchanged and shrinks as phases are ported.
"""
from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from geoeyes.core.types import OrbitDirection

SCHEMA_ID = "geoeyes.project/1"
PROJECT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SUBSWATH_RE = re.compile(r"^(IW[1-3]|EW[1-5])$")


class Sensor(StrEnum):
    SENTINEL1 = "sentinel1"
    COSMO_SKYMED = "cosmo_skymed"
    TERRASAR_X = "terrasar_x"
    CAPELLA = "capella"
    ALOS = "alos"


class Method(StrEnum):
    PSI = "psi"
    SBAS = "sbas"
    PSDS = "psds"
    COMSAR = "comsar"
    PS_LITE = "ps_lite"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Organization(_Section):
    name: str = ""
    email: str = ""


class ProjectSection(_Section):
    name: str
    method: Method
    description: str = ""
    organization: Organization | None = None   # optional (ADR-016)

    @field_validator("name")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not PROJECT_NAME_RE.match(v):
            raise ValueError("project name must be 1-64 chars of a-z, 0-9, '_' or '-', starting alphanumeric")
        return v


class AoiSection(_Section):
    bbox: tuple[float, float, float, float] | None = None   # west, south, east, north (EPSG:4326)
    file: str = ""                                          # GeoJSON/GPKG polygon, relative to project dir

    @field_validator("bbox")
    @classmethod
    def _bbox(cls, v):
        if v is not None:
            w, s, e, n = v
            if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
                raise ValueError(f"invalid bbox {v}")
        return v


class TrackConfig(_Section):
    sensor: Sensor
    direction: OrbitDirection
    relative_orbit: int | None = None
    frame: int | None = None
    subswaths: tuple[str, ...] = ()

    @field_validator("direction", mode="before")
    @classmethod
    def _direction(cls, v):
        return OrbitDirection.parse(v) if isinstance(v, str) else v

    @field_validator("subswaths")
    @classmethod
    def _subswaths(cls, v):
        for s in v:
            if not SUBSWATH_RE.match(s):
                raise ValueError(f"invalid subswath {s!r}")
        return v

    @property
    def track_id(self) -> str:
        parts = [self.sensor.value, self.direction.short]
        if self.relative_orbit is not None:
            parts.append(f"{self.relative_orbit:03d}")
        elif self.frame is not None:
            parts.append(f"f{self.frame}")
        return "-".join(parts)


class AcquireSection(_Section):
    date_range: tuple[date, date] | None = None
    max_per_month: int = Field(0, ge=0)        # 0 = no limit
    archive: str = ""                          # shared raw-imagery root ("" = workspace archive)

    @model_validator(mode="after")
    def _order(self):
        if self.date_range and self.date_range[0] > self.date_range[1]:
            raise ValueError("acquire.date_range: start after end")
        return self


class SbasNetwork(_Section):
    redundant_pairs: bool = True
    redundant_max_days: int = Field(24, ge=0)
    max_temporal_days: int = Field(0, ge=0)


class NetworkSection(_Section):
    reference: date | Literal["auto"] = "auto"
    max_perp_m: float = Field(150.0, gt=0)
    max_temporal_days: int = Field(0, ge=0)
    extent_min_ratio: float = Field(0.95, ge=0, le=1)
    sbas: SbasNetwork = SbasNetwork()


class StackSection(_Section):
    engine: Literal["snap", "native"] = "native"          # snap: legacy configs only, not available (blocked)
    geometry: Literal["radar", "map"] | None = None       # None = sensor default (TSX: map; ADR-005)
    dem: str = "srtm-1"         # srtm-1 | copernicus-30 (both downloaded when missing) | folder of .hgt | GeoTIFF
    esd: bool = True
    multilook: tuple[int, int] = (1, 1)
    merge_subswaths: bool = False
    merge_subswaths_max_match_dist_deg: float = 3e-4
    process_range: tuple[str, ...] = ()
    reestimate: bool = True
    renew: bool = True
    # native: new scenes are coregistered and appended, the unchanged dates copied from the previous build;
    # a new reference (master), AOI, DEM or subswath set always coregisters every date again
    incremental: bool = True
    # Sentinel-1 native: "split_spectrum" estimates the ionospheric phase of every secondary by range
    # split-spectrum and removes it (geoeyes.processing.stack.native.iono; dusk passes near the equatorial anomaly)
    ionosphere: Literal["none", "split_spectrum"] = "none"
    # the ionosphere is estimated over the whole bursts: a plane around the AOI with Gaussian weights of
    # ionosphere_smooth_m (default), a quadratic surface or a plane over the bursts, or a Gaussian surface
    ionosphere_model: Literal["local", "quadratic", "plane", "smooth"] = "local"
    ionosphere_smooth_m: float = Field(10000.0, gt=0)
    byteswap: int = 1
    options: dict[str, Any] = {}                          # engine/sensor-specific extras


class PhaseLinkingSection(_Section):
    enabled: bool = False
    estimator: Literal["evd", "emi", "mle", "pta", "adaptive", "psds", "comsar"] = "adaptive"
    half_window: tuple[int, int] = (7, 7)
    shp_test: Literal["ad", "ks", "bws"] = "ad"           # Anderson-Darling | Kolmogorov-Smirnov | (bws not ported)
    shp_alpha: float = Field(0.05, gt=0, lt=1)
    min_shp: int = Field(25, ge=1)
    ps_da_max: float = Field(0.25, ge=0)                  # PS (amplitude dispersion) keep their SLC; 0 = link all
    adaptive_coherence_threshold: float = Field(0.6, ge=0, le=1)
    tile_size: int = Field(512, ge=16)
    ministack_size: int = Field(5, ge=2)
    gaussian_sigma: float = Field(0.0, ge=0)              # post-filter; 0 = off
    gaussian_scope: Literal["linked", "all"] = "linked"   # linked pixels only (PS untouched) | all (legacy)
    nlinsar: dict[str, Any] | None = None                 # None = off
    options: dict[str, Any] = {}


class SelectionSection(_Section):
    da_threshold: float = Field(0.4, gt=0)
    robust_da: bool = True
    # distributed scatterers from phase linking: per ds_cell x ds_cell block the pixel of highest linking
    # temporal coherence, if >= ds_coherence_min; None = PS only. Ignored when phase linking is off
    ds_coherence_min: float | None = Field(None, gt=0, le=1)
    ds_cell: int = Field(3, ge=1)
    forced_points: str = ""
    mask: str = ""
    water_mask: Literal["none", "model", "static"] = "none"
    water_model: dict[str, Any] = {}


class PsLiteSection(_Section):
    """Capella workflow (ADR-020); names and defaults of ``modules.ps_stack.run_stack``."""

    window: tuple[int, int, int, int] | None = None
    ref_date: str = "auto"
    dem: str | None = None
    dem_datum: str = "EGM96"
    sign: str = "auto"
    da_max: float = 0.4
    sd_max: float | None = 0.45
    ps_cell: tuple[int, int] = (4, 6)
    uw_cell: tuple[int, int] = (16, 24)
    amp_floor_pct: float = 10.0
    phase_std_max: float = 0.8
    ifg_std_max: float = 1.5
    tropo: bool = False
    remove_plane: bool = False
    gs_alpha: float = 0.8
    gs_win: int = 32
    gs_passes: int = 1
    irls_iter: int = 50
    unwrap_method: Literal["s1", "capella"] = "s1"
    tcoh_min: float = 0.7
    ref_latlon: tuple[float, float] | None = None
    ref_radius_m: float = 200.0
    aps_sigma_m: float = 1000.0
    geo_step: tuple[int, int] = (8, 12)
    block_lines: int = 256
    exclude_dates: tuple[str, ...] = ()
    # EXPERIMENTAL: height error from the wrapped phase *before* spatial unwrapping (StaMPS-style),
    # for small height ambiguities. Did not rescue a 3.5-year CSK series (2026-10-22); off = original method.
    topo_first: bool = False
    topo_first_dh_max: float = 100.0
    topo_first_smooth_cells: int = 3
    # "box": neighbour mean on the unwrapping grid + periodogram (original); "gamma": the StaMPS step-2
    # estimator (CLAP-filtered patch phase, iterated topofit with ambiguity score, spatial K regularisation)
    topo_first_method: Literal["box", "gamma"] = "box"
    topo_first_grid_m: float = 50.0
    # "ps": unwrap the (cell-averaged) PS phase; "patch": unwrap the CLAP-filtered patch phase of the
    # topo-first "gamma" estimator and add each PS's wrapped residual back (StaMPS unwrap_patch_phase)
    unwrap_input: Literal["ps", "patch"] = "ps"


class AtmosphereSection(_Section):
    # APS removed in the second unwrapping pass: none/linear = the engine's linear (topography-correlated)
    # APS; era5 | gacos = weather model, the linear APS where it has no data
    method: str = "none"
    # era5/gacos per interferogram: "auto" = only where it explains the pass-1 residual phase better than the
    # linear APS (linear elsewhere); "all" = every interferogram
    select: Literal["auto", "all"] = "auto"
    # cache (default <workspace>/cache/era5), auto_download (true), buffer_deg (2.0), component
    # (total | hydro | wet), pressure_levels, workers (4), fallback_utc ("HH:MM:SS" for stacks without times)
    era5: dict[str, Any] = {}
    gacos: dict[str, Any] = {}            # dir: folder of <YYYYMMDD>.ztd(.rsc|.tif) products


class PostprocessSection(_Section):
    decompose_3d: Literal["auto", "off"] = "auto"
    alerts: dict[str, Any] = {}
    # hazard zoning with rainfall (geoeyes hazard): see geoeyes.hazard.HazardParams and
    # docs/en/research/rainfall-insar-hazard.md
    hazard: dict[str, Any] = {}
    # AI (geoeyes susceptibility / geoeyes forecast): see geoeyes.ml and docs/en/research/ai-*.md
    susceptibility: dict[str, Any] = {}
    forecast: dict[str, Any] = {}
    # kinds of motion of the hazard cells, risk to buildings: geoeyes.ml.behaviour / geoeyes.ml.risk and
    # docs/en/research/behaviour-and-risk.md
    behaviour: dict[str, Any] = {}
    risk: dict[str, Any] = {}
    # linear infrastructure and consolidation: geoeyes.ml.lines / geoeyes.ml.consolidation and
    # docs/en/research/lines-and-consolidation.md
    lines: dict[str, Any] = {}
    consolidation: dict[str, Any] = {}
    # vertical and east-west motion from two geometries, soft-soil thickness: geoeyes.ml.decompose /
    # geoeyes.ml.geology and docs/en/research/two-geometries-and-soft-soil.md
    decompose: dict[str, Any] = {}
    geology: dict[str, Any] = {}


class ValidationSection(_Section):
    gnss: dict[str, Any] = {}
    # points, setup (CSV paths relative to the project), timezone, edge_m, start, end:
    # see geoeyes.validation.corner_reflector
    corner_reflector: dict[str, Any] = {}


class ReportSection(_Section):
    copy_to: str = ""


class ExportSection(_Section):
    # pmtiles: vector tiles (QGIS 3.32+, the web app's tiled mode for large products)
    formats: tuple[Literal["gpkg", "shp", "csv", "las", "qml", "pmtiles"], ...] = ("gpkg", "pmtiles")


class ComputeSection(_Section):
    backend: Literal["auto", "numpy", "cupy"] = "auto"
    workers: int = Field(0, ge=0)          # 0 = auto
    memory_gb: float = Field(0, ge=0)      # 0 = auto


class PipelineSection(_Section):
    disabled: tuple[str, ...] = ()         # optional phases switched off (water_mask, validate, ...)


class ProjectConfig(_Section):
    schema_: str = Field(SCHEMA_ID, alias="schema")
    project: ProjectSection
    aoi: AoiSection = AoiSection()
    tracks: tuple[TrackConfig, ...]
    acquire: AcquireSection = AcquireSection()
    network: NetworkSection = NetworkSection()
    stack: StackSection = StackSection()
    phase_linking: PhaseLinkingSection = PhaseLinkingSection()
    selection: SelectionSection = SelectionSection()
    ps: dict[str, Any] = {}
    ps_lite: PsLiteSection = PsLiteSection()
    atmosphere: AtmosphereSection = AtmosphereSection()
    postprocess: PostprocessSection = PostprocessSection()
    validation: ValidationSection = ValidationSection()
    report: ReportSection = ReportSection()
    export: ExportSection = ExportSection()
    compute: ComputeSection = ComputeSection()
    pipeline: PipelineSection = PipelineSection()
    overrides: dict[str, dict[str, Any]] = {}     # per subswath, deep-merged (resolve_subswath)
    legacy: dict[str, Any] = {}

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @field_validator("schema_")
    @classmethod
    def _schema(cls, v: str) -> str:
        if v != SCHEMA_ID:
            raise ValueError(f"unsupported schema {v!r} (expected {SCHEMA_ID!r})")
        return v

    @model_validator(mode="after")
    def _consistency(self):
        if not self.tracks:
            raise ValueError("at least one [[tracks]] entry is required")
        sensors = {t.sensor for t in self.tracks}
        if self.project.method is Method.PS_LITE and sensors != {Sensor.CAPELLA}:
            raise ValueError("method 'ps_lite' is the Capella workflow (ADR-020)")
        if Sensor.CAPELLA in sensors and self.project.method is not Method.PS_LITE:
            raise ValueError("Capella projects use method 'ps_lite' (ADR-020)")
        for key in self.overrides:
            if not SUBSWATH_RE.match(key):
                raise ValueError(f"overrides.{key}: keys must be subswaths (IW1..IW3)")
        return self

    @property
    def sensors(self) -> frozenset[Sensor]:
        return frozenset(t.sensor for t in self.tracks)
