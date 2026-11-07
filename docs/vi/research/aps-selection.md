# Chọn có trừ pha khí quyển (APS) hay không

Trạng thái (07/11/2026): đã viết kế hoạch; **A0 xong cho `hcm_d18`** (§5.1), các trường hợp khác chưa làm; A1–A4
chưa bắt đầu. Yêu cầu của chủ dự án: "một cách tự động để quyết định có trừ APS hay không". Tài liệu liên quan:
[ramp-selection.md](ramp-selection.md) (cùng ý tưởng cho ramp), memory `hcm-d18-sarproz`.

## Mục lục

1. [Câu hỏi](#1-câu-hỏi)
2. [Bối cảnh](#2-bối-cảnh)
3. [Phương pháp: `subtr_tropo = "auto"`](#3-phương-pháp-subtr_tropo--auto)
4. [Các bước và điểm duyệt](#4-các-bước-và-điểm-duyệt)
5. [Kết quả](#5-kết-quả)
6. [Hạn chế](#6-hạn-chế)
7. [Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

## 1. Câu hỏi

`[ps] subtr_tropo = "y"` (mặc định) trừ, cho từng giao thoa đồ, APS tương quan địa hình `pha = a·h + b`
(`aps.py::linear_aps`, `a_l` của StaMPS TRAIN) hoặc APS từ mô hình thời tiết (`[atmosphere]`). APS bị trừ hai lần:
trước khi giải chập lượt 2 và khỏi vận tốc (`velocity.py::corrected_phase`), nên đầu ra là "v-dao" của StaMPS.

Ở `hcm_d18` (TP.HCM, bằng phẳng), kết quả khớp SARPROZ hơn khi **không** trừ ("v-do": r 0,89 so với 0,84; NMAD vùng
ổn định 1,0 so với 1,7 mm/năm; mất độ lệch +1,8 mm/năm và mặt nghiêng ±5 mm/năm). Ở vùng núi thì vẫn cần hiệu chỉnh
này (khí quyển phân tầng cỡ cm trên mỗi km độ cao).

Câu hỏi: **engine có tự quyết định được từ dữ liệu rằng APS có giúp hay không, và nếu không giúp thì không để nó làm
đổi vận tốc?**

## 2. Bối cảnh

### 2.1 APS nên và không nên chứa gì

| Thành phần | Không gian | Thời gian | Có được làm đổi vận tốc? |
|---|---|---|---|
| Khí quyển phân tầng (a·h) | theo địa hình | mùa + ngẫu nhiên | không (trung bình nhiều năm ≈ 0) |
| Khí quyển rối | cỡ km, ngẫu nhiên | ngẫu nhiên theo ngày | không |
| Biến dạng tương quan với độ cao | theo lớp phủ (đất san lấp, khu mới thấp; nội thành cũ cao) | **đều đặn** | — đây là tín hiệu |

APS thật không có xu hướng nhiều năm. Nếu chuỗi APS của một điểm có xu hướng, phép hồi quy đã nuốt phần biến dạng
tình cờ tương quan với độ cao.

### 2.2 Engine hiện làm gì

- `linear_aps`: đường thẳng a·h + b có trọng số cho từng giao thoa đồ trên mọi PS (hoặc `aps_non_defo`), dùng pha
  giải chập lượt 1, còn nguyên biến dạng.
- APS thời tiết (`[atmosphere] method`): `choose_aps` chỉ giữ cho ngày nào nó giảm phương sai phần dư nhiều hơn APS
  tuyến tính: chọn giữa hai mô hình theo từng ngày, không bao giờ chọn "không trừ".
- Bước 8 SCN khử phần tương quan không gian, không tương quan thời gian khỏi chuỗi (`disp_scn_mm`), khớp tuyến tính
  cục bộ nên giữ xu hướng: làm sạch chuỗi nhưng không đổi vận tốc (−0,2 mm/năm ở các điểm lún nhanh của `hcm_d18`).
- "step 7 HP": ±0,2 mm/năm ở `hcm_d18`; không phải nguyên nhân.

### 2.3 Các công cụ khác làm gì

- StaMPS / TRAIN (Bekaert và cs. 2015): người dùng chọn cách hiệu chỉnh (`a_l`, `a_e`, `a_p`, …) và đánh giá qua đồ
  thị pha–độ cao; `a_p` lọc dải để ước lượng tỷ số pha–độ cao ở bước sóng ngắn, tránh biến dạng.
- MintPy (Yunjun và cs. 2019): mô hình thời tiết hoặc "height_correlation" trên chuỗi thời gian, có thể dùng mặt nạ;
  người dùng chọn. Người dùng GACOS thường đánh giá bằng mức giảm phương sai (Yu và cs. 2018).
- SARPROZ: APS là phần dư thông thấp không gian, thông cao thời gian sau mô hình chuyển động (giống SCN): vận tốc
  thực chất là v-do.

## 3. Phương pháp: `subtr_tropo = "auto"`

Giá trị mới; `"y"` và `"n"` giữ nguyên từng bit.

### 3.1 Kiểm tra 1 — địa hình (rẻ)

Độ dốc địa hình = p5–p95 của DEM trong stack (`geometry_hgt`, địa hình trần, không nhà cửa) trên vùng có PS. Thay đổi
trễ phân tầng giữa hai ngày tối đa ≈ k·Δh với k ≈ 10 mm/km (rộng rãi). Nếu k·độ dốc nhỏ hơn mức nhiễu (1 mm) thì
không đo được hệ số a·h: **tắt APS** ("địa hình 11 m").

Ngưỡng ứng viên: dưới 100 m → tắt. Tinh chỉnh ở A0/A1.

### 3.2 Kiểm tra 2 — rò rỉ vào vận tốc

Với APS ước lượng như hiện nay:

1. v_aps = vận tốc tuyến tính của chuỗi APS tại mỗi PS (trừ trung vị toàn cảnh: phần đều được điểm tham chiếu khử);
2. coi là rò rỉ khi độ trải p5–p95 của v_aps vượt L mm/năm **và** |corr(v_aps, v_def)| > c, trong đó v_def là vận
   tốc của (unwrapped − SCLA) không trừ APS.

Ứng viên: L = 1 mm/năm, c = 0,1.

### 3.3 Kiểm tra 3 — APS có giúp gì không

Phần dư = pha giải chập lượt 1 − (c + v·t + K·B⊥) của từng PS (`aps._detrend_parts`, như `choose_aps`). Với mỗi giao
thoa đồ, tính mức giảm phương sai nhờ APS. Xu hướng đã bị trừ trước, nên rò rỉ không thể được tính là lợi ích. APS
hữu ích khi mức giảm trung vị > 5 % (ứng viên).

### 3.4 Quyết định

| Địa hình | Có giúp (3.3) | Rò rỉ (3.2) | Hành động |
|---|---|---|---|
| thấp | — | — | tắt |
| đủ | không | — | tắt |
| đủ | có | không | bật (như hiện nay) |
| đủ | có | có | bật, **khử xu hướng APS theo từng PS** (làm sạch chuỗi, giữ vận tốc) — hoặc cách ước lượng ở A2 |

Quyết định, các con số và quy tắc được ghi vào `resolved` (như `max_topo_err = "auto"`) và vào báo cáo.

### 3.5 Ước lượng APS không dính biến dạng (A2)

Khớp a·h trên pha lượt 1 đã trừ chuyển động lượt 1 (v·t + K·B⊥ từng PS), có thể lọc dải (`a_p` của TRAIN), để phép
hồi quy không lấy được phần đều đặn. So với cách khử xu hướng theo từng PS ở 3.4.

## 4. Các bước và điểm duyệt

| Bước | Nội dung | Điểm duyệt |
|---|---|---|
| A0 | Kiểm tra 1–3 trên các lần chạy đã có: `hcm_d18` (phẳng), một vùng núi (Choshui S1 PS hoặc ICEYE Tenerife), golden CSK Hà Nội (phẳng, băng X). Mỗi trường hợp: kết quả có / không APS so với tham chiếu (SARPROZ, GNSS, golden). | chủ dự án duyệt ngưỡng |
| A1 | `steps/aps_auto.py`: hàm thuần cho kiểm tra 1–3 và bảng quyết định; test đơn vị (phẳng + lún tương quan độ cao → tắt; núi + trễ phân tầng → bật; rò rỉ → khử xu hướng) | duyệt |
| A2 | Ước lượng a·h không dính biến dạng (3.5) so với khử xu hướng từng PS, trên các trường hợp A0 | duyệt |
| A3 | Nối vào engine: `subtr_tropo = "auto"` trong `params.py` / `runner.py`, `resolved`, văn bản báo cáo; parity: "y"/"n" không đổi; chạy lại các trường hợp A0 | duyệt |
| A4 | Mặc định theo preset (S1: "auto"?) sau A3 | chủ dự án quyết |

## 5. Kết quả

### 5.1 A0 — `hcm_d18` (TP.HCM, S1 desc 18, 98 ngày, lần chạy `ps_exp/new50`)

| Kiểm tra | Giá trị | Kết luận |
|---|---|---|
| 1 địa hình | p5–p95 địa hình **10,9 m**; p5–p95 độ cao PS 34,3 m (nhà cửa, sai số DEM) | tắt |
| 2 rò rỉ | v_aps p5..p95 −2,0..+2,8 mm/năm (độ trải **4,9**); corr(v_aps, v_def) **+0,25**; corr(v_aps, h) +0,28; corr(v_def, h) +0,17; xu hướng chiếm 26 % phương sai APS | rò rỉ |
| 3 lợi ích | mức giảm phương sai phần dư trung vị **+0,9 %**; > 5 % ở 19 % số giao thoa đồ; tệ hơn ở 29 % | không giúp |

Cả ba đều nói tắt. So với SARPROZ, v-do (không APS, mặt phẳng quỹ đạo khớp trên vùng ổn định phía bắc) so với v-dao:
r 0,89 / 0,84; độ lệch 0,0 / +1,9; NMAD vùng ổn định 1,0 / 1,7; độ lệch nhóm v < −15 là +2,7 / +5,3 mm/năm.

Chạy bằng engine (chạy lại bước 6–8 trên cùng bước 1–5, điểm SARPROZ trong vòng 20 m):

| Biến thể | tất cả: r / độ lệch | v < −15: r / độ lệch | v < −25: độ lệch | ổn định: độ lệch |
|---|---|---|---|---|
| `subtr_tropo = "y"` (`new50`) | 0,84 / +1,94 | 0,58 / +5,33 | +7,00 | +1,60 |
| **`subtr_tropo = "n"`** (`new50_noaps`) | **0,89 / −0,06** | **0,60 / +1,96** | **+3,91** | **−0,21** |

Bỏ APS ở cả hai lượt thì chính engine cho mức khớp như v-do mà không cần mặt phẳng quỹ đạo: APS là toàn bộ nguồn của
độ lệch và mặt nghiêng.

Còn lại: một vùng núi và CSK Hà Nội.

## 6. Hạn chế

- Ngưỡng mới rút từ một trường hợp phẳng; phép thử quan trọng là một thành phố đồi núi (Đà Lạt, Tenerife).
- k = 10 mm/km là cận rộng rãi cho trễ phân tầng khô/ướt; mùa mưa nhiệt đới có thể vượt cục bộ.
- Kiểm tra 2 cần vận tốc biến dạng không trừ APS, bản thân nó lấy từ giải chập lượt 1.
- Tham chiếu (SARPROZ) là một cách xử lý khác, không phải sự thật mặt đất; GNSS / thuỷ chuẩn mới phân xử được.

## 7. Tài liệu tham khảo

- Bekaert D. P. S., Walters R. J., Wright T. J., Hooper A. J., Parker D. J. (2015). Statistical comparison of InSAR
  tropospheric correction techniques. *Remote Sensing of Environment* 170, 40–47.
- Yu C., Li Z., Penna N. T., Crippa P. (2018). Generic atmospheric correction model for InSAR observations.
  *JGR Solid Earth* 123, 9202–9222.
- Yunjun Z., Fattahi H., Amelung F. (2019). Small baseline InSAR time series analysis: unwrapping error correction
  and noise reduction. *Computers & Geosciences* 133, 104331.
- Hooper A., Bekaert D., Spaans K., Arıkan M. (2012). Recent advances in SAR interferometry time series analysis
  for measuring crustal deformation. *Tectonophysics* 514–517, 1–13.
