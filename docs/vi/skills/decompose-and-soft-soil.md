# Skill: chuyển dịch thẳng đứng và đông–tây từ hai hướng chụp; bề dày đất yếu so với sụt lún

> Bản dịch của [docs/en/skills/decompose-and-soft-soil.md](../../en/skills/decompose-and-soft-soil.md). Dịch ngày 2026-11-01.

> Tách chuyển dịch thẳng đứng và đông–tây khi không gian làm việc có hai sản phẩm nhìn cùng một vùng từ hai phía đối
> diện trong cùng thời kỳ; đồng thời đọc bề dày lớp đất yếu (dễ nén) dưới mỗi ô của phân vùng nguy cơ để so với sụt
> lún và kiểm tra hằng số thời gian cố kết.
> Trạng thái: đang vận hành (v1, 2026-10-27); lưới bề dày mở toàn cầu chỉ là giá trị tạm. Đối chiếu với mã lần gần
> nhất 2026-11-01. Lệnh `geoeyes decompose`, `geoeyes geology`; web app **Phân tích chuyên sâu → Phân tích chuyên
> đề**, các lớp "Chuyển dịch thẳng đứng", "Chuyển dịch đông–tây", "Bề dày đất yếu".

## 1. Khi nào dùng

- **Tách thành phần.** Mọi phân tích trên một sản phẩm (phân vùng, hạ tầng tuyến, công trình, cố kết) đều coi
  v_LOS / l_u là chuyển dịch thẳng đứng. Điều này sai nơi mặt đất dịch ngang: quanh phễu lún và trên sườn dốc. Dùng
  `decompose` để đo chuyển dịch thẳng đứng và biết phép chiếu thẳng đứng từ một hướng chụp sai bao nhiêu.
- **Địa chất.** Mặt đất có lún ở nơi lớp đất yếu dày không? Dùng `geology` để so bề dày với tốc độ lún, và kiểm tra
  xem một ô "đang cố kết" có phù hợp với lớp đất bên dưới hay không.
- **Không dùng cho.** Chuyển dịch bắc–nam (giả định bằng 0), vận tốc tuyệt đối (kết quả là tương đối so với vùng
  chung), các cặp sản phẩm không trùng thời kỳ, hay coi lưới mở toàn cầu là bản đồ lớp đất yếu.

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Sản phẩm cần tách | có | [insar-processing.md](insar-processing.md) | `projects/<name>/products/<track>_v<N>/` gồm `item.json` (bbox, `geoeyes:first_date`, `geoeyes:last_date`, vệt quỹ đạo, dự án) và `points.parquet` (`lon`, `lat`, `vel_los_mm_yr`, `vel_std_mm_yr`, `los_e`, `los_n`, `los_u`) | |
| Sản phẩm đối tác | có | Sản phẩm của vệt quỹ đạo (hoặc vệ tinh) khác trên cùng vùng: thêm vệt vào dự án ([insar-processing.md](insar-processing.md)) hoặc dùng dự án khác trong cùng không gian làm việc | Bất kỳ `projects/*/products/*_v<N>/` nào trong không gian làm việc; chỉ xét phiên bản mới nhất của mỗi (dự án, vệt) | Phải giao nhau về phạm vi, trùng ≥ 50 % thời kỳ ngắn hơn, và khác nhau \|Δl_e\| ≥ 0.5 |
| Phân vùng nguy cơ của sản phẩm | có, cho `geology` | [hazard-zoning.md](hazard-zoning.md) | `projects/<name>/analyses/hazard/<id>/` | Bề dày được đọc tại tâm các ô |
| Phân tích cố kết | tuỳ chọn, cho `geology` | [lines-and-consolidation.md](lines-and-consolidation.md): `geoeyes consolidation` | `projects/<name>/analyses/consolidation/<id>/consolidation.parquet` | Cần cho kiểm tra c_v; phải từ cùng một lần phân vùng (cùng số ô) |
| Bản đồ bề dày đất yếu | nên có | Bản đồ lớp đất yếu của cơ quan địa chất (Hà Nội: sét và than bùn Holocen của hệ tầng Hải Hưng và Thái Bình, ví dụ Phi & Strokova 2017), số hoá | GeoTIFF đơn vị mét, hệ toạ độ bất kỳ; `[postprocess.geology] raster = "geom/soft_soil.tif"` (đường dẫn tương đối theo thư mục dự án) | Nguồn được dùng đầu tiên khi có |
| Lỗ khoan | thay thế | Nhật ký lỗ khoan: độ sâu đáy lớp đất yếu | CSV có `lon`, `lat`, `thickness_m` (có thể thêm `name`); `[postprocess.geology] boreholes = "geom/boreholes.csv"` | ≥ 3 lỗ khoan. Chỉ dùng khi `raster` để trống |
| Lưới mở | dự phòng (mặc định) | Pelletier et al. 2016, bề dày trầm tích trên đá gốc ở vùng thấp, 1 km, chặn trên ở 50 m (NASA ORNL DAAC) | Tải một lần vào `<workspace>/cache/geology/pelletier2016_lowland_sediment_thickness.tif`; cần `EARTHDATA_TOKEN` | `open_fallback = true`. Đây là độ sâu tới đá gốc, không phải lớp đất yếu |
| Tham số | tuỳ chọn | – | `[postprocess.decompose]`, `[postprocess.geology]` | Khoá lạ làm lệnh dừng |

