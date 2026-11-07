# Skill: kiểm định InSAR bằng GNSS và gắn vào hệ quy chiếu mặt đất

> Bản dịch của [docs/en/skills/gnss-calibration.md](../../en/skills/gnss-calibration.md). Dịch ngày 2026-11-01.

> So một sản phẩm InSAR với vị trí GNSS hằng ngày của Nevada Geodetic Laboratory (NGL, hệ IGS20), tính hiệu chỉnh
> tốc độ (hoặc mặt nghiêng, hoặc theo từng ngày chụp) từ các trạm, kiểm tra bằng kiểm tra chéo bỏ-một
> (leave-one-out), rồi chuyển hiệu chỉnh sang sản phẩm không có trạm bằng cách gắn nó vào một sản phẩm khác.
> Trạng thái: đang vận hành (v1; đã xong bước nghiên cứu G1, G2, G7). Đối chiếu với mã lần gần nhất 2026-11-01
> (`validation/tie.py` là phần mới, chưa commit). Lệnh `geoeyes gnss`, `geoeyes tie`. Web app: dự án →
> **Validation** → khung GNSS và Calibration; Explorer → công tắc **Calibrated** của lớp; Phân tích chuyên sâu →
> Phân tích chuyên đề → "GNSS tie".

## 1. Khi nào dùng

- **Câu hỏi.** Chuỗi thời gian InSAR có khớp với GNSS về tốc độ và về hình dạng không? Bản thân điểm tham chiếu của
  sản phẩm (một điểm hay trung bình cảnh) có đang chuyển dịch không, bao nhiêu? Sản phẩm không có trạm nào bên trong
  có đưa về cùng mốc được không?
- **Quyết định hỗ trợ.** Công bố sản phẩm dưới dạng tương đối hay đã gắn vào GNSS; đặt
  `[postprocess.hazard] gnss_tie = true` ([hazard-zoning.md](hazard-zoning.md)); xuất tệp đã hiệu chỉnh.
- **Nên dùng** khi có trạm NGL nằm trong sản phẩm và ghi số liệu trong khoảng thời gian của nó, và sai số tham chiếu
  dự kiến lớn hơn độ bất định tốc độ GNSS (Mexico City: tham chiếu lệch 130 mm/năm).
- **Không nên gắn** khi chuyển dịch quanh trạm chỉ vài mm/năm trên một năm số liệu (Hà Nội, §6.2 của ghi chú nghiên
  cứu): gắn chỉ thêm nhiễu. Không chuyển hiệu chỉnh từ thành phố này sang thành phố khác: hệ số của nó là chuyển
  dịch của tham chiếu một cảnh cụ thể (ghi chú nghiên cứu §7.1, §7.2).

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Sản phẩm InSAR | có | `geoeyes run` ([insar-processing.md](insar-processing.md)) | `products/<id>/points.parquet` có `point_uid`, `lon`, `lat`, `los_e`, `los_n`, `los_u`, `vel_los_mm_yr`; `timeseries.parquet` (`point_uid`, `date`, `disp_mm`) | thiếu `los_e/n/u` thì dừng; véc-tơ đơn vị LOS hướng từ mặt đất lên vệ tinh |
| Danh sách trạm NGL | tự động | `https://geodesy.unr.edu/NGLStationPages/DataHoldings.txt` (không cần tài khoản, chỉ https) | bộ đệm `<workspace>/cache/gnss/ngl/DataHoldings.txt`, làm mới sau 7 ngày | chỉ lấy trạm **nằm trong phạm vi kinh vĩ của sản phẩm** và có số liệu trùng khoảng thời gian |
| Các bước nhảy thiết bị | tự động | `https://geodesy.unr.edu/NGLStationPages/steps.txt` | bộ đệm, 7 ngày | dùng loại 1 (thiết bị); động đất để phần phát hiện bước nhảy xử lý |
| Vị trí hằng ngày | tự động | `https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/IGS20/<SITE>.tenv3` | bộ đệm `<SITE>.tenv3`, làm mới sau 1 ngày | hệ IGS20 (NGL dùng từ tháng 8/2025) |
| Vận tốc MIDAS | tự động | `https://geodesy.unr.edu/gps_timeseries/IGS20/midas/midas.IGS.txt` | bộ đệm, 7 ngày | dùng khi `gnss_rate = "midas"`, và luôn được báo cáo |
| Tham số | tuỳ chọn | – | `[validation.gnss]` trong project.toml, hoặc `geoeyes gnss --set key=value`, hoặc biểu mẫu web | §3.5 |
| Sản phẩm tham chiếu để gắn | cho `geoeyes tie` | một sản phẩm khác trên cùng vùng, thuộc dự án bất kỳ trong không gian làm việc, tốt nhất đã hiệu chỉnh GNSS | `--reference <project>/<product_id>` | cần ít nhất 3 ngày chụp quanh khoảng thời gian của sản phẩm đích và ít nhất 10 ô chung |

