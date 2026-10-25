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
    stacks/<track>-ref<YYYYMMDD>/      chồng ảnh đã đồng đăng ký (Zarr)
    ps_runs/<track>/                   kết quả engine điểm (trạng thái, điểm, chuỗi thời gian, hình QC)
    products/<project>_<track>_<first>_<last>_v<N>/   sản phẩm bất biến + report.pdf
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
| `[stack]` | `dem` | `"srtm-1"` (mặc định: tile SRTM 1" trong `~/.snap/auxdata/dem/SRTM 1Sec HGT`, tile thiếu tự tải từ mirror của ESA), `"copernicus-30"` (Copernicus GLO-30 lấy từ dữ liệu mở trên AWS, lưu vào `<workspace>/cache/dem`; dùng được cả trên 60° N/S), một thư mục tile `.hgt`, hoặc một GeoTIFF (EPSG:4326, độ cao EGM2008) |
| `[[tracks]]` | `subswaths` | Sentinel-1: chỉ xử lý dải con chỉ định, ví dụ `["IW2"]` |
| `[phase_linking]` | `enabled`, `estimator`, `shp_test`, `half_window`, `gaussian_sigma` | bật `enabled = true` cho chồng ảnh băng X dài (COSMO-SkyMed); mặc định `adaptive`, `ad` |
| `[selection]` | `da_threshold`, `ds_coherence_min` | PS chọn theo độ phân tán biên độ; DS lấy từ liên kết pha |
| `[ps]` | tên tham số StaMPS | ví dụ `unwrap_grid_size` (mặc định 10 m), `max_topo_err`, `scla_deramp`, hộp tham chiếu `ref_lon`/`ref_lat` |
| `[atmosphere]` | `method`, `select`, `era5`, `gacos` | `select = "auto"`: chỉ dùng mô hình thời tiết ở nơi nó tốt hơn APS tuyến tính |
| `[export]` | `formats` | `["gpkg"]`, thêm `"csv"` nếu cần |
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
độ kết hợp) và ghi kết quả ra `validation/corner_reflector/<time>_<track>/cr_report.pdf`.

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
