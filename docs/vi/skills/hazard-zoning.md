# Skill: phân vùng nguy cơ sụt lún và trượt lở chậm

> Bản dịch của [docs/en/skills/hazard-zoning.md](../../en/skills/hazard-zoning.md). Dịch ngày 2026-11-01.

> Xếp mỗi ô 100 m của một sản phẩm InSAR vào một mức nguy cơ, từ rất thấp đến rất cao, dựa trên chuyển dịch theo
> hướng gây hại (thẳng đứng hoặc xuôi dốc), phản ứng của nó với mưa và độ lún lệch mà nó gây ra.
> Trạng thái: công cụ sàng lọc đang vận hành (v1, đã xong bước nghiên cứu R0–R1 và một phần R2). Đối chiếu với mã
> lần gần nhất 2026-11-01. Lệnh `geoeyes hazard`; web app **Phân tích chuyên sâu → Phân tích chuyên đề**.

## 1. Khi nào dùng

- **Câu hỏi.** Ở đâu mặt đất chuyển dịch đủ nhanh, theo hướng gây hại, để cần chú ý; chuyển dịch có đi theo mưa
  (hoặc trữ lượng nước ngầm) không; ở đâu lún lệch vượt ngưỡng gây hư hại?
- **Quyết định hỗ trợ.** Khu nào cần kiểm tra trước, chỗ nào cần xem chuỗi thời gian, khu nào cần tham chiếu tốt
  hơn hoặc hướng chụp thứ hai. Đây là lớp nền cho [behaviour-and-risk.md](behaviour-and-risk.md),
  [lines-and-consolidation.md](lines-and-consolidation.md) (phần cố kết), [decompose-and-soft-soil.md](decompose-and-soft-soil.md)
  (phần địa chất) và [susceptibility-and-forecast.md](susceptibility-and-forecast.md).
- **Không dùng cho.** Nguy cơ theo xác suất (chưa ước tính chu kỳ lặp hay xác suất phá huỷ: Fell et al. 2008), kích
  hoạt trượt lở nhanh theo từng trận mưa, bản đồ rủi ro (dùng [behaviour-and-risk.md](behaviour-and-risk.md)), hay
  đọc lớp cường độ trên sản phẩm tham chiếu theo trung bình cảnh mà không có `reference_bbox` hoặc `gnss_tie`.

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Sản phẩm điểm (PS/DS) | có | [insar-processing.md](insar-processing.md): `geoeyes run` | `projects/<name>/products/<product_id>/` gồm `points.parquet` (cột `point_uid`, `lon`, `lat`, `los_e`, `los_n`, `los_u`, có thể có `temporal_coherence`), `timeseries.parquet`, `manifest.json` | Thiếu `los_e/los_n/los_u` thì dừng. Cần ≥ 12 tháng và ≥ 12 lần chụp cho kiểm định mưa, ≥ 18 tháng cho gia tốc |
| DEM | có (nếu không, mọi ô coi là "subsidence") | `[stack].dem` của dự án: `srtm-1` (mặc định), `copernicus-30`, `lidar-3dep`, thư mục `.hgt` hoặc GeoTIFF; tự tải khi thiếu | `[stack] dem`, hoặc ghi đè bằng `[postprocess.hazard] dem = "<đường dẫn hoặc tên>"`; bộ đệm `<workspace>/cache/dem` | DEM mặt đất trần (FABDEM) giảm nhiễu do nhà cửa trong đô thị |
| Mưa tháng và tổng mưa năm | có (tự động) | COG CHIRPS v3 từ data.chc.ucsb.edu (0,05°); dự phòng là ERA5 ngày qua Open-Meteo archive (0,25°) | `[postprocess.hazard] rain_source = "auto" \| "chirps" \| "era5"`; bộ đệm `<workspace>/cache/rainfall/chirps3_*.npz`, `era5_*.json` | Lần đầu cần mạng. 30 tệp năm (1991–2020) và mỗi tháng một tệp |
| Trữ lượng nước ngầm GLDAS | tuỳ chọn (chẩn đoán) | NASA GLDAS CLSM025 DA1 D v2.2, `GWS_tavg`, qua Earthdata OPeNDAP (dự phòng Harmony) | `EARTHDATA_TOKEN` trong biến môi trường hoặc `.env`; `[postprocess.hazard] groundwater = "auto" \| "gldas" \| "off"`; bộ đệm `<workspace>/cache/groundwater/gldas_gws_*.npz` | Công bố chậm vài tháng: các ngày gần đây bị loại khỏi kiểm định |
| Vùng tham chiếu ổn định | rất nên có khi sản phẩm tham chiếu theo trung bình cảnh | Nền ổn định đã biết (đá gốc, cụm công trình cũ kiên cố, vị trí trạm GNSS), từ bản đồ địa chất hoặc hiểu biết tại chỗ | `[postprocess.hazard] reference_bbox = [w, s, e, n]` (độ), hoặc ô "Stable" trên web | Phải chứa ít nhất một ô. Bị bỏ qua khi `gnss_tie = true` |
| Hiệu chỉnh GNSS | tuỳ chọn, thay cho `reference_bbox` | [gnss-calibration.md](gnss-calibration.md): `geoeyes gnss <project> --product <id>` | `projects/<name>/analyses/gnss/<product_id>/`; `[postprocess.hazard] gnss_tie = true` | Sản phẩm chưa có hiệu chỉnh thì lệnh dừng. Một trạm = chưa kiểm tra độc lập (cảnh báo) |
| Raster tính nhạy cảm trượt lở | tuỳ chọn | Bản đồ của người dùng, lớp 0..3 | GeoTIFF, hệ toạ độ bất kỳ; `[postprocess.hazard] susceptibility = "<đường dẫn>"` | Thay cho lớp độ dốc tạm (15° / 25° / 35°) ở ô trượt lở. Giá trị ngoài 0..3 bị bỏ |