Khi mất mạng, các tệp trong bộ đệm được dùng (kèm cảnh báo); nếu bộ đệm trống thì dừng.

Danh sách kiểm tra trước khi chạy:

- [ ] `DataHoldings.txt` có trạm nằm trong phạm vi sản phẩm trong khoảng ngày của nó (khung web hiện các trạm tìm
      được, kèm lý do nếu trạm không được so);
- [ ] sản phẩm có `los_e`, `los_n`, `los_u`;
- [ ] các trạm đã biết là xấu (mốc trạm trên mái, ăng-ten đã dời) đã đưa vào `exclude`;
- [ ] khi gắn: sản phẩm tham chiếu chồng lên sản phẩm đích về không gian và các ngày của nó bao trùm khoảng thời gian
      của sản phẩm đích.

## 3. Phương pháp

### 3.1 Trạm và làm sạch số liệu (`validation/gnss/ngl.py`)

Trên khoảng thời gian của sản phẩm ±30 ngày, với từng trạm:

1. **Giá trị ngoại lai:** theo từng thành phần, loại các ngày lệch quá 5 sigma bền (1,4826·MAD, tối thiểu 0,1 mm) so
   với trung vị trượt 15 ngày.
2. **Đoạn:** cắt tại các lần thay thiết bị của NGL và tại các bước nhảy giữa hai ngày liên tiếp lớn hơn max(15 mm
   ngang / 30 mm đứng, 5·σ); bỏ các đoạn ngắn hơn 30 ngày; cửa sổ có ít hơn 30 ngày thì loại trạm.
3. **Nối đoạn:** một xu hướng tuyến tính chung và một độ lệch cho mỗi đoạn (giữ được tốc độ của ăng-ten bị dời,
   như JNAV ở Hà Nội tháng 10/2025). Vị trí trạm lấy ở cuối cửa sổ.

### 3.2 Ghép InSAR với GNSS (`validation/gnss/compare.py`)

- InSAR: chuỗi trung vị của các điểm trong bán kính `radius_m` quanh ăng-ten, ít nhất `min_points` điểm; giữ lại độ
  tản mát của chúng.
- GNSS: ENU lấy trung bình trong ±`window_days` quanh mỗi ngày chụp InSAR.
- Véc-tơ đơn vị LOS **l** = trung vị của (`los_e`, `los_n`, `los_u`) các điểm, đã chuẩn hoá. Hai cách chiếu:
  - `full`: d = e·l_e + n·l_n + u·l_u (gồm cả chuyển động mảng kiến tạo trong IGS20, ví dụ ~31 mm/năm về phía đông ở
    Hà Nội);
  - `vertical` (mặc định): d = u·l_u (chuyển dịch ngang coi là đồng đều trên cảnh, nên đã nằm trong tham chiếu InSAR).
