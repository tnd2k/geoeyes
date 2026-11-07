# Skill: tính nhạy cảm trượt lở cấp vùng từ bản kiểm kê

> Bản dịch của [docs/en/skills/landslide-susceptibility.md](../../en/skills/landslide-susceptibility.md). Dịch ngày 2026-11-01.

> Khi bão đến, sườn dốc nào sẽ trượt? Câu trả lời được học từ các đa giác trượt lở đã khoanh vẽ, trên lưới 30 m
> (về sau thêm mưa và InSAR trước sự kiện). Trạng thái: nghiên cứu; đã có bước L0 (kiểm kê, vùng bao, phân bố diện
> tích – tần suất) và L1 (nhãn), chưa có L2–L7 (biến dự báo, mô hình, mưa, InSAR, ngưỡng mưa, tái dựng sự kiện).
> Kiểm tra lần cuối 2026-11-01. CLI: `geoeyes landslide inventory | audit | labels [--study <name>]`. Web app: chưa có.

## 1. Khi nào dùng

- Câu hỏi: trượt lở *nhanh* do mưa bắt đầu ở đâu, khi có bản kiểm kê đa giác từ các cơn bão trước (Das 2024:
  Ketsana 2009, Podul 2013, Molave 2020 ở miền Trung)? Kết quả sẽ là bản đồ tính nhạy cảm 30 m, kiểm định bằng khối
  không gian và bằng chuyển giao giữa các sự kiện.
- Phục vụ quy hoạch sử dụng đất và cảnh báo sớm ở cấp huyện, tỉnh.
- Không thuộc skill này: chuyển dịch sườn chậm đo bằng InSAR (chế độ `landslide` của
  [hazard-zoning.md](hazard-zoning.md)), và tính nhạy cảm lấy nhãn từ InSAR của
  [susceptibility-and-forecast.md](susceptibility-and-forecast.md). Ở đây nhãn lấy từ bản kiểm kê, không từ InSAR.
- Chưa dùng được như một sản phẩm: mới có nhãn. Hiện dùng để chuẩn bị, rà soát bản kiểm kê và tạo nhãn huấn luyện
  tái lập được.

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Đa giác trượt lở đã khoanh vẽ (Das 2024) | có (audit, labels) | Zenodo 15596033, `Landslide_data_V2.zip` (CC-BY-4.0) | giải nén vào `<workspace>/cache/opendata/landslide/das2024/raw/Landslide_data/Landslide_data/` (shapefile `Ketsana_landslides/kesana_landslides/Ketsana_landslides.shp`, `Podul_landslides/Podul_landslides/Podul_landslides.shp`, `Molave_landslides/Molave_landslides/Molave_landslides.shp`) | `geoeyes landslide inventory` chuyển thành `inventories/landslide/central_vn_das2024.gpkg` |
| Bản xuất NASA Global Landslide Catalog | có (`inventory`) | data.nasa.gov, CSV | `<workspace>/cache/opendata/landslide/nasa_glc.csv` | cột được đọc: `latitude`, `longitude`, `country_name`, `event_date`, `location_accuracy`, `landslide_category`, `landslide_trigger`, `storm_name`, … |
| Sự kiện tự thu thập | tuỳ chọn | tự thu thập (báo chí, AHA Centre ADINet) | `<workspace>/inventories/landslide/curated_events.csv` (UTF-8): `date` (YYYY-MM-DD hoặc YYYY-MM), `lat`, `lon`, `accuracy` (`exact`, `1km`, `5km`, `commune`, `10km`, `district`, `province`…), `type`, `place`, `trigger`, `fatalities`, `source`, `url`, `notes` | sửa được; được dựng lại vào `vietnam.csv` |
| Ranh giới tỉnh | có (`inventory`) | geoBoundaries VNM ADM1 (63 tỉnh, trước 2025) | `<workspace>/cache/opendata/boundaries/vnm_adm1.geojson` (`shapeName`) | dùng để bỏ điểm ngoài Việt Nam và gán tên tỉnh |
| DEM Copernicus GLO-30 | có (audit, labels) | tự tải, mỗi mảnh 1° một lần | `<workspace>/cache/dem/copernicus-30/` | độ cao cho điểm vách trượt và độ dốc |
| Vùng nghiên cứu | có (labels) | tự vẽ hoặc tự tính (vùng thí điểm là phần giao của hai burst Sentinel-1, do script L0 tạo) | một lớp GeoPackage có cột `name`, ví dụ `studies/landslide_central_vn/l0/pilot.gpkg`, lớp `pilot`, dòng `bursts` | CLI không tạo |
| Vùng bao sự kiện | có (labels) | `geoeyes landslide audit` | `studies/<name>/audit/footprints.gpkg`, lớp `footprints` (`event`, `variant` = `near` / `hull` / `hull_shrunk`) | phạm vi khoanh vẽ không được công bố: phải ước lượng |
| Tệp nghiên cứu | có (labels) | tự viết | `studies/<name>/study.toml`, schema `geoeyes.landslide_study/1` (dưới đây) | đường dẫn tương đối với gốc không gian làm việc |

