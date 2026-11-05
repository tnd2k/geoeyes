# Skill: dân và công trình trên nền đang lún và trong vùng ngập (các lớp của Source Cooperative)

> Bản dịch của [docs/en/skills/exposure-and-flood-layers.md](../../en/skills/exposure-and-flood-layers.md). Dịch ngày 2026-11-01.

> Bao nhiêu người và công trình nằm trên nền lún từ 5, 10, 20 mm/năm trở lên; bao nhiêu nằm trong vùng ngập của một
> tháng có sự kiện, hoặc sẽ nằm trong một kịch bản lũ sông mô hình hoá? Các lớp mở toàn cầu của Source Cooperative,
> chỉ đọc trong phạm vi sản phẩm. Trạng thái: vận hành (sàng lọc). Kiểm tra lần cuối 2026-11-01. CLI:
> `geoeyes exposure`, `geoeyes coop sync | search | layers | get`. Web app: Dự án → Source Cooperative; Phân tích
> chuyên sâu → Phân tích chuyên đề → lớp "Dân và công trình phơi nhiễm".

## 1. Khi nào dùng

- Để biến một sản phẩm vận tốc thành con số người ra quyết định đọc được: số dân và công trình theo từng lớp lún, và
  bao nhiêu trong số đó InSAR không quan sát được.
- Để đặt nền đang lún cạnh một trận ngập đã xảy ra (tháng có sự kiện, ví dụ bão Yagi, 2024-09) hoặc một kịch bản lũ
  sông (chu kỳ lặp GloFAS).
- Để tìm các lớp mở khác trên Source Cooperative (tìm trong danh mục, kể cả bằng từ tiếng Việt) và đọc một lớp trong
  một vùng để mở bằng QGIS.
- Không dùng để ước tính thiệt hại hay rủi ro từng công trình (dùng `geoeyes risk`,
  [behaviour-and-risk.md](behaviour-and-risk.md)), không dùng để lập bản đồ ngập đô thị (nước mặt quang học theo tháng
  bỏ sót ngập đường phố), không dùng để dự báo ngập.

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Sản phẩm InSAR | có | `geoeyes run` ([insar-processing.md](insar-processing.md)) | `<project>/products/<product_id>/points.parquet` có `lon`, `lat`, `vel_los_mm_yr`, `los_u` | vùng phân tích là khung bao các điểm |
| GHS-POP R2023A, mốc 2025, 3″ | tự động | `wfp/jrc-ghsl-pop` | `<workspace>/cache/sourcecoop/ghsl-pop/<bbox>.tif` | số dân cư trú mỗi ô khoảng 90 m: đây là ô phơi nhiễm |
| GlobalBuildingAtlas LoD1 | tự động (`buildings = true`) | `tge-labs/globalbuildingatlas-lod1`, mảnh GeoParquet 5°, lọc nhóm dòng theo bbox (DuckDB qua HTTP) | `cache/sourcecoop/gba-buildings/<bbox>_points.parquet` (tâm và chiều cao) | nếu lỗi thì phần dân số vẫn chạy, kèm cảnh báo |
| JRC Global Surface Water theo tháng, 30 m | khi có `flood_month` | `epoch/jrc-global-surface-water-monthly`, 2017-01 … 2024-12 | `cache/sourcecoop/gsw-monthly/<YYYY-MM>_<bbox>.tif` (1 đất, 2 nước, NaN không quan sát) | tháng sự kiện và tháng khô |
| CHIRPS v3 ngày (RNL), 0,05° | khi có `flood_month` | `wfp/chirps-rnl-daily` | `cache/sourcecoop/chirps-daily/<bbox>.json` (trung bình vùng và cực đại mỗi ngày) | máy chủ CHC giới hạn tốc độ; bản sao này thì không |
| NASA GPM IMERG late, nửa giờ, 0,1° | tuỳ chọn (khi có `flood_month`) | `dynamical/nasa-imerg-analysis-late` (kho Icechunk 2) | `cache/sourcecoop/imerg-late/<bbox>_<from>_<to>.npz` | cần Python ≥ 3.12 có icechunk ≥ 2 (dưới đây) |
| Độ sâu ngập JRC GloFAS, 90 m | khi có `glofas_rp` | `nlebovits/jrc-glofas`, chu kỳ lặp 10, 20, 50, 75, 100, 200, 500 năm | `cache/sourcecoop/glofas-depth/rp<N>_<bbox>.tif`, danh sách mảnh `tiles.json` | không tính đê |
| Trình thông dịch Icechunk | tuỳ chọn | `conda create -p <envs>/icechunk -c conda-forge python=3.12 "icechunk>=2.3" xarray zarr numpy` | `.env`: `GEOEYES_ICECHUNK_PYTHON=<envs>/icechunk/python.exe` | không có thì bỏ qua IMERG; chỉ còn CHIRPS |
| Chỉ mục danh mục | cho `coop search` | `geoeyes coop sync` (site map + API công khai) | `<workspace>/cache/opendata/source_coop.json` | quá 24 giờ là cũ; `search` tự đồng bộ lại |
| Tham số | tuỳ chọn | `[postprocess.exposure]` trong `project.toml` hoặc `--set` | TOML | `min_points`, `breaks_mm_yr`, `buildings`, `flood_month`, `dry_month`, `glofas_rp` |