- Cần ít nhất `min_epochs` ngày chung; hai chuỗi được đưa về cùng mốc 0 (trung bình trên các ngày chung).
- Thống kê cho từng cách chiếu: tốc độ OLS và sai số chuẩn, `rate_diff_mm_yr` = v_GNSS − v_InSAR, `rmse_mm`,
  `rmse_detrended_mm` (sau khi bỏ xu hướng tuyến tính của hiệu: mức khớp về hình dạng), `corr` (giữa hai chuỗi sau khi bỏ xu hướng tuyến tính riêng của từng chuỗi; schema 2,
  2026-11-05), `corr_with_trend` (giá trị cũ, bị xu hướng chi phối); tốc độ MIDAS chiếu
  theo cùng cách và `rate_diff_midas_mm_yr`.

### 3.3 Hiệu chỉnh (`calibration`)

Với Δv_i là hiệu tốc độ ở trạm i (`window`: trên khoảng thời gian InSAR; `midas`: so với tốc độ MIDAS):

- `offset`: Δv = trung bình_i Δv_i, cộng vào mọi điểm dưới dạng Δv·t;
- `plane`: Δv = a + b·x + c·y (x, y tính bằng km từ tâm sản phẩm), cần ≥ 3 trạm (nếu không, quay về `offset` kèm
  cảnh báo);
- `epoch`: c(t) = trung vị theo các trạm của hiệu hai chuỗi (thành phần chung theo từng ngày, nội suy qua các ngày
  thiếu, bằng 0 ở ngày đầu); với một trạm, nhiễu hằng ngày của trạm đi vào mọi điểm (cảnh báo).

**Kiểm tra chéo bỏ-một** (≥ 2 trạm): mỗi trạm được dự đoán bằng hiệu chỉnh tính khi bỏ chính nó ra; báo cáo
`loo_rms_before_mm_yr` và `loo_rms_after_mm_yr`. Với một trạm: cảnh báo rằng không kiểm tra được.

Hiệu chỉnh cộng vào một chuỗi là `correction(calib, dates, lon, lat)`: tốc độ·t (kèm các hệ số mặt phẳng), hoặc chuỗi
theo ngày.

### 3.4 Gắn vào một sản phẩm khác (`validation/tie.py`)

Với sản phẩm đích không có trạm:

1. **Khoảng thời gian:** tốc độ của sản phẩm tham chiếu được tính trên các lần chụp của nó, từ lần cuối cùng ≤ ngày
   đầu của sản phẩm đích tới lần đầu tiên ≥ ngày cuối của nó (cảnh báo khi không phủ đủ; tối thiểu 3 ngày).
2. Hiệu chỉnh riêng của sản phẩm tham chiếu (`active_calibration`: GNSS, nếu không thì phép gắn của chính nó) được
   cộng trước.
3. **LOS:** cả hai tốc độ đổi sang thẳng đứng, v / `los_u`.
4. **Không gian:** trung vị trên ô `cell_m` (CLI `--cell`, mặc định 100 m; web 20–1000 m), giữ các ô có ≥
   `min_points` = 3 điểm của mỗi sản phẩm; cần ≥ 10 ô chung.
5. Hiệu chỉnh: Δv_đứng = trung vị theo ô của (tham chiếu − đích); hiệu chỉnh theo LOS = Δv_đứng × trung vị `los_u`
   của sản phẩm đích. Độ tản mát = 1,4826·MAD. Hệ số khuếch đại (độ dốc đích theo tham chiếu) chỉ báo cáo, không
   hiệu chỉnh.
6. Cảnh báo: tương quan < 0,5 ("the tie is uncertain"); |hệ số − 1| > 0,25.

Kết quả có cùng các khoá với một hiệu chỉnh GNSS (`kind = "offset"`, `source = "tie"`). Hiệu chỉnh **được áp dụng**
cho một sản phẩm là hiệu chỉnh GNSS của nó nếu có, nếu không thì là phép gắn.

