> Bản tiếng Việt của [`docs/en/guide/projects-and-data.md`](../../en/guide/projects-and-data.md); bản gốc tiếng Anh là bản chuẩn (ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.

# Khai báo dự án và dữ liệu

Mỗi dự án GeoEyes là một thư mục chỉ có một tệp, `project.toml`. Mọi kết quả xử lý đều ghi ra ngay cạnh tệp này;
ảnh thô nằm trong kho lưu trữ chung của không gian làm việc.

## 1. Không gian làm việc

Biến `GEOEYES_WORKSPACE` (đặt trong `.env` hoặc biến môi trường) trỏ tới thư mục gốc của không gian làm việc:

```
<workspace>/
  archive/<sensor>/<track_id>/...      cảnh thô, dùng chung cho mọi dự án (xem §3)
  cache/                               quỹ đạo, ERA5, ... (tải lại được)
  projects/<name>/
    project.toml                       tệp khai báo (tệp duy nhất bạn phải viết)
    geom/                              đầu vào tuỳ chọn: danh sách gương phản xạ góc, nhật ký lắp đặt
    stacks/<track>-ref<YYYYMMDD>/      chồng ảnh đã khớp (Zarr)
    ps_runs/<track>/                   kết quả engine điểm (trạng thái, điểm, chuỗi thời gian, hình QC)
    products/<project>_<track>_<first>_<last>_v<N>/   sản phẩm bất biến + report.pdf, report.json, indicators.json (§6)
    exports/<product>/                 GeoPackage (kèm kiểu hiển thị QGIS), CSV
    validation/corner_reflector/       báo cáo gương phản xạ góc
    runs/<run_id>/                     hồ sơ lần chạy: manifest, log.jsonl, mỗi pha một tệp log
    .state/                            trạng thái các pha (pha nào đã cập nhật)
```

`<track_id>` có dạng `<sensor>-<asc|desc>[-<quỹ đạo tương đối, 3 chữ số>]`, ví dụ `sentinel1-desc-091`, `cosmo_skymed-asc`,
`capella-asc`.

## 2. `project.toml`

Chỉ vài dòng là bắt buộc; phần còn lại lấy từ preset cảm biến và giá trị mặc định. Ví dụ dự án Sentinel-1
tối giản (chính là `projects/hanoi_s1`):

```toml
schema = "geoeyes.project/1"

[project]
name = "hanoi_s1"                 # = tên thư mục: a-z, 0-9, _ -
method = "psi"                    # psi | psds (liên kết pha + điểm tán xạ phân bố) | ps_lite (Capella)

[aoi]
bbox = [105.76, 20.97, 105.89, 21.07]     # tây, nam, đông, bắc (độ, WGS84)

[[tracks]]
sensor = "sentinel1"              # sentinel1 | cosmo_skymed | capella
direction = "descending"          # ascending | descending
relative_orbit = 91               # Sentinel-1: bắt buộc để tải dữ liệu

[acquire]
date_range = [2025-10-01, 2026-10-23]
max_per_month = 3                 # tuỳ chọn, lọc bớt: chỉ lấy N lần chụp đầu mỗi tháng

[atmosphere]
method = "era5"                   # none (APS tuyến tính) | era5 | gacos
```

`geoeyes check <project>` kiểm tra tệp và môi trường. Các mục tuỳ chọn hay dùng:

| Mục | Khoá | Ghi chú |
|---|---|---|
| `[network]` | `reference` | `"auto"` (lấy ngày trung vị, rồi giữ cố định khi có cảnh mới) hoặc một ngày cụ thể |
| `[stack]` | `dem` | `"srtm-1"` (mặc định: tile SRTM 1" trong `~/.snap/auxdata/dem/SRTM 1Sec HGT`, tile thiếu tự tải từ mirror của ESA), `"copernicus-30"` (Copernicus GLO-30 lấy từ dữ liệu mở trên AWS, lưu vào `<workspace>/cache/dem`; dùng được cả trên 60° N/S), `"lidar-3dep"` (chỉ ở Mỹ: mặt trên cùng của đợt khảo sát lidar USGS 3DEP mới nhất phủ AOI cộng 500 m, ô 1 m, có cả công trình, đặt trong GLO-30; cần `pip install laspy[lazrs]`; dùng cho stack spotlight có độ cao mơ hồ dưới 1 m), một thư mục tile `.hgt`, hoặc một GeoTIFF (EPSG:4326, độ cao EGM2008) |
| `[[tracks]]` | `subswaths` | Sentinel-1: chỉ xử lý dải con chỉ định, ví dụ `["IW2"]` |
| `[phase_linking]` | `enabled`, `estimator`, `shp_test`, `half_window`, `gaussian_sigma` | bật `enabled = true` cho chồng ảnh băng X dài (COSMO-SkyMed); mặc định `adaptive`, `ad` |
| `[selection]` | `da_threshold`, `ds_coherence_min` | PS chọn theo độ phân tán biên độ; DS lấy từ liên kết pha |
| `[ps]` | tên tham số StaMPS | ví dụ `unwrap_grid_size` (mặc định 10 m), `max_topo_err`, `scla_deramp`, hộp tham chiếu `ref_lon`/`ref_lat` |
| `[atmosphere]` | `method`, `select`, `era5`, `gacos` | `select = "auto"`: chỉ dùng mô hình thời tiết ở nơi nó tốt hơn APS tuyến tính |
| `[export]` | `formats` | `["gpkg"]`, thêm `"csv"` nếu cần |
| `[product]` | `spatial_filter`, `spatial_filter_radius_m`, `_k`, `_min_neighbours`, `_dv_min`, `_z` | mặc định bật: điểm có vận tốc lệch khỏi trung vị của các điểm lân cận (30 điểm gần nhất trong 200 m) quá max(10 mm/năm, 4 × MAD) bị loại khỏi sản phẩm (danh sách trong `spatial_outliers.parquet`) |
| `[report]` | `copy_to` | chép thêm báo cáo PDF vào thư mục này |
| `[validation.corner_reflector]` | `points`, `setup`, `timezone`, `edge_m` | xem §4 |

Tệp đầy đủ, có chú thích, của `projects/mexico_s1`, `mexico_capella` và `hanoi_csk` liệt kê mọi mục kèm
giá trị đang có hiệu lực.

## 3. Dữ liệu thô theo cảm biến

**Sentinel-1** — không phải chép gì. Khi có `[acquire] date_range` và `relative_orbit` của vệt quỹ đạo, pha `acquire`
tự tìm trên ASF các burst phủ AOI và tải về `archive/sentinel1/<track_id>/<year>/<SLC>/`
(mỗi lần chụp một thư mục: `bursts.json`, `IWn_POL_<burst>.tiff`, tệp XML siêu dữ liệu). Cần token NASA Earthdata
đặt trong `EARTHDATA_TOKEN`. Quỹ đạo chính xác (POEORB) tự động tải về. Không khai báo `date_range` thì dùng kho lưu trữ
đúng như hiện có.

**COSMO-SkyMed** — mỗi ngày chụp một thư mục, chứa sản phẩm HDF5 (SCS_B / SCS_U):

```
archive/cosmo_skymed/<track_id>/          hoặc thư mục bất kỳ khai báo ở [acquire] archive
  20111017/CSKS2_SCS_B_HI_03_HH_RA_SF_20111017225221_20111017225229.h5
  20111220/...
```

**Capella** — mỗi ngày chụp một thư mục, chứa GeoTIFF SLC và tệp siêu dữ liệu JSON mở rộng đi kèm:

```
archive/capella/<track_id>/
  20240626/CAPELLA_C14_SM_SLC_HH_20240626150051_20240626150055.tif
           CAPELLA_C14_SM_SLC_HH_20240626150051_20240626150055_extended.json
```

Tên thư mục phải bắt đầu bằng `YYYYMMDD`; cần tối thiểu 3 ngày chụp (thực tế nên từ 15 trở lên cho PS). Nếu dữ liệu nằm
chỗ khác, đặt `[acquire] archive = "D:/path/to/folders"`.

## 4. Gương phản xạ góc (tuỳ chọn, Sentinel-1)

```toml
[validation.corner_reflector]
points = "geom/points.csv"        # name, lat, lon, height (m, độ cao ellipsoid), edge_m
setup = "geom/cr_setup.csv"       # name, valid_from, face_azimuth_deg, base_tilt_deg, note  (giờ địa phương)
timezone = "Asia/Ho_Chi_Minh"
```

`geoeyes cr-report <project>` đo từng gương phản xạ trên từng lần chụp trong kho lưu trữ (RCS, vị trí,
độ nhất quán) và ghi kết quả ra `validation/corner_reflector/<time>_<track>/cr_report.pdf`.

## 5. Chạy

```
geoeyes check  <project>          # kiểm tra cấu hình + môi trường
geoeyes plan   <project>          # xem sẽ chạy gì và vì sao (cảnh mới, tham số đã đổi)
geoeyes run    <project>          # acquire -> build_stack -> [phase_linking] -> ps -> build_product -> export -> report
geoeyes status <project>
```

Chạy lại tốn rất ít: pha nào có đầu vào hoặc tham số thay đổi thì mới chạy. `plan` phát hiện lần chụp mới (trên ASF, hoặc thư mục
ngày mới); chồng ảnh được nối thêm mà vẫn giữ ngày tham chiếu (đổi ngày tham chiếu thì dựng lại toàn bộ),
rồi các pha sau tạo ra phiên bản sản phẩm mới. Dùng `--force <phase>` để buộc chạy lại một
pha, `--from` / `--to` / `--only` để chọn pha, `--track` để chỉ chạy một vệt quỹ đạo trong dự án nhiều vệt.

**Bỏ qua pha.** `--skip <phase>` (hoặc `--skip <track>/<phase>`, dùng nhiều lần được) giữ nguyên một pha: pha đó
không được kiểm tra (bỏ qua `acquire` thì không tìm trên ASF) và trạng thái của nó không làm các pha sau phải chạy.
Trên trang dự án, công tắc ở góc trên bên phải mỗi thẻ pha làm đúng việc này cho các lần chạy bấm từ đó (lựa chọn
được trình duyệt nhớ theo từng dự án).

**Các bước của bộ xử lý điểm.** Bộ `ps` lưu checkpoint sau mỗi bước trong 8 bước
(`ps_runs/<track>/checkpoints/step<N>.pkl`): 1 điểm ứng viên, 2 ước lượng gamma, 3 chọn điểm, 4 lọc điểm, 5 hiệu
chỉnh pha, 6 giải gói pha lượt 1, 7 giải gói pha lượt 2, 8 vận tốc, SCN và xuất kết quả. Lần chạy bị dừng, bị tắt
hoặc lỗi sẽ chạy tiếp sau bước cuối cùng đã xong, miễn là stack và tham số của bước đó cùng các bước trước không
đổi (ví dụ đổi một tham số giải gói pha thì bước 1-5 vẫn được giữ). `--ps-from N` tính lại bước N và các bước sau;
`--ps-to N` dừng sau bước N (pha chuyển sang *tạm dừng*, lần chạy sau tiếp tục từ bước N + 1). Thẻ `ps` hiện các
bước đã lưu và có hai lựa chọn tương ứng.

`[ps] unwrap_time_win = "auto"` tự đặt cửa sổ thời gian của bước giải gói pha không gian–thời gian theo dữ liệu: một phần tư khoảng thời gian của chuỗi, ít nhất bốn khoảng lấy mẫu, trong khoảng 60–730 ngày (giá trị đã dùng được ghi trong `params.json` của lần chạy). Mặc định 730 ngày của StaMPS hợp với chuỗi nhiều năm; với chuỗi ngắn hơn, mô hình thời gian gần như là một đường thẳng và yếu nhất ở hai đầu chuỗi.

```bash
geoeyes run hcm_hist_des --skip acquire --skip build_stack          # vào thẳng ps
geoeyes run hcm_hist_des --skip acquire --ps-from 6 --ps-to 6       # giải gói pha lượt 1 lại rồi dừng
```

**Kiểm tra stack trước khi chọn điểm.** Tab **Stack** của dự án (hoặc lệnh `geoeyes stack-qc <project>`) hiện từng
ngày chụp của stack đã đồng đăng ký so với ảnh tham chiếu, đã multilook: biên độ, interferogram đã quấn (đã trừ pha
hình học) và độ kết hợp. Bảng đi kèm liệt kê baseline vuông góc, độ cao mơ hồ, độ kết hợp trung bình, độ lệch còn lại
sau đồng đăng ký và tương quan biên độ; hai chỉ số cuối tính trên vùng cắt giữa ảnh ở độ phân giải đầy đủ. Ảnh được
ghi vào `stacks/<stack_id>/qc/`.

Phần kiểm tra tự chạy sau `build_stack` với mọi cảm biến trừ Sentinel-1 (stack S1 rất lớn); khi cần thì chạy từ tab.
Một stack tốt có độ lệch dưới 0,1 pixel, tương quan biên độ gần với cặp tốt nhất, và có vân hoặc pha trơn ở nơi độ
kết hợp cao. Độ lệch hàng chục pixel, hoặc interferogram toàn nhiễu trong khi ảnh biên độ vẫn thấy rõ nhà cửa, nghĩa
là đồng đăng ký đã hỏng ở ngày đó. Umbra từng như vậy trước khi có bước dò độ lệch thô: quỹ đạo đặt các lần chụp
cách nhau 15–25 m.

## 6. Báo cáo

Pha `report` (hoặc lệnh `geoeyes report <project> [--product <id>]`, chạy lúc nào cũng được) ghi ba tệp vào thư mục
sản phẩm: `report.pdf`, `report.json` (mọi giá trị có trong báo cáo) và `indicators.json`. Bản PDF gồm hai phần:

- **Phần A — Đánh giá**, viết bằng lời dễ hiểu cho cán bộ thành phố và người dân: một trang tóm tắt (chỗ nào lún hay
  trồi, ở đâu, nhanh đến mức nào, chắc chắn đến đâu, việc cần làm trước, kèm bản đồ vận tốc theo phương đứng); các
  **điểm nóng** (những ô 100 m liền nhau chuyển động nhanh hơn 5 mm/năm hoặc gấp đôi sai số trung vị, mỗi điểm nóng
  có vị trí, tốc độ, xu hướng — đang nhanh lên, chậm lại, theo mùa hay đều — và chuỗi thời gian); các **tác động** đọc
  từ những phân tích đã chạy trên sản phẩm (`hazard`, `behaviour`, `buildings`, `risk`, `lines`, danh mục điểm ngập
  của `geoeyes floods`, mối liên hệ với nước ngầm trong `hazard`); **độ tin cậy** (mức tin cậy, số ảnh, mức khớp với
  GNSS của `geoeyes gnss`, các phép kiểm tra xử lý, những chỗ cần kiểm tra ngoài thực địa); **khuyến nghị** và
  **bảng chỉ số**.
- **Phần B — Phụ lục kỹ thuật**: tóm tắt kỹ thuật, dữ liệu, phương pháp, kiểm tra chất lượng, kết quả, hạn chế,
  nguồn gốc dữ liệu, danh sách tệp sản phẩm, tài liệu tham khảo (mục B.1–B.6).

Phân tích nào chưa chạy thì mục tương ứng ghi rõ là chưa đánh giá, kèm lệnh để chạy, nên không mục nào bị bỏ trống
mà không có lời giải thích; muốn đưa phân tích vào báo cáo thì chạy phân tích trước rồi mới chạy `geoeyes report`.
Tốc độ ở Phần A là theo phương đứng (v_LOS / l_u, giả định mặt đất chỉ lên hoặc xuống), âm = lún; Phần B vẫn giữ
hướng nhìn của vệ tinh (LOS). Tên địa danh chỉ lấy từ bộ nhớ đệm có sẵn trên máy (tên địa điểm của các chồng ảnh, tên
tuyến OSM của `geoeyes lines`, các điểm ngập đã định vị): báo cáo không gửi yêu cầu nào ra mạng.

`indicators.json` (lược đồ `geoeyes.indicators/1`) chứa cùng một bộ chỉ số trong mọi báo cáo, để so sánh các báo cáo
theo thời gian và làm đầu vào cho bản sao số (digital twin). Khoá nào cũng luôn có mặt; `value` là `null` khi phân
tích tương ứng chưa chạy (`source: "not assessed"`):

| Khoá | Đơn vị | |
|---|---|---|
| `area_monitored_km2`, `points_n`, `points_density_per_km2` | km², số lượng, 1/km² | độ phủ |
| `period_first`, `period_last`, `period_days`, `images_n` | ngày tháng, ngày, số lượng | thời kỳ |
| `vel_p01/p05/p50/p95/p99_mm_yr`, `vel_min/max_mm_yr`, `vel_std_p50_mm_yr` | mm/năm | tốc độ các điểm (`velocity_basis`) |
| `sinking_rate_max_mm_yr`, `area_sinking_over_{5,10,20}_mm_yr_km2`, `area_rising_over_{5,10,20}_mm_yr_km2` | mm/năm, km² | ô 100 m có ≥ 3 điểm |
| `hotspots_sinking_n`, `hotspots_rising_n`, `hotspot_threshold_mm_yr` | số lượng, mm/năm | điểm nóng |
| `hazard_{subsidence,landslide}_{very_low…very_high}_km2`, `hazard_accelerating_cells_n`, `hazard_rain_coupled_cells_n` | km², số lượng | `geoeyes hazard` |
| `groundwater_coupled_cells_n`, `groundwater_storage_trend_mm_yr` | số lượng, mm/năm | `hazard` có GLDAS |
| `motion_{stable,steady,seasonal,speeding,slowing,onset,step}_cells_n` | số lượng | `geoeyes behaviour` |
| `buildings_with_points_n`, `buildings_sinking_over_{5,10,20}_mm_yr_n`, `buildings_tilt_over_1_{500,300}_n` | số lượng | `geoeyes buildings` |
| `buildings_risk_{very_low…very_high}_n` | số lượng | `geoeyes risk` |
| `lines_km`, `lines_flagged_stations_n` | km, số lượng | `geoeyes lines` |
| `flood_reports_n`, `flood_reports_in_sinking_n` | số lượng | `geoeyes floods` |
| `gnss_stations_n`, `gnss_rate_diff_rms_mm_yr` | số lượng, mm/năm | `geoeyes gnss` |
| `qc_review_n`, `confidence` | số lượng, mức | kiểm tra chất lượng, quy tắc độ tin cậy |

Mỗi mục có dạng `{"value", "unit", "description", "source"}`; tệp còn ghi `velocity_basis` (`vertical` hoặc `los`),
mã sản phẩm, dự án, vệt quỹ đạo và khung bao.
