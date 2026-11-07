# Skill: xử lý InSAR, từ chồng ảnh SAR đến sản phẩm vận tốc

> Bản dịch của [docs/en/skills/insar-processing.md](../../en/skills/insar-processing.md). Dịch ngày 2026-11-01.

> Biến một chồng ảnh SAR trên một vùng thành sản phẩm điểm có phiên bản: vận tốc theo hướng nhìn của vệ tinh (LOS),
> chuỗi thời gian chuyển dịch, hình kiểm tra chất lượng, dữ liệu xuất cho GIS và báo cáo PDF. Trạng thái: vận hành
> (Sentinel-1, COSMO-SkyMed, Capella, ICEYE, Umbra); TerraSAR-X và ALOS đã khai báo nhưng còn bị chặn (chưa có bộ
> dựng chồng ảnh). Kiểm tra gần nhất 2026-11-01. CLI: `geoeyes check / plan / run / status / report`. Web app:
> Projects → New project, sau đó trang dự án (các tab Pipeline, Stack, Runs, Settings).

## 1. Khi nào dùng

- Bạn có, hoặc tải được, ít nhất 3 lần chụp của một vệ tinh trên cùng vệt quỹ đạo (thực tế cần từ 15 trở lên cho
  điểm tán xạ bền vững) và muốn đo chuyển dịch mặt đất theo LOS tại từng điểm, kèm chuỗi thời gian.
- Đây là skill đầu tiên của chuỗi: [stack-qc.md](stack-qc.md), khí quyển, hiệu chỉnh GNSS, phân vùng nguy cơ và
  các phân tích khác đều đọc chồng ảnh hoặc sản phẩm của nó.
