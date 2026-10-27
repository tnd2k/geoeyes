# Tầng điện ly: nhận diện và xử lý

Hướng dẫn này dành cho người xử lý dữ liệu InSAR bằng GeoEyes. Nó giúp nhận ra một mặt nghiêng hay một vệt bất
thường trên bản đồ vận tốc có phải do tầng điện ly không, và nếu đúng thì xử lý thế nào. Các con số minh hoạ lấy từ
Hà Nội, Sentinel-1 quỹ đạo lên 128 và quỹ đạo xuống 91, 2025-10 → 2026-10
([two-geometries-and-soft-soil.md §4.2](../research/two-geometries-and-soft-soil.md)).

## Mục lục

1. [Khi nào phải nghĩ tới tầng điện ly](#1-khi-nào-phải-nghĩ-tới-tầng-điện-ly)
2. [Dấu hiệu và cách phân biệt](#2-dấu-hiệu-và-cách-phân-biệt)
3. [Chẩn đoán từng bước](#3-chẩn-đoán-từng-bước)
4. [Hiệu chỉnh trong GeoEyes](#4-hiệu-chỉnh-trong-geoeyes)
5. [Tiêu chí chấp nhận sản phẩm](#5-tiêu-chí-chấp-nhận-sản-phẩm)
6. [Trường hợp Hà Nội](#6-trường-hợp-hà-nội)
7. [Giới hạn](#7-giới-hạn)

## 1. Khi nào phải nghĩ tới tầng điện ly

Pha tầng điện ly tỉ lệ với tổng điện tử (TEC) và tỉ lệ nghịch với tần số. Nguy cơ cao khi có từ hai yếu tố trở lên:

| Yếu tố | Nguy cơ cao | Nguy cơ thấp |
|---|---|---|
| Vĩ độ từ | 5–25° (hai đỉnh dị thường ion hoá xích đạo, EIA), vùng cực | vĩ độ trung bình |
| Giờ chụp (giờ địa phương) | chiều, chạng vạng, đầu đêm (Sentinel-1 quỹ đạo lên ≈ 18:00) | rạng sáng (quỹ đạo xuống ≈ 06:00) |
| Chu kỳ mặt trời | gần cực đại (chu kỳ 25: 2024–2026) | gần cực tiểu |
| Băng tần | L (ALOS-2, NISAR): pha gấp ~4 lần C, quy ra mm gấp ~18 lần | C (Sentinel-1), X |
| Kích thước vùng | > 10 km, chuỗi dài theo phương bay | vài km |

Hà Nội (21° B, vĩ độ từ ≈ 11–14°) chụp lúc 18:06 gần cực đại chu kỳ 25 là trường hợp xấu nhất có thể gặp với
băng C. GIM (CODE IONEX) cho 39–111 TECU lúc quỹ đạo lên đi qua, so với 8–19 TECU lúc quỹ đạo xuống.

## 2. Dấu hiệu và cách phân biệt

Một mặt nghiêng hay một vệt trên bản đồ vận tốc có thể đến từ nhiều nguồn. Bảng sau giúp loại trừ:

| Dấu hiệu | Tầng điện ly | Tầng đối lưu | Quỹ đạo | Bậc giữa dải con | Chuyển dịch thật |
|---|---|---|---|---|---|
| Hình dạng | mặt nghiêng rộng, thường theo **phương bay**; dải sóng dài 10–100 km | mảng 1–10 km, hoặc tỉ lệ với độ cao | mặt phẳng | **đường thẳng** dọc phương bay, đúng ở cột nối IW1/IW2/IW3 | theo địa chất, công trình |
| Có ở cả hai quỹ đạo | không (chỉ quỹ đạo chụp chiều/tối) | có, mạnh hơn ở quỹ đạo chiều | không nhất thiết | chỉ quỹ đạo có chỗ nối trong vùng | **có**, khớp phép chiếu hướng nhìn |
| Từng ngày | đổi dấu, đổi độ lớn | ngẫu nhiên, mạnh vào mùa mưa | hằng số theo ngày | **hai mức**: ≈ 0 hoặc một hằng số (−2,2 rad ở Hà Nội) | tích luỹ đều |
| Tán sắc (tách phổ thấy) | **có** | không | không | không | không |
| ESD | dịch chuyển phương vị tương quan với mặt nghiêng phương bay | không | không | hiệu ESD giữa hai dải con lệch (+0,012 dòng) | không |
| Sai số trong burst TOPS | gradient mạnh gây vệt ngang ở biên burst | không | không | không | không |

Hai phép thử quyết định:
1. **So hai quỹ đạo.** Chuyển dịch thẳng đứng xuất hiện gần như nhau ở cả hai (l_u ≈ 0,77). Chuyển dịch Bắc–Nam
   gần như không vào hướng nhìn (hệ số bắc ≈ 0,1). Một mặt nghiêng Bắc–Nam chỉ có ở một quỹ đạo vì vậy **không thể
   là chuyển dịch**.
2. **Tách phổ.** Chỉ tầng điện ly là tán sắc. Sau khi tách phổ, phần còn lại không phải tầng điện ly, trừ khi ước
   lượng sai (xem §5).

## 3. Chẩn đoán từng bước

1. **Mặt phẳng vận tốc của từng quỹ đạo.** Phép tách thành phần (`[postprocess.decompose]`) in mặt nghiêng của mỗi
   sản phẩm và cảnh báo khi một bên lớn gấp đôi bên kia (`ramp_warning_mm_yr`). Ở Hà Nội ban đầu: quỹ đạo lên 26,9
   mm/năm, quỹ đạo xuống 3,9 trên vùng chung.
2. **Mặt phẳng của từng giao thoa đồ** (tệp `ps_runs/<track>/state.h5`, `phase/unwrapped` và các thành phần
   `aps`, `scla`, `scn`). Nếu mặt nghiêng đã có trong pha mở, không do ERA5 hay sai số DEM, thì nó nằm trong ảnh.
3. **Giờ chụp và TEC.** `sensing_mid_utc` trong stack, đổi sang giờ địa phương; mức TEC từ GIM. GIM (ô 2,5° × 5°)
   chỉ cho mức, không cho gradient trên 15 km.
4. **ESD theo ngày** (`esd_shift` trong stack). Tương quan với mặt nghiêng phương bay của từng ngày (Hà Nội, trước
   hiệu chỉnh: r = −0,56, p = 0,003 ở quỹ đạo lên; +0,19, p = 0,37 ở quỹ đạo xuống).
5. **Đường thẳng dọc phương bay?** So cột của nó với `subswath_columns` của stack. Nếu trùng chỗ nối, đó là bậc
   giữa dải con (§4.3), không phải tầng điện ly và càng không phải đứt gãy.

## 4. Hiệu chỉnh trong GeoEyes

### 4.1 Bật tách phổ

```toml
[stack]
ionosphere = "split_spectrum"      # none (mặc định) | split_spectrum
ionosphere_model = "local"         # local (mặc định) | plane | quadratic | smooth
ionosphere_smooth_m = 10000        # bán kính trọng số Gauss quanh vùng cắt
```

Băng tần được chia làm ba; hai băng con thấp và cao cho hai giao thoa đồ, từ đó tách phần tán sắc. Ước lượng làm
trên **toàn bộ burst** (ô thô 32 × 122 điểm ảnh, khoảng 45 × 175 km), không chỉ vùng cắt, rồi đánh giá lại trên vùng
cắt.

Chọn mô hình:
- `local` (nên dùng): mặt phẳng quanh vùng cắt, trọng số Gauss `ionosphere_smooth_m`. Tầng điện ly lúc chạng vạng có
  cấu trúc 10–30 km mà một mặt trên toàn burst làm mờ mất, còn riêng vùng cắt (~15 km) thì quá nhiễu.
- `plane` / `quadratic`: một mặt trên toàn burst, khi vùng cắt lớn hoặc tầng điện ly yên tĩnh.
- `smooth`: mặt Gauss, khi cần giữ cấu trúc nhỏ và dữ liệu đủ kết hợp.

Thay đổi các khoá này buộc dựng lại stack (khoá `ionosphere_key`). Chạy:
`geoeyes run <project> --track <track> --force build_stack`.

### 4.2 Đọc nhật ký

Mỗi ngày một dòng:

```
2025-10-04: ionosphere gradient (az, rg) [-0.1342, 0.0014] ± [0.0161, 0.0142] rad/km at the crop, 3898 cells over [45.6, 174.9] km
```

- Gradient tính bằng rad/km ở tần số trung tâm; nhân 4,41 để ra mm/km theo hướng nhìn (băng C).
- Sai số ± là sai số hình thức; cỡ 0,015 rad/km (0,07 mm/km) là bình thường.
- `noise_rad` trong `ionosphere_per_date` của stack cỡ 10 rad mỗi ô là bình thường: tách phổ khuếch đại nhiễu pha
  khoảng 95 lần. Bù lại có hàng nghìn ô.
- Nếu số ô `kept` dưới vài trăm, hoặc sai số ± vượt 0,05 rad/km, ngày đó ước lượng yếu: xem độ kết hợp.

Giá trị theo ngày được lưu trong stack: biến `iono` (pha đã khử, theo ngày) và thuộc tính `ionosphere_per_date`.

### 4.3 Bậc giữa các dải con

Khi vùng cắt trùm hai dải con, GeoEyes tự đo bậc pha qua từng chỗ nối, từng ngày, và khử trước khi ghép. Dải con
rộng nhất làm mốc. Bậc này không phụ thuộc tần số, nên nó được trừ khỏi cả băng con thấp trước khi tách phổ: nếu
không, khoảng một nửa của nó (a ≈ 0,5) sẽ lọt vào ước lượng tầng điện ly.

```
2026-07-02 seam IW3: interferogram phase step -2.298 rad (consistency 0.96, 32 blocks) removed
```

- Độ nhất quán dưới 0,3 hoặc ít hơn 8 khối: không đo được, bậc được giữ nguyên và có cảnh báo.
- Giá trị theo ngày nằm trong thuộc tính `subswath_phase_offsets` của stack.
- Bậc có hai mức (≈ 0 hoặc một hằng số) và trùng với các ngày ESD hai dải con lệch nhau. Nguyên nhân gốc chưa rõ.

### 4.4 Khi tách phổ chưa đủ: khử mặt phẳng

`[postprocess.decompose] deramp = "plane"` khử một mặt phẳng khỏi vận tốc của mỗi sản phẩm trước khi tách thành
phần. Nó khử cả mọi độ nghiêng thật của vùng. Chỉ dùng khi §5 không đạt, và ghi rõ trong báo cáo.

## 5. Tiêu chí chấp nhận sản phẩm

So với quỹ đạo kia (hoặc GNSS) trên vùng chung:

| Tiêu chí | Đạt | Cần xem lại |
|---|---|---|
| Hiệu gradient vận tốc giữa hai quỹ đạo (mỗi trục) | < 0,3 mm/năm/km | > 0,5 |
| Bậc vận tốc qua chỗ nối dải con | < 2 mm/năm | > 4 |
| Tách E–U không khử phẳng: tương quan Đông–Đứng | \|r\| < 0,3 | \|r\| > 0,5 |
| Tách E–U: tỉ lệ ô có chuyển dịch ngang "đáng kể" | < 10 % | > 15 % |
| Tương quan (mặt nghiêng còn sót, gradient tầng điện ly đã khử) theo ngày | \|r\| < 0,3 | \|r\| > 0,5, tức thang sai |

Nếu chỉ tiêu chí cuối đạt mà các tiêu chí khác chưa, phần còn sót **không phải tầng điện ly**. Xem tầng đối lưu, mở
pha, các ngày bất thường.

## 6. Trường hợp Hà Nội

| Sản phẩm quỹ đạo lên 128 | Bậc chỗ nối | gx / gy (mm/năm/km) | Tách E–U không khử: ngang / r |
|---|---|---|---|
| v1, không hiệu chỉnh | +8,0 | +0,75 / −1,50 | 41 % / −0,80 |
| v3, tách phổ | +9,6 | +0,22 / −0,79 | |
| v4, + cân pha chỗ nối | +0,9 | −0,58 / −0,92 | 17,1 % / −0,59 |
| v6, + trừ bậc khỏi băng con | +1,4 | −0,49 / −0,77 | 11,5 % / −0,51 |
| quỹ đạo xuống 91 (đối chứng) | — | −0,02 / −0,20 | |

Tách phổ khử được một tín hiệu thật: gradient phương bay đã khử dao động 0,49 mm/km giữa các ngày, với xu thế 0,81
mm/km/năm (khoảng 11 mm/năm trên 14 km).

**Phần còn sót sau v6 không phải tầng điện ly.** Theo từng ngày:
- Mặt nghiêng phương bay còn sót gần như không tương quan với gradient tầng điện ly đã khử (r = 0,18), nên không phải
  khử thiếu theo tỉ lệ.
- Nó dao động 0,64 mm/km giữa các ngày, gấp gần 10 lần sai số hình thức của ước lượng tầng điện ly (0,07 mm/km).
- Mặt nghiêng theo cự ly còn sót lớn nhất vào mùa hè 2026 (+2,4 … +3,6 và −3,0 mm/km ở 07-14, 08-19, 08-31). Quỹ
  đạo xuống cùng mùa chỉ −0,3 … +0,9.

Phần còn sót này không tán sắc, nên nhiều khả năng là **tầng đối lưu**: đối lưu chiều tối mùa mưa ở Hà Nội mà ERA5
(0,25°, mỗi giờ) không bắt được. Một phần có thể do mở pha ở các ngày có bậc.

Kết luận cho Hà Nội: dùng v6, giữ `deramp = "plane"` khi tách thành phần, và không diễn giải gradient Bắc–Nam của
quỹ đạo lên khi chỉ có một quỹ đạo.

## 7. Giới hạn

- Tách phổ trên băng C rất nhiễu (khuếch đại ~95 lần); chỉ ước lượng được dạng trơn (mặt phẳng cục bộ), không ước
  lượng được cấu trúc dưới vài km như dải bất ổn định sau hoàng hôn (plasma bubble).
- Mô hình `local` giả định tầng điện ly gần tuyến tính trong ~10 km quanh vùng cắt.
- Pha hình học phải được tính lại chính xác trước khi tách. Khoảng một nửa sai số của nó lọt vào ước lượng.
- Nhấp nháy tầng điện ly (scintillation) làm mất kết hợp; tách phổ không sửa được.
- Bậc giữa các dải con chỉ đo được khi hai bên chỗ nối đủ kết hợp (đô thị). Ở vùng nông nghiệp, ngập nước có thể
  không đo được.