Danh sách kiểm tra trước khi chạy:

- [ ] Sản phẩm có `los_e`, `los_n`, `los_u` và chuỗi thời gian; đã biết khoảng thời gian và số lần chụp.
- [ ] Đã biết sản phẩm tham chiếu theo gì (điểm, trung bình cảnh): `manifest.json` → `metrics.reference`.
- [ ] Nếu là trung bình cảnh: đã chọn `reference_bbox` trên nền ổn định, hoặc đã chạy `geoeyes gnss` và đặt
  `gnss_tie = true`.
- [ ] Truy cập được data.chc.ucsb.edu và archive-api.open-meteo.com (lần đầu), Earthdata cho GLDAS.
- [ ] DEM của dự án đúng là DEM cần dùng (DSM cho độ dốc giả ở mép nhà).
- [ ] Các tham số thay đổi đã ghi trong `[postprocess.hazard]` (khoá lạ làm lệnh dừng).

## 3. Phương pháp

Mã: `src/geoeyes/hazard/assess.py` (`HazardParams`, `assess`). Tên tham số dưới đây là các khoá của
`[postprocess.hazard]`.

1. **Ô.** Các điểm được gom vào ô vuông cạnh `cell_m` (100 m; cho phép 5–5000) trên lưới mét cục bộ. Mỗi ô cần
   `min_points` (3) điểm và giữ trung vị của chuỗi LOS, trung vị vectơ đơn vị LOS (chuẩn hoá lại) và trung vị độ
   nhất quán.
2. **Tham chiếu.** Có `gnss_tie` thì cộng hiệu chỉnh GNSS của sản phẩm vào mọi chuỗi. Nếu không mà có
   `reference_bbox` thì trừ chuỗi trung vị của các ô bên trong khỏi mọi ô. Nếu không có cả hai, giữ tham chiếu của
   sản phẩm; tham chiếu trung bình cảnh sinh cảnh báo.
3. **Địa hình và chế độ.** DEM được làm trơn bằng Gauss với σ = nửa ô, rồi lấy độ dốc trên một ô (sai phân trung
   tâm). `slope ≥ landslide_min_slope_deg` (10°) → chế độ `landslide`, còn lại `subsidence`.
4. **Chuyển dịch theo hướng gây hại** (bên trong phân tích, dương = lún hoặc xuôi dốc):
   - sụt lún: y = −d_LOS / l_u (ô có |l_u| < 0,1 không đánh giá);
   - trượt lở: y = d_LOS / (**s**·**l**), **s** là vectơ đơn vị hướng dốc nhất; không đánh giá khi
     |**s**·**l**| < `min_sensitivity` (0,3).
   - Một phép bình phương tối thiểu với [1, t, ½t²] (t đã trừ trung bình, chỉ có số hạng bậc hai khi ≥ 6 lần chụp)
     cho tốc độ (mm/năm) và σ của nó, gia tốc và σ của gia tốc.
   - Ngưỡng ổn định của từng ô: max(`stable_floor_mm_yr` 2, `stable_sigma` 2 × σ).
