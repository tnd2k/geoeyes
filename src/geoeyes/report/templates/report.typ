// GeoEyes deformation report. Data: report.json (geoeyes.report/1), figures in figures/.
// Part A: the assessment, in plain language (report.assess); Part B: the technical appendix.
#let d = json("report.json")
#let a = d.acquisition
#let s = d.stats
#let asm = d.assessment
#let imp = asm.impacts
#let fig(name) = d.figures.at(name, default: none)
#let num(x, digits: 1) = if x == none { "–" } else { str(calc.round(float(x), digits: digits)) }
#let signed(x, digits: 1) = if x == none { "–" } else if x > 0 { "+" + num(x, digits: digits) } else { num(x, digits: digits) }
#let thousands(n) = {
  let t = str(int(n))
  let out = ""
  let k = 0
  for i in range(t.len() - 1, -1, step: -1) {
    if k > 0 and calc.rem(k, 3) == 0 { out = "," + out }
    out = t.at(i) + out
    k += 1
  }
  out
}
#let val(x) = if x == none { "–" } else if type(x) == float { str(calc.round(x, digits: 2)) } else if type(x) == int { thousands(x) } else { str(x) }

#let size(b) = if b < 1e6 { num(b / 1e3) + " kB" } else { num(b / 1e6) + " MB" }
#let rate-word = if asm.basis == "vertical" { "vertical" } else { "line-of-sight" }

#set document(title: "Deformation report " + d.product_id, author: "GeoEyes")
#set page(paper: "a4", margin: (x: 2cm, top: 2.2cm, bottom: 2cm),
  header: context { if counter(page).get().first() > 1 [
    #set text(7.5pt, fill: luma(110))
    #d.project · #d.track #h(1fr) #d.product_id
  ] },
  footer: context { if counter(page).get().first() > 1 [
    #set text(7.5pt, fill: luma(110))
    GeoEyes #d.software.at("geoeyes", default: "") #h(1fr) #counter(page).display("1 / 1", both: true)
  ] })
#set text(font: ("Segoe UI", "DejaVu Sans", "Libertinus Serif"), size: 9.5pt, lang: "en")
#set par(justify: true, leading: 0.6em)
#set heading(numbering: (..n) => if n.pos().len() <= 2 { numbering("1.1", ..n) })
#show heading.where(level: 1): it => { v(0.6em); text(13pt, it); v(0.2em) }
#show heading.where(level: 2): it => text(10.5pt, it)
#show table.cell.where(y: 0): set text(weight: "bold")
#let tbl(..args) = table(stroke: (x, y) => (top: if y <= 1 { 0.5pt + luma(150) } else { 0.3pt + luma(220) }),
  inset: (x: 5pt, y: 3.5pt), ..args)
#let level-colour(level) = if level == "high" { rgb("#0ca30c") } else if level == "medium" { rgb("#eda100") } else { rgb("#d03b3b") }
#let badge(level) = {
  let c = level-colour(level)
  box(fill: c.lighten(80%), stroke: 0.6pt + c, inset: (x: 6pt, y: 3pt), radius: 3pt,
    text(weight: "bold", fill: c.darken(30%), upper(level) + " confidence"))
}
#let part(letter, title, intro) = {
  pagebreak(weak: true)
  block(width: 100%, fill: luma(245), inset: (x: 10pt, y: 9pt), radius: 3pt)[
    #text(9pt, fill: luma(100), upper("Part " + letter)) \
    #text(17pt, weight: "bold", title) \
    #v(0.1em)
    #text(9pt, fill: luma(70), intro)
  ]
  v(0.4em)
}
// one line for an analysis that has not been run: what to run
#let notrun(x) = block(inset: (left: 8pt), stroke: (left: 1.5pt + luma(190)))[
  #text(fill: luma(70))[_Not assessed:_ run #raw(x.run)#if x.at("why", default: "") != "" [ (#x.why)].]
]
#let say(x) = for t in x.text [#t ]
#let small(body) = { set par(justify: false); set text(8.5pt, hyphenate: false); body }