### 3.5 Tham số (`[validation.gnss]`)

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `source` | `ngl` | chỉ có NGL |
| `radius_m` | 100 | các điểm InSAR quanh ăng-ten (web: 50, 100, 200, 300) |
| `min_points` | 5 | số điểm cần trong bán kính |
| `window_days` | 3 | số ngày GNSS lấy trung bình quanh mỗi ngày chụp (±) |
| `min_epochs` | 6 | số ngày chung cần có |
| `los_mode` | `vertical` | `vertical` \| `full` |
| `calibration` | `offset` | `offset` \| `plane` \| `epoch` |
| `gnss_rate` | `window` | `window` \| `midas` |
| `series` | `raw` | `raw` (`disp_mm`, dùng để kiểm định) \| `scn` (`disp_scn_mm`: đã bỏ nhiễu tương quan không gian, kể cả ramp toàn cảnh của từng ngày chụp; giữ nguyên xu thế — chỉ để chẩn đoán: với chuỗi ngắn nó gần như chỉ còn xu thế nên phép kiểm hình dạng thành vòng lặp). Sản phẩm không có `disp_scn_mm` thì quay về `raw` kèm cảnh báo. Cột đã dùng ghi ở `comparison.json` → `insar_column` |
| `stations`, `exclude` | tất cả, không | mã trạm (chữ hoa) |

Khoá lạ bị từ chối (`n_rovers` từ cấu hình cũ được bỏ qua).

## 4. Các bước triển khai

1. **So sánh.**
   ```
   geoeyes gnss <project> [--product ID] [--track ID] [--set radius_m=200] [--set calibration=plane]
   ```
   Web: dự án → **Validation** → khung GNSS → chọn sản phẩm và tham số → **Compare with GNSS** (chạy nền). Thời gian:
   vài giây đến một phút khi tệp NGL đã có trong bộ đệm (lần đầu tải mỗi trạm một tệp `tenv3`). Ghi ra
   `analyses/gnss/<product>/comparison.json`, `series.npz`, `manifest.json`. CLI in các trạm đã so và tốc độ hiệu
   chỉnh.
2. **Đọc** bảng trạm (tốc độ, RMSE, RMSE đã bỏ xu hướng, tương quan, so với MIDAS), biểu đồ từng trạm (trung vị
   InSAR, GNSS tại các ngày chụp, GNSS hằng ngày; `vertical` / `full`), dòng hiệu chỉnh và kết quả bỏ-một.
3. **Gắn sản phẩm không có trạm (tuỳ chọn).**
   ```
   geoeyes tie <project> --reference <ref_project>/<ref_product_id> [--product ID] [--cell 100]
   ```
   Web: Validation → khung Calibration → **Tie to another product** → chọn sản phẩm tham chiếu → **Tie** (vài giây).
   Ghi ra `analyses/tie/<product>/tie.json` và manifest. **Remove the tie** xoá phép gắn.
4. **Dùng hiệu chỉnh.**
   - bản đồ: Explorer → lớp → công tắc **Calibrated** (bộ đệm lớp `<product_id>@cal`, dựng lại khi hiệu chỉnh thay
     đổi; tệp sản phẩm giữ nguyên);
   - tệp: khung Calibration → **Write the calibrated GeoPackage + CSV** →
     `exports/<product>/<product>_calibrated.gpkg`, `.csv`, `.qml`;
   - nguy cơ: `[postprocess.hazard] gnss_tie = true` hoặc ô "GNSS tie", rồi `geoeyes hazard`.

## 5. Kết quả và cách đọc

