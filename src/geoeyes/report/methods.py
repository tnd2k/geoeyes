"""Method description, limitations and references of a report, built from what actually ran.

Each step carries the keys of the papers it relies on; the reference list holds only those (ARCHITECTURE §13.2:
cite only the steps that ran).
"""
from __future__ import annotations

from typing import Any

REFERENCES = {
    "ferretti2001": "Ferretti, A., Prati, C., Rocca, F. (2001). Permanent scatterers in SAR interferometry. "
                    "IEEE Trans. Geosci. Remote Sens., 39(1), 8–20.",
    "hooper2004": "Hooper, A., Zebker, H., Segall, P., Kampes, B. (2004). A new method for measuring deformation on "
                  "volcanoes and other natural terrains using InSAR persistent scatterers. Geophys. Res. Lett., 31, "
                  "L23611.",
    "hooper2007": "Hooper, A., Segall, P., Zebker, H. (2007). Persistent scatterer interferometric synthetic aperture "
                  "radar for crustal deformation analysis, with application to Volcán Alcedo, Galápagos. "
                  "J. Geophys. Res., 112, B07407.",
    "hooper2007uw": "Hooper, A., Zebker, H. A. (2007). Phase unwrapping in three dimensions with application to "
                    "InSAR time series. J. Opt. Soc. Am. A, 24(9), 2737–2747.",
    "ferretti2011": "Ferretti, A., Fumagalli, A., Novali, F., Prati, C., Rocca, F., Rucci, A. (2011). A new algorithm "
                    "for processing interferometric data-stacks: SqueeSAR. IEEE Trans. Geosci. Remote Sens., 49(9), "
                    "3460–3470.",
    "ansari2018": "Ansari, H., De Zan, F., Bamler, R. (2018). Efficient phase estimation for interferogram stacks. "
                  "IEEE Trans. Geosci. Remote Sens., 56(7), 4109–4125.",
    "cao2015": "Cao, N., Lee, H., Jung, H. C. (2015). Mathematical framework for phase-triangulation algorithms in "
               "distributed-scatterer interferometry. IEEE Geosci. Remote Sens. Lett., 12(9), 1838–1842.",
    "scholz1987": "Scholz, F. W., Stephens, M. A. (1987). K-sample Anderson–Darling tests. J. Am. Stat. Assoc., "
                  "82(399), 918–924.",
    "prats2012": "Prats-Iraola, P., Scheiber, R., Marotti, L., Wollstadt, S., Reigber, A. (2012). TOPS "
                 "interferometry with TerraSAR-X. IEEE Trans. Geosci. Remote Sens., 50(8), 3179–3188.",
    "sansosti2006": "Sansosti, E., Berardino, P., Manunta, M., Serafino, F., Fornaro, G. (2006). Geometrical SAR image "
                    "registration. IEEE Trans. Geosci. Remote Sens., 44(10), 2861–2870.",
    "goldstein1998": "Goldstein, R. M., Werner, C. L. (1998). Radar interferogram filtering for geophysical "
                     "applications. Geophys. Res. Lett., 25(21), 4035–4038.",
    "ghiglia1998": "Ghiglia, D. C., Pritt, M. D. (1998). Two-Dimensional Phase Unwrapping: Theory, Algorithms, and "
                   "Software. Wiley.",
    "hersbach2020": "Hersbach, H., et al. (2020). The ERA5 global reanalysis. Q. J. R. Meteorol. Soc., 146, 1999–2049.",
    "jolivet2011": "Jolivet, R., Grandin, R., Lasserre, C., Doin, M.-P., Peltzer, G. (2011). Systematic InSAR "
                   "tropospheric phase delay corrections from global meteorological reanalysis data. Geophys. Res. "
                   "Lett., 38, L17311.",
    "yu2018": "Yu, C., Li, Z., Penna, N. T., Crippa, P. (2018). Generic atmospheric correction model for "
              "interferometric synthetic aperture radar observations. J. Geophys. Res. Solid Earth, 123, 9202–9222.",
    "bekaert2015": "Bekaert, D. P. S., Walters, R. J., Wright, T. J., Hooper, A. J., Parker, D. J. (2015). Statistical "
                   "comparison of InSAR tropospheric correction techniques. Remote Sens. Environ., 170, 40–47.",
}


