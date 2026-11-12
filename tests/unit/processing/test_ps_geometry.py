import numpy as np

from geoeyes.processing.ps.geometry import geolocate


def test_point_above_the_dem_lies_away_from_the_sensor():
    lat, lon, inc, dh = np.array([0.0]), np.array([0.0]), np.array([45.0]), np.array([10.0])
    # flying north, looking right (east): a 10 m high scatterer is 10 m farther east than the DEM-height pixel
    la, lo = geolocate(lat, lon, inc, 0.0, "right", dh)
    assert abs(lo[0] * 111_320.0 - 10.0) < 1e-6 and abs(la[0]) < 1e-12
    la, lo = geolocate(lat, lon, inc, 0.0, "left", dh)                 # looking west
    assert abs(lo[0] * 111_320.0 + 10.0) < 1e-6
    la, lo = geolocate(lat, lon, inc, 180.0, "right", -dh)             # flying south, looking west; below DEM
    assert abs(lo[0] * 111_320.0 - 10.0) < 1e-6                        # -> toward the sensor (east)


def test_local_dem_error_drops_the_scene_plane_and_keeps_buildings():
    from geoeyes.processing.ps.geometry import geolocation_dh
    rng = np.random.default_rng(0)
    lat = 20.65 + rng.uniform(0, 0.08, 5000)
    lon = 105.0 + rng.uniform(0, 0.15, 5000)
    plane = 30.0 - 500.0 * (lon - 105.0) + 300.0 * (lat - 20.65)     # tens of metres over the scene
    local = np.where(rng.uniform(size=5000) < 0.05, 25.0, 0.0) + rng.normal(0, 1.0, 5000)   # 5 % buildings
    got = geolocation_dh(plane + local, lat, lon, "local")
    assert np.median(np.abs(got - local)) < 1.0
    assert np.median(got[local > 20]) > 22
    np.testing.assert_allclose(geolocation_dh(plane, lat, lon, "full"), plane)
    assert not geolocation_dh(plane, lat, lon, "off").any()
