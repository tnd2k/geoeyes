# Skill: tính nhạy cảm chuyển dịch mặt đất và dự báo biến dạng

> Bản dịch của [docs/en/skills/susceptibility-and-forecast.md](../../en/skills/susceptibility-and-forecast.md). Dịch ngày 2026-11-01.

> Biết InSAR thấy mặt đất chuyển dịch ở đâu, thì còn những nơi nào khác có thể chuyển dịch, và mỗi ô sẽ dịch thêm
> bao nhiêu trong vài tháng tới? Trạng thái: nghiên cứu (cả hai chạy trọn quy trình; đến nay dự báo hiếm khi thắng
> được mô hình "không đổi"). Kiểm tra lần cuối 2026-11-01. CLI: `geoeyes susceptibility`, `geoeyes forecast`. Web
> app: Phân tích chuyên sâu → Nghiên cứu học máy (`#/ai/<project>/<product>/susceptibility` hoặc `/forecast`).

## 1. Khi nào dùng

- **Tính nhạy cảm (susceptibility)** trả lời: tổ hợp địa hình, lớp phủ, công trình, đất và bề dày đất yếu nào đi
  cùng các ô mà InSAR thấy đang lún (hoặc trượt xuống dốc), và những ô *không có* điểm InSAR (thảm thực vật, mép
  nước) nào giống chúng. Dùng để mở rộng bản đồ sụt lún sang vùng InSAR không đo được, và xếp hạng các lớp chuyên đề
  theo mức giải thích.
- **Dự báo (forecast)** trả lời: chuyển dịch theo hướng nhìn của vệ tinh (LOS) của mỗi ô sẽ thay đổi bao nhiêu ở vài
  tầm dự báo, và có mô hình nào làm tốt hơn "không đổi" hay "giữ nguyên xu thế" không? Dùng để biết trước điều cần
  chờ ở các lần chụp sau, và kiểm tra xem mưa hay nước ngầm có thêm khả năng dự báo không.
- Không đọc bản đồ tính nhạy cảm như bản đồ nguyên nhân: khai thác nước ngầm, tác nhân chính của sụt lún đô thị,
  không có trong các lớp. Không dùng riêng dự báo để cảnh báo: phải đọc kết quả kiểm định ngược (backtest) trước
  (§6). Cả hai không thay cho phân vùng nguy cơ ([hazard-zoning.md](hazard-zoning.md)); tính nhạy cảm còn lấy nhãn
  từ chính phân vùng đó.

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Sản phẩm InSAR | có | `geoeyes run` ([insar-processing.md](insar-processing.md)) | `<project>/products/<product_id>/points.parquet` có `los_e`, `los_n`, `los_u`; `timeseries.parquet` | dự báo đọc trực tiếp; tính nhạy cảm đọc qua các ô của phân vùng nguy cơ |
| Phân vùng nguy cơ của cùng sản phẩm | bắt buộc với tính nhạy cảm; tuỳ chọn với dự báo | `geoeyes hazard <project> --product <id>` | `<project>/analyses/hazard/<product_id>/hazard.json`, `cells.parquet`, `rain.npz`, `groundwater.npz` (nếu đã đọc GLDAS) | cho lưới (`cell_m`, `bounds`, `lat0`), nhãn (`rate_mm_yr`, `mode`, `n_points`), và mưa / nước ngầm làm biến đầu vào của dự báo |
| DEM | có (tính nhạy cảm) | `[stack] dem` của dự án (SRTM 1″ / Copernicus GLO-30), tải khi cần | `<workspace>/cache/dem/` | là mô hình bề mặt: có cả nhà cửa |
| ESA WorldCover 10 m 2021 v200 | tự động | đọc qua HTTPS (`esa-worldcover.s3.eu-central-1.amazonaws.com`, mảnh 3°) | không lưu cache: đọc lại mỗi khi dựng lại các lớp | cần mạng ở lần chạy đầu |
| Công trình Overture Maps | tự động | `geoeyes.ml.overture` | `<workspace>/cache/overture/` | chiều cao thường thiếu (Hà Nội: 1,4 %) |
| Hàm lượng sét SoilGrids 2.0, 0–5 cm | tự động | VRT `files.isric.org`, 250 m | không lưu cache | |
| Bề dày đất yếu | tuỳ chọn | `[postprocess.geology]`: `raster` (GeoTIFF, m), `boreholes` (CSV `lon, lat, thickness_m`), nếu không có thì `open_fallback = true` (Pelletier et al. 2016) | đường dẫn tương đối với dự án; cache `<workspace>/cache/geology/` | nguồn mở dự phòng cần `EARTHDATA_TOKEN`; xem [decompose-and-soft-soil.md](decompose-and-soft-soil.md) |
| Tham số | tuỳ chọn | `[postprocess.susceptibility]`, `[postprocess.forecast]` trong `project.toml`, hoặc `--set KEY=VALUE` | TOML | khoá lạ bị từ chối |