| Tệp / trường | Ý nghĩa |
|---|---|
| `comparison.json` → `stations[]` | từng trạm: `used`, `reason` (lý do không dùng), `n_points`, `median_distance_m`, `segments`, `jumps`, `outliers`, `los`, `gnss_rate_enu_mm_yr`, thống kê `full` / `vertical`, `midas` |
| `…vertical.rate_diff_mm_yr` | hiệu tốc độ GNSS − InSAR theo LOS (mm/năm): sai số tham chiếu tại trạm đó |
| `…rmse_detrended_mm`, `corr` | mức khớp về hình dạng; 5–8 mm là mức thấy được giữa trung vị PS Sentinel-1 và GNSS hằng ngày (ghi chú nghiên cứu §7.1) |
| `calibration` | `kind`, `los_mode`, `gnss_rate`, `stations`, `rate_coef`, `rate_offset_mm_yr`, `epoch_mm`, `leave_one_out`, `loo_rms_before/after_mm_yr`, `centre`, `lat0` |
| `warnings` | không có trạm, chỉ một trạm, quay về `offset`, thiếu MIDAS |
| `series.npz` | từng trạm: `insar`, `spread`, `gnss_full`, `gnss_vertical`, `day`, `enu_mm` |
| `tie.json` | `window`, `reference_dates`, `target_period`, `n_cells`, `corr`, `slope`, `intercept_mm_yr`, `spread_mm_yr`, `median_reference_mm_yr`, `median_target_mm_yr`, `calibration` (`rate_offset_mm_yr` theo LOS, `vertical_offset_mm_yr`, `reference_calibration`) |
| tệp xuất đã hiệu chỉnh | `vel_los_cal_mm_yr` cạnh `vel_los_mm_yr` (độ dốc bình phương tối thiểu của chuỗi đã hiệu chỉnh), `cal_source`, các cột `DYYYYMMDD` đã hiệu chỉnh |

Dấu: LOS dương khi hướng về vệ tinh. Hiệu chỉnh `offset` bằng tốc độ theo LOS của chính điểm tham chiếu của sản phẩm
như GNSS nhìn thấy: âm khi tham chiếu đang lún (Mexico City S1, trung bình cảnh: −126,4 mm/năm, ghi chú nghiên cứu
§7.3).

## 6. Kiểm tra chất lượng

- Có ít nhất một trạm `used`; hiểu rõ lý do của các trạm còn lại.
- Khớp về hình dạng: `rmse_detrended_mm` gần mức nhiễu InSAR và `corr` > 0,8 ở nơi chuyển dịch vượt nhiễu (tiêu chí
  G1). Mexico City MMX1: 5,3 mm, 0,96; Hà Nội HUMG/JNAV: 0,27 / −0,33 (không có tín hiệu chung).
- Bỏ-một: `loo_rms_after_mm_yr` < `loo_rms_before_mm_yr`, với ≥ 3 trạm (tiêu chí G2). Hà Nội, `offset`: 12,0 → 9,8;
  với MIDAS 4,1 → 8,1 (kém hơn, không nên gắn). TP.HCM 2017–2019: 5,1 → 6,3 (kém hơn).
- Một trạm: hợp lý nhưng chưa kiểm chứng; phải ghi rõ ở mọi nơi dùng sản phẩm đã gắn.
- `vertical` so với `full`: chênh lớn là do chuyển động mảng kiến tạo (Hà Nội: +16–19 mm/năm theo LOS), không phải
  sai số InSAR.
- Phép gắn: `corr` ≥ 0,5, hệ số khuếch đại gần 1, `spread_mm_yr` báo cáo cùng hiệu chỉnh (Capella → S1 Mexico:
  1 731 ô, 0,888, hệ số 1,07, −109,0 mm/năm theo LOS, ±49,6 mm/năm; ghi chú nghiên cứu §7.3).
- Sau khi chạy phân vùng nguy cơ với `gnss_tie`, tốc độ nằm trong dải đã công bố (Mexico City: tới ~40 cm/năm).

## 7. Hạn chế và lỗi thường gặp

- **Mốc trạm khác điểm tán xạ.** Trung vị PS trong 100 m có thể không chuyển dịch giống ăng-ten (mái nhà so với mặt
  đất).
- **Sigma GNSS quá lạc quan.** Sai số tốc độ theo giả định nhiễu trắng; v1 chưa mô hình nhiễu flicker hay thành phần
  năm. Tốc độ tính trên một năm phụ thuộc pha của tín hiệu mùa.
