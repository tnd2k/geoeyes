// Principles, chapter 1: the scientific basis of each step (pages/Learn.tsx, section "Scientific basis") — the
// symbols of the formulas, where the formulas come from and what they assume, the parameters and how GeoEyes sets
// them, the literature. Typical values: Sentinel-1 IW (C band). Vietnamese: i18n/vi/learnScience.ts.

export interface Science {
  symbols: [string, string, string][]; // symbol, meaning, unit / typical value
  theory: string[]; // paragraphs: derivation, assumptions, orders of magnitude
  params?: [string, string, string][]; // parameter, effect, how GeoEyes sets it
  refs: string[]; // keys of REFS
}

export const REFS: Record<string, string> = {
  bamler1998: "Bamler, R., Hartl, P. (1998). Synthetic aperture radar interferometry. Inverse Problems, 14(4), R1–R54.",
  hanssen2001: "Hanssen, R. F. (2001). Radar Interferometry: Data Interpretation and Error Analysis. Kluwer.",
  ferretti2007: "Ferretti, A., Monti-Guarnieri, A., Prati, C., Rocca, F., Massonnet, D. (2007). InSAR Principles (ESA TM-19). ESA Publications.",
  rosen2000: "Rosen, P. A., et al. (2000). Synthetic aperture radar interferometry. Proceedings of the IEEE, 88(3), 333–382.",
  massonnet1998: "Massonnet, D., Feigl, K. L. (1998). Radar interferometry and its application to changes in the Earth's surface. Reviews of Geophysics, 36(4), 441–500.",
  moreira2013: "Moreira, A., et al. (2013). A tutorial on synthetic aperture radar. IEEE Geoscience and Remote Sensing Magazine, 1(1), 6–43.",
  torres2012: "Torres, R., et al. (2012). GMES Sentinel-1 mission. Remote Sensing of Environment, 120, 9–24.",
  zebker1992: "Zebker, H. A., Villasenor, J. (1992). Decorrelation in interferometric radar echoes. IEEE TGRS, 30(5), 950–959.",
  sansosti2006: "Sansosti, E., Berardino, P., Manunta, M., Serafino, F., Fornaro, G. (2006). Geometrical SAR image registration. IEEE TGRS, 44(10), 2861–2870.",
  prats2012: "Prats-Iraola, P., Scheiber, R., Marotti, L., Wollstadt, S., Reigber, A. (2012). TOPS interferometry with TerraSAR-X. IEEE TGRS, 50(8), 3179–3188.",
  yague2016: "Yagüe-Martínez, N., et al. (2016). Interferometric processing of Sentinel-1 TOPS data. IEEE TGRS, 54(4), 2220–2234.",
  farr2007: "Farr, T. G., et al. (2007). The Shuttle Radar Topography Mission. Reviews of Geophysics, 45, RG2004.",
  just1994: "Just, D., Bamler, R. (1994). Phase statistics of interferograms with applications to synthetic aperture radar. Applied Optics, 33(20), 4361–4368.",
  touzi1999: "Touzi, R., Lopes, A., Bruniquel, J., Vachon, P. W. (1999). Coherence estimation for SAR imagery. IEEE TGRS, 37(1), 135–149.",
  rodriguez1992: "Rodriguez, E., Martin, J. M. (1992). Theory and design of interferometric synthetic aperture radars. IEE Proceedings F, 139(2), 147–159.",
  goldstein1998: "Goldstein, R. M., Werner, C. L. (1998). Radar interferogram filtering for geophysical applications. Geophysical Research Letters, 25(21), 4035–4038.",
  baran2003: "Baran, I., Stewart, M. P., Kampes, B. M., Perski, Z., Lilly, P. (2003). A modification to the Goldstein radar interferogram filter. IEEE TGRS, 41(9), 2114–2118.",
  goldstein1988: "Goldstein, R. M., Zebker, H. A., Werner, C. L. (1988). Satellite radar interferometry: two-dimensional phase unwrapping. Radio Science, 23(4), 713–720.",
  itoh1982: "Itoh, K. (1982). Analysis of the phase unwrapping algorithm. Applied Optics, 21(14), 2470.",
  ghiglia1994: "Ghiglia, D. C., Romero, L. A. (1994). Robust two-dimensional weighted and unweighted phase unwrapping that uses fast transforms and iterative methods. JOSA A, 11(1), 107–117.",
  ghiglia1998: "Ghiglia, D. C., Pritt, M. D. (1998). Two-Dimensional Phase Unwrapping: Theory, Algorithms, and Software. Wiley.",
  chen2001: "Chen, C. W., Zebker, H. A. (2001). Two-dimensional phase unwrapping with use of statistical models for cost functions in nonlinear optimization. JOSA A, 18(2), 338–351.",
  hooper2007uw: "Hooper, A., Zebker, H. A. (2007). Phase unwrapping in three dimensions with application to InSAR time series. JOSA A, 24(9), 2737–2747.",
  wright2004: "Wright, T. J., Parsons, B. E., Lu, Z. (2004). Toward mapping surface deformation in three dimensions using InSAR. Geophysical Research Letters, 31, L01607.",
  ferretti2001: "Ferretti, A., Prati, C., Rocca, F. (2001). Permanent scatterers in SAR interferometry. IEEE TGRS, 39(1), 8–20.",
  hooper2004: "Hooper, A., Zebker, H., Segall, P., Kampes, B. (2004). A new method for measuring deformation on volcanoes and other natural terrains using InSAR persistent scatterers. Geophysical Research Letters, 31, L23611.",
  berardino2002: "Berardino, P., Fornaro, G., Lanari, R., Sansosti, E. (2002). A new algorithm for surface deformation monitoring based on small baseline differential SAR interferograms. IEEE TGRS, 40(11), 2375–2383.",
  crosetto2016: "Crosetto, M., Monserrat, O., Cuevas-González, M., Devanthéry, N., Crippa, B. (2016). Persistent scatterer interferometry: a review. ISPRS Journal of Photogrammetry and Remote Sensing, 115, 78–89.",
};