Không cần tài khoản hay khoá: mọi đối tượng đều công khai tại `https://data.source.coop/<account>/<product>/<path>`.

Danh sách kiểm tra:

- [ ] `points.parquet` của sản phẩm có `los_u` và `vel_los_mm_yr`.
- [ ] Điểm tham chiếu của sản phẩm đáng tin (gắn GNSS hoặc vùng ổn định): số liệu phơi nhiễm phụ thuộc mốc 0 của vận
      tốc ([gnss-calibration.md](gnss-calibration.md)).
- [ ] `flood_month` dạng `YYYY-MM` trong khoảng 2017-01 đến 2024-12; chọn `dry_month` trong mùa khô nếu mặc định (sáu
      tháng trước) không khô.
- [ ] `glofas_rp` là một trong 10, 20, 50, 75, 100, 200, 500, hoặc 0.
- [ ] Đã đặt `GEOEYES_ICECHUNK_PYTHON` nếu muốn có đỉnh mưa nửa giờ.
- [ ] Có mạng (lần đầu đọc mọi thứ; các lần sau dùng cache).

## 3. Phương pháp

`geoeyes.hazard.exposure.run`, tham số `ExposureParams` (`[postprocess.exposure]`):

1. **Tốc độ thẳng đứng mỗi điểm**: `v_vert = vel_los_mm_yr / max(los_u, 0.2)`. Giả định chuyển dịch là thẳng đứng
   (đúng với phần lớn sụt lún trên nền phẳng; chuyển dịch ngang sẽ lẫn vào).
2. **Ô** = điểm ảnh GHS-POP (3″, khoảng 90 m) trong khung bao các điểm. Ô có `v_vert_mm_yr` = trung vị `v_vert` của
   các điểm trong ô khi có ít nhất `min_points` (3) điểm; nếu không thì ô *không được quan sát* (lớp −1), số dân của
   ô báo cáo riêng, không suy đoán.
3. **Lớp lún**: `class = searchsorted(breaks_mm_yr, −v_vert, side="right")` với `breaks_mm_yr` = (5, 10, 20, 50) →
   các lớp `< 5` (lớp 0, gồm cả nền ổn định và nâng), `5-10`, `10-20`, `20-50`, `>= 50` mm/năm lún (quy ước dấu
   GeoEyes: âm = lún).
4. **Đếm**: số dân theo lớp (tổng GHS-POP); với `buildings`, các công trình GlobalBuildingAtlas gán vào ô chứa tâm
   (tâm khung bao), theo lớp, và số công trình cao ≥ 21 m (`buildings_over_21m`); công trình trong ô không quan sát
   được đếm riêng.