Danh sách kiểm tra trước khi chạy:

- [ ] Cả hai hướng chụp đã xử lý trong cùng không gian làm việc, thời kỳ trùng nhau (xem `first`/`last`).
- [ ] Đã biết chất lượng riêng của từng sản phẩm; mặt nghiêng (ramp) trong một sản phẩm sẽ thành chuyển dịch đông–tây
  (Hanoi asc 128).
- [ ] Đã quyết định có đặt `deramp = "plane"` không (mặt phẳng trừ đi cả độ nghiêng thật của vùng).
- [ ] Với geology: có raster hoặc lỗ khoan trong thư mục dự án, hoặc có `EARTHDATA_TOKEN` cho lưới mở.
- [ ] Với kiểm tra c_v: đã chạy `geoeyes consolidation` sau lần phân vùng hiện tại.

## 3. Phương pháp

### 3.1 Tách thành phần (`src/geoeyes/ml/decompose.py`, `DecomposeParams`)

Một sản phẩm đo v_LOS = e·l_e + n·l_n + u·l_u (vectơ đơn vị từ mặt đất tới vệ tinh); n giả định bằng 0
(|l_n| ≈ 0,1–0,15 với Sentinel-1).

1. **Đối tác.** Phiên bản mới nhất của mọi (dự án, vệt) trong không gian làm việc, trừ chính vệt của sản phẩm, có
   khung bao giao nhau, thời kỳ trùng ≥ `min_overlap_share` (0,5) thời kỳ ngắn hơn và |Δl_e| ≥ `min_east_contrast`
   (0,5). Sắp theo số ngày trùng.
2. **Nền chung.**
   - `support = "cells"` (mặc định): lưới ô `cell_m` (100 m) tính bằng độ trên khung bao chung; mỗi sản phẩm và mỗi
     ô lấy trung vị v_LOS và vectơ LOS, nếu có ≥ `min_points` (3). σ = max(1,4826·MAD/√n, trung vị
     `vel_std_mm_yr`/√n, `sigma_floor_mm_yr` 0,5).
   - `support = "points"`: tại mỗi điểm của sản phẩm trong khung bao chung, mỗi sản phẩm lấy trung vị của tối đa
     `max_neighbours` (16) điểm trong bán kính `radius_m` (20 m); σ tính như trên.
   - Cần ít nhất 10 vị trí mà mọi sản phẩm đều thấy, nếu không lệnh dừng.