Danh sách kiểm tra:

- [ ] Sản phẩm đã có và đúng là sản phẩm cần dùng (`geoeyes status <project>`; nếu không thì truyền `--product`).
- [ ] Đã chạy `geoeyes hazard` cho sản phẩm đó (có `analyses/hazard/<product_id>/hazard.json`).
- [ ] `cell_m` của phân vùng nguy cơ là ô mong muốn cho lưới tính nhạy cảm (được dùng lại nguyên như vậy).
- [ ] Dải tốc độ rộng hơn nhiễu: ít nhất 20 ô có nhãn đạt hoặc vượt `label_rate` và 20 ô dưới ngưỡng.
- [ ] Với dự báo: chuỗi dài ít nhất `min_history_days` cộng tầm dự báo dài nhất (hơn khoảng 6 tháng).
- [ ] Có mạng để đọc WorldCover, SoilGrids và Overture ở lần chạy tính nhạy cảm đầu tiên.

## 3. Phương pháp

### 3.1 Tính nhạy cảm (`geoeyes.ml.susceptibility`, `geoeyes.ml.layers`)

1. **Lưới.** Lưới của phân vùng nguy cơ (`cell_m`, `lat0` lấy từ `hazard.json`), mở rộng ra mọi ô trong hình chữ
   nhật bao sản phẩm, dù có hay không có điểm InSAR (`Grid`: chỉ số ô `kx = floor(lon · 111320 cos(lat0) / cell_m)`,
   `ky = floor(lat · 110540 / cell_m)`).
2. **Các lớp** (mỗi lớp một cột; lớp nào không đọc được để NaN và ghi tên vào `warnings`): `height_m`, `slope_deg`
   (DEM); `lc_built`, `lc_crop`, `lc_tree`, `lc_grass`, `lc_water`, `lc_bare`, `lc_wetland` (tỉ lệ diện tích ô theo
   lớp WorldCover 50, 40, 10, 30, 80, 60, 90); `dist_water_m` (khoảng cách Euclid trung bình từ các điểm ảnh 10 m của
   ô đến lớp 80); `bld_count`, `bld_cover` (diện tích mái / diện tích ô, chặn ở 1), `bld_height_m` (trung bình theo
   diện tích, nơi biết chiều cao) từ Overture; `soil_clay` (g/kg, điểm ảnh 250 m gần nhất); `rain_annual_mm` (tổng
   mưa năm trung bình từ `rain.npz` của phân vùng nguy cơ); `soft_soil_m`. Bảng được lưu thành `layers.parquet` và
   dùng lại khi lưới và nguồn đất yếu không đổi.
3. **Nhãn.** Các ô của phân vùng nguy cơ có `n_points >= min_points` (mặc định 3), tốc độ hữu hạn, thuộc chế độ
   `mode` (mặc định `subsidence`, hoặc `landslide`, `all`). Ô *đang chuyển dịch* (nhãn 1) khi
   `−rate_mm_yr >= label_rate` (mặc định 5 mm/năm; quy ước dấu GeoEyes, âm = lún / xuống dốc), ngược lại nhãn 0. Ô
   không có InSAR thì không có nhãn.