def _orbit_text(orbit: str) -> str:
    """Stack ``orbit`` attribute (``POEORB``, or ``POEORB (24), RESORB (3)``) -> report wording."""
    if not orbit or orbit == "annotation":
        return "annotation"
    if orbit.split(" (")[0] == "POEORB" and "," not in orbit:
        return "precise (POEORB)"
    return f"precise where available, restituted or annotation otherwise: {orbit}"


def _step(title: str, text: str, cites: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"title": title, "text": text, "cites": list(cites)}


def linking_params(cfg, ps_manifest, params: dict, stack_attrs: dict) -> dict | None:
    """Phase-linking parameters of the run that made the product (not of the current configuration): the PS
    run's manifest, else (older runs) the stack's record of its last linking, read as KS when it predates the
    ``shp_test`` parameter. ``None``: the run did not use the linked stack."""
    if "phase_linking" in ps_manifest.extra:
        return ps_manifest.extra["phase_linking"] or stack_attrs.get("phase_linking_done") or {}
    linked = params.get("slc_var") == "slc_linked" or (
        "slc_var" not in params and cfg is not None and cfg.phase_linking.enabled)
    done = stack_attrs.get("phase_linking_done")
    if not linked or not isinstance(done, dict):
        return None
    return {"shp_test": "ks", **done}


def weather_used(cfg, ps_manifest) -> tuple[str, str, int]:
    """(method, selection, interferograms) of the weather-model APS the run removed; method '' if none.
    From the run's manifest; older ps_lite runs only flag the pairs, the method then comes from the config."""
    aps = ps_manifest.metrics.get("aps")
    if isinstance(aps, dict):
        ifgs = aps.get("weather_ifgs")
        n = len(ifgs) if isinstance(ifgs, list) else len(ps_manifest.extra.get("pairs", [])) or 0
        return (aps.get("method", ""), aps.get("select", ""), n) if n or ifgs == "all" else ("", "", 0)
    n = sum(bool(p.get("weather_aps")) for p in ps_manifest.extra.get("pairs", []))
    if n and cfg is not None and cfg.atmosphere.method in ("era5", "gacos"):
        return cfg.atmosphere.method, cfg.atmosphere.select, n
    return "", "", 0