- Không dùng cho: một giao thoa đồ đơn lẻ (xem ../guide/learn-insar-pair.md), mạng đường cơ sở ngắn SBAS
  (`method = "sbas"` được schema chấp nhận nhưng chưa có cài đặt), dữ liệu TerraSAR-X hoặc ALOS (chưa có bộ dựng
  chồng ảnh `native`: `geoeyes plan` báo `build_stack` là *blocked*).

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Thư mục gốc không gian làm việc | có | thư mục bất kỳ còn nhiều chỗ (chồng ảnh S1 cỡ hàng chục GB) | `GEOEYES_WORKSPACE` trong `.env` hoặc biến môi trường; hoặc `--workspace` | chứa `archive/`, `cache/`, `projects/` |
| Khai báo dự án | có | viết tay hoặc tạo từ web app (Projects → New project) | `<workspace>/projects/<name>/project.toml`, `schema = "geoeyes.project/1"` | `name`: a-z, 0-9, `_`, `-`, tối đa 64 ký tự, trùng tên thư mục |
| Phương pháp | có | `psi` (hoặc `psds`, cùng một engine) hay `ps_lite` | `[project] method` | Capella bắt buộc `ps_lite`; `ps_lite` chỉ cho Capella và Umbra (schema kiểm tra) |
| Vùng quan tâm (AOI) | có | khung bao, độ WGS84 | `[aoi] bbox = [west, south, east, north]` | `acquire` và `build_stack` đều cần; `[aoi] file` không được bộ dựng `native` đọc |
| Vệt quỹ đạo | có | vệ tinh và hướng bay; S1 thêm số quỹ đạo tương đối | `[[tracks]] sensor`, `direction`, `relative_orbit` (S1), tuỳ chọn `subswaths = ["IW2"]` | `track_id` = `<sensor>-<asc|desc>[-<quỹ đạo 3 chữ số>]`, ví dụ `sentinel1-desc-091`, `cosmo_skymed-asc` |
| Burst Sentinel-1 | có (S1) | pha `acquire` tải từ ASF (burst SLC, VV) | `[acquire] date_range = [start, end]`; tệp vào `archive/sentinel1/<track_id>/<year>/<SLC>/` (`bursts.json`, `IWn_VV_<i>.tiff`, XML) | cần `EARTHDATA_TOKEN`; `[acquire] max_per_month` (preset S1: 2) giữ N ngày đầu mỗi tháng |
| Ảnh COSMO-SkyMed | có (CSK) | nhà cung cấp giao (không tải tự động) | mỗi ngày một thư mục `YYYYMMDD/` chứa `CSK*_SCS_*.h5` (SCS_B / SCS_U), trong `archive/cosmo_skymed/<track_id>/` hoặc `[acquire] archive` | tên thư mục đúng 8 chữ số |
| Ảnh Capella | có (Capella) | nhà cung cấp hoặc dữ liệu mở ([opendata-stacks.md](opendata-stacks.md)) | `YYYYMMDD/CAPELLA_*_SLC_*.tif` + `*_extended.json` | nguyên cảnh |
| Ảnh ICEYE | có (ICEYE) | nhà cung cấp hoặc dữ liệu mở | `YYYYMMDD/ICEYE_*_SLC.json` + tệp SLC-COG `.tif` cùng tên | dữ liệu mở: `[acquire] opendata = "<stack id>"` tự tải và cắt |
| Ảnh Umbra | có (Umbra) | dữ liệu mở hoặc nhà cung cấp | `YYYYMMDD/*SICD*.nitf`, hoặc bản cắt `*SICD*.tif` + `*SICD*.xml` | chỉ `ps_lite` |
| DEM | có (tự động) | `[stack] dem`: `srtm-1` (mặc định, ô SRTM 1" trong `~/.snap/auxdata/dem/SRTM 1Sec HGT`, ô thiếu tự tải), `copernicus-30` (GLO-30 vào `<workspace>/cache/dem`), `lidar-3dep` (chỉ ở Mỹ, bề mặt lidar USGS lồng trong GLO-30, cần `laspy[lazrs]`), thư mục `.hgt`, hoặc GeoTIFF | nạp trên AOI ± 0,2° | GeoTIFF: EPSG:4326, độ cao trên EGM2008; `copernicus-30` dùng được trên 60° N/S |
| Quỹ đạo chính xác (S1) | tự động | POEORB tải vào `<workspace>/cache/orbits` | không cần đặt | ngày dựng bằng quỹ đạo RESORB / annotation sẽ được khớp lại khi có POEORB (kiểm tra với ngày đã ≥ 15 ngày tuổi) |
| Mô hình thời tiết | tuỳ chọn | ERA5 (`~/.cdsapirc`), CERRA (châu Âu), GACOS (đặt hàng thủ công) | `[atmosphere] method = "era5" / "cerra" / "gacos"`, `[atmosphere.gacos] dir` | mặc định `none` = APS tuyến tính pha – độ cao; xem skill khí quyển |
| Vùng tham chiếu | tuỳ chọn | nền ổn định đã biết | `ps`: `[ps] ref_lon = [min, max]`, `ref_lat = [min, max]` hoặc `ref_centre_lonlat` + `ref_radius`; `ps_lite`: `[ps_lite] ref_latlon`, `ref_radius_m` | mặc định `ps`: mọi điểm (trung bình cảnh); `ps_lite`: tự chọn theo độ phân tán biên độ |

Danh sách kiểm tra trước `geoeyes run`:

- [ ] `geoeyes check <project>` kết thúc bằng `all checks passed` (gói, không gian làm việc, cấu hình, không pha nào *blocked*).
- [ ] S1: đã có `relative_orbit`, có `EARTHDATA_TOKEN`, `date_range` phủ đúng giai đoạn cần.
- [ ] Dữ liệu thương mại: mọi thư mục ngày tên `YYYYMMDD` và chứa đúng các tệp trên; ít nhất 3 ngày nằm trong
      `date_range`; `direction` của `[[tracks]]` khớp cảnh tham chiếu (nếu không, bước dựng sẽ dừng).
- [ ] AOI nằm trong vùng phủ của mọi ngày (S1: burst được chọn theo lần chụp tham chiếu).
- [ ] Cần liên kết pha? Đặt `[phase_linking] enabled = true` (preset COSMO-SkyMed và ICEYE đã bật sẵn).
- [ ] Ổ đĩa: chồng ảnh S1 26 ngày trên một thành phố cỡ hàng chục GB; nên để `stacks/` trên ổ nhanh.

## 3. Phương pháp

**Quy trình xử lý.** Với mỗi vệt quỹ đạo: `acquire` → `build_stack` → `phase_linking` (tuỳ chọn) → `ps` →
`build_product` → `export` → `report` (`controller/pipeline.py`). Mỗi pha có một dấu vân tay (fingerprint) của đầu
vào và tham số; `plan` đánh dấu pha là *up-to-date* khi dấu vân tay không đổi và đầu ra còn đủ. Một pha phải chạy
thì mọi pha sau nó cũng chạy. Cấu hình hiệu lực là preset của vệ tinh (`config/presets/<sensor>.toml`, theo vệ tinh
của vệt đầu tiên) trộn sâu dưới `project.toml`.

**acquire.** Chỉ cho S1 (hoặc chồng ảnh dữ liệu mở). Bật khi vệt là Sentinel-1, `[acquire] archive` để trống và có
`date_range`. Pha này tìm trên ASF các burst phủ AOI theo `relative_orbit`, lọc bớt theo `max_per_month` rồi tải các
burst còn thiếu. Khi mất mạng, pha dùng lại danh mục của lần chạy trước.

**build_stack** (engine `native`; `[stack] engine = "snap"` bị từ chối).

- Ngày tham chiếu: `[network] reference = "auto"` lấy ngày giữa (trung vị) ở lần dựng đầu và giữ nguyên chừng nào
  ngày đó còn là một lần chụp (Umbra: ngày có góc tới giữ được nhiều cảnh nhất trong phạm vi 3°). Mã chồng ảnh
  `<track_id>-ref<YYYYMMDD>`, lưu ở `stacks/<stack_id>/stack.zarr`.
- Sentinel-1 (`s1_stack.py`): các burst của lần chụp tham chiếu giao với AOI + 0,01°, khớp ảnh hình học bằng POEORB
  và DEM, đa dạng phổ tăng cường (ESD, luôn bật; khoá `[stack] esd` của schema không được đọc), khử bước nhảy pha ở
  đường nối giữa các dải con, tuỳ chọn khử tầng điện ly bằng tách phổ (`[stack] ionosphere = "split_spectrum"`,
  `ionosphere_model = "local"`, `ionosphere_smooth_m = 10000`).
- Stripmap / spotlight (`stripmap.py`: COSMO-SkyMed, Capella, ICEYE): khớp ảnh hình học từ quỹ đạo + DEM, sau đó đo
  độ lệch còn lại bằng tương quan pha của biên độ trên các ô 256 điểm ảnh (trung vị, loại lặp theo 3-MAD), một hằng
  số cho mỗi ngày (`coreg_model = "constant"`) hoặc một mặt phẳng theo độ cao, dòng và cột (`"terrain"`). Ngày bị
  loại khi khác hướng bay hoặc phía nhìn, hướng bay lệch > 2°, khoảng cách gần lệch > 3 % (chùm khác), hoặc (ICEYE)
  PRF lệch > 0,5 %.
- SICD (`sicd_stack.py`, Umbra): độ lệch nguyên thô (tương quan pha của log-biên độ trên 9 cửa sổ 2048 điểm ảnh,
  ±1024 điểm ảnh) rồi mới đến độ lệch còn lại; ngày bị loại khi khác phía nhìn / hướng bay, góc tới lệch > 3° so
  với tham chiếu, hoặc `DeltaKCOAPoly` khác 0.
- Kho chồng ảnh chứa `slc` đã khử pha hình học, `bperp`, `kh` (độ nhạy độ cao, rad/m), hình học
  (`geometry_incidence`, `geometry_slant_range`, ...). Với mọi vệ tinh trừ S1, cuối pha có chạy kiểm tra chồng ảnh
  ([stack-qc.md](stack-qc.md)).

**phase_linking** (`[phase_linking] enabled = true`; riêng tên phương pháp `psds` không bật được pha này).

- Điểm ảnh đồng nhất thống kê (SHP) trong cửa sổ `(2·half_window+1)²` điểm ảnh, `half_window = [7, 7]`: kiểm định
  Anderson-Darling hai mẫu trên chuỗi biên độ (`shp_test = "ad"`, `shp_alpha = 0.05`; có thêm `"ks"`).
- Điểm ảnh có ≥ `min_shp = 25` SHP và tỉ số độ lệch chuẩn/trung bình biên độ > `ps_da_max = 0.25` được liên kết;
  các điểm còn lại (PS) giữ nguyên SLC. Ma trận độ nhất quán tính trên các SHP, chuẩn hoá theo đường chéo.
- `estimator = "adaptive"`: EMI nơi trung bình |C| ngoài đường chéo > `adaptive_coherence_threshold = 0.6`, PTA (tam
  giác hoá pha) ở nơi khác; chọn được `evd`, `emi`, `pta`/`mle`; `psds`, `comsar`, `shp_test = "bws"` và `nlinsar`
  chưa được chuyển sang (pha bị chặn).
- Độ nhất quán theo thời gian γ = Re Σ_{i<j} e^{j(arg C_ij − θ_i + θ_j)} / (n(n−1)/2), lưu ở `pl_temporal_coherence`;
  `slc_linked[k] = |slc[k]| · e^{j(arg slc[ref] + θ_k)}`.
- Tuỳ chọn lọc Gauss sau liên kết cho từng giao thoa đồ, `gaussian_sigma` điểm ảnh (0 = tắt; preset CSK và ICEYE:
  1,5), chỉ trên các điểm ảnh đã liên kết (`gaussian_scope = "linked"`).
- Tuỳ chọn `store_pairs = [["YYYY-MM-DD", "YYYY-MM-DD"], ...]`: |C_ij| của các cặp ngày đó tính trên họ SHP, lưu ở
  `pl_pair_coherence` (`pl_pair`, y, x) kèm thuộc tính `pairs`, NaN ở điểm ảnh không được liên kết. Giá trị được
  tính ngay trong cùng một lượt, nên phép thử thay đổi trên điểm tán xạ phân bố không phải chạy SHP lần thứ hai
  (bước `verify` của nghiên cứu trượt lở đọc biến này; nếu không có, `runner.pair_coherence` sẽ tính lại SHP).

**Engine ps** (`method = "psi"` hoặc `"psds"`; kiểu StaMPS, `processing/ps/`, tham số `[ps]` giữ tên StaMPS, mặc định
trong `processing/ps/params.py`). Tám bước, mỗi bước có điểm lưu (checkpoint):

1. Ứng viên: biên độ hiệu chuẩn theo trung bình cảnh của từng ngày, D_A = sqrt(k·Σa²/(Σa)² − 1) ≤
   `[selection] da_threshold` (0.42), biên độ trung bình trên ngưỡng Otsu (loại mặt nước). Khi có liên kết pha và
   đặt `[selection] ds_coherence_min` (preset CSK / ICEYE: 0.7): thêm, trong mỗi khối `ds_cell × ds_cell` (3), điểm
   ảnh có γ liên kết pha cao nhất.
2. Ước lượng γ (lọc CLAP `clap_win = 16`, lưới `filter_grid_size = 10` m, sai số địa hình tới `max_topo_err = 20` m;
   `"auto"` = trung vị độ cao ứng với một vân λ·R·sinθ / (2|B⊥|) chia 4).
3. Chọn điểm (`select_method = "PERCENT"`, `percent_rand = 80`, hoặc `"DENSITY"` với `density_rand`).
4. Loại bớt (`weed_standard_dev = 1.0`, `weed_max_noise = inf`, `weed_adjacent_keep_per_group = 1`).
5. Hiệu chỉnh pha (sai số góc nhìn, số hạng ảnh chủ).
6. Giải chập pha lượt 1 trên lưới `unwrap_grid_size = 10` m (lọc trước Gauss `unwrap_grid_filter = "gaussian"`,
   `unwrap_gold_n_win = 16`), mô hình không gian – thời gian với `unwrap_time_win = 730` ngày (`"auto"`: một phần tư
   khoảng thời gian, ít nhất 4 bước lấy mẫu, trong 60–730 ngày), IRLS tinh chỉnh (`unwrap_irls_iter = 50`,
   `unwrap_irls_target_rms = 0.01`, `unwrap_irls_epsilon = 0.001`).
   Từ 06/11/2026, mỗi cạnh của lưới được giải chập theo thời gian trước bằng tốc độ tuyến tính của nó
   (`unwrap_edge_velocity = "y"`, periodogram tới `unwrap_max_edge_velocity = 100` mm/năm), và IRLS lấy số chu kỳ
   của từng bước lưới từ mô hình đó (`unwrap_model_cycles = "y"`, như offset trong cost SNAPHU của StaMPS). Trước
   đó mô hình được khớp trên pha chập và IRLS đi theo gradient chập: một cụm điểm có hiệu pha với lân cận vượt π
   (20 mm/năm: sau khoảng 250 ngày với S1) bị lệch nguyên một chu kỳ ở các ngày xa ảnh chủ. `legacy_quirks = "y"`
   tắt cả hai.
   Từ 07/11/2026 (Bình Chánh, TP.HCM so với SARPROZ): bộ lọc Gauss của lưới có σ tính theo mét
   (`unwrap_grid_filter_sigma = "auto"` = (`unwrap_gold_n_win` // 8) × 10 m, tức bộ lọc cũ ở lưới 10 m; σ cũ tính
   theo ô thành 100 m ở lưới 50 m và làm bẹt vùng lún); và khi có ≥ 40 giao thoa đồ (`unwrap_ps_rate = "auto"`),
   tốc độ tuyến tính của từng PS lấy từ mạng PS (cạnh Delaunay ≤ 500 m, periodogram, tích phân L1) được trừ trước khi
   lên lưới rồi cộng lại, nên một con đường hay bờ kênh lún nhanh hơn ô của nó không bị mất chu kỳ. Với vùng đồng
   bằng phẳng nên cân nhắc `subtr_tropo = "n"` ([aps-selection.md](../research/aps-selection.md)).
7. Giải chập pha lượt 2 (`subtr_tropo = "y"`) sau khi trừ sai số góc nhìn đã làm trơn ở lượt 1 (`scla_deramp`) và
   nhiễu khí quyển (APS): APS tuyến tính pha – độ cao (khớp trong đa giác `aps_non_defo` nếu có), hoặc mô hình thời
   tiết, cho từng giao thoa đồ mà nó giải thích phần dư lượt 1 tốt hơn (`[atmosphere] select = "auto"`).
   `scla_deramp`: `"n"` giữ nguyên ramp, `"y"` bỏ toàn bộ mặt phẳng / bậc hai của mọi giao thoa đồ, `"auto"` (đang
   thử nghiệm, [tự chọn deramp](../research/ramp-selection.md)) bỏ phần thay đổi giữa các lần chụp, còn phần tăng
   đều chỉ bỏ khi có nền ổn định neo được một mặt phẳng duy nhất trên cả khung (`deramp_non_defo` = đa giác vùng ổn
   định do người dùng chỉ định); quyết định được ghi trong manifest (`ramp`) và `figures/ramp.png`.
8. Vận tốc và nhiễu tương quan không gian (SCN) (`scn_time_win = 365` ngày, `scn_wavelength = 100` m,
   `scn_time_fit = "linear"`); chuyển dịch d = −φ·λ/4π, rồi quy về `ref_lon/ref_lat` hoặc trung bình cảnh.

Thử nghiệm: `unwrap_align_constant = "y"` căn hằng số của IRLS trước khi bám về pha chập (sửa lỗi trượt một chu kỳ
theo vùng ở các giao thoa đồ có pha trung bình gần ±π, ICEYE Tenerife). Mặc định `"n"`: tuỳ chọn này làm đổi kết
quả CSK Hà Nội đã kiểm định (89,6 % số điểm trùng khớp, `params.py`) và cần đánh giá so với SNAP+StaMPS trước khi
dùng rộng. Lưu ý preset ICEYE đang đặt `"y"`.

**ps_lite** (`method = "ps_lite"`, Capella và Umbra, ADR-020; `[ps_lite]`). D_A ≤ `da_max = 0.4` và đa dạng phổ theo
phương nhìn ngang ≤ `sd_max = 0.45`, trên ngưỡng biên độ (`amp_floor_pct = 10`), mỗi ô `ps_cell = [4, 6]` điểm ảnh
giữ một PS tốt nhất; ngày tham chiếu riêng (`ref_date = "auto"`: ngày có đường cơ sở dài nhất là nhỏ nhất); với mỗi
giao thoa đồ, IRLS tinh chỉnh hai lượt trên lưới `uw_cell = [16, 24]` điểm ảnh có lọc Goldstein (`gs_alpha = 0.8`,
`gs_win = 32`) và chu kỳ đồ (periodogram) sai số độ cao xen giữa hai lượt; vùng tham chiếu bán kính `ref_radius_m =
200` m; bình phương tối thiểu có trọng số cho từng PS: φ_k = s·4π/λ·v·t_k + s·kh_k·dh + c + APS_k, APS = phần dư lọc
thông thấp bằng Gauss `aps_sigma_m = 1000` m; giao thoa đồ có độ lệch chuẩn pha > `ifg_std_max = 1.5` rad bị loại;
PS được giữ khi γ ≥ `tcoh_min = 0.7` và độ lệch chuẩn pha ≤ `phase_std_max = 0.8` rad. Engine này không đọc `[ps]`
(không có `unwrap_grid_size`, không có `unwrap_align_constant`); dưới 100 PS thì dừng.

**build_product.** Mỗi lần chạy tạo một thư mục bất biến mới `products/<project>_<track>_<first>_<last>_v<N>/`, cùng
schema cho mọi vệ tinh và engine (`products/schema.py`): vận tốc LOS dương khi hướng về vệ tinh, chuỗi thời gian đặt
mốc 0 tại ngày đầu của từng điểm, biên độ mùa, sigma phần dư, véc-tơ đơn vị LOS.

**export.** `[export] formats` (mặc định `["gpkg", "pmtiles"]`; thêm được `csv`, `kmz`, `3dtiles`): GeoPackage có một
cột `DYYYYMMDD` cho mỗi ngày và nhúng sẵn kiểu hiển thị QGIS, luôn kèm `<product>.qml`. Kiểu hiển thị: Pretty Breaks,
10 lớp trên toàn bộ min–max (không cắt), `jet_r`, hình tròn không viền, kích thước tính bằng mét theo khoảng cách
giữa các điểm (`export/styles.py`).

## 4. Các bước triển khai

1. **Không gian làm việc.** Đặt `GEOEYES_WORKSPACE` (chép `.env.example` thành `.env`); S1: `EARTHDATA_TOKEN`. Làm một lần.
2. **Khai báo dự án.** Viết `projects/<name>/project.toml` (ví dụ S1 tối giản ở ../guide/projects-and-data.md §2),
   hoặc trên web app Projects → *New project* (tên, phương pháp, vệ tinh, vẽ AOI trên bản đồ, tìm vệt S1). Dữ liệu
   thương mại: đặt các thư mục ngày vào `archive/<sensor>/<track_id>/`.
3. **Kiểm tra.** `geoeyes check <name>` (vài giây): môi trường, cấu hình, các pha bị chặn, `~/.cdsapirc` hoặc thư
   mục GACOS khi chọn mô hình thời tiết.
4. **Lập kế hoạch.** `geoeyes plan <name>` (vài giây; S1 có truy vấn ASF): mỗi vệt và pha một dòng, `run` /
   `up-to-date` / `disabled` / `blocked` kèm lý do ("2 new scene(s) …; incremental: 26 coregistered date(s) kept").
5. **Chạy.** `geoeyes run <name>` (hoặc nút *Run* ở tab Pipeline). Cỡ thời gian (theo ../guide/incremental.md, Hà Nội
   S1 quỹ đạo lên 128, 26 ngày, khoảng 730.000 điểm, có khử tầng điện ly): `build_stack` 71 phút, `ps` 12 phút,
   `build_product` + `export` + `report` 2 phút; Capella Mexico City, 18 ngày: chồng ảnh khoảng 5 phút
   (docs/en/refactor/TODO.md). Ghi ra `stacks/`, `ps_runs/<track_id>/`, `products/<id>/`, `exports/<id>/`,
   `runs/<run_id>/` (manifest, `log.jsonl`, mỗi pha một log), `.state/state.json`.
6. **Theo dõi.** `geoeyes status <name>`: trạng thái và thời gian từng pha, 5 lần chạy gần nhất, các khoá.
7. **Kiểm tra chồng ảnh** trước khi tin các điểm: `geoeyes stack-qc <name>` hoặc tab Stack ([stack-qc.md](stack-qc.md)).
8. **Chạy lại một phần.** `--force PHASE`, `--from` / `--to` / `--only PHASE`, `--track ID`, `--skip PHASE` hoặc
   `--skip TRACK/PHASE` (giữ nguyên, không kiểm tra). Các bước của engine: `--ps-from N` tính lại từ bước N trở đi,
   `--ps-to N` dừng sau bước N (pha ở trạng thái *paused*); ví dụ `geoeyes run hcm_hist_des --skip acquire
   --ps-from 6 --ps-to 6` chỉ làm lại giải chập lượt 1. Đổi một tham số giải chập thì bước 1–5 tự được dùng lại.
9. **Báo cáo.** Pha `report` tự ghi; `geoeyes report <name> [--product ID]` dựng lại sau khi chạy thêm phân tích
   (`report.pdf`, `report.json`, `indicators.json` trong thư mục sản phẩm).

## 5. Kết quả và cách đọc

| Tệp | Nội dung |
|---|---|
| `products/<id>/points.parquet` | GeoParquet, mỗi điểm một dòng: `point_uid` (`<track>:<geohash>:<height>`), `lon`, `lat`, `height_m`, `type` (PS / DS), `vel_los_mm_yr` (+ hướng về vệ tinh), `vel_std_mm_yr`, `acc_los_mm_yr2`, `temporal_coherence`, `amp_dispersion`, `dem_err_m`, `seasonal_amp_mm`, `seasonal_phase_day`, `fit_rmse_mm`, `residual_sigma_mm`, `los_e/n/u`, `incidence_deg`, `heading_deg` |
| `products/<id>/timeseries.parquet` | dạng dài `point_uid`, `date`, `disp_mm` (và chuỗi đã khử SCN), mốc 0 tại ngày đầu của từng điểm |
| `products/<id>/rasters/velocity.tif`, `ps_density.tif` | COG: vận tốc trung bình và số điểm mỗi ô |
| `products/<id>/item.json`, `manifest.json` | STAC item (bbox, ngày, chỉ số `vel_min/max/p02/median/p98_mm_yr`, `n_points`, `n_ds`), nguồn gốc xử lý |
| `products/<id>/report.pdf`, `report.json`, `indicators.json` | Phần A đánh giá (tốc độ thẳng đứng v_LOS / l_u), Phần B phụ lục kỹ thuật; schema chỉ số `geoeyes.indicators/1` |
| `ps_runs/<track_id>/` | trạng thái engine `state.h5`, `params.json` (giá trị hiệu lực, các `"auto"` đã quy ra số), `figures/*.png`, `checkpoints/step<N>.pkl` (ps); `pairs.parquet` (ps_lite) |
| `exports/<id>/` | `<id>.gpkg` (lớp `points`, có kiểu hiển thị), `<id>.qml`, tuỳ chọn `.csv`, `.pmtiles`, `.kmz`, `3dtiles/` |

`vel_los_mm_yr` âm là chuyển dịch ra xa vệ tinh (sụt lún khi chuyển động chủ yếu theo phương đứng). Hãy hiển thị đúng
min–max thật của vận tốc: kiểu hiển thị QGIS và các hình của engine (`velocity.png`, `velocity_scn.png`) cố ý dùng
toàn dải; không cắt thang màu theo P2–P98.

## 6. Kiểm tra chất lượng

- Chồng ảnh: độ lệch < 0,1 điểm ảnh, độ nhất quán và tương quan biên độ đồng đều giữa các ngày ([stack-qc.md](stack-qc.md)).
- `ps_runs/<track_id>/figures/`: bản đồ vận tốc có đánh dấu điểm tham chiếu, bản đồ đã khử SCN cùng thang màu, APS và
  nhiễu pha theo từng giao thoa đồ; giao thoa đồ có nhiễu vượt xa các cái khác thường chỉ ra một ngày xấu.
- `ps_lite`: `pairs.parquet` (`unwrap_rms`, `islands`, `phase_std_rad`, `used`); các giao thoa đồ bị loại có ghi log.
- Chỉ số sản phẩm trong `item.json`: số điểm, tỉ lệ DS, trung vị độ nhất quán, `vel_std_median_mm_yr`; nền ổn định
  (vùng tham chiếu, công trình biết là ổn định) phải gần 0 mm/năm.
- Lỗi giải chập: cả mảng lệch một chu kỳ (λ/2 mỗi ngày: 28 mm băng C, 15,5 mm băng X) trong chuỗi thời gian, hoặc
  các khối ngược dấu nối với nhau bằng cung dài (trường hợp TP.HCM ở dưới).
- Phần A của báo cáo, mục *how sure are we*; kiểm tra độc lập bằng GNSS (skill hiệu chỉnh GNSS) hoặc vệt thứ hai.

## 7. Hạn chế và lỗi thường gặp

- TerraSAR-X, ALOS: mới có preset, `build_stack` bị chặn. `method = "sbas"` / `"comsar"`: chạy cùng engine `ps` như `psi`.
- Các khoá schema chấp nhận nhưng quy trình `native` không đọc: `[network] max_perp_m` (form Settings trên web ghi là
  "Largest perpendicular baseline kept" nhưng không ngày nào bị loại theo nó), `extent_min_ratio`, `[network.sbas]`,
  `[stack] geometry`, `esd`, `multilook`, `merge_subswaths*`, `byteswap`, `reestimate`, `renew`, `[selection]
  robust_da`, `forced_points`, `mask`, `water_mask`, `[phase_linking] ministack_size`, `[compute] memory_gb`,
  `[pipeline] disabled`.
- `[compute] backend` (`auto` | `numpy` | `cupy`; biến môi trường `GEOEYES_COMPUTE_BACKEND` được ưu tiên): hiện mới
  có `topofit` (bước 2–3) và `clap_at_points` (bước 3) của ps chạy được trên GPU (ADR-014); mọi phần khác chạy CPU.
- Đổi ngày tham chiếu, AOI, DEM hay tập dải con thì mọi ngày được khớp lại (sang thư mục chồng ảnh khác).
- `max_per_month` trên kho ảnh dùng chung: ưu tiên các ngày do pha `acquire` của chính dự án chọn.
- Băng X, độ cao ứng với một vân nhỏ: dùng `max_topo_err = "auto"`; đường cơ sở hàng km của Umbra cho độ cao ứng với
  một vân dưới một mét: dùng `lidar-3dep` nếu có, AOI nhỏ trên công trình.
- Lưới giải chập quá mịn trên vùng thưa điểm sẽ nối các khối bằng cung dài nhiễu (TP.HCM: lệch nguyên chu kỳ ở 10 m).
- `geoeyes run` giữ khoá dự án theo từng vệt; lần chạy thứ hai trên cùng vệt bị từ chối.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

Cần đổi: `[aoi] bbox`, `[[tracks]]`, `date_range`, vùng tham chiếu nếu biết nền ổn định, DEM nơi SRTM kém (địa hình
dốc, vĩ độ > 60°, lidar ở Mỹ). Giữ preset của vệ tinh trừ khi có thử nghiệm cho thấy khác.

Thói quen và quyết định đã biết:

- `unwrap_grid_size = 10` m (nay là mặc định; 200 m của StaMPS làm chồng phổ sụt lún nhanh: S1 Mexico so với Capella
  r 0,64 → 0,86, `params.py`). Ngoại lệ TP.HCM (`hcm_hist_des`): `unwrap_grid_size = 50` cùng `filter_grid_size =
  50`, `percent_rand = 50`; ở 10 m các khối phía tây và phía đông bị nối bằng cung dài nhiễu, lệch nguyên chu kỳ;
  `unwrap_time_win = "auto"` không đổi gì ở đó và tuỳ chọn căn hằng số chỉ dời chỗ trượt (chú thích trong dự án,
  2026-10-31 / 11-01).
- Liên kết pha: `shp_test = "ad"`, `estimator = "adaptive"` (mặc định).
- Chuỗi COSMO-SkyMed: liên kết pha + lọc Gauss sau liên kết (`gaussian_sigma = 1.5`), ngoài ra không gì khác: không
  wavelet, không FAMM, không lọc lưới Goldstein. Các bổ sung của CSK cũ (`dem_error_ambiguity = "y"`,
  `select_nr_scaling = "population"`, `unwrap_grid_filter = "goldstein"`) làm chồng ảnh Hà Nội kém đi (RMSE khớp
  4,12 → 4,81 mm; độ phân tán vận tốc 1,51 → 1,67 mm/năm; chú thích preset, thử loại bỏ 2026-10-23) nên vẫn tắt.
- `unwrap_align_constant`: thử nghiệm, chưa làm mặc định cho `ps` khi chưa so với SNAP+StaMPS, kể cả trong
  preset ICEYE (muốn thử thì đặt `"y"` trong dự án).
- Lượt chụp Sentinel-1 lúc chạng vạng gần dị thường xích đạo (Hà Nội quỹ đạo lên 18:06 giờ địa phương): `[stack]
  ionosphere = "split_spectrum"`.
- Hiển thị: min–max thật của VLOS; QGIS Pretty Breaks 10 lớp, `jet_r`, không viền.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/controller/pipeline.py`, `controller/phases/{acquire,build_stack,phase_linking,ps}.py`,
  `processing/stack/native/{s1_stack,stripmap,sicd_stack}.py`, `processing/phase_linking/{runner,estimators,shp}.py`,
  `processing/ps/{runner,params,candidates}.py`, `processing/ps_lite/{runner,ps,unwrap,invert}.py`,
  `products/{builder,schema}.py`, `export/{vector,styles}.py`, `config/schema.py`, `config/presets/*.toml`,
  `cli/main.py`.
- Hướng dẫn: ../guide/projects-and-data.md, ../guide/incremental.md, ../guide/atmosphere.md, ../guide/ionosphere.md,
  ../guide/opendata.md. Kiến trúc: ../architecture/decisions.md (ADR-005, -020, -023, -028, -029).
- Skill: [stack-qc.md](stack-qc.md), [opendata-stacks.md](opendata-stacks.md),
  [incremental-monitoring.md](incremental-monitoring.md), [atmosphere.md](atmosphere.md),
  [gnss-calibration.md](gnss-calibration.md).
- Bài báo: Hooper et al. 2004, 2007 (StaMPS); Ferretti et al. 2011 (SqueeSAR, SHP và liên kết pha); Ansari et al.
  2018 (EMI); Scholz & Stephens 1987 (Anderson-Darling k mẫu).