4. **Biến dự báo.** Mọi lớp trừ `exclude` (mặc định `["rain_annual_mm"]`: lưới 5–25 km, trong một thành phố chỉ mã
   hoá vị trí) và trừ các cột rỗng hoặc hằng số.
5. **Chặn sớm.** Dưới 20 ô chuyển dịch hoặc dưới 20 ô ổn định thì dừng, kèm P5–P95 của tốc độ và một gợi ý
   `label_rate` (P90 của tốc độ lún), có cảnh báo nếu giá trị này nhỏ hơn hai lần sai số tốc độ trung vị.
6. **Mô hình** (scikit-learn, `seed` = 0): `logistic` (điền thiếu bằng trung vị, chuẩn hoá, `LogisticRegression`,
   `class_weight="balanced"`, C = 1); `random_forest` (300 cây, `min_samples_leaf=5`, `max_features="sqrt"`,
   `balanced_subsample`); `gradient_boosting` (`HistGradientBoostingClassifier`, 300 vòng, tốc độ học 0,05, 31 lá,
   `min_samples_leaf=30`, L2 = 1, cân bằng lớp).
7. **Đánh giá.** Khối không gian cạnh `block_m` (mặc định 1000 m): `block = (floor(kx·cell_m/block_m),
   floor(ky·cell_m/block_m))`; `GroupKFold` với `min(folds, n_blocks)` phần (`folds` = 5; dưới 2 khối thì dừng).
   Điểm số trên dự đoán của phần giữ lại: ROC AUC, average precision, Brier. Làm lại với `StratifiedKFold` xáo trộn
   (kiểm tra chéo ngẫu nhiên) để thấy tự tương quan không gian làm điểm số "ngây thơ" cao lên bao nhiêu (Brenning
   2005). Độ quan trọng hoán vị tính trên từng phần không gian giữ lại (mức giảm AUC, lặp 5 lần), có trọng số theo
   kích thước phần.
8. **Chọn mô hình và lập bản đồ.** Mô hình có AUC không gian cao nhất là `chosen`. Cả ba được khớp lại trên mọi ô có
   nhãn và dự đoán cho mọi ô lưới (`p_logistic`, `p_random_forest`, `p_gradient_boosting`); `probability` = của mô
   hình được chọn; `class` 0–4 = rất thấp … rất cao, ranh giới 0,2 / 0,4 / 0,6 / 0,8. `outside` = đúng khi có biến
   nằm ngoài khoảng 1–99 % của các ô có nhãn (ngoại suy). Tỉ số odds của hồi quy logistic cho mỗi độ lệch chuẩn =
   `exp(coef)`.

### 3.2 Dự báo (`geoeyes.ml.forecast`)

1. **Ô.** Các điểm của sản phẩm gom vào ô vuông `cell_m` (mặc định 100 m, ít nhất `min_points` = 3): chuỗi LOS trung
   vị mỗi ô, đặt mốc 0 tại ngày đầu (mm, dương = tiến về phía vệ tinh). Đây là ô riêng của dự báo, không phải ô của
   phân vùng nguy cơ.
2. **Tầm dự báo.** `horizons_days`, hoặc mặc định 1/6, 1/3 và 1/2 độ dài chuỗi, làm tròn đến 10 ngày, mỗi tầm trong
   khoảng 10–365 ngày.
3. **Mô hình.** `last`: không đổi. `linear`: đường thẳng bình phương tối thiểu của lịch sử đến gốc t0, ngoại suy (cần
   3 ngày chụp). `seasonal`: đường thẳng cộng sin và cos chu kỳ năm (cần 5 ngày chụp và 1,5 năm lịch sử). `gbm`: một
   mô hình `HistGradientBoostingRegressor` *chung* (hàm mất mát sai số tuyệt đối, 300 vòng, tốc độ học 0,06, 31 lá,
   `min_samples_leaf=40`, L2 = 1, dừng sớm trên 15 %) cho mọi ô và mọi tầm, với các biến `d30`, `d60`, `d90`,
   `d180`, `d365` (thay đổi trong k ngày gần nhất), `rate_90`, `rate_all`, `acc` (hệ số bậc hai), `noise` (độ lệch
   chuẩn phần dư của đường thẳng), `doy_sin`, `doy_cos`, `h`, `rain_1`, `rain_3`, `rain_6` (dị thường mưa trung bình
   vùng của 1 / 3 / 6 tháng trước, từ `rain.npz`), `gws_anom`, `gws_d3`, `gws_d12` (trữ lượng nước ngầm GLDAS của
   tháng cuối cùng đã công bố trước t0: dị thường, thay đổi 3 và 12 tháng), `span`. Tối đa `max_samples` = 400 000
   dòng huấn luyện (lấy mẫu ngẫu nhiên).
