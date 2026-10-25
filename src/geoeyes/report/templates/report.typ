// GeoEyes deformation report. Data: report.json (geoeyes.report/1), figures in figures/.
#let d = json("report.json")
#let a = d.acquisition
#let s = d.stats
#let fig(name) = d.figures.at(name, default: none)
#let num(x, digits: 1) = if x == none { "–" } else { str(calc.round(float(x), digits: digits)) }
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

#let size(b) = if b < 1e6 { num(b / 1e3) + " kB" } else { num(b / 1e6) + " MB" }

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
#let badge(level) = {
  let c = if level == "high" { rgb("#0ca30c") } else if level == "medium" { rgb("#eda100") } else { rgb("#d03b3b") }
  box(fill: c.lighten(80%), stroke: 0.6pt + c, inset: (x: 6pt, y: 3pt), radius: 3pt,
    text(weight: "bold", fill: c.darken(30%), upper(level) + " confidence"))
}

// ------------------------------------------------------------------ cover
#v(3cm)
#text(10pt, fill: luma(100), upper("Ground deformation report"))
#v(0.3em)
#text(22pt, weight: "bold", d.project)
#v(0.2em)
#text(12pt, a.sensor + " · " + a.pass_direction + " · " + a.first + " to " + a.last)
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
#v(1fr)
#text(8pt, fill: luma(110))[Values are line-of-sight (LOS) motion relative to the reference area, positive toward the
satellite. Read section 6 before using the results.]
#pagebreak()

// ------------------------------------------------------------------ summary
= Summary
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
= Appendix A — Provenance
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

= Appendix B — Product files
#text(8pt, tbl(columns: (auto, auto, 1fr), [File], [Size], [SHA-256],
  ..d.files.map(f => (f.path, size(f.bytes), raw(f.sha256))).flatten()))
#v(0.4em)
Points: GeoParquet (`points.parquet`, EPSG:4326, one row per point); time series: Parquet in long format
(`timeseries.parquet`: point_uid, date, disp_mm); rasters: Cloud-Optimized GeoTIFF; metadata: STAC 1.0 (`item.json`).

= References
#for (i, r) in d.references.enumerate() [ [#(i + 1)] #r.text \ ]