def describe(cfg, ps_manifest, params: dict, stack_attrs: dict) -> dict[str, Any]:
    """Steps (title, text, citation keys) and the key parameters of the processing that made the product."""
    steps, table = [], []
    mode = stack_attrs.get("mode", "")
    if mode == "tops":
        steps.append(_step("Coregistration",
                           "Sentinel-1 TOPS bursts were coregistered to the reference acquisition geometrically, from "
                           f"{_orbit_text(stack_attrs.get('orbit', ''))} orbits and "
                           "the DEM; the azimuth alignment was refined by enhanced spectral diversity over the burst "
                           "overlaps, and the bursts were debursted and cropped to the area of interest. The "
                           "topographic and flat-earth phase was removed from each SLC.",
                           ("sansosti2006", "prats2012")))
    elif mode:
        steps.append(_step("Coregistration",
                           "Each scene was coregistered to the reference acquisition geometrically from its orbit and "
                           "the DEM, with a residual constant offset estimated by tile cross-correlation, then "
                           "resampled and cropped to the area of interest. The topographic and flat-earth phase was "
                           "removed from each SLC.", ("sansosti2006",)))
    if stack_attrs.get("dem"):
        table.append(("DEM", str(stack_attrs["dem"]).split(" (")[0]))      # name, without the local path

    pl = linking_params(cfg, ps_manifest, params, stack_attrs)
    if pl:
        shp, estimator, hw = pl.get("shp_test", "ks"), pl.get("estimator", ""), pl.get("half_window", [7, 7])
        test = {"ad": "two-sample Anderson–Darling", "ks": "two-sample Kolmogorov–Smirnov"}.get(shp, shp)
        est = {"adaptive": "EMI where the mean coherence of the window exceeds "
                           f"{pl.get('adaptive_coherence_threshold', 0.6):g}, phase triangulation elsewhere",
               "emi": "eigendecomposition-based maximum-likelihood (EMI)", "evd": "eigenvalue decomposition (EVD)",
               "pta": "phase triangulation", "mle": "maximum likelihood"}.get(estimator, estimator)
        cites = ["ferretti2011", "scholz1987"] if shp == "ad" else ["ferretti2011"]
        cites += {"adaptive": ["ansari2018", "cao2015"], "emi": ["ansari2018"], "pta": ["cao2015"]}.get(estimator, [])
        window = f"{2 * hw[0] + 1} × {2 * hw[1] + 1}"
        text = (f"Statistically homogeneous pixels were found in a {window} window by the {test} test on the "
                f"amplitude time series (α = {pl.get('shp_alpha', 0.05):g}, at least {pl.get('min_shp')} pixels). "
                f"The coherence matrix over these pixels was inverted for one phase per acquisition: {est}.")
        if pl.get("ps_da_max"):
            text += (f" Pixels with amplitude dispersion ≤ {pl['ps_da_max']:g} (persistent scatterers) kept their "
                     "own phase.")
        if pl.get("gaussian_sigma"):
            text += (f" A Gaussian filter (σ = {pl['gaussian_sigma']:g} pixels) was applied to the linked phase "
                     f"({'all pixels' if pl.get('gaussian_scope') == 'all' else 'linked pixels only'}).")
        steps.append(_step("Phase linking", text, tuple(cites)))
        table += [("SHP test / α", f"{shp} / {pl.get('shp_alpha', 0.05):g}"), ("Estimator", estimator),
                  ("Window", window)]

    if "ps_lite" in ps_manifest.engine:
        steps.append(_step("Point selection",
                           f"Persistent scatterers: amplitude dispersion ≤ {params.get('da_max')} and range spectral "
                           f"diversity ≤ {params.get('sd_max')}, the best pixel per {params.get('ps_cell')} cell.",
                           ("ferretti2001",)))
        steps.append(_step("Phase unwrapping",
                           f"The PS phase of each interferogram was gridded ({params.get('uw_cell')} pixel cells), "
                           f"Goldstein-filtered (α = {params.get('gs_alpha')}) and unwrapped with an iteratively "
                           "reweighted least-squares (L1-type) solver whose edge weights come from the space–time "
                           "consistency of the phase; a height-error estimate between two passes removes the "
                           "baseline-dependent phase before the second pass.", ("goldstein1998", "ghiglia1998")))
        steps.append(_step("Inversion",
                           "Per point, a weighted least-squares fit of the unwrapped phase gives the LOS velocity, the "
                           "height error and a reference-epoch term; interferograms whose noise exceeds "
                           f"{params.get('ifg_std_max')} rad are left out, and a spatially filtered atmospheric screen "
                           f"(σ = {params.get('aps_sigma_m')} m) is removed. Points with temporal coherence below "
                           f"{params.get('tcoh_min')} are discarded."))
        table += [("D_A max", params.get("da_max")), ("Temporal coherence min", params.get("tcoh_min")),
                  ("Unwrapping grid", params.get("uw_cell"))]
    else:
        t = params.get("table", {})
        steps.append(_step("Point selection",
                           f"Candidates with amplitude dispersion ≤ {params.get('da_max')} were tested for phase "
                           "stability: the phase noise about a spatially filtered estimate and a height-error fit "
                           "gives a temporal coherence, thresholded per amplitude-dispersion bin so that at most "
                           f"{t.get('percent_rand', 20)} % of the selected pixels are expected to be random-phase "
                           "pixels; adjacent and noisy pixels were "
                           "then weeded on the Delaunay network.", ("ferretti2001", "hooper2004", "hooper2007")))
        if params.get("ds_tcoh_min"):
            steps.append(_step("Distributed scatterers",
                               f"In each {params.get('ds_cell')} × {params.get('ds_cell')} block the phase-linked "
                               f"pixel of highest linking coherence (≥ {params.get('ds_tcoh_min')}) was added as a "
                               "distributed-scatterer candidate.", ("ferretti2011",)))
        steps.append(_step("Phase unwrapping",
                           "Space–time unwrapping of the persistent-scatterer network: the phase differences of the "
                           "network edges are unwrapped in time first, then in space with an iteratively reweighted "
                           "least-squares solver, in two passes (the height error and atmosphere of the first pass "
                           "removed before the second).", ("hooper2007uw", "ghiglia1998")))
        steps.append(_step("Inversion",
                           "The unwrapped phase, corrected for the spatially correlated look-angle error, the "
                           "atmosphere and the reference-epoch error, was converted to LOS displacement and fitted per "
                           "point with a linear rate; spatially correlated noise was estimated by high-pass filtering "
                           "in time and low-pass in space.", ("hooper2007",)))
        table += [("D_A max", params.get("da_max")), ("Random-pixel fraction", f"{t.get('percent_rand', '')} %"),
                  ("Max. height error (m)", t.get("max_topo_err", ""))]

    method, select, n_weather = weather_used(cfg, ps_manifest)
    lite = "ps_lite" in ps_manifest.engine
    if method:
        src = ("ERA5 pressure-level reanalysis, integrated along the line of sight" if method == "era5"
               else "GACOS zenith delays mapped to the line of sight")
        other = "the engine's spatially filtered screen only" if lite else "the linear model"
        sel = (f"for the {n_weather} interferograms where it reduces the residual phase more than {other} "
               f"(per-interferogram selection), {other} elsewhere" if select == "auto" else "for every interferogram")
        steps.append(_step("Atmospheric correction",
                           f"Tropospheric delays from {src} were removed before the second unwrapping pass, {sel}.",
                           ("hersbach2020", "jolivet2011") if method == "era5" else ("yu2018",)))
        table.append(("Atmosphere", f"{method} ({select}, {n_weather} interferograms)"))
    elif not lite:
        steps.append(_step("Atmospheric correction",
                           "A linear, topography-correlated tropospheric phase was estimated per interferogram and "
                           "removed.", ("bekaert2015",)))
        table.append(("Atmosphere", "linear (phase–elevation)"))
    ref = ps_manifest.metrics.get("reference")
    if isinstance(ref, dict):
        how = "given" if ref.get("given") else "automatic"
        table.append(("Reference area", f"{ref.get('lat', 0):.5f}° N, {ref.get('lon', 0):.5f}° E "
                                        f"({ref.get('n_ps', '?')} points, {how})"))
    elif ref:
        table.append(("Reference area", str(ref)))
    return {"steps": steps, "params": [[str(k), f"{v:.4g}" if isinstance(v, float) else str(v)] for k, v in table]}