`study.toml` (bản đang dùng):

```toml
schema = "geoeyes.landslide_study/1"
[study]
name = "landslide_central_vn"
[inventory]
polygons = "inventories/landslide/central_vn_das2024.gpkg"
citation = "Das, R. (2024) ... https://doi.org/10.5281/zenodo.15596033 (CC-BY-4.0)"
[area]
file = "studies/landslide_central_vn/l0/pilot.gpkg"
layer = "pilot"
name = "bursts"
[footprints]
file = "studies/landslide_central_vn/audit/footprints.gpkg"
main = "near"
sensitivity = "hull"
[[events]]          # oldest first: reactivations look back at the earlier events
name = "Ketsana"
date = "2009-09-29"
[[events]]
name = "Molave"
date = "2020-10-28"
[labels]
cell_m = 30.0
negative_buffer_m = 60.0
ratio = 1.0
draws = 10
seed = 0
```

Danh sách kiểm tra:

- [ ] Bản kiểm kê gốc và CSV GLC nằm trong `cache/opendata/landslide/`, ranh giới tỉnh trong
      `cache/opendata/boundaries/`.
- [ ] `geoeyes landslide inventory` đã ghi `central_vn_das2024.gpkg` (lớp `polygons`, `points`).
- [ ] `geoeyes landslide audit` đã ghi `footprints.gpkg`, và đã đối chiếu bằng mắt với ảnh của từng sự kiện.
- [ ] GeoPackage vùng nghiên cứu có một dòng với `name` trùng `[area] name`.
- [ ] Tên trong `[[events]]` trùng cột `event` của đa giác, xếp từ cũ đến mới; sự kiện nào cũng có đa giác trong vùng.
- [ ] Có mạng để tải các mảnh GLO-30 ở lần chạy đầu.

## 3. Phương pháp

### 3.1 Bản kiểm kê (`geoeyes landslide inventory`, `landslide.inventory`)

- **Sự kiện được báo cáo → `vietnam.csv` / `.geojson`.** Các dòng GLC trong khung 102–110° E, 8–23,5° N, cộng các
  dòng tự thu thập. Điểm nằm ngoài mọi tỉnh quá 0,03° (khoảng 3 km, do đường bờ biển đã giản lược) bị loại. Hai
  dòng cách nhau không quá 2 ngày và 10 km là một sự kiện: giữ vị trí chính xác hơn (cùng độ chính xác thì ưu tiên
  dòng tự thu thập), dòng kia ghi vào `also_in`. `usable = 1` khi là phá huỷ sườn (`landslide`, `debris_flow`,
  `mudslide`, `rock_fall`, `complex`, `flash_flood_landslide`) và định vị từ 5 km trở xuống. `id` = SHA-1 của ngày và
  vị trí.
- **Đa giác → `central_vn_das2024.gpkg`.** WGS84; `area_m2` tính trong múi UTM gốc; hình học lỗi được sửa
  (`valid = 0`), chỉ giữ phần đa giác; `points` = một điểm nằm trong mỗi đa giác; `province` gán bằng phép nối không
  gian.

### 3.2 Rà soát, L0 (`geoeyes landslide audit`)