export const SCIENCE: Record<string, Science> = {
  setup: {
    symbols: [
      ["B⊥", "perpendicular baseline: the distance between the two orbits measured perpendicular to the line of sight", "m; Sentinel-1 flies in a narrow orbital tube, so |B⊥| is mostly below ~200 m"],
      ["Bₜ", "temporal baseline: the time between the two acquisitions", "days; 6 or 12 for Sentinel-1"],
      ["B⊥,c", "critical baseline: the B⊥ at which the two scenes no longer share any spectrum in range", "~6 km for Sentinel-1 IW"],
      ["γ", "coherence of the pair (step 6), the product of the decorrelation terms below", "0–1"],
    ],
    theory: [
      "Two radar echoes of the same ground can only be compared if they are similar. Their similarity drops for three main reasons: the viewing geometry differs (geometric decorrelation), the ground changed between the dates (temporal decorrelation), and the noise of the instrument (thermal decorrelation). The coherence of a pair is approximately the product γ = γ_geo · γ_temp · γ_thermal.",
      "Geometric decorrelation grows linearly with the baseline: γ_geo ≈ 1 − |B⊥| / B⊥,c, with B⊥,c = λ · B_r · R · tan θ / c (B_r range bandwidth, c speed of light). For Sentinel-1 IW, B⊥,c ≈ 6 km, so a baseline of 150 m costs only ~2.5 % of coherence: the geometry is rarely the problem.",
      "Temporal decorrelation is the main limit at C band: vegetation, fields and water change in days, so only buildings, rocks and bare ground stay coherent over months. Short Bₜ is therefore the first criterion; this is why time-series methods use either very stable points (persistent scatterers, one reference date) or many short pairs (small-baseline methods).",
      "The baseline also scales the sensitivity to height (steps 4–5): a larger B⊥ gives more topographic fringes and a larger phase for a given DEM error.",
    ],
    params: [
      ["Pair", "Bₜ and B⊥ set the coherence and the height sensitivity", "Default: the reference date of the stack and the acquisition closest to it in time"],
      ["Area", "only what is computed here; larger areas take longer", "A 3 km window around the centre of the stack, adjustable"],
      ["Looks", "averaging for display and noise (step 6)", "About 400 multilooked pixels across the window"],
    ],
    refs: ["zebker1992", "hanssen2001", "ferretti2007"],
  },
  scenes: {
    symbols: [
      ["s", "complex value of an SLC pixel, s = A · e^{jψ}", "–"],
      ["A, |s|", "amplitude: strength of the echo", "plotted as 10·log₁₀|s|² in dB"],
      ["ψ", "phase of the echo: ψ = −4πR/λ + ψ_scat", "rad, −π…π"],
      ["R", "slant range: distance from the antenna to the ground", "~800–950 km for Sentinel-1 IW"],
      ["λ", "radar wavelength", "5.55 cm (C band, f₀ = 5.405 GHz)"],
      ["θ", "incidence angle at the ground", "29°–46° across the IW swath"],
      ["ψ_scat", "phase of the coherent sum of the scatterers inside the pixel", "unknown, uniform in −π…π"],
    ],
    theory: [
      "The radar emits a chirp and records the echo; focusing (range compression, then azimuth compression over the synthetic aperture) turns the raw echoes into a single-look complex image whose pixels are about 2.3 m (slant range) × 14 m (azimuth) for Sentinel-1 IW. In ground range a pixel is 2.3 m / sin θ ≈ 3.5–4.5 m wide.",
      "Each pixel is the coherent sum of all scatterers inside its resolution cell. With many scatterers of random positions, the sum is a random walk in the complex plane: the amplitude follows a Rayleigh law and the phase is uniform. This is speckle: a property of coherent imaging, not of the instrument. Averaging L independent pixels (multilooking) reduces the relative variance of the intensity by a factor L.",
      "The phase of one scene is ψ = −4πR/λ + ψ_scat: the two-way travel path R measured in wavelengths, plus the scattering phase. Since R is about 10⁷ wavelengths and ψ_scat is unknown, one phase alone says nothing. In an interferogram, ψ_scat cancels if the scatterers did not change, and the difference of R remains (step 3).",
      "Bright targets are corners formed by walls and the ground (double bounce), metal and inclined roofs; smooth water and roads reflect the wave away and look dark. Layover and shadow on steep slopes or tall buildings mix or hide signals.",
    ],
    params: [["Phase-linked SLCs", "replace each pixel by a phase estimated from statistically similar neighbours over time: less noise for distributed scatterers", "Only when the project uses phase linking (method psds)"]],
    refs: ["moreira2013", "torres2012", "bamler1998"],
  },
  coreg: {
    symbols: [
      ["δr, δa", "residual misregistration in range and azimuth", "pixels; target ≪ 0.1"],
      ["Δf_DC", "Doppler centroid difference between the looks of two consecutive TOPS bursts in their overlap", "several kHz for Sentinel-1 IW"],
      ["φ_ESD", "phase of the double-difference interferogram in the burst overlaps", "rad"],
      ["Tₐ", "azimuth sampling interval", "~2.06 ms"],
    ],
    theory: [
      "Geometric coregistration computes, for every pixel of the reference scene, the range and azimuth of the same ground point in the secondary scene from the orbits and the DEM (range-Doppler equations). With precise orbits (POEORB, ~5 cm) the error is already a few hundredths of a pixel.",
      "A misregistration δ (in resolution cells) decorrelates the pair: γ_reg ≈ sinc(δ). A shift of 0.1 pixel costs ~1.6 % of coherence; this is enough for stripmap data.",
      "TOPS (the Sentinel-1 IW mode) steers the antenna along azimuth, so the Doppler centroid changes linearly within each burst. A small azimuth misregistration δa then produces a phase ramp 2π · f_DC(t) · δa · Tₐ that changes sign from one burst to the next: visible steps at the burst edges. The requirement becomes ~0.001 pixel.",
      "Enhanced spectral diversity (ESD) measures that shift where consecutive bursts overlap: the same ground is seen with two Doppler centroids, and the double-difference phase is φ_ESD = 2π · Δf_DC · δa · Tₐ. Averaged over all overlaps, it gives δa to ~10⁻³ pixel.",
    ],
    params: [
      ["Orbits", "precise orbits (POEORB, after ~3 weeks) or restituted (RESORB, a few hours)", "POEORB when available; the stack is updated when it is published"],
      ["DEM", "used to predict the position of every pixel", "[stack] dem: SRTM 1\" or Copernicus 30 m"],
      ["ESD", "fine azimuth correction for TOPS", "[stack] esd = true (Sentinel-1)"],
    ],
    refs: ["sansosti2006", "prats2012", "yague2016"],
  },
  raw: {
    symbols: [
      ["I", "complex interferogram", "–"],
      ["s₂*", "complex conjugate of scene 2", "–"],
      ["φ", "interferometric phase, arg(I)", "rad, wrapped to −π…π"],
      ["R₁, R₂", "slant ranges from the two orbits to the same ground point", "m"],
      ["φ_atm", "difference of the atmospheric delays of the two dates", "troposphere: up to a few cm; ionosphere: dispersive"],
    ],
    theory: [
      "With s = A·e^{j(−4πR/λ + ψ_scat)}, the product I = s₁·s₂* = A₁A₂·e^{j(4π(R₂ − R₁)/λ + ψ_scat,1 − ψ_scat,2)}. If the scatterers did not change, the scattering phases cancel and φ = 4π(R₂ − R₁)/λ: the difference of the two-way paths in units of the wavelength.",
      "R₂ − R₁ has several causes, which add: the different orbits seen over a smooth Earth (flat earth), the height of the ground (topography), the motion of the ground between the dates, the different atmospheric delays, orbit errors, and the noise left by decorrelation. Separating them is the work of the next steps and of the time series.",
      "One fringe (2π) is a change of λ/2 = 2.8 cm in the one-way distance. Atmospheric delays differ between dates by up to a few centimetres over tens of kilometres (troposphere: water vapour; ionosphere: free electrons): one pair alone cannot tell them from motion.",
      "Sign convention of GeoEyes: I = s_reference · conj(s_secondary); a displacement away from the satellite gives a positive phase change, converted to a negative LOS displacement (step 9).",
    ],
    refs: ["massonnet1998", "rosen2000", "hanssen2001"],
  },
  flat: {
    symbols: [
      ["kₕ", "height-to-phase factor: phase per metre of height", "rad/m; 4πB⊥ / (λ R sin θ)"],
      ["r", "slant range coordinate across the swath", "m"],
      ["φ_flat", "phase of a smooth reference Earth (ellipsoid) seen from the two orbits", "rad"],
    ],
    theory: [
      "Moving across the swath, the look angle increases. Two orbits a distance B⊥ apart see a point at slant range r with a range difference that changes with the look angle: Δφ = (4π/λ)·B⊥·Δθ. A step Δr in slant range on a flat Earth changes the look angle by Δθ = Δr / (R tan θ), hence dφ_flat/dr = 4πB⊥ / (λ R tan θ) = kₕ · cos θ.",
      "For Sentinel-1 (λ = 5.55 cm, R ≈ 880 km, θ ≈ 39°) and B⊥ = 100 m this is about 0.032 rad per metre of slant range, one fringe every ~200 m: dense, regular fringes along range.",
      "GeoEyes does not use this linear approximation: it computes R₁ and R₂ for every pixel from the orbits and the ellipsoid, so the curvature of the Earth and the change of B⊥ across the swath are included.",
      "When the fringe rate reaches one cycle per range resolution cell, the two scenes no longer share any spectrum: this is the critical baseline of step 0.",
    ],
    params: [["Orbit accuracy", "an error of the baseline leaves a residual phase ramp across the scene", "Precise orbits; a residual ramp is removed in the time series"]],
    refs: ["bamler1998", "hanssen2001"],
  },
  topo: {
    symbols: [
      ["h", "height of the ground above the ellipsoid", "m"],
      ["h_a", "height of ambiguity: the height difference that makes one fringe", "m; ~150 m for B⊥ = 100 m"],
      ["Δh", "error of the DEM at a point (e.g. a building missing from SRTM)", "m"],
      ["φ_topo", "topographic phase, kₕ·h", "rad"],
    ],
    theory: [
      "A point at height h above the reference surface is seen at a slightly different look angle from the two orbits; the extra range difference gives φ_topo = kₕ · h, with kₕ = 4πB⊥/(λ R sin θ). The height of ambiguity is h_a = 2π/kₕ = λ R sin θ / (2B⊥).",
      "Example: B⊥ = 100 m, λ = 5.55 cm, R = 880 km, θ = 39° gives h_a ≈ 154 m. A 20 m DEM error then leaves 2π·20/154 ≈ 0.8 rad, about 3.6 mm of apparent motion — comparable to the signals we look for.",
      "This residual is proportional to B⊥, which changes from pair to pair. In a time series, the DEM error of each point is therefore estimated as the part of its phase that correlates with B⊥ (the look-angle error), and removed; it also corrects the position of the point on the map.",
      "Heights must be ellipsoidal (WGS84) for the orbit geometry; SRTM and Copernicus give heights above the geoid (EGM96 / EGM2008), converted with the geoid undulation.",
    ],
    params: [["DEM", "residual topographic phase and geolocation", "SRTM 1\" (30 m, absolute error ≤ 16 m, 90 %) or Copernicus GLO-30 (≤ 4 m); [stack] dem"]],
    refs: ["farr2007", "ferretti2001", "hanssen2001"],
  },
  coh: {
    symbols: [
      ["γ", "coherence: magnitude of the normalised complex correlation of the two scenes", "0–1"],
      ["N", "number of pixels in the estimation window", "e.g. 5 × 5 = 25"],
      ["L", "number of independent looks averaged", "≤ N"],
      ["σ_φ", "standard deviation of the interferometric phase", "rad"],
    ],
    theory: [
      "Coherence is estimated in a window: γ̂ = |Σ s₁s₂*| / √(Σ|s₁|² · Σ|s₂|²). It combines the decorrelation sources of step 0 and those of the processing (misregistration, filtering).",
      "Coherence sets the phase noise. For L looks, the Cramér–Rao bound is σ_φ = √(1 − γ²) / (γ·√(2L)) (valid for large L): γ = 0.8 and L = 20 give σ_φ ≈ 0.12 rad, about 0.5 mm. For one look the phase distribution is wide and heavy-tailed (Just & Bamler 1994).",
      "The estimator is biased upward when the window is small: for a true coherence of 0, the expected estimate is about √(π/(4N)) — 0.30 for N = 9, 0.18 for N = 25. Low values from small windows are therefore not reliable, and a coherence threshold must be read with the window size.",
      "Multilooking (averaging the interferogram over neighbouring pixels) trades resolution for noise: the variance of the phase decreases roughly as 1/L for coherent areas.",
    ],
    params: [
      ["Window", "number of pixels in the estimate: bias and resolution", "Fixed per view; shown below"],
      ["Threshold", "pixels below it are dimmed and left out of the filter, the unwrapping and the displacement", "Slider; 0.3–0.4 is common for a single pair"],
    ],
    refs: ["just1994", "touzi1999", "rodriguez1992", "zebker1992"],
  },
  filter: {
    symbols: [
      ["Z(u, v)", "2-D Fourier spectrum of the complex interferogram in a small window", "–"],
      ["S(u, v)", "smoothed magnitude of that spectrum", "–"],
      ["α", "filter exponent", "0 (none) … 1 (strong)"],
      ["residue", "discrete curl of the wrapped phase gradient around a 2×2 loop", "−1, 0, +1"],
    ],
    theory: [
      "Within a small window, a fringe pattern is close to a single frequency: its spectrum has one peak. Noise spreads over all frequencies. Goldstein & Werner (1998) multiply the spectrum by its own smoothed magnitude raised to α: Z′ = Z·S^α. The peak is amplified relative to the noise; windows overlap and are blended back.",
      "α = 0 leaves the phase unchanged; α near 1 filters strongly. Baran et al. (2003) proposed α = 1 − γ, filtering more where coherence is low.",
      "A residue is a loop of four neighbouring pixels whose wrapped phase differences do not sum to zero: a charge of ±1. Integrating the phase along a path around it gives different results depending on the side: residues mark where unwrapping is ambiguous (Goldstein et al. 1988).",
      "Filtering removes most residues in noisy areas, but it also smooths sharp real gradients and can create coherent-looking fringes in pure noise: the coherence mask must still be respected.",
    ],
    params: [
      ["α", "strength of the filter", "Slider; GeoEyes' unwrapping grid uses a Gaussian or adaptive CLAP filter instead ([ps] unwrap_grid_filter)"],
      ["Window", "size of the spectral window: larger = smoother fringes", "16, 32 or 64 pixels"],
      ["Passes", "repeat the filter", "0–3"],
    ],
    refs: ["goldstein1998", "baran2003", "goldstein1988"],
  },
  unwrap: {
    symbols: [
      ["φ_w", "wrapped phase, in −π…π", "rad"],
      ["k", "integer number of cycles added to each pixel", "–"],
      ["W(·)", "wrapping operator: adds the multiple of 2π that brings a value into −π…π", "–"],
      ["∇", "difference between neighbouring pixels (row and column)", "–"],
      ["w", "weight of each difference", "γ² in this page"],
    ],
    theory: [
      "Unwrapping looks for φ = φ_w + 2πk. It is possible when the true phase changes by less than π between neighbours (Itoh 1982): then the true gradient equals the wrapped gradient W(∇φ_w), and integrating it gives φ up to a constant.",
      "Noise, residues and steep motion break this condition. Path-following methods integrate around branch cuts that connect residues (Goldstein et al. 1988). Minimum-norm methods find the surface whose gradients best match the wrapped gradients: min Σ w·|∇φ − W(∇φ_w)|^p. For p = 2 this is a Poisson equation solved with fast cosine transforms (Ghiglia & Romero 1994); network-flow methods with statistical costs (SNAPHU) minimise the number of cycle errors (Chen & Zebker 2001).",
      "GeoEyes starts from the least-squares solution (DCT) and reweights it iteratively (IRLS) towards an L1-like norm, which keeps sharp gradients better; the result is then snapped to the wrapped phase plus whole cycles (congruence), so that each pixel keeps its measured phase.",
      "The unwrapped phase is relative: one reference point is set to zero. Patches separated from the rest by incoherent areas can be offset by whole cycles (2π = 2.8 cm). In time series, unwrapping in space and time together (Hooper & Zebker 2007) uses the temporal smoothness of the motion to reduce such errors.",
    ],
    params: [
      ["Weights", "how much each difference counts", "γ²: coherent pixels dominate"],
      ["Reference", "the zero of the unwrapped phase", "Median of the 10 % most coherent pixels, or a clicked pixel"],
      ["Iterations / target RMS", "convergence of the IRLS solver", "Up to 50 iterations; [ps] unwrap_irls_iter, unwrap_irls_target_rms"],
    ],
    refs: ["itoh1982", "goldstein1988", "ghiglia1994", "ghiglia1998", "chen2001", "hooper2007uw"],
  },
  disp: {
    symbols: [
      ["d_LOS", "displacement along the line of sight between the two dates", "mm; + toward the satellite"],
      ["l = (l_e, l_n, l_u)", "unit vector from the ground to the satellite", "l_u = cos θ ≈ 0.77; |l_n| ≈ 0.1"],
      ["σ_d", "noise of the displacement from the phase noise", "mm"],
    ],
    theory: [
      "The phase measures the change of the two-way path: φ = 4π·Δ/λ for a one-way change Δ. GeoEyes reports d_LOS = −φ·λ/(4π), positive toward the satellite: uplift, or horizontal motion toward the side the radar looks from (west for an ascending track, which looks east; east for a descending one).",
      "The radar sees only the projection of the 3-D motion on its line of sight: d_LOS = e·l_e + n·l_n + u·l_u. Polar orbits fly almost north–south, so the north component is nearly invisible (|l_n| ≈ 0.1); two geometries (ascending and descending) are needed to separate vertical and east–west motion (chapter 5).",
      "Phase noise alone gives σ_d = λ·σ_φ/(4π): with σ_φ = 0.12 rad, about 0.5 mm. In practice the atmosphere dominates a single pair: turbulent water vapour gives centimetre-level delays at scales of kilometres, which is why rates are not taken from one pair.",
      "The displacement is relative to the reference point and to the first date: absolute values need a reference on stable ground or a GNSS station.",
    ],
    refs: ["hanssen2001", "wright2004", "massonnet1998"],
  },
  velocity: {
    symbols: [
      ["N", "number of acquisitions in the stack", "e.g. 26 over one year"],
      ["d(tᵢ)", "displacement of a point at date tᵢ", "mm"],
      ["v", "mean LOS velocity", "mm/yr"],
      ["D_A", "amplitude dispersion σ_A / μ_A of a pixel over the stack", "≤ 0.4 for PS candidates"],
      ["γ_t", "temporal coherence: how well the phase of a point follows a smooth model over time", "0–1"],
      ["σ_v", "standard error of the velocity", "mm/yr"],
    ],
    theory: [
      "Persistent scatterers (PS) are pixels dominated by one stable reflector (a building corner, a pole). Their amplitude barely changes over time, and for D_A ≲ 0.25 the phase noise is about D_A radians (Ferretti et al. 2001): a cheap first selection over the whole stack. StaMPS-type methods then keep the candidates whose phase is consistent in space and time (temporal coherence; Hooper et al. 2004).",
      "For each point and date, the unwrapped phase is the sum of motion, DEM error (∝ B⊥ of the date), atmosphere and noise. The DEM error is estimated from its correlation with B⊥; the atmosphere is random from date to date but smooth in space, so it is separated by filtering: low-pass in space, high-pass in time.",
      "The velocity is the slope of the least-squares line d(t) = d₀ + v·t. Its standard error is σ_v = σ_d / √(Σ(tᵢ − t̄)²): with 26 dates spread over one year and σ_d = 3 mm, σ_v ≈ 2 mm/yr. Longer series reduce σ_v quickly (∝ T^−3/2 for regular sampling) and allow seasonal terms.",
      "Small-baseline methods (SBAS; Berardino et al. 2002) take another route: many short pairs of multilooked distributed scatterers, inverted for the time series. Phase linking (method psds) combines both, estimating one phase per date for distributed scatterers.",
    ],
    params: [
      ["D_A threshold", "how many PS candidates", "[selection] da_threshold = 0.4"],
      ["Reference area", "zero of the velocities", "Scene mean by default, or [ps] ref_lon / ref_lat"],
      ["Atmosphere", "APS model", "[atmosphere] method: linear, era5 or gacos"],
    ],
    refs: ["ferretti2001", "hooper2004", "berardino2002", "crosetto2016"],
  },
};