5. **Ngập của một sự kiện** (`flood_month`): `flooded = (nước trong flood_month) VÀ (đất trong dry_month)` trên lưới
   GSW 30 m (tháng khô được lấy mẫu lại theo láng giềng gần nhất nếu khác lưới); nước thường xuyên và sông bị loại.
   `dry_month` mặc định là sáu tháng trước (không sớm hơn 2017). Với mỗi ô dân số, `flooded_share` = số điểm ảnh ngập
   / số điểm ảnh của ô; dân bị ngập = Σ dân × tỉ lệ; trên nền lún = như trên nhưng chỉ với lớp ≥ 1. `flooded_km2` tính
   từ diện tích điểm ảnh; `unobserved_share` = tỉ lệ điểm ảnh của tháng sự kiện không có quan sát. Điểm InSAR trên đất
   ngập so với đất khô (đất trong tháng sự kiện, không ngập): trung vị `v_vert` của mỗi bên khi có ≥ 10 điểm. Mưa:
   tổng tháng của trung bình vùng CHIRPS ngày, và ngày mưa lớn nhất. `rain_peak_30min`: nửa giờ có cường độ IMERG late
   trung bình vùng cao nhất trong tháng (UTC, mm/giờ), kèm cường độ của ô mưa lớn nhất.
6. **Kịch bản lũ sông** (`glofas_rp`): độ sâu GloFAS tại tâm mỗi ô dân số (điểm ảnh 90 m gần nhất; khô = NaN). Số
   dân trong vùng lũ, số dân ở độ sâu ≥ 1 m, số dân trên nền lún (lớp ≥ 1).

`geoeyes coop` (`geoeyes.opendata.coop`): `sync` đọc các tài khoản trong site map và sản phẩm công khai của từng tài
khoản (12 luồng); `search` xếp hạng sản phẩm theo từng từ của câu hỏi (tiêu đề và mã sản phẩm trọng số 3, thẻ 2, tài
khoản 1,5, mô tả 1; từ ≥ 4 chữ cái khớp cả theo tiền tố, ≥ 6 chữ cái khớp cả chuỗi con; phải khớp ít nhất một nửa số
từ; cộng 0,5 cho sản phẩm GeoEyes đọc được). Từ tiếng Việt của các chủ đề thường gặp được dịch trước, bỏ dấu ("dân
số" → population, "nhà", "tòa nhà", "công trình" → building, "ngập", "lũ lụt" → flood, "mưa" → rain, "lún" →
subsidence, "trượt lở" → landslide, "độ cao" → elevation, "nước" → water, …). Các hàm đọc chỉ lấy cửa sổ của vùng: yêu
cầu theo khoảng byte của COG, căn theo lưới điểm ảnh gốc; với Parquet, lọc nhóm dòng theo bbox.

## 4. Các bước triển khai

1. **(Tuỳ chọn) Khám phá danh mục.** `geoeyes coop sync` (in số sản phẩm và tài khoản); `geoeyes coop search lũ lụt`;
   `geoeyes coop layers` (sáu lớp GeoEyes đọc). Web app: Dự án → Source Cooperative.
2. **(Tuỳ chọn) Đọc một lớp để mở bằng QGIS.**
   `geoeyes coop get gsw-monthly --bbox 105.7,20.95,105.95,21.1 --month 2024-09`;
   `geoeyes coop get chirps-daily --bbox ... --from 2024-09-05 --to 2024-09-12` (≤ 10 năm);
   `geoeyes coop get imerg --bbox ... --from 2024-09-06 --to 2024-09-08` (≤ 92 ngày; in các nửa giờ ≥ 0,1 mm/giờ);
   `geoeyes coop get glofas-depth --bbox=-99.25,19.3,-99.0,19.5 --rp 100` (dùng "=" khi bbox bắt đầu bằng "-");
   `geoeyes coop get ghsl-pop --bbox ...`; `geoeyes coop get gba-buildings --bbox ...`. Tệp ghi vào
   `<workspace>/cache/sourcecoop/<layer>/`.
3. **Phơi nhiễm.** `geoeyes exposure <project> [--product <id>] --set flood_month=2024-09 --set glofas_rp=100
   [--set dry_month=2024-03] [--set breaks_mm_yr=[5,10,20,50]] [--set buildings=false]`. Web app: Phân tích chuyên sâu
   → Phân tích chuyên đề → nhóm "Kiểu chuyển dịch và rủi ro" → "Dân và công trình phơi nhiễm" → Tháng lũ, GloFAS →
   "Count the people and buildings exposed". Khoảng 110 giây cho lần chạy đầu ở Hà Nội (tải dữ liệu); nhanh hơn khi đã
   có cache. Ghi `<project>/analyses/exposure/<product_id>/exposure.json`, `exposure_cells.parquet`, `manifest.json`.