- **Vùng bao** từng sự kiện, dựng từ các điểm bên trong đa giác, trong múi UTM: `near` = hợp các vùng đệm 1 km, đóng
  bằng +1,5 km / −1,5 km (lấp khoảng hở dưới 3 km); `hull` = bao lõm (tỉ số 0,3) + 1 km; `hull_shrunk` = bao lõm −
  1 km. Mỗi biến thể đều trừ đi vùng đất bằng liền khối (độ dốc GLO-30 < 5°) rộng hơn 1 km². L0 thấy bao lõm của
  Ketsana chứa những vùng lớn không được khoanh vẽ, nên `near` là vùng bao chính và `hull` là biến thể để thử độ
  nhạy.
- **Diện tích – tần suất** từng sự kiện: các phân vị, đỉnh mật độ (rollover) trên 40 khoảng logarit từ 10 m² đến
  1 km², số trượt lở dưới 900 m² (một ô), và đuôi luỹ thừa (Clauset et al. 2009): `x_min` làm nhỏ nhất khoảng cách
  Kolmogorov–Smirnov trên 60 phân vị (5–90 %, đuôi ít nhất 50 phần tử) và α = 1 + n / Σ ln(A / x_min).
- **Chồng lấn**: đa giác của sự kiện này cắt đa giác của sự kiện khác (tái hoạt động), và các cặp trong cùng sự kiện
  (chồng diện tích > 1 m², chung cạnh, chạm tại điểm).

### 3.3 Nhãn, L1 (`geoeyes landslide labels`, `landslide.labels`)

- **Lưới**: `Grid(cell_m=30)` của `geoeyes.ml.layers` phủ khung bao vùng nghiên cứu (`lat0` = vĩ độ giữa); độ cao
  GLO-30 tại tâm ô; độ dốc từ gradient của chúng.
- **Mẫu dương** theo từng đa giác (vùng khởi phát, Steger et al. 2016): `scarp` = ô chứa điểm cao nhất trong số tâm ô
  nằm trong đa giác và các đỉnh của đa giác; `upper` = các ô bên trong có độ cao thuộc phần trên `upper_fraction`
  (1/3) của dải độ cao đa giác (không có thì lấy ô `scarp`); `centroid` = ô chứa trọng tâm (nếu trọng tâm nằm ngoài
  thì lấy một điểm bên trong), chỉ để so sánh. Mỗi ô và biến thể chỉ một mẫu dương; `n_polygons` đếm số đa giác cùng
  ô. `reactivated` = đa giác cắt một đa giác của sự kiện sớm hơn trong nghiên cứu.
- **Mẫu âm** theo từng biến thể vùng bao (`main` và `sensitivity`): các ô nằm trong vùng bao ∩ vùng nghiên cứu, có độ
  cao hữu hạn, cách mọi đa giác của *chính sự kiện đó* xa hơn `negative_buffer_m` (60 m), và không phải mẫu dương;
  rút không hoàn lại `ratio` × số mẫu dương, lặp `draws` lần, mỗi lần một bộ sinh số `default_rng([seed, draw,
  variant, footprint])`. Nếu không đủ ô ứng viên thì lấy hết và ghi vào `short`.
- **Không lọc theo độ dốc**: giữ cả mẫu âm trên đất bằng; báo cáo phân bố độ dốc của mẫu dương và âm để đánh giá
  mức "dễ" của mẫu âm.

## 4. Các bước triển khai

1. **Kiểm kê.** `geoeyes landslide inventory` → `inventories/landslide/vietnam.csv`, `vietnam.geojson`,
   `central_vn_das2024.gpkg`; in số lượng theo nguồn và theo sự kiện. Vài giây đến một phút.
2. **Rà soát (L0).** `geoeyes landslide audit --study landslide_central_vn` → `studies/<name>/audit/footprints.gpkg`,
   `audit.json` (vùng bao, diện tích – tần suất, chồng lấn); in diện tích và số trượt lở nằm trong mỗi vùng bao. Lần
   đầu tải các mảnh GLO-30 phủ toàn bộ bản kiểm kê.
3. **Vùng nghiên cứu và `study.toml`.** Tạo GeoPackage vùng nghiên cứu và viết tệp nghiên cứu (§2). Xem vùng bao trên
   QGIS trước khi chọn `main` và `sensitivity`.