4. **Kiểm định ngược với gốc trượt (rolling origin).** `last_cut = t_end − h_max`, `step = max(h_max/2, 10 ngày)`,
   các mốc cắt `last_cut − k·step` với k < `n_origins` (3), chỉ giữ mốc cách ngày đầu ít nhất `min_history_days`
   (90). Ở mỗi mốc cắt, GBM chỉ học từ các gốc và đích không muộn hơn mốc (chỉ huấn luyện khi có ≥ 200 dòng); mọi mô
   hình dự đoán thay đổi từ mốc cắt đến mốc cắt + h cho mọi ô; sai số = dự đoán − thực đo.
5. **Chọn.** MAE theo mô hình và tầm; `base_best[h]` = MAE thấp nhất của các mô hình cơ sở; điểm = trung bình theo
   tầm của MAE / `base_best`; điểm thấp nhất là `chosen`. Kỹ năng (skill) = 1 − MAE / `base_best` (bằng 0 với mô
   hình cơ sở tốt nhất).
6. **Khoảng tin cậy.** Conformal tách (Vovk et al. 2005): nửa độ rộng = phân vị ⌈(n+1)·mức⌉/n của sai số tuyệt đối
   trong kiểm định ngược của mô hình được chọn, với mức 0,8 và 0,95. Độ phủ được kiểm tra trên mốc cắt muộn nhất với
   độ rộng tính từ các mốc sớm hơn (cần từ 2 mốc cắt trở lên).
7. **Dự báo cuối** tính từ ngày chụp cuối: mô hình cơ sở được chọn, hoặc GBM học lại trên mọi gốc.

## 4. Các bước triển khai

1. **Chạy phân vùng nguy cơ trước.** `geoeyes hazard <project> --product <product_id>` → `analyses/hazard/<product_id>/`
   ([hazard-zoning.md](hazard-zoning.md)).
2. **Tính nhạy cảm.** `geoeyes susceptibility <project> [--product <id>] [--set label_rate=5] [--set block_m=1000]
   [--set mode=subsidence]`. Không có `--product` thì lấy sản phẩm mới nhất của mỗi vệt quỹ đạo. Web app: Nghiên cứu
   học máy → chọn sản phẩm → thẻ Susceptibility → ngưỡng và cỡ khối → Run (bị khoá khi chưa có phân vùng nguy cơ).
   Thời gian chạy: chưa ghi nhận; lần đầu tải các lớp, các lần sau in "layers: reused" và chỉ khớp mô hình (ba mô
   hình × năm phần cộng kiểm tra chéo ngẫu nhiên). Ghi vào `<project>/analyses/susceptibility/<product_id>/`:
   `layers.parquet`, `layers.json`, `grid.parquet`, `models.joblib`, `susceptibility.json`, `manifest.json`.
3. **Dự báo.** `geoeyes forecast <project> [--product <id>] [--set horizons_days=[30,90,180]] [--set n_origins=3]`.
   Web app: cùng trang, thẻ Forecast → Run. Ghi vào `<project>/analyses/forecast/<product_id>/`: `forecast.parquet`,
   `cells_ts.npy`, `forecast.json`, `model.joblib` (chỉ khi GBM được chọn), `manifest.json`.
4. **Bản đồ.** Trên web app, "View on the results map" thêm kết quả thành một lớp chuyên đề; "Make a map" mở trình
   biên tập bản đồ.

## 5. Kết quả và cách đọc