3. **Mặt nghiêng.** Khớp mặt phẳng a + b·x + c·y cho vận tốc của từng sản phẩm (bỏ ngoại lai > 3 MAD, 3 lượt). Với
   `deramp = "plane"` thì trừ mặt phẳng đó. Với `deramp = "none"`, có cảnh báo khi biên độ mặt phẳng lớn nhất vượt
   `ramp_warning_mm_yr` (5) và gấp đôi biên độ nhỏ nhất.
4. **Tham chiếu chung.** Mỗi sản phẩm trừ đi trung vị vận tốc của chính nó trên các vị trí chung.
5. **Lời giải.** Bình phương tối thiểu có trọng số tại từng vị trí cho [l_e, l_u]·[e, u] = v_LOS (trọng số 1/σ²),
   σ_e và σ_u lấy từ ma trận chuẩn.
6. **Cờ chuyển dịch ngang:** |e| ≥ `horizontal_mm_yr` (5) và |e| ≥ 2σ_e. **Sai số của một hướng chụp:**
   v_LOS / l_u − u cho từng sản phẩm (trung vị và P90 của |·|).

### 3.2 Bề dày đất yếu (`src/geoeyes/ancillary/geology.py`, `GeologyParams`; `src/geoeyes/ml/geology.py`)

1. **Bề dày** tại mỗi ô phân vùng, từ nguồn có sẵn đầu tiên: `raster` (lấy mẫu; giá trị âm và nodata → NaN), nếu
   không có thì `boreholes` (nghịch đảo khoảng cách, luỹ thừa `idw_power` 2, `idw_neighbours` 8, NaN khi cách lỗ
   khoan gần nhất quá `max_borehole_km` 3 km), nếu vẫn không có thì lưới mở khi `open_fallback`.
2. **Tốc độ theo lớp bề dày:** `bins` (5) lớp theo phân vị; mỗi lớp cho tốc độ trung vị của các ô đang lún (chế độ
   sụt lún, tốc độ < 0) và tỉ lệ ô có tốc độ ≤ −`moving_mm_yr` (5). Cần ≥ 5 × `bins` ô.
3. **Spearman ρ** giữa bề dày và độ lún (−tốc độ) của các ô đang lún (≥ 20 ô, bề dày không hằng).
4. **Kiểm tra cố kết** cho các ô đang cố kết: số hạng đầu trong lời giải Terzaghi cho τ = 4·H_dr² / (π²·c_v), suy ra
   c_v = 4·H_dr² / (π²·τ), H_dr = H/2 với `drainage = "double"` (H với `"single"`). So với 0,1–10 m²/năm của sét yếu
   (Holtz & Kovacs 1981).

Cơ sở đã công bố: Wright et al. 2004 và Fuhrmann & Garthwaite 2019 (tách thành phần từ nhiều hướng chụp), Pelletier
et al. 2016, Terzaghi 1925, Holtz & Kovacs 1981.

## 4. Các bước triển khai

1. **Hướng chụp thứ hai.** Xử lý vệt quỹ đạo còn lại trong cùng thời kỳ (Hà Nội: thêm asc 128 vào `hanoi_s1` cạnh
   desc 091).
2. **Quyết định cách xử lý mặt nghiêng**, ví dụ trong `project.toml` của dự án chứa sản phẩm:

   ```toml
   [postprocess.decompose]
   deramp = "plane"        # as in hanoi_s1
   # support = "points"    # 20 m neighbourhoods, no GeoTIFF
   ```
3. **Tách thành phần.** `geoeyes decompose <project> --product <id>` (ví dụ `--set deramp=plane --set cell_m=50`).
   Web: Phân tích chuyên đề → lớp "Chuyển dịch thẳng đứng" hoặc "Chuyển dịch đông–tây" → **Tách thẳng đứng và
   đông–tây**. Thời gian chạy chưa đo (đọc điểm của mọi sản phẩm). Ghi ra `projects/<name>/analyses/decompose/<id>/`:
   `decompose.parquet`, `decompose.json`, `up.tif` và `east.tif` (chỉ với nền ô), `manifest.json`.
