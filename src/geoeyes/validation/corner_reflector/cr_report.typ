// GeoEyes corner reflector identification report. Data: cr_report.json, figures next to it.
#let d = json("cr_report.json")
#let num(x, digits: 1) = if x == none { "–" } else { str(calc.round(float(x), digits: digits)) }
#let sgn(x, digits: 1) = if x == none { "–" } else if x >= 0 { "+" + num(x, digits: digits) } else { num(x, digits: digits) }

#set document(title: "Corner reflector report " + d.project, author: "GeoEyes")
#set page(paper: "a4", margin: (x: 1.8cm, top: 2cm, bottom: 1.8cm),
  footer: context [
    #set text(7.5pt, fill: luma(110))
    GeoEyes · #d.project · corner reflector identification #h(1fr) #counter(page).display("1 / 1", both: true)
  ])
#set text(font: ("Segoe UI", "DejaVu Sans", "Libertinus Serif"), size: 9.5pt, lang: "en")
#set par(justify: true, leading: 0.6em)
#show heading.where(level: 1): it => { v(0.5em); text(12.5pt, it); v(0.15em) }
#show heading.where(level: 2): it => text(10pt, it)
#show table.cell.where(y: 0): set text(weight: "bold")
#let tbl(..args) = table(stroke: (x, y) => (top: if y <= 1 { 0.5pt + luma(150) } else { 0.3pt + luma(220) }),
  inset: (x: 4pt, y: 3pt), ..args)

#text(9pt, fill: luma(100), upper("Corner reflector identification"))
#v(0.2em)
#text(18pt, weight: "bold", d.project)
#v(0.1em)
#text(9pt, fill: luma(90))[Generated #d.generated_at (#d.timezone) · tolerance ±#num(d.tolerance_db, digits: 0) dB]

= Summary
#for s in d.summary [- #s]
#for w in d.warnings [#text(fill: rgb("#8a5300"))[⚠ #w] \ ]

= Data
#tbl(columns: (auto, auto, auto, auto, auto), align: (left, right, right, right, right),
  [Reflector], [Latitude], [Longitude], [Height (m)], [Edge (m)],
  ..d.reflectors.map(r => (r.name, num(r.lat, digits: 7), num(r.lon, digits: 7), num(r.height, digits: 2),
    num(r.edge_m, digits: 2))).flatten())
#v(0.4em)
#text(8.5pt, tbl(columns: (auto, auto, auto, auto, auto, 1fr),
  [Date (UTC)], [Local time], [Satellite], [Track], [Pass], [Product],
  ..d.acquisitions.map(a => (a.date, a.acquired_local, a.platform, str(a.track), a.direction,
    text(7pt, a.product))).flatten()))

= Required pointing
The reflector faces the satellite azimuth and its boresight is raised to the elevation of the satellite, from the
orbit of the latest acquisition of each track; base tilt = boresight elevation − 35.26°, front edge raised.
#tbl(columns: (auto, auto, auto, auto, auto, auto), align: (left, left, right, right, right, right),
  [Reflector], [Satellite / track], [Face azimuth (°)], [Boresight (°)], [Base tilt (°)], [Incidence (°)],
  ..d.pointing.map(p => (p.reflector, p.platform + " " + str(p.track) + " " + p.direction, num(p.face_azimuth_deg),
    num(p.boresight_elevation_deg), num(p.base_tilt_deg), num(p.incidence_deg))).flatten())

#for r in d.reflectors {
  let oo = d.observations.filter(o => o.reflector == r.name)
  if oo.len() > 0 [
    = Results — #r.name
    #text(8.5pt, tbl(columns: (auto, 1fr, auto, auto, auto, auto, auto, auto),
      align: (left, left, right, right, right, center, right, right),
      [Date], [Set-up], [Expected (dBsm)], [Measured (dBsm)], [Meas. − exp.], [Within], [SCR (dB)], [From GPS (m)],
      ..oo.map(o => (o.date,
        [#num(o.setup_face_azimuth_deg, digits: 0)°, base #num(o.setup_base_tilt_deg)° \ #text(7.5pt, fill: luma(90),
          if o.setup_note != "" { o.setup_note } else if o.setup_source == "assumed" { "assumed as required" } else { "" })],
        if o.expected_dbsm == none { "– (faces away)" } else { num(o.expected_dbsm) },
        if o.measured_dbsm == none { "– (below clutter)" } else { num(o.measured_dbsm) },
        sgn(o.difference_db), if o.within_tolerance { "yes" } else { text(fill: rgb("#b71c1c"), "no") },
        num(o.scr_db), num(o.offset_m))).flatten()))
    #let f = d.figures.at(r.name, default: none)
    #if f != none [
      #figure(image(f.chips, width: 100%), caption: [β⁰ around the reflector at each acquisition, one grey scale,
        radar geometry (horizontal axis along the line of sight).])
      #figure(image(f.rcs, width: 90%), caption: [Measured RCS against the RCS expected for the set-up of each
        acquisition.])
    ]
    #let coh = d.coherence.filter(c => c.reflector == r.name)
    #if coh.len() > 0 [
      == Coherence between acquisitions
      #tbl(columns: (auto, auto, auto, auto), align: (left, right, right, right),
        [Pair], [At the reflector], [Area median], [Area 90th percentile],
        ..coh.map(c => (c.date_1 + " – " + c.date_2, num(c.at_reflector, digits: 2), num(c.area_median, digits: 2),
          num(c.area_p90, digits: 2))).flatten())
      #text(8pt, fill: luma(90))[Area: about 1 × 1 km around the reflector. Coherence close to 1 means a stable
        phase between the two acquisitions, the condition for InSAR displacement measurement.]
    ]
  ]
}

= Method
- *Predicted position*: the GPS coordinates (with ellipsoidal height) are converted to SLC pixel coordinates by
  range–Doppler geometry with the orbit of the acquisition's annotation.
- *Measured RCS (dBsm)*: calibration β⁰ = |DN|² / A² (betaNought LUT of the product); peak search within one
  resolution cell of the predicted position; energy of 3 × 5 pixels around the peak minus the clutter (median β⁰
  outside the cross of the peak), times the pixel area.
- *Expected RCS*: effective area of a triangular trihedral for the actual viewing direction and the set-up in the
  log (face azimuth, base tilt); 4πa⁴/(3λ²) on boresight.
- *Assessment*: within tolerance when the measured RCS is within ±#num(d.tolerance_db, digits: 0) dB of the expected
  one (measurement error in urban clutter).
- *Coherence*: the two chips are aligned to sub-pixel (amplitude correlation, TOPS azimuth Doppler removed), the
  linear fringe of each block removed, coherence estimated in a 3 × 5 window (biased high by the small window, so
  compared with the surrounding area).