// ------------------------------------------------------------------ cover
#v(3cm)
#text(10pt, fill: luma(100), upper("Ground motion assessment"))
#v(0.3em)
#text(22pt, weight: "bold", d.project)
#v(0.2em)
#text(12pt, (if asm.place != "" { asm.place + " · " } else { "" }) + a.sensor + " · " + a.pass_direction + " · " + a.first + " to " + a.last)
#if d.description != "" { v(0.6em); text(10pt, d.description) }
#v(1.2cm)
#grid(columns: (auto, 1fr), column-gutter: 1.2em, row-gutter: 0.6em,
  [*Product*], d.product_id,
  [*Track*], d.track,
  [*Sensor / band*], a.sensor + " (" + a.band + "-band" + if a.mode != "" { ", " + a.mode } else { "" } + ")",
  [*Acquisitions*], str(a.n_dates) + " (" + str(a.span_days) + " days), reference " + a.reference_date,
  [*Processing*], d.ps_engine,
  [*Software*], "GeoEyes " + d.software.at("geoeyes", default: ""),
  [*Generated*], d.generated,
)
#v(1cm)
#grid(columns: (auto, 1fr), column-gutter: 1.2em, row-gutter: 0.5em,
  [*Part A*], [Assessment: what moves, where, how fast, what it affects, how sure we are, what to do (plain language)],
  [*Part B*], [Technical appendix: data, method, quality checks, results, limitations, provenance],
)
#v(1fr)
#text(8pt, fill: luma(110))[Part A gives #rate-word rates: negative means the ground goes down (sinks)#if asm.basis == "vertical" [, derived from the radar line of sight assuming the ground moves only up or down]. Part B gives line-of-sight (LOS) motion, positive toward the satellite. All values are relative to the reference area. Read section B.6 before using the results. The indicators of section 5 are also in `indicators.json` next to this report.]
#pagebreak()

// ================================================================== PART A
#part("A", "Assessment", [What the radar measurements say about the ground, for decision makers and residents. Rates are in millimetres per year (mm/yr); negative means sinking. Jargon is explained where it first appears.])

// ------------------------------------------------------------------ 1 summary
= Summary
#badge(d.confidence.level)
#v(0.3em)
#for t in asm.statements [- #t]
#if asm.recommendations.len() > 0 [
  *What to do first*
  #for (i, r) in asm.recommendations.slice(0, calc.min(3, asm.recommendations.len())).enumerate() [
    + #r.text
  ]
]
#if fig("summary_map") != none [
  #figure(image(fig("summary_map"), width: 100%, height: 10.5cm, fit: "contain"),
    caption: [#if asm.basis == "vertical" [Vertical] else [Line-of-sight] velocity of every measurement point (red and yellow: sinking, blue: rising; the class bounds, not only the hue, near zero). H1, H2…: hot spots of section 2. Star: reference area, assumed stable.])
]