4. **Phân vùng** (cho geology): `geoeyes hazard <project> --product <id>`; tuỳ chọn `geoeyes consolidation`.
5. **Nguồn bề dày**, ví dụ:

   ```toml
   [postprocess.geology]
   raster = "geom/soft_soil.tif"          # or: boreholes = "geom/boreholes.csv"
   drainage = "double"
   ```
6. **Địa chất.** `geoeyes geology <project> --product <id>`. Web: lớp "Bề dày đất yếu" → **Đọc bề dày đất yếu**. Lần
   đầu dùng lưới mở sẽ tải lưới toàn cầu một lần. Ghi ra `projects/<name>/analyses/geology/<id>/`: `geology.parquet`,
   `geology.json`, `manifest.json`.
7. Bề dày cũng đi vào mô hình tính nhạy cảm dưới tên `soft_soil_m`
   ([susceptibility-and-forecast.md](susceptibility-and-forecast.md)).

## 5. Kết quả và cách đọc

**`decompose.parquet`**: `cell`, `lon`, `lat`, `up`, `east`, `sigma_up`, `sigma_east` (mm/năm; lên dương, đông
dương), với mỗi sản phẩm k: `v_los_k` (sau khi đặt tham chiếu và trừ mặt nghiêng), `n_k`, `vert_only_k` (giá trị
thẳng đứng mà riêng sản phẩm đó cho ra), và `horizontal`. **`decompose.json`**: các sản phẩm (id, vệt, vệ tinh, thời
kỳ, LOS, phần trùng), `grid`, `up_mm_yr` và `east_mm_yr` (min, p02, trung vị, p98, max), σ trung vị,
`horizontal_share`, `vertical_only_bias` theo sản phẩm, `ramps` (mm/năm trên km, biên độ, đã trừ hay chưa), cảnh báo.
`up.tif`, `east.tif`: EPSG:4326, mm/năm.

**`geology.parquet`**: `cell`, `lon`, `lat`, `thickness_m`, `nearest_borehole_km` (khi dùng lỗ khoan), `cv_m2_yr`
(ô đang cố kết). **`geology.json`**: `source`, `thickness_m` (min, trung vị, max), `spearman_rho`, `spearman_p`,
`by_class` (from_m, to_m, cells, median_rate_mm_yr, moving_share), `consolidation_cv` (trung vị, p10, p90, tỉ lệ nằm
trong khoảng), cảnh báo.

Cách đọc: ρ > 0 nghĩa là đất yếu càng dày lún càng nhanh. Mexico City S1 với lưới mở: ρ = 0,51, tốc độ trung vị −97 /
−116 / −204 mm/năm từ lớp mỏng tới lớp bị chặn trên; Hà Nội: 92 % số ô ở mức chặn, ρ = −0,11, không mang thông tin
(ghi chú nghiên cứu §4.3).

## 6. Kiểm tra chất lượng

- **Mặt nghiêng.** So `ramps[].span_mm_yr`: độ nghiêng chỉ một sản phẩm thấy là sai số (quỹ đạo, tầng điện ly, khí
  quyển). Hanoi asc 128 v1 có biên độ 26,9 mm/năm, trong khi desc 091 chỉ 3,9.
- **Tương quan đông và thẳng đứng.** Tương quan mạnh (Hà Nội khi chưa trừ mặt nghiêng: −0,80) cho thấy sai số của một
  hướng nhìn đã lan vào cả hai thành phần (`report/qc.py` có báo con số này).
- **Nhiễu thực nghiệm của e** đo trên các ô ổn định: ở Hà Nội trung vị |e| = 1,8 mm/năm (σ_e ≈ 2,7, gấp bốn lần giá
  trị hình thức 0,64). Ở đó chỉ nên đọc chuyển dịch đông–tây trên khoảng 5–8 mm/năm.
- **Chuyển dịch ngang có hướng về các phễu lún không?** Nếu không (Hà Nội: 48–53 % hướng về, tức là ngẫu nhiên), đó
  là sai khác còn lại giữa hai sản phẩm, không phải chuyển dịch mặt đất.