5. **Mưa.** Mưa tháng theo từng pixel, từ `max_lag_months` (6) tháng trước ngày đầu đến ngày cuối; tổng mưa năm
   trong `climate_years` (1991, 2020) cho P10 và P90 (cần ≥ 10 năm). Với `auto`, ERA5 thay CHIRPS khi đọc được
   dưới 80 % số tháng hoặc số năm khí hậu.
   - CRD(t) = Σ(P_tháng − P̄), P̄ là trung bình trong cửa sổ phân tích, tuyến tính trong tháng; tháng thiếu tính
     bằng P̄; pixel thiếu > 20 % số tháng thì không kiểm định.
6. **Liên hệ mưa – biến dạng** (`coupling.py`), theo từng ô, chỉ khi khoảng thời gian ≥ `min_span_months` (12) và
   số lần chụp ≥ `min_epochs` (12):

       y(t) = a + b·t + k·CRD(t − τ) + ε,   τ ∈ {0 … max_lag_months}

   - τ = độ trễ cho |tương quan riêng phần| r lớn nhất giữa y và CRD khi đã khử [1, t].
   - p = tỉ lệ trong `n_surrogates` (500) chuỗi thay thế (xáo pha ngẫu nhiên) của dị thường mưa (Ebisuzaki 1997) có
     |r| tốt nhất đạt tới |r| quan sát; khi dưới 10 chuỗi vượt, p lấy từ phân phối chuẩn khớp với Fisher z của
     phân phối rỗng.
   - q = Benjamini–Hochberg trên mọi ô đã kiểm định (`fdr` = true). Ô **có liên hệ** khi q ≤ `alpha` (0,05).
   - Kịch bản ở ô có liên hệ: rate_dry = b + k·(P10 − 12·P̄), rate_wet = b + k·(P90 − 12·P̄).
7. **Liên hệ với nước ngầm** (chẩn đoán, không đổi mức nguy cơ): cùng kiểm định nhưng thay CRD bằng trữ lượng GLDAS
   S tại giữa tháng, chuỗi thay thế dựng từ thay đổi trữ lượng hằng tháng, chỉ trên các ngày mà trữ lượng đã phủ
   (vẫn cần ≥ 12 tháng và ≥ 12 lần chụp). Kết quả ở các cột `gw_*`.
8. **Cường độ I** (theo hướng gây hại; ở ô có liên hệ lấy giá trị xấu nhất giữa tốc độ quan sát, năm khô và năm
   ướt):

   | Lớp | Sụt lún, `subsidence_breaks` (10, 30) mm/năm | Trượt lở, `landslide_breaks` (16, 160) mm/năm |
   |---|---|---|
   | I0 | < ngưỡng ổn định, hoặc chuyển dịch ngược | như bên trái |
   | I1 | ngưỡng … 10 | ngưỡng … 16 |
   | I2 | 10 … 30 | 16 … 160 |
   | I3 | ≥ 30 | ≥ 160 |

   - Tăng 1 lớp (tối đa I3) khi khoảng thời gian ≥ `accel_min_span_months` (18), gia tốc/σ ≥ `accel_t` (3) và tốc
     độ > 0.
   - Tốc độ < −ngưỡng → gắn cờ `opposite_motion` (nâng hoặc như đi ngược dốc), xếp I0.
9. **Tổn hại tiềm tàng S.**
   - Sụt lún: β = max trên 8 ô lân cận của |v_i − v_j| · `horizon_yr` (10) / L, L là khoảng cách tâm ô; phân lớp
     theo `distortion_breaks` (1/500, 1/300, 1/150) → S0…S3. Không phụ thuộc tham chiếu.
   - Trượt lở: lớp 0..3 của `susceptibility` nếu có, nếu không dùng lớp độ dốc `slope_breaks` (15°, 25°, 35°).