// ------------------------------------------------------------------ 2 hot spots
= Hot spots
Areas where neighbouring 100 m cells all move faster than #num(asm.hot_threshold) mm/yr (at least 3 cells and 30 points), the largest and fastest first. The trend comes from the median series of each area: the rates of the first and second half of the period are compared (dashed lines) and an annual swing is fitted.
#if asm.hotspots.len() == 0 [

  No hot spot: no group of cells moves faster than #num(asm.hot_threshold) mm/yr.
]
#for h in asm.hotspots [
  #block(breakable: false, width: 100%, stroke: 0.5pt + luma(200), radius: 3pt, inset: 8pt, above: 0.8em)[
    #grid(columns: (1fr, 1.15fr), column-gutter: 1em,
      {
        set par(justify: false)
        text(11pt, weight: "bold", fill: if h.kind == "sinking" { rgb("#c23a39") } else { rgb("#2a78d6") })[#h.id · #h.kind]
        linebreak()
        [*Where:* #h.label]
        linebreak()
        if h.name != "" or h.place != "" {
          text(8pt, fill: luma(90))[#num(h.lat, digits: 5)° N, #num(h.lon, digits: 5)° E]
          linebreak()
        }
        [*How fast:* #signed(h.rate_mm_yr) mm/yr (median), #signed(h.fastest_mm_yr) mm/yr at its fastest points]
        linebreak()
        [*Trend:* #h.trend.text]
        linebreak()
        [*Size:* #num(h.area_km2, digits: 2) km², #thousands(h.n) points]
      },
      if fig("hotspot_" + h.id) != none { image(fig("hotspot_" + h.id), width: 100%) })
  ]
]

// ------------------------------------------------------------------ 3 impacts
= Impacts
What the motion means for land, buildings, networks and flooding, from the analyses run on this product. An analysis that has not been run is named with the command that runs it.

== Hazard zones
#let hz = imp.hazard
#if hz.assessed [
  #say(hz)
  #let modes = hz.by_level.keys()
  #grid(columns: (1fr, 1.5fr), column-gutter: 1em,
    tbl(columns: (auto, ..modes.map(m => 1fr)), align: (left, ..modes.map(m => right)),
      [Level], ..modes.map(m => [#m (km²)]),
      ..("very low", "low", "moderate", "high", "very high").map(lv => (lv, ..modes.map(m => num(hz.by_level.at(m).at(lv), digits: 2)))).flatten()),
    if fig("hazard_map") != none { image(fig("hazard_map"), width: 100%) })
] else [ #notrun(hz) ]

== Kind of motion
#let bh = imp.behaviour
#if bh.assessed [
  #say(bh)
  #tbl(columns: (auto, 1fr, auto, auto), align: (left, left, right, right),
    [Kind], [Reading], [Cells], [Share],
    ..bh.rows.map(r => (r.kind, r.reading, thousands(r.cells), num(r.share * 100, digits: 0) + " %")).flatten())
] else [ #notrun(bh) ]

== Buildings
#let bd = imp.buildings
#if bd.assessed [
  #say(bd)
  #grid(columns: (1fr, 1fr), column-gutter: 1em,
    if "damage" in bd {
      tbl(columns: (1fr, auto), align: (left, right), [Tilt in 10 years (angular distortion)], [Buildings],
        ..bd.damage.pairs().map(((k, v)) => (k, thousands(v))).flatten())
    },
    if "risk" in bd {
      tbl(columns: (1fr, auto), align: (left, right), [Risk (screening)], [Buildings],
        ..bd.risk.pairs().map(((k, v)) => (k, thousands(v))).flatten())
    } else if "risk_run" in bd {
      notrun((run: bd.risk_run, why: "risk to buildings"))
    })
  #if "buildings_run" in bd { notrun((run: bd.buildings_run, why: "motion and tilt of single buildings")) }
] else [ #notrun(bd) ]

== Dykes, railways and main roads
#let ln = imp.lines
#if ln.assessed [
  #say(ln)
  #grid(columns: (1fr, 1.2fr), column-gutter: 1em,
    tbl(columns: (auto, auto, auto, auto), align: (left, right, right, right),
      [Kind], [km], [Covered], [Flagged],
      ..ln.kinds.map(k => (k.kind, num(k.km), if k.covered_share == none { "–" } else { num(k.covered_share * 100, digits: 0) + " %" }, str(k.flagged_stations))).flatten()),
    if ln.hotspots.len() > 0 {
      small(tbl(columns: (1fr, auto, auto), align: (left, right, right),
        [Most uneven sections], [Fastest], [Distortion],
        ..ln.hotspots.map(x => ([#x.name (#x.kind)], signed(x.v_min_mm_yr) + " mm/yr", "1/" + str(int(calc.round(1 / x.beta_max))))).flatten()))
    })
  #text(8pt, fill: luma(90))[Covered: share of the line with measurement points nearby. Flagged: places where the settlement differs enough between neighbouring stations to reach 1/500 (one in five hundred) within the horizon of the analysis. © OpenStreetMap contributors.]
] else [ #notrun(ln) ]

== Reported floods
#let fl = imp.floods
#if fl.assessed [
  #say(fl)
  #if fl.rows.len() > 0 {
    small(tbl(columns: (1fr, auto, auto, auto, auto), align: (left, left, left, right, right),
      [Location (as reported)], [Cause], [Reported], [Rate], [vs. around],
      ..fl.rows.map(r => (r.where, r.cause, r.reported, signed(r.rate_mm_yr) + " mm/yr",
        if r.contrast_mm_yr == none { "–" } else { signed(r.contrast_mm_yr) })).flatten()))
    text(8pt, fill: luma(90))[Rate: median of the points within 100 m of the location; vs. around: the same minus the median 100–500 m around it (negative: the spot sinks faster than its surroundings). Fastest-sinking locations first.]
  }
] else [ #notrun(fl) ]

== Groundwater
#let gw = imp.groundwater
#if gw.assessed [ #say(gw) ] else [ #notrun(gw) ]

// ------------------------------------------------------------------ 4 reliability
= How sure are we
#badge(d.confidence.level)
#if d.confidence.plain.len() > 0 [ Why: #d.confidence.plain.join("; "). ] else [ No rule of section B.1 lowers the confidence. ]
The rates are relative to a reference area assumed stable (star on the map): if it moves, every rate shifts by the same amount.
#if asm.suspect_dates.len() > 0 [
  The image(s) of #asm.suspect_dates.join(", ") lie far off the trend in most hot spots at once: more likely an error of those images (weather in the atmosphere, phase unwrapping) than motion of the ground. They were left out of the trends of section 2 but are in the rates; check them (section B.2) before relying on the fastest rates.
]

#let gn = imp.gnss
#small(tbl(columns: (auto, 1fr), align: (left, left),
  [Item], [Value],
  [Radar images], str(a.n_dates) + " from " + a.first + " to " + a.last + " (" + str(a.span_days) + " days)",
  [Images kept (noise test)], d.ifgs_used,
  [Measurement points], thousands(s.n_points) + " over " + num(s.area_km2) + " km²" + if s.density_per_km2 != none { " (" + thousands(s.density_per_km2) + " per km²)" } else { "" },
  [Typical rate error], if asm.stats.std_p50 == none { "–" } else { "±" + num(asm.stats.std_p50) + " mm/yr (median standard error, " + rate-word + ")" },
  [GNSS agreement], if gn.assessed and gn.n > 0 { str(gn.n) + " station(s), RMS difference " + num(gn.rms_mm_yr) + " mm/yr" } else if gn.assessed { "no station could be compared" } else { "not assessed" },
  [Processing checks], str(d.qc_summary.pass) + " pass, " + str(d.qc_summary.borderline) + " borderline, " + str(d.qc_summary.review) + " to look at again (section B.4.1)",
))

=== GNSS stations
#if gn.assessed [
  #say(gn)
  #if gn.rows.len() > 0 {
    small(tbl(columns: (auto, auto, auto, auto, auto, auto, auto), align: (left, right, right, right, right, right, left),
      [Station], [Distance], [Dates], [InSAR], [GNSS], [Difference], [Agreement],
      ..gn.rows.map(r => (r.site, num(r.distance_m, digits: 0) + " m", str(r.epochs), signed(r.insar_mm_yr), signed(r.gnss_mm_yr), signed(r.diff_mm_yr) + " mm/yr", r.agreement)).flatten()))
    text(8pt, fill: luma(90))[Rates along the line of sight, mm/yr, over the period of the images; good: within 2 mm/yr, fair: within 5.]
  }
] else [ #notrun(gn) ]

=== What to check on the ground
#if asm.field_checks.len() > 0 [
  Visit these places to confirm the motion (cracks, tilted poles and fences, broken pipes, doors that jam) and, where possible, re-level a benchmark:
  #for t in asm.field_checks [- #t]
] else [ Nothing stands out that needs a field visit. ]