4. **Nhãn (L1).** `geoeyes landslide labels --study landslide_central_vn [--set draws=5] [--set
   negative_buffer_m=90]` → `studies/<name>/labels/labels_<event>.parquet`, `labels.json`, `labels_<event>.png` (ba
   cửa sổ 1,5 km mỗi sự kiện: đa giác, mẫu dương từng biến thể, mẫu âm của lần rút 0), `manifest.json`. In số đa
   giác, số mẫu dương theo biến thể, số ứng viên theo vùng bao, và các lần rút bị thiếu (`short`).
5. **Duyệt tại cổng.** Mỗi bước kết thúc bằng việc chủ dự án duyệt trước khi sang bước sau (ghi chú nghiên cứu §5).
   L2–L7 chưa có lệnh.

## 5. Kết quả và cách đọc

- `labels_<event>.parquet`: `event, footprint, variant, draw, label, cell, lon, lat, height_m, slope_deg, src_fid,
  area_m2, n_polygons, reactivated`. Mẫu dương có `label = 1`, `footprint = ""`, `draw = -1`; mẫu âm `label = 0`, mỗi
  vùng bao, biến thể và lần rút một bộ dòng. Để huấn luyện, lấy mẫu dương của một biến thể và mẫu âm cùng biến thể,
  một vùng bao và một lần rút.
- `labels.json`: tham số, kích thước lưới, và theo từng sự kiện: `polygons`, `positives` theo biến thể, `candidates`
  theo vùng bao, `short`, `reactivated_positives`, `slope_deg` (n, P5, trung vị, P95, tỉ lệ dưới 5°) của mẫu dương
  và âm.
- `audit.json`: `footprints` (area_km2, n_inside / n_landslides theo biến thể), `area_frequency`, `overlaps`.

Kết quả vùng thí điểm (2026-11-01; 107,56–108,20° E, 15,00–15,21° N; lưới 2270 × 768 ô 30 m):

| Sự kiện | Đa giác | Mẫu dương scarp / upper / centroid | Ứng viên `near` / `hull` | Tái hoạt động | Độ dốc mẫu dương scarp (trung vị) | Độ dốc mẫu âm `near` (trung vị) |
|---|---|---|---|---|---|---|
| Ketsana | 1 125 | 1 111 / 2 277 / 1 106 | 532 435 / 883 671 | 0 | 29.0° | 21.8° |
| Molave | 895 | 864 / 1 011 / 872 | 284 180 / 745 167 | 46 | 26.2° | 22.5° |

L0 trên toàn bản kiểm kê (`l0/l0_audit.md`): vùng bao `near` 2 501 km² (Ketsana), 480 km² (Podul), 1 772 km²
(Molave); đuôi luỹ thừa α ≈ 2,45–2,59; không thấy rollover; Ketsana thiếu nhiều trượt lở nhỏ dưới khoảng 1 000 m².

## 6. Kiểm tra chất lượng

- `n_inside` sát `n_landslides` với `near` và `hull` (L0: 8 742 trên 8 744 trượt lở Ketsana nằm trong; `hull_shrunk`
  mất 27 % trượt lở của Podul, nên đã bị bỏ).
- Vùng bao được đối chiếu bằng mắt với ảnh PlanetScope / Sentinel-2 của từng sự kiện: cạnh thẳng như mép ảnh nghĩa là
  vùng chưa khoanh vẽ.
- Số mẫu dương mỗi sự kiện sát số đa giác trong vùng (biến thể scarp); `short` rỗng.
- Phân bố độ dốc: mẫu dương dốc hơn rõ so với mẫu âm, rất ít mẫu dương dưới 5° (scarp: 0,2–0,5 %). Báo cáo tỉ lệ mẫu
  âm dưới 5° (ở đây 1,6–3,7 %): chúng làm AUC cao lên.
- Ảnh xem nhanh (`labels_<event>.png`): tam giác scarp nằm ở đầu trên của đa giác, mẫu âm nằm ngoài đa giác.
- Số mũ đuôi diện tích – tần suất trong dải thường gặp (khoảng 2,4, Malamud et al. 2004) và ghi lại giới hạn đầy đủ
  của bản kiểm kê.