| Tệp / trường | Ý nghĩa |
|---|---|
| `susceptibility.json` `labels` | số ô có nhãn, số ô chuyển dịch, tỉ lệ, điểm tham chiếu của phân vùng nguy cơ |
| `models.<name>.spatial_cv` / `random_cv` | `auc`, `ap`, `brier`; điểm không gian là điểm trung thực cho vùng mới |
| `models.<name>.importance` | mức giảm AUC trung bình khi hoán vị lớp đó trên các khối giữ lại |
| `chosen`, `odds_ratio_per_sd` | mô hình được lập bản đồ; tỉ số odds logistic cho một độ lệch chuẩn của mỗi lớp |
| `outside_share`, `warnings` | tỉ lệ ô lưới phải ngoại suy; các lớp không đọc được hoặc không mang thông tin |
| `grid.parquet` | mỗi ô lưới: `kx, ky, lon, lat`, các lớp, `rate_mm_yr`, `label` (1 / 0 / NaN), `p_*`, `probability`, `class` (0–4), `outside` |
| `forecast.parquet` | mỗi ô và tầm: `cell, lon, lat, horizon_days, change_mm, lo80, hi80, lo95, hi95` (mm LOS, dương = về phía vệ tinh, thay đổi tính từ ngày cuối) |
| `forecast.json` `backtest` | `cuts_days`, `mae_mm`, `skill`, `coverage`, `interval_mm` theo mô hình và tầm |

Bản đồ trên web app: *probability* (dự đoán chỉ từ các lớp, kể cả nơi InSAR không có điểm; ô gạch chéo = ngoài khoảng
huấn luyện), *label* (điều InSAR đã đo: đỏ đang chuyển dịch, xanh dưới ngưỡng, xám không có điểm), *outside*, và từng
lớp dưới dạng bản đồ chuyên đề; với dự báo là thay đổi theo từng tầm và chuỗi thời gian của ô được bấm.

Ví dụ (các lần chạy ngày 2026-10-25/26, Hà Nội S1 quỹ đạo xuống vệt 91, sản phẩm `..._20251001_20261015_v4`): tính
nhạy cảm trên 27 680 ô 100 m, 15 071 ô có nhãn, 1 606 ô chuyển dịch ở ngưỡng 5 mm/năm (10,7 %); AUC không gian 0,708
(logistic), 0,732 (random forest), 0,734 (gradient boosting, được chọn), so với AUC kiểm tra chéo ngẫu nhiên 0,726 /
0,778 / 0,780; 31 % lưới nằm ngoài khoảng huấn luyện; hai lớp quan trọng nhất là `lc_built` và `bld_count` (≈ 0,05
mỗi lớp). Dự báo 15 071 ô, tầm 60 / 130 / 190 ngày, chỉ có hai mốc cắt: chọn `last`; kỹ năng của GBM −0,66 / −0,67 /
−0,39, của linear −0,21 / −0,65 / −0,83; độ phủ của khoảng 80 % là 47 % / 87 % / 47 %. Với COSMO-SkyMed Hà Nội
2011–2014 cũng chọn `last`; với S1 Mexico City (6 tháng) chọn `linear`.

## 6. Kiểm tra chất lượng

- **AUC không gian so với ngẫu nhiên.** Báo cáo AUC không gian. Chênh lệch lớn nghĩa là mô hình học vị trí chứ không
  học quá trình. AUC không gian dưới khoảng 0,7 là yếu; 0,5 là không có kỹ năng.
- **Nhãn phải vượt nhiễu.** `label_rate` phải lớn hơn hai lần `rate_se_mm_yr` điển hình của các ô; khi nhãn quá ít,
  thông báo lỗi nêu cả hai con số.
- **Cỡ khối.** Thử `block_m` gấp 2 và 3 lần mặc định: nếu AUC tụt mạnh, khối 1 km vẫn còn rò rỉ thông tin.
- **Độ quan trọng và tỉ số odds khớp về dấu và thứ hạng** với hiểu biết sẵn có (đất yếu, khu mới xây). Lớp có độ quan
  trọng cao mà không có liên hệ vật lý (ví dụ khoảng cách tới nước thay cho một quận) là dấu hiệu cảnh báo.