10. **Mức nguy cơ** = `matrix`[I][S], các mức 0 rất thấp … 4 rất cao, −1 chưa đánh giá:

    | | S0 | S1 | S2 | S3 |
    |---|---|---|---|---|
    | I0 | rất thấp | rất thấp | thấp | thấp |
    | I1 | thấp | thấp | trung bình | cao |
    | I2 | trung bình | trung bình | cao | rất cao |
    | I3 | cao | cao | rất cao | rất cao |

Cơ sở đã công bố: Cigna et al. 2013 (ma trận PSI, phép chiếu L2S), Barra et al. 2017 và Tomás et al. 2019 (ngưỡng ổn
định, ≥ 3 PS), Navarro et al. 2020 (quy tắc độ dốc), Cruden & Varnes 1996 (16 mm/năm), Skempton & MacDonald 1956 và
Bjerrum 1963 (góc biến dạng), Bredenkamp et al. 1995 (CRD), Ebisuzaki 1997, Benjamini & Hochberg 1995, Knijnenburg
et al. 2009. Nguồn gốc của từng giá trị mặc định: [../research/rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md) §5.

## 4. Các bước triển khai

1. **Kiểm tra tham chiếu.** Đọc `metrics.reference` trong `projects/<name>/products/<id>/manifest.json`. Nếu là
   `"scene mean"`, chọn một vùng ổn định, hoặc chạy trước `geoeyes gnss <project> --product <id>`
   ([gnss-calibration.md](gnss-calibration.md)).
2. **Ghi tham số** (chỉ những gì khác mặc định):

   ```toml
   [postprocess.hazard]
   cell_m = 100
   reference_bbox = [105.770, 21.010, 105.780, 21.020]   # stable ground (example from the research note)
   # gnss_tie = true
   # susceptibility = "D:/data/landslide_susceptibility_classes.tif"
   ```
3. **Chạy.**

   ```
   geoeyes hazard <project> --product <product_id>
   geoeyes hazard <project> --product <product_id> --set cell_m=50 --set rain_source=era5
   geoeyes hazard <project> --product <product_id> --set "reference_bbox=[105.77,21.01,105.78,21.02]"
   ```
   Không có `--product` thì lấy sản phẩm mới nhất của mỗi vệt quỹ đạo. Giá trị của `--set` được đọc như JSON.
   Web app: **Phân tích chuyên sâu → Phân tích chuyên đề**, chọn dự án và sản phẩm, đặt kích thước ô (50/100/200/500
   m), tầm nhìn (5/10/20/50 năm), trễ tối đa (3/6/9/12 tháng), FDR (0,01/0,05/0,1), nguồn mưa, nước ngầm, vùng ổn
   định (W, S, E, N), gắn vào GNSS, rồi bấm **Chạy phân vùng nguy cơ**.
4. **Thời gian chạy.** Chưa đo. Lần chạy đầu trên một vùng tốn thời gian chủ yếu cho tải dữ liệu: CHIRPS đọc từng tệp
   một (dừng ở lần bị từ chối đầu tiên), GLDAS mất vài phút ở lần đọc đầu (theo thông báo của chương trình). Các lần
   sau đọc từ bộ đệm. Kiểm định bằng chuỗi thay thế chạy một lần cho mỗi pixel mưa, không phải cho mỗi ô.
5. **Tệp ghi ra** trong `projects/<name>/analyses/hazard/<product_id>/`: `cells.parquet`, `cells_ts.npy`,
   `rain.npz`, `groundwater.npz` (khi đọc được GLDAS), `hazard.json`, `hazard.gpkg` (lớp `hazard_cells`),
   `manifest.json`. Sản phẩm gốc không bao giờ bị sửa; chạy lại sẽ ghi đè phân tích.

## 5. Kết quả và cách đọc

Quy ước dấu của mọi kết quả (`hazard.json` `"sign"`, lược đồ `geoeyes.hazard/2`): **âm = lún hoặc xuôi dốc**,
dương = nâng hoặc ngược dốc.