4. **Chiều cao công trình cho bài toán rủi ro.** `geoeyes risk` điền chiều cao Overture còn thiếu từ GlobalBuildingAtlas
   (mặc định `gba_heights = true`; [behaviour-and-risk.md](behaviour-and-risk.md)).

## 5. Kết quả và cách đọc

- `exposure.json` → `subsidence.classes[]`: `class`, `cells`, `people`, `buildings`, `buildings_over_21m`;
  `people_observed`, `people_not_observed`, `people_total`, `cells_observed`, `buildings_observed`,
  `buildings_not_observed`. → `flood`: `month`, `dry_month`, `flooded_km2`, `unobserved_share`, `people`,
  `people_on_sinking_ground`, `points_flooded`, `points_dry`, `v_vert_flooded_mm_yr`, `v_vert_dry_mm_yr`,
  `rain_month_mm`, `rain_wettest_day`, `rain_peak_30min`. → `glofas`: `return_period`, `people`, `people_over_1m`,
  `people_on_sinking_ground`. Thêm `credits` (phải trích dẫn) và `params`.
- `exposure_cells.parquet`: mỗi ô dân số có `lon, lat, people, points, v_vert_mm_yr, class` (−1 không quan sát), và
  `flooded_share`, `glofas_depth_m` khi có yêu cầu.
- Bản đồ web: ô tô màu theo lớp lún (xám = không quan sát), màu đậm hơn nơi đông dân (đậm hết mức ở khoảng 50 000
  người/km²); chuyển sang "Flood of the month" (tỉ lệ ngập: < 10 %, 10–30 %, 30–60 %, ≥ 60 %) hoặc "River flood" (độ
  sâu < 0,5, 0,5–1, 1–2, ≥ 2 m); các con số nằm trong chú giải.

Hà Nội, S1 quỹ đạo xuống vệt 91, sản phẩm `hanoi_s1_sentinel1-desc-091_20251001_20261015_v4` (một năm dữ liệu):

| Lớp lún (mm/năm) | Số dân | Công trình |
|---|---|---|
| < 5 | 2 581 513 | 457 022 |
| 5–10 | 155 661 | 41 690 |
| 10–20 | 16 900 | 6 247 |
| 20–50 | 225 | 123 |
| ≥ 50 | 0 | 0 |
| không quan sát | 386 197 | 109 891 |

- Yagi, 2024-09 so với tháng khô 2024-03: GSW chỉ thấy 0,05 km² nước mới, 20,7 % điểm ảnh không có quan sát; CHIRPS
  679,5 mm trong tháng, 226 mm ngày 2024-09-07. Đỉnh IMERG late 15,86 mm/giờ lúc 2024-09-09T12:30 UTC; IMERG late cho
  79 mm ngày 7/9 so với 226 mm của CHIRPS (chỉ từ vệ tinh, chưa hiệu chỉnh theo trạm đo).
- Lũ GloFAS chu kỳ 100 năm: 1 339 041 người, 1 005 341 người ở độ sâu trên 1 m, 71 927 người trên nền lún (không
  tính đê: là cận trên).
- Overture có chiều cao cho 1,4 % công trình ở Hà Nội, lên 67 % khi thêm GlobalBuildingAtlas.

(`exposure.json` hiện trên đĩa là một lần chạy sau với `glofas_rp = 500` và không có tháng ngập: 1 545 654 người,
1 224 053 người > 1 m, 80 742 người trên nền lún.)

## 6. Kiểm tra chất lượng

- `people_total` sát dân số chính thức của vùng được phủ (GHS-POP là số liệu mô hình hoá).
- `people_not_observed` và `buildings_not_observed`: luôn nêu bên cạnh số liệu của từng lớp.
- Ranh giới lớp là tốc độ thẳng đứng: kiểm tra điểm tham chiếu của sản phẩm để 0 mm/năm thật sự là nền ổn định; điểm
  tham chiếu lệch sẽ chuyển dân từ lớp này sang lớp khác.
- Phần ngập: `unobserved_share` trên khoảng 20 % hoặc `flooded_km2` gần 0 trong một trận ngập đã biết nghĩa là ảnh tổng
  hợp tháng không thấy nó; không được kết luận "không ngập".