- **`outside_share`** và các ô gạch chéo: không đọc xác suất ở đó.
- **Dự báo: kỹ năng > 0 ở mọi tầm** thì mới dùng mô hình khác mô hình cơ sở; khi chọn `last`, báo cáo là "không mô
  hình nào thắng được giả định không đổi". So `coverage` với 0,8 / 0,95; độ phủ thiếu (ví dụ 47 %) nghĩa là khoảng
  tin cậy quá hẹp. Dưới 2 mốc cắt thì không kiểm tra được độ phủ.

## 7. Hạn chế và lỗi thường gặp

- Tính nhạy cảm là quan hệ đồng hành; các lớp thiếu khai thác nước ngầm, lịch sử gia tải và tuổi công trình.
- DEM là mô hình bề mặt: trong đô thị, `height_m` và `slope_deg` có cả nhà cửa.
- WorldCover là năm 2021, Overture là hiện tại: các lớp có thể muộn hơn chuyển dịch.
- Nhãn thừa hưởng điểm tham chiếu (trung bình cảnh, GNSS) và cách chiếu (thẳng đứng hoặc xuống dốc) của phân vùng nguy
  cơ.
- Chuỗi ngắn (một năm) cho ít mốc cắt và MAE nhiễu; mô hình mùa cần 1,5 năm, nếu không sẽ để trống. Dự báo theo LOS,
  không phải thẳng đứng.
- Khoảng conformal giả định sai số hoán đổi được, điều mà chuỗi thời gian không thoả: vì vậy phải kiểm tra độ phủ.
- Các ghi chú nghiên cứu mà mã trích dẫn (`docs/en/research/ai-susceptibility.md`, `ai-forecasting.md`) chưa có; skill
  này và mã là tài liệu chuẩn.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- Chạy phân vùng nguy cơ với `cell_m` hợp mật độ điểm (100 m cho Sentinel-1; nhỏ hơn cho băng X). Lưới tính nhạy cảm
  đi theo.
- Chỉnh `label_rate` theo dải tốc độ và nhiễu của vùng; dùng `mode = "landslide"` (theo quy tắc độ dốc của phân vùng
  nguy cơ) cho sườn dốc, `all` để gộp cả hai.
- Đưa raster đất yếu hoặc lỗ khoan địa phương vào `[postprocess.geology]` nếu có.
- Với chồng ảnh băng X ngắn, đặt `horizons_days` rõ ràng (ví dụ `[30, 60]`); chỉ giảm `min_history_days` khi chấp
  nhận kiểm định ngược yếu hơn.
- Giữ nguyên được: các lớp (toàn cầu), các mô hình, kiểm tra chéo theo khối, khoảng conformal.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/ml/susceptibility.py`, `src/geoeyes/ml/layers.py`, `src/geoeyes/ml/forecast.py`,
  `src/geoeyes/ml/__init__.py` (`run_susceptibility`, `run_forecast`), `src/geoeyes/hazard/assess.py`
  (`load_cells`, `read_cells`), `webapp/src/pages/Ai.tsx`.
- Hướng dẫn và ghi chú: [hazard-zoning.md](hazard-zoning.md), [decompose-and-soft-soil.md](decompose-and-soft-soil.md),
  [../research/rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md),
  [../research/groundwater-insar.md](../research/groundwater-insar.md) §4.2 (biến nước ngầm).
- Brenning, A. (2005). Spatial prediction models for landslide hazards: review, comparison and evaluation. NHESS 5,
  853–862. https://doi.org/10.5194/nhess-5-853-2005
- Vovk, V., Gammerman, A., Shafer, G. (2005). *Algorithmic Learning in a Random World*. Springer.
- Zanaga, D., et al. (2022). ESA WorldCover 10 m 2021 v200. https://doi.org/10.5281/zenodo.7254221
- Poggio, L., et al. (2021). SoilGrids 2.0. SOIL 7, 217–240. https://doi.org/10.5194/soil-7-217-2021
- Pelletier, J. D., et al. (2016). A gridded global data set of soil, intact regolith, and sedimentary deposit
  thicknesses. JAMES 8, 41–65. https://doi.org/10.1002/2015MS000526