- **Gắn theo phương đứng** giả định chuyển dịch ngang cục bộ không đáng kể; giả định này sai gần mép các phễu lún.
- **Nối đoạn** giả định hai mốc trạm chuyển dịch như nhau.
- **`midas`** sai ở nơi chuyển dịch đã thay đổi (MMX1: thành phần đứng −364 mm/năm năm 2024 so với −265 dài hạn).
- **`epoch`** với ít trạm đưa nhiễu GNSS hằng ngày vào mọi điểm.
- **Chỉ tìm trạm bên trong phạm vi sản phẩm** (không có lề): trạm nằm ngay bên ngoài không được dùng.
- **`gnss_tie` của phân vùng nguy cơ chỉ đọc kết quả so sánh GNSS** của sản phẩm (`analyses/gnss/…`), không đọc phép
  gắn: sản phẩm chỉ được hiệu chỉnh bằng `geoeyes tie` không dùng được `gnss_tie` (lệnh dừng với "no GNSS
  calibration").
- Hiệu chỉnh là thuộc tính của một sản phẩm và tham chiếu của nó; chạy lại khi có phiên bản sản phẩm mới.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- **Trước tiên** liệt kê các trạm NGL hoạt động trong khoảng thời gian cần (ngày đầu/cuối trong DataHoldings). Nhiều
  trạm ở Việt Nam đã ngừng trong 2016–2021 (Hà Nội: chỉ HUMG, JNAV còn gần đây; TP.HCM: không có trạm nào cho
  2025–2026).
- **Không có trạm:** gắn vào một sản phẩm đã hiệu chỉnh GNSS trên cùng vùng và cùng thời kỳ (`geoeyes tie`), hoặc dùng
  `reference_bbox` trên nền ổn định khi phân vùng nguy cơ; đặt gương phản xạ góc cạnh một trạm mới
  ([corner-reflector.md](corner-reflector.md)).
- **Mạng dày (≥ 3 trạm quanh cảnh):** thử `plane`; chỉ dùng `epoch` khi có 3–5 trạm phân bố đều.
- **Chuỗi dài (≥ 2 năm):** so `window` với `midas`.
- **Giữ nguyên được:** phương pháp (chiếu đứng, xử lý đoạn, tốc độ theo cửa sổ, bỏ-một) và mức sai số (5–8 mm mỗi
  ngày chụp). **Không chuyển được:** hệ số hiệu chỉnh giữa các thành phố.
- **Vệ tinh:** không cần đổi gì; phép chiếu dùng `los_e/n/u` của chính sản phẩm (Capella nhìn trái và S1 nhìn phải đã
  được so theo cách này ở ghi chú nghiên cứu §7.3).

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/validation/gnss/ngl.py`, `src/geoeyes/validation/gnss/compare.py`,
  `src/geoeyes/validation/tie.py`, `src/geoeyes/api/gnss.py`, `src/geoeyes/api/app.py` (`/tie`,
  `/export-calibrated`), `src/geoeyes/api/points.py`, `src/geoeyes/export/vector.py`, `src/geoeyes/hazard/assess.py`
  (`gnss_tie`), `webapp/src/components/Gnss.tsx`, `webapp/src/components/Calibration.tsx`; test
  `tests/unit/validation/test_gnss.py`, `tests/unit/validation/test_tie.py`.
- Nghiên cứu: [../research/gnss-insar-calibration.md](../research/gnss-insar-calibration.md) (phương pháp §4, tham số
  §5, kết quả §6–7), script [../research/code/gnss_transfer.py](../research/code/gnss_transfer.py) (thử chuyển giao
  §7.1) và [../research/code/gnss_g7.py](../research/code/gnss_g7.py) (TP.HCM 2017–2019, §7.2).
- Skill: [hazard-zoning.md](hazard-zoning.md), [corner-reflector.md](corner-reflector.md),
  [atmosphere.md](atmosphere.md), [ionosphere.md](ionosphere.md).
- Bài báo (DOI ở §11 của ghi chú nghiên cứu): Blewitt, Hammond & Kreemer (2018) *Eos* 99; Blewitt et al. (2016)
  MIDAS, *JGR* 121; Neely et al. (2020) GInSAR, *IEEE TGRS* 58; Williams et al. (2004) *JGR* 109; Blewitt & Lavallée
  (2002) *JGR* 107; Wright et al. (2004) *GRL* 31; Farolfi et al. (2019) *EuJRS* 52.