| Trường (`cells.parquet`, cũng có trong `hazard.gpkg`) | Ý nghĩa |
|---|---|
| `mode` | `subsidence` hoặc `landslide` |
| `slope_deg`, `sensitivity` | độ dốc sau làm trơn; l_u (sụt lún) hoặc **s**·**l** (trượt lở) |
| `rate_mm_yr`, `rate_se_mm_yr`, `stable_mm_yr` | tốc độ theo hướng gây hại, σ của nó, ngưỡng ổn định của ô |
| `acc_mm_yr2`, `accelerating`, `opposite_motion` | gia tốc; đã tăng 1 lớp; chuyển dịch ngược hướng gây hại |
| `rain_lag_months`, `rain_r`, `rain_p`, `rain_q`, `rain_coupled` | độ trễ τ, tương quan riêng phần, p từ chuỗi thay thế, q theo FDR, có ý nghĩa thống kê |
| `rain_k_mm_per_100mm`, `trend_rain_corrected_mm_yr` | độ nhạy k trên 100 mm độ lệch mưa; b |
| `rate_dry_year_mm_yr`, `rate_wet_year_mm_yr` | tốc độ theo kịch bản (ô có liên hệ) |
| `intensity_observed`, `intensity` | I từ tốc độ quan sát; I sau kịch bản và gia tốc |
| `angular_distortion`, `susceptibility`, `secondary` | β; lớp của người dùng; S |
| `hazard` (gpkg: `hazard_level`) | mức 0–4, −1 chưa đánh giá |
| `gw_*` | các trường liên hệ tương tự, với trữ lượng nước ngầm |

- **Dấu của k.** Theo dấu GeoEyes, k < 0 nghĩa là mưa nhiều hơn → lún hoặc trượt xuôi dốc nhiều hơn
  (`coupling.share_negative_k` trong `hazard.json`). Với nước ngầm, g > 0 nghĩa là mặt đất lên xuống theo trữ lượng
  (tầng chứa nước đàn hồi, `groundwater.share_positive_g`).
- `hazard.json`: tham số, `by_level` (số ô và km² theo chế độ và mức), `coupling` (đã kiểm định, p < α thô, có ý
  nghĩa, độ trễ trung vị), `accelerating_cells`, `opposite_motion_cells`, `reference`, `rain` (nguồn, pixel,
  P10/P50/P90), `groundwater`, `warnings`.
- Lớp trên web: Mức nguy cơ, Cường độ (InSAR), Tổn hại tiềm tàng, Tốc độ, Liên hệ với mưa, Độ trễ so với mưa, Liên
  hệ với nước ngầm, Chế độ. Bấm vào một ô để xem chuỗi thời gian, các mô hình đã khớp và mưa tháng.

## 6. Kiểm tra chất lượng

- **Đọc cảnh báo trước.** Mục `warnings` trong `hazard.json`: tham chiếu trung bình cảnh, không kiểm định được liên
  hệ (thiếu thời gian/lần chụp), CHIRPS từ chối (đã dùng ERA5), tháng mưa chưa đủ, độ phủ của nước ngầm, không có địa
  hình.
- **Tham chiếu.** Không đọc bản đồ cường độ khi chưa tham chiếu về nền ổn định (tiêu chí R0 của nghiên cứu). Số
  `opposite_motion_cells` lớn (Mexico S1: 19 087 ô "nâng") cho thấy tham chiếu chỉ là tương đối.
- **Độ tin của liên hệ.** Tỉ lệ thô p < α (`cells_p_below_alpha` / `cells_tested`) phải lớn hơn α thì mới diễn giải
  các ô có liên hệ (tiêu chí R1). Hanoi CSK: 3,7 %, Hanoi S1: 1,7 %, không ô nào có ý nghĩa: kết quả âm tính (ghi chú
  nghiên cứu §7).
- **Nguồn mưa.** `rain.source`: ERA5 làm phẳng các đỉnh mưa đối lưu (Hà Nội tháng 6/2011: ERA5 224 mm, CHIRPS 430
  mm).
- **Bản đồ chế độ.** Ô trượt lở trên nền đô thị bằng phẳng là dấu hiệu nhiễu DSM; đối chiếu `slope_deg` với địa
  hình thực.
- **β không phụ thuộc tham chiếu**, nên vẫn đọc được lớp S trên sản phẩm tương đối (Mexico S1: 9 314 ô ≥ 1/500 trong
  10 năm, ghi chú nghiên cứu §7).

## 7. Hạn chế và lỗi thường gặp

- **Một hướng chụp.** Chuyển dịch được giả định là thẳng đứng hoặc xuôi dốc. Chuyển dịch ngang quanh phễu lún, hay
  sụt lún trên sườn dốc, bị quy sai: hãy tách thành phần bằng hai hướng chụp
  ([decompose-and-soft-soil.md](decompose-and-soft-soil.md)).