## 7. Hạn chế và lỗi thường gặp

- **Không biết phạm vi khoanh vẽ**: mẫu âm ở nơi chưa ai khoanh vẽ dạy mô hình rằng sườn chưa khoanh là sườn ổn định.
  Dùng `near`, giữ `hull` để thử độ nhạy.
- **Độ phân giải bản kiểm kê khác nhau giữa các sự kiện** (RapidEye 5 m năm 2009, PlanetScope 3 m năm 2020): so sánh
  thêm trên các trượt lở ≥ 1 000 m².
- **Ngày sự kiện là ngày bão**, không phải từng trượt lở; bộ Molave có lẽ gồm cả chuỗi bão tháng 10/2020.
- **DEM có sau Ketsana** (GLO-30, 2011–2015): vết trượt cũ có thể đã nằm trong địa hình.
- **Mẫu âm chỉ tránh đa giác của chính sự kiện đó**: một ô trên đa giác của sự kiện cũ hơn vẫn có thể là mẫu âm;
  `reactivated` chỉ đánh dấu mẫu dương.
- `audit` luôn chạy trên toàn bộ bản kiểm kê của không gian làm việc, không theo vùng nghiên cứu, nhưng ghi vào thư
  mục nghiên cứu.
- CLI không tạo vùng nghiên cứu; `[area] layer` mặc định là `pilot`.
- Chưa tính biến dự báo, mô hình, ngưỡng mưa hay biến InSAR.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- Bản kiểm kê mới: viết một hàm dựng như `build_das2024` (hoặc chuyển sang cùng dạng GeoPackage: lớp `polygons` có
  `event`, `date`, `src_fid`, `area_m2`, `province`, `valid`), rồi trỏ `[inventory] polygons` vào đó. `audit` đọc
  `inventories/landslide/central_vn_das2024.gpkg` theo tên cố định: bản kiểm kê mới phải nằm ở đường dẫn này hoặc
  phải sửa mã.
- Vùng mới cho sự kiện được báo cáo: `VN_BBOX`, tệp ranh giới và tên tỉnh đều riêng cho Việt Nam.
- Giữ nguyên: ô 30 m theo GLO-30, mẫu dương scarp, vùng đệm 60 m (hai ô), tỉ lệ 1:1, 10 lần rút, vùng bao `near`.
- Miền Bắc chưa có bản kiểm kê đa giác mở (Yagi 2024 cần khoanh vẽ; điểm của Viện Khoa học Địa chất và Khoáng sản (VIGMR) phải xin).

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/landslide/inventory.py`, `src/geoeyes/landslide/labels.py`, `src/geoeyes/landslide/study.py`,
  `src/geoeyes/cli/main.py` (`cmd_landslide`), `src/geoeyes/ml/layers.py` (`Grid`).
- Không gian làm việc: `inventories/landslide/SOURCES.md` (các bộ dữ liệu đã kiểm tra),
  `studies/landslide_central_vn/l0/l0_audit.md` (báo cáo L0 và quyết định tại cổng).
- Ghi chú nghiên cứu: [../research/landslide-susceptibility.md](../research/landslide-susceptibility.md) (kế hoạch
  L0–L8, giả thuyết, tham số).
- Das, R. (2024). Mapped landslides for Typhoon Ketsana, Molave and Tropical Storm Podul in central Vietnam
  [dataset]. Zenodo. https://doi.org/10.5281/zenodo.15596033
- Steger, S., Brenning, A., Bell, R., Glade, T. (2016). NHESS 16, 2729–2745. https://doi.org/10.5194/nhess-16-2729-2016
- Malamud, B. D., Turcotte, D. L., Guzzetti, F., Reichenbach, P. (2004). ESPL 29, 687–711.
  https://doi.org/10.1002/esp.1064
- Clauset, A., Shalizi, C. R., Newman, M. E. J. (2009). Power-law distributions in empirical data. SIAM Review 51,
  661–703. https://doi.org/10.1137/070710111
- Brenning, A. (2005). NHESS 5, 853–862. https://doi.org/10.5194/nhess-5-853-2005
- Kirschbaum, D., Stanley, T. (2018). Earth's Future 6, 505–523. https://doi.org/10.1002/2017EF000715
