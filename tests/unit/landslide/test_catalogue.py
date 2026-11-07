"""F1 catalogue: name normalisation, matching to administrative units (merged provinces too), event merging."""
import pandas as pd

from geoeyes.landslide import catalogue as cat


def test_norm_strips_diacritics_and_prefixes():
    assert cat.norm("Xã Trà Leng") == "tra leng"
    assert cat.norm("huyện Nam Trà My") == "nam tra my"
    assert cat.norm("Thừa Thiên Huế") == "thua thien hue"
    assert cat.norm("Đắk Lắk") == "dak lak"
    assert cat.norm("Hòa Vang") == cat.norm("Hoà Vang")                # tone mark placement does not matter
    assert cat.norm(None) == "" and cat.norm(float("nan")) == ""


def _admin():
    rows = [(1, "P1", "quang nam", "", "", "Quảng Nam", 108.0, 15.5, 30000.0),
            (1, "P2", "da nang", "", "", "Đà Nẵng", 108.2, 16.0, 20000.0),
            (2, "D1", "quang nam", "nam tra my", "", "Nam Trà My", 108.1, 15.1, 15000.0),
            (3, "C1", "quang nam", "nam tra my", "tra leng", "Trà Leng", 108.05, 15.2, 5000.0),
            (3, "C2", "quang nam", "bac tra my", "tra son", "Trà Sơn", 108.2, 15.3, 4000.0),
            (3, "C3", "quang nam", "nam tra my", "tra son", "Trà Sơn", 108.0, 15.0, 4000.0)]
    u = pd.DataFrame(rows, columns=["level", "gid", "p", "d", "c", "name", "lon", "lat", "radius_m"])
    u["province"] = u["p"].map({"quang nam": "Quảng Nam", "da nang": "Đà Nẵng"})
    return cat.Admin(u, None)


def test_locate_commune_district_and_merged_province():
    a = _admin()
    assert a.locate("Quảng Nam", "Nam Trà My", "xã Trà Leng")["gid"] == "C1"
    assert a.locate("Quảng Nam", "", "Trà Leng")["gid"] == "C1"           # unique in the province: no district needed
    assert a.locate("Quảng Nam", "Bắc Trà My", "Trà Sơn")["gid"] == "C2"  # ambiguous name resolved by the district
    assert a.locate("Quảng Nam", "", "Trà Sơn")["level"] == 1             # ambiguous, no district: province only
    assert a.locate("Đà Nẵng", "", "Trà Leng")["gid"] == "C1"             # 2025 Đà Nẵng holds the former Quảng Nam
    assert a.locate("Quảng Nam", "Nam Trà My", "Unknown")["gid"] == "D1"
    assert a.locate("", "", "") is None


def test_clean_names_and_osm_queries():
    assert cat.clean("Trà Leng (cũ)") == "Trà Leng" and cat.clean("Xuân Hương - Đà Lạt") == "Xuân Hương"
    a = _admin()
    assert a.locate("Quảng Nam", "", "Trà Leng (cũ); Trà Vân")["gid"] == "C1"     # several communes: the first known
    q = cat.osm_queries({"place": "Đèo Khánh Lê QL27C Km45; Km43", "commune": "Nam Khánh Vĩnh",
                         "province": "Khánh Hòa"})
    assert q[0] == ("Đèo Khánh Lê QL27C Km45, Nam Khánh Vĩnh, Khánh Hòa", "place")
    assert ("Nam Khánh Vĩnh, Khánh Hòa", "commune") in q
    road = cat.osm_queries({"place": "Quốc lộ 27C Km65", "commune": "", "province": "Lâm Đồng"})
    assert road == []                                                      # a road is not a location


def test_osm_answers_must_match_the_name_asked():
    pas = {"name": "Đèo Cù Hin, Phường Nam Nha Trang, Khánh Hòa", "kind": "natural/mountain_pass"}
    assert cat.osm_accept("Đèo Cù Hin, Khánh Hòa", "place", pas)
    assert not cat.osm_accept("Đường Định Bình, Bình Định", "place", {"name": "Bình Định, Đường Quang Trung"})
    assert not cat.osm_accept("Đường tỉnh 676, Kon Tum", "place", {"name": "Đường tỉnh 671, Kon Tum"})
    com = {"name": "Xã Hùng Sơn, Thành phố Đà Nẵng", "kind": "boundary/administrative"}
    assert cat.osm_accept("Hùng Sơn, Đà Nẵng", "commune", com)
    assert not cat.osm_accept("Thượng Đức, Đà Nẵng", "commune", {"name": "Thượng Đức, Phường Ngũ Hành Sơn",
                                                                  "kind": "place/hamlet"})


def test_merge_events_and_unit_days():
    t = pd.DataFrame({
        "date": pd.to_datetime(["2020-10-28", "2020-10-29", "2020-11-05", "2020-10-28"]),
        "date_precision": ["day", "report", "day", "day"], "province": ["Quảng Nam"] * 4,
        "gid": ["C1", "C1", "C1", None], "level": ["commune", "commune", "commune", "province"],
        "lon": [108.05, 108.05, 108.05, 108.0], "lat": [15.2, 15.2, 15.2, 15.5], "source_db": ["news", "curated",
                                                                                                "news", "news"]})
    ev = cat.merge_events(t)
    assert len(ev) == 3                                                    # 28 + 29 Oct merged; 5 Nov separate
    first = ev[(ev.gid == "C1") & (ev.date == "2020-10-28")].iloc[0]
    assert first["n_sources"] == 2 and first["sources"] == "curated;news"
    pos = cat.unit_days(ev)
    assert len(pos) == 2 and set(pos.gid) == {"C1"}                        # the province-only record is not a label