- So `v_vert_flooded_mm_yr` với `v_vert_dry_mm_yr` chỉ khi mỗi bên có đủ điểm (mã yêu cầu tối thiểu 10).
- IMERG late so với CHIRPS: dùng IMERG cho thời điểm và cường độ, CHIRPS cho tổng ngày và tổng tháng.
- GloFAS: ở đồng bằng có đê, mỗi con số đều phải kèm câu "không tính đê, là cận trên".

## 7. Hạn chế và lỗi thường gặp

- `v_vert` giả định chuyển dịch thẳng đứng; khi `los_u` nhỏ hoặc có chuyển dịch ngang (sườn dốc) thì sai. Dùng
  [decompose-and-soft-soil.md](decompose-and-soft-soil.md) khi có hai hướng chụp.
- GHS-POP đếm dân cư trú (ban đêm), mốc 2025, ô khoảng 90 m: không phải người lao động, không chính xác đến từng nhà.
- Tâm công trình GlobalBuildingAtlas là tâm khung bao; chiều cao là giá trị mô hình hoá.
- GSW là ảnh tổng hợp tháng từ Landsat / Sentinel-2: mây và ngập đô thị ngắn ngày lọt khỏi nó (Yagi ở Hà Nội:
  0,05 km²). Ngập đô thị cần biên độ SAR của chính ngày đó (ý tưởng 4 trong
  [../research/paper-ideas.md](../research/paper-ideas.md)).
- Chỉ có các tháng GSW từ 2017-01 đến 2024-12 (bản sao); GloFAS bỏ qua đê; CHIRPS ngày là tổng 5 ngày chia theo tỉ lệ
  ngày của ERA5; IMERG late chỉ từ vệ tinh. Các khoảng IMERG gần đây (kết thúc trong vòng 3 ngày) không được lưu cache.
- Sản phẩm một năm cho tốc độ nhiễu; ngưỡng lớp 5 mm/năm sát mức nhiễu của nó.
- Vùng phân tích là khung bao các điểm chứ không phải đa giác vùng quan tâm: ô ở các góc có thể nằm ngoài vùng phủ và
  bị tính là không quan sát.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- Mọi lớp đều toàn cầu: chỉ cần đổi sản phẩm. Mexico City cần viết `--bbox=` có dấu "=" trong `coop get`.
- Chỉnh `breaks_mm_yr` theo vùng (ví dụ `[10, 50, 100, 200]` cho sụt lún nhanh ở Mexico City) và `min_points` theo mật
  độ điểm (băng X: nhiều điểm hơn trong mỗi ô 90 m).
- Chọn `flood_month` theo một sự kiện đã biết trong 2017–2024, và `dry_month` có cùng chế độ thuỷ văn.
- `glofas_rp`: 100 năm là kịch bản quy hoạch thường dùng; kiểm tra nơi có đê trước khi nêu số liệu.
- Thói quen đã biết: ở Hà Nội, chỉ trình bày GloFAS như vùng bãi được đê bảo vệ, và phần sự kiện luôn kèm lưu ý về
  GSW.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/hazard/exposure.py`, `src/geoeyes/opendata/coop.py`, `src/geoeyes/opendata/imerg_reader.py`,
  `src/geoeyes/ml/__init__.py` (`run_exposure`), `src/geoeyes/cli/main.py` (`cmd_coop`), `src/geoeyes/config/settings.py`
  (`icechunk_python`), `webapp/src/pages/Hazard.tsx` (`ExposureLegend`), `webapp/src/pages/Coop.tsx`.
- Hướng dẫn: [../guide/opendata.md](../guide/opendata.md) §8. Skill liên quan: [flood-reports.md](flood-reports.md),
  [behaviour-and-risk.md](behaviour-and-risk.md), [hazard-zoning.md](hazard-zoning.md).
- Schiavina, M., et al. (2023). GHS-POP R2023A. EC JRC. https://doi.org/10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE
- Pekel, J.-F., Cottam, A., Gorelick, N., Belward, A. S. (2016). High-resolution mapping of global surface water and
  its long-term changes. Nature 540, 418–422. https://doi.org/10.1038/nature20584
- Zhu, X. X., et al. (2025). GlobalBuildingAtlas. TUM (mediatum 1782307).
- JRC CEMS-GloFAS v2.1.2 flood hazard maps (CC BY 4.0).
- Climate Hazards Center CHIRPS3, https://doi.org/10.15780/G2JQ0P.
- NASA GPM IMERG, processed by dynamical.org (CC BY 4.0).