// ------------------------------------------------------------------ 5 recommendations, indicators
= Recommendations and indicators
== Recommendations and follow-up
#for r in asm.recommendations [
  + #r.text #text(fill: luma(100))[(#r.why)]
]

== Indicators
Standard indicators of this assessment, the same in every GeoEyes report, so that reports can be compared over time and fed to a digital twin of the city (file `indicators.json`, schema #d.indicators.schema). Rates: #rate-word, negative = sinking. "–": the analysis behind the value has not been run.
#{
  set par(justify: false)
  set text(7.5pt, hyphenate: false)
  tbl(columns: (auto, auto, auto, 1fr), align: (left, right, left, left),
    [Key], [Value], [Unit], [Description · source],
    ..d.indicators.indicators.pairs().map(((k, x)) => (raw(k), val(x.value), x.unit, [#x.description #text(fill: luma(110))[· #x.source]])).flatten())
}

// ================================================================== PART B
#part("B", "Technical appendix", [Data, processing, quality checks and detailed results, for specialists who assess or reproduce the measurements. Values are line-of-sight (LOS) motion, positive toward the satellite.])
#counter(heading).update(0)
#set heading(numbering: (..n) => if n.pos().len() <= 2 { "B." + n.pos().map(str).join(".") })

// ------------------------------------------------------------------ technical summary
= Technical summary
#badge(d.confidence.level)
#v(0.4em)
#for f in d.findings [- #f]
#if d.confidence.issues.len() > 0 [
  *What limits the confidence:* #d.confidence.issues.join("; ").
]
#if d.confidence.notes.len() > 0 [ #text(fill: luma(80), d.confidence.notes.join("; ") + ".") ]

#grid(columns: (1fr, 1fr), column-gutter: 1.5em,
  tbl(columns: (1fr, auto), align: (left, right),
    [Quantity], [Value],
    [Measurement points], thousands(s.n_points),
    [of which DS], thousands(s.n_ds),
    [Density], if s.density_per_km2 == none { "–" } else { thousands(s.density_per_km2) + " / km²" },
    [Area with points], num(s.area_km2) + " km²",
    [Velocity min / max], num(s.vel_min) + " / " + num(s.vel_max) + " mm/yr",
    [Velocity median], num(s.vel.p50) + " mm/yr",
    [Velocity std. error (median)], if "vel_std" in s { num(s.vel_std.p50) + " mm/yr" } else { "–" },
    [Temporal coherence (median)], if "tcoh" in s { num(s.tcoh.p50, digits: 2) } else { "–" },
    [Interferograms used], d.ifgs_used,
  ),
  if fig("velocity_map") != none { image(fig("velocity_map"), width: 100%) },
)

// ------------------------------------------------------------------ data
= Area and data
The stack covers #num(d.bbox.at(0), digits: 4)° to #num(d.bbox.at(2), digits: 4)° E and
#num(d.bbox.at(1), digits: 4)° to #num(d.bbox.at(3), digits: 4)° N. #a.n_dates acquisitions from #a.first to #a.last
(#a.span_days days) were processed as single-reference interferograms against #a.reference_date.
#if a.heading_deg != none [Satellite heading #num(a.heading_deg)°, #a.look_side\-looking.]
#if a.wavelength_m != none [Wavelength #num(a.wavelength_m * 100, digits: 2) cm.]
#if a.orbit != "" [Orbits: #a.orbit.]

#if fig("baselines") != none [
  #figure(image(fig("baselines"), width: 100%),
    caption: [Perpendicular baseline of each acquisition against the reference (star); each line is one
    interferogram.])
]

#tbl(columns: (auto, auto, auto, auto, auto, 1fr), align: (left, right, right, right, center, left),
  [Date], [Days], [B⊥ (m)], [Noise], [Used], [Note],
  ..d.dates.map(r => (
    r.date, if r.days == none { "–" } else { str(r.days) }, num(r.at("bperp_m", default: none)),
    num(r.at("noise", default: none), digits: 2), if r.used { "yes" } else { "no" },
    if r.reference { "reference" } else if r.at("weather", default: false) { "weather APS" } else { "" },
  )).flatten()
)