def limitations(data: dict) -> list[str]:
    a = data["acquisition"]
    out = ["Velocities and displacements are along the radar line of sight (LOS), positive toward the satellite: "
           "uplift or motion toward the satellite is positive, subsidence negative."]
    if a.get("heading_deg") is not None:
        out.append(f"The LOS is almost insensitive to north–south motion (heading {a['heading_deg']:.0f}°); "
                   "horizontal east–west motion and vertical motion cannot be separated from one track.")
    out.append("All values are relative to the reference area, assumed stable; motion of the reference area appears, "
               "with opposite sign, everywhere.")
    out.append("Residual atmospheric delay remains in single acquisitions; it averages down in the velocity but not "
               "in the individual time-series values.")
    out.append("Areas without points (vegetation, water, steep slopes facing away from the radar, rapidly changing "
               "surfaces) are not measured; the absence of points is not evidence of stability.")
    if a.get("span_days", 9999) < 365:
        out.append("The series is shorter than one year: seasonal (thermal, hydrological) motion is not separated "
                   "from the trend and the velocity applies to the observed period only.")
    if a.get("band") == "X":
        out.append("X-band: a phase cycle is 1.6 cm of LOS motion; motion faster than about a quarter cycle between "
                   "consecutive acquisitions may be unwrapped wrongly.")
    return out


def references(method: dict) -> list[dict[str, str]]:
    keys = []
    for s in method["steps"]:
        for k in s["cites"]:
            if k not in keys:
                keys.append(k)
    return [{"key": k, "text": REFERENCES[k]} for k in keys]