- **Phản ứng tuyến tính với mưa** được ngoại suy cho năm P10/P90; phản ứng của trượt lở và tầng chứa nước là phi tuyến.
- **Tương quan không phải nhân quả.** Mưa, nhiệt độ và trữ lượng nước cùng biến thiên trong khí hậu gió mùa (R2 chưa
  làm).
- **Tác nhân độ phân giải thô.** Pixel CHIRPS ≈ 5,5 km, ERA5 0,25°, GLDAS 0,25°: liên hệ tính theo pixel mưa.
- **Lớp chưa hiệu chỉnh.** `subsidence_breaks`, `slope_breaks` và `matrix` là lựa chọn chuyên gia cho tới khi làm
  R3/R4.
- **Chuỗi ngắn.** Dưới 12 tháng / 12 lần chụp thì bỏ qua liên hệ mưa; dưới 18 tháng thì không có gia tốc.
- **CHIRPS giới hạn truy cập.** Máy chủ từ chối client đọc nhiều tệp: một lần từ chối làm dừng việc đọc và `auto`
  chuyển sang ERA5. Chạy lại sau để bổ sung bộ đệm.
- **Chạy lại làm cũ các phân tích phụ thuộc.** Behaviour, risk, consolidation và geology đọc `cells.parquet`; chạy
  lại chúng sau khi chạy lại phân vùng.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- **Cần đổi:** `reference_bbox` (hoặc `gnss_tie`), `cell_m` (giữ lớn hơn kích thước nhà trên DSM; đây cũng là L của
  β), `dem` (dùng DEM mặt đất trần nếu có), `susceptibility` ở vùng núi, `rain_source = "era5"` nơi CHIRPS không phủ
  (CHIRPS chỉ có trên đất liền; pixel biển là không dữ liệu).
- **Giữ nguyên được:** mô hình CRD, kiểm định chuỗi thay thế/FDR, các ngưỡng góc biến dạng, ngưỡng trượt lở (Cruden &
  Varnes).
- **Hiệu chỉnh tại chỗ:** `subsidence_breaks` và `matrix` theo bản kiểm kê hư hại (nghiên cứu R3).
- **Vệ tinh:** mọi sản phẩm có vectơ LOS đều chạy được. Chồng ảnh băng X chỉ vài tuần (Capella, ICEYE) không cho liên
  hệ mưa và gia tốc; chỉ đọc β và tốc độ.
- **Thói quen đã biết:** độ dốc sau làm trơn ở Hà Nội có P99 = 4,3°, nên gần như mọi ô ở chế độ sụt lún; các sản phẩm
  Mexico City cần một vùng ổn định trên đá núi lửa trước khi đọc cường độ.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/hazard/assess.py`, `coupling.py`, `zoning.py`, `terrain.py`; `src/geoeyes/ancillary/rainfall.py`,
  `groundwater.py`; `src/geoeyes/api/hazard.py`; `webapp/src/pages/Hazard.tsx`, `LearnHazard.tsx` (Nguyên lý,
  chương 2); test `tests/unit/hazard/test_hazard.py`, `test_groundwater.py`.
- Nghiên cứu: [../research/rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md),
  [../research/groundwater-insar.md](../research/groundwater-insar.md); ADR-024 trong
  [../architecture/decisions.md](../architecture/decisions.md).
- Skill: [insar-processing.md](insar-processing.md), [gnss-calibration.md](gnss-calibration.md),
  [behaviour-and-risk.md](behaviour-and-risk.md), [exposure-and-flood-layers.md](exposure-and-flood-layers.md).
- Bài báo: Cigna, Bianchini & Casagli 2013 (*Landslides* 10:267); Barra et al. 2017 (*Remote Sensing* 9:1002);
  Tomás et al. 2019 (*Remote Sensing* 11:1675); Navarro et al. 2020 (*IJGI* 9:584); Cruden & Varnes 1996;
  Skempton & MacDonald 1956; Bjerrum 1963; Fernández-Torres et al. 2020; Ebisuzaki 1997; Benjamini & Hochberg
  1995; Knijnenburg et al. 2009; Funk et al. 2026 (CHIRPS v3); Hersbach et al. 2020 (ERA5); Li et al. 2019
  (GLDAS DA). Danh sách đầy đủ ở §10 của ghi chú nghiên cứu.