// ------------------------------------------------------------------ method
= Method
#for (i, st) in d.method.steps.enumerate() [
  == #st.title
  #st.text
  #if st.cites.len() > 0 [ #text(fill: luma(90))[(#st.cites.map(k => "[" + str(d.references.position(r => r.key == k) + 1) + "]").join(", "))] ]
]

== Key parameters
#tbl(columns: (auto, 1fr), [Parameter], [Value], ..d.method.params.flatten())

// ------------------------------------------------------------------ quality
= Quality
#let qc = d.at("qc", default: ())
#let mark(st) = {
  let c = if st == "pass" { rgb("#0ca30c") } else if st == "review" { rgb("#d03b3b") } else if st == "borderline" { rgb("#eda100") } else { luma(120) }
  let label = if st == "pass" { "pass" } else if st == "review" { "look again" } else if st == "borderline" { "borderline" } else { "info" }
  box(fill: c.lighten(80%), stroke: 0.5pt + c, inset: (x: 4pt, y: 2pt), radius: 2pt, text(7.5pt, weight: "bold", fill: c.darken(30%), label))
}
== Quality checks
#if qc.len() == 0 [
  No check could be made: no stack, no other track and no decomposition of this product.
] else [
  Acceptance criteria against the other geometry, the subswath seams and the ionospheric correction
  (docs/en/guide/ionosphere.md §5). A tilt of the ground shows in every line of sight; a ramp in one only is an error.
  #{
    set par(justify: false)
    set text(8.5pt, hyphenate: false)
    tbl(columns: (1.15fr, 0.85fr, auto, 2fr), align: (left, left, center, left),
      [Check], [Value], [Status], [Rule · note],
      ..qc.map(r => (r.check, r.value, mark(r.status), [#r.rule. #text(fill: luma(90), r.note)])).flatten())
  }
]

#if fig("distributions") != none [
  #figure(image(fig("distributions"), width: 100%),
    caption: [Distribution of the velocity (full range, minimum to maximum), its standard error, the temporal coherence
    and the height error (0.5–99.5 percentile range shown) over all points; vertical line: median.])
]
#if fig("noise") != none [
  #figure(image(fig("noise"), width: 100%),
    caption: [Phase noise of each interferogram (reference date excluded); grey: left out of the inversion.])
]
#let counts = d.ps_counts.pairs().filter(((k, v)) => type(v) == int)
#if counts.len() > 0 [
  Points at each selection stage: #counts.map(((k, v)) => k.replace("_", " ") + " " + thousands(v)).join(", ").
]