- **Cảnh báo của geology:** đang dùng lưới mở; > 50 % số ô ở mức chặn 50 m.
- **c_v:** giá trị gấp khoảng 100 lần khoảng của sét yếu (830–1 000 m²/năm ở mọi sản phẩm thử) bác bỏ việc coi bề
  dày đó là lớp đang cố kết, hoặc bác bỏ cách đọc cố kết.

## 7. Hạn chế và lỗi thường gặp

- Thời kỳ phải trùng nhau; nếu không, mã giả định tốc độ không đổi (có cảnh báo).
- Bỏ qua thành phần bắc–nam; với vệ tinh nhìn xiên (Capella, l_n = −0,46 trên Mexico City) thành phần này lan vào e và
  u.
- Kết quả là tương đối so với trung vị của vùng chung; phép gắn GNSS của phân vùng chưa được chuyển sang đây.
- σ hình thức không tính các mặt nghiêng và khí quyển khác nhau giữa các sản phẩm; chuỗi băng X ngắn bị ảnh hưởng
  nặng nhất (Mexico City S1 + Capella 50 ngày: không đáng tin, ghi chú nghiên cứu §4.1).
- `deramp = "plane"` trừ cả độ nghiêng khu vực có thật.
- Chỉ tìm đối tác trong phiên bản mới nhất của mỗi vệt; trên CLI không chỉ định được đối tác cụ thể cho `decompose`.
- Nội suy lỗ khoan không vẽ được cấu trúc địa chất giữa các lỗ khoan (lòng sông cổ cần bản đồ).
- Bỏ qua kiểm tra c_v khi `consolidation.parquet` không có đúng một dòng cho mỗi ô của phân vùng hiện tại.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- **Tách thành phần:** xử lý hướng chụp thứ hai trong cùng thời kỳ; đặt `deramp` sau khi xem các mặt nghiêng;
  `support = "points"` cho băng X dày điểm (Mexico City ở 15 m: 60 027 vị trí thay vì 1 731 ô); đặt
  `horizontal_mm_yr` theo nhiễu thực nghiệm của e.
- **Lần chụp lúc chạng vạng gần dị thường xích đạo** (Hà Nội quỹ đạo lên, 18:06 giờ địa phương): dự kiến có mặt
  nghiêng do tầng điện ly; dùng hiệu chỉnh tách phổ ([ionosphere.md](ionosphere.md)) và giữ `deramp = "plane"`.
- **Địa chất:** tìm bản đồ lớp đất yếu hoặc dữ liệu lỗ khoan (Hà Nội: mô hình 3D của BGS, 271 lỗ khoan; Phi &
  Strokova 2017, nghiên cứu G1); đặt `drainage` theo địa tầng; chỉnh `moving_mm_yr` và `bins`.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/ml/decompose.py`, `src/geoeyes/ml/geology.py`, `src/geoeyes/ancillary/geology.py`,
  `src/geoeyes/ml/layers.py` (`soft_soil_m`), `src/geoeyes/report/qc.py`; `webapp/src/pages/Hazard.tsx`,
  `LearnGeometry.tsx` (Nguyên lý, chương 5); test `tests/unit/ml/test_decompose_geology.py`.
- Nghiên cứu: [../research/two-geometries-and-soft-soil.md](../research/two-geometries-and-soft-soil.md);
  [../guide/ionosphere.md](../guide/ionosphere.md).
- Skill: [hazard-zoning.md](hazard-zoning.md), [lines-and-consolidation.md](lines-and-consolidation.md),
  [ionosphere.md](ionosphere.md), [gnss-calibration.md](gnss-calibration.md).
- Bài báo: Wright, Parsons & Lu 2004 (*GRL* 31:L01607); Fuhrmann & Garthwaite 2019 (*Remote Sensing* 11:241);
  Pelletier et al. 2016 (*JAMES* 8:41, dữ liệu doi:10.3334/ORNLDAAC/1304); Terzaghi 1925; Holtz & Kovacs 1981;
  Phi & Strokova 2017; Gomba et al. 2016; Liang & Fielding 2017.
