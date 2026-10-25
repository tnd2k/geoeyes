from geoeyes.sensors.sentinel1.plan import parse_kml

KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Folder>
<Placemark><ExtendedData>
  <Data name="SatelliteId"><value>Sentinel-1D</value></Data>
  <Data name="Mode"><value>IW</value></Data>
  <Data name="Polarisation"><value>DV</value></Data>
  <Data name="OrbitAbsolute"><value>5207</value></Data>
  <Data name="OrbitRelative"><value>91</value></Data>
  <Data name="ObservationTimeStart"><value>2026-10-27T22:49:44</value></Data>
  <Data name="ObservationTimeStop"><value>2026-10-27T22:52:10</value></Data>
</ExtendedData>
<Polygon><outerBoundaryIs><LinearRing><coordinates>
105.0,20.0,0 107.0,20.0,0 107.0,22.0,0 105.0,22.0,0 105.0,20.0,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>no times: ignored</name></Placemark>
</Folder></Document></kml>"""


def test_parse_esa_plan_kml():
    (d,) = parse_kml(KML, "s1d_mp_user_x")
    assert (d.platform, d.mode, d.polarisation, d.orbit, d.relative_orbit) == ("S1D", "IW", "DV", 5207, 91)
    assert d.start.isoformat() == "2026-10-27T22:49:44+00:00" and d.stop > d.start
    assert d.footprint.contains(__import__("shapely").geometry.Point(105.85, 21.02))