// ------------------------------------------------------------------ results
= Results
#if fig("velocity_map") != none [
  #figure(image(fig("velocity_map"), width: 100%),
    caption: [Mean LOS velocity, in the classes of the QGIS style and the web app (Pretty Breaks, 10 classes over
    the full range, reversed jet): red and yellow move away from the satellite (e.g. subsidence), blue toward
    it; mind the class bounds, not only the hue, near zero. Fastest points drawn on top; star: reference area;
    arrows: flight and look direction.])
]
#if fig("clusters") != none [
  #figure(image(fig("clusters"), width: 100%),
    caption: [Mean displacement (± one standard deviation) of the fastest-moving 0.5 % of points in each direction
    and of stable, coherent points.])
  #tbl(columns: (1fr, auto, auto, auto), align: (left, right, right, right),
    [Group], [Points], [Median velocity], [Centre],
    ..d.clusters.map(c => (c.label, thousands(c.n), num(c.vel_mm_yr) + " mm/yr",
      num(c.lat, digits: 4) + "° N, " + num(c.lon, digits: 4) + "° E")).flatten())
]

// ------------------------------------------------------------------ limits
= Interpretation and limitations
#for l in d.limitations [- #l]

// ------------------------------------------------------------------ appendices
#pagebreak()
#set heading(numbering: none)
= Provenance
#tbl(columns: (auto, auto, 1fr), [Phase], [Duration], [Run],
  ..d.phases.map(p => (p.phase, if p.seconds == none { "–" } else { num(p.seconds / 60) + " min" }, p.run_id)).flatten())
#v(0.5em)
Software: #d.software.pairs().filter(((k, v)) => type(v) == str).map(((k, v)) => k + " " + v).join(", ").
#if "packages" in d.software [ Packages: #d.software.packages.pairs().map(((k, v)) => k + " " + v).join(", "). ]
#if a.scenes.len() > 0 [
  == Scenes
  #tbl(columns: (auto, 1fr), [Date], [Scene], ..a.scenes.pairs().flatten())
]
#if a.burst_ids.len() > 0 [ Bursts: #a.burst_ids.join(", "). ]

= Product files
#text(8pt, tbl(columns: (auto, auto, 1fr), [File], [Size], [SHA-256],
  ..d.files.map(f => (f.path, size(f.bytes), raw(f.sha256))).flatten()))
#v(0.4em)
Points: GeoParquet (`points.parquet`, EPSG:4326, one row per point); time series: Parquet in long format
(`timeseries.parquet`: point_uid, date, disp_mm); rasters: Cloud-Optimized GeoTIFF; metadata: STAC 1.0 (`item.json`).
The report writes `report.json` (the data shown) and `indicators.json` (the indicators of section 5) next to `report.pdf`.

= References
#for (i, r) in d.references.enumerate() [ [#(i + 1)] #r.text \ ]
