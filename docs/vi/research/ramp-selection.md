# Chọn nơi cần bỏ ramp của interferogram

Trạng thái (2026-11-05): xong D0, xong D1 (`steps/ramp.py` + unit test), **phần nối D2 đã viết nháp, chưa commit,
đang chờ duyệt** (§5.3), ba giới hạn phát hiện khi duyệt đã được sửa trong code (xu thế phẳng cần vùng ổn định hoặc
tham số ghi đè, kiểm định F cho chốt theo mùa, trừ SCLA sơ bộ ở lần 2); chưa bắt đầu D3 / D4, D4 vẫn chờ kiểm parity
và lần chạy `mexico_g3`. Kế hoạch viết ngày 2026-11-04. Yêu cầu của chủ dự án: "một logic để chọn khu vực nào cần bật
`scla_deramp` và khu vực nào thì không". Ghi chú liên quan: [gnss-insar-calibration.md](gnss-insar-calibration.md)
§9.1 (G3.1d / G3.1e, nơi câu hỏi này xuất hiện).

## Mục lục

1. [Câu hỏi](#1-câu-hỏi)
2. [Bối cảnh](#2-bối-cảnh)
3. [Phương pháp: `scla_deramp = "auto"`](#3-phương-pháp-scla_deramp--auto)
4. [Các bước và điểm duyệt](#4-các-bước-và-điểm-duyệt)
5. [Kết quả](#5-kết-quả)
6. [Giới hạn](#6-giới-hạn)
7. [Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

## 1. Câu hỏi

`[ps] scla_deramp` là công tắc bật/tắt cho từng dự án, đặt theo preset của cảm biến: bật cho ICEYE và COSMO-SkyMed,
tắt cho Sentinel-1. Không lựa chọn nào đúng ở mọi nơi:

- **Bật** thì mỗi interferogram bị bỏ một mặt phẳng (hoặc mặt bậc hai), *kể cả phần tăng đều theo thời gian*. Nếu
  vùng biến dạng rộng hơn khung ảnh, như phễu lún Mexico City, phần đó là độ nghiêng thật, và bỏ nó làm sai tốc độ.
- **Tắt** thì mọi ramp được giữ lại. Ở Mexico City năm 2024 (G3.1d), ramp theo từng ngày chụp lên tới ±16 mm mỗi
  10 km. Nó lấn át chuỗi thời gian ở các trạm cách nhau 30 km, và không có trong ERA5 (tầng điện ly hoặc quỹ đạo).

Câu hỏi: **engine có thể tự quyết định, cho từng dự án và dựa trên dữ liệu, phần nào của ramp cần bỏ không? Và có
nói rõ được khi nào không quyết định được không?**

## 2. Bối cảnh

### 2.1 Engine đang làm gì

- `steps/scla.py::deramp` khớp cho mỗi interferogram một mặt phẳng có trọng số (bậc 1). Nếu mặt `x² + y² + xy + c`
  giảm RMS ít nhất 8% (`nonlinear_improvement`) thì dùng mặt đó. Đầu vào là pha unwrap lần 1 sau APS, trên mọi PS.
- Mảng ramp (`SclaResult.ph_ramp`) sau đó được trừ ở mọi bước phía sau:
  - phép khớp SCLA;
  - unwrap lần 2 (`unwrap.py`);
  - vận tốc (`velocity.py::corrected_phase`);
  - SCN (`scn_filt.py`).

  Vì vậy chỉ cần đổi *cách tính ramp*, các bước phía sau giữ nguyên.
- Bộ lọc thông cao vận tốc ("step 7 HP") đã bỏ một mặt phẳng theo từng ngày khỏi phần dư quanh chuyển động tuyến
  tính, nhưng chỉ cho `v`, không cho chuỗi thời gian.
- Bước 8 (SCN) bỏ phần phi tuyến của mọi tín hiệu bước sóng dài khỏi `disp_scn_mm` (G3.1e), nhưng giữ xu thế.

### 2.2 Ramp đến từ đâu

| Nguồn | Độ lớn trên khung 30 km | Theo thời gian |
|---|---|---|
| Sai số quỹ đạo | quỹ đạo chính xác S1 (~5 cm): vài mm; ICEYE / CSK: cm hoặc hơn | ngẫu nhiên theo lần chụp |
| Tầng điện ly | băng C: tới cm vào năm cực đại Mặt Trời (2024–2025), lượt chụp chạng vạng, vĩ độ thấp; băng L: nhiều cm | ngẫu nhiên, cộng trôi theo mùa / chu kỳ Mặt Trời |
| Tầng đối lưu bước sóng dài | mm–cm; ERA5 / GACOS bỏ được một phần | ngẫu nhiên, cộng theo mùa |
| Thuỷ triều Trái Đất rắn, chuyển động mảng | < 1 mm trên 30 km | — |
| **Biến dạng rộng hơn khung ảnh** (phễu lún lưu vực, gradient liên địa chấn) | cm/năm | **đều (tuyến tính) hoặc theo mùa** |

Biến dạng trông giống ramp phần lớn là **tuyến tính theo thời gian**. Các nguồn nhiễu phần lớn **không** như vậy:
chúng thay đổi giữa các lần chụp. Đây là chỗ dựa để quyết định.

### 2.3 Các công cụ khác làm thế nào

- StaMPS: `scla_deramp` bật/tắt trên mọi PS, như GeoEyes hiện nay.
- MintPy (Yunjun và cs. 2019): `deramp` trên chuỗi thời gian, khớp trên các pixel của một mặt nạ, nên có thể loại vùng
  biến dạng khỏi phép khớp. Người dùng tự chọn mặt nạ.
- Fattahi & Amelung (2014): trên chuỗi dài, ramp quỹ đạo trung bình hoá thành một phần sai số vận tốc, nhưng không
  biến mất.

## 3. Phương pháp: `scla_deramp = "auto"`

Đây là giá trị mới. `"y"` và `"n"` giữ nguyên như cũ, từng bit.

### 3.1 Tách mỗi ramp thành phần xu thế và phần còn lại

1. Với mỗi interferogram k, ramp R_k(x, y) được ước lượng như hiện nay: cùng dạng mặt, cùng bậc, cùng pha unwrap lần
   1 sau APS, trên mọi PS.
2. Chuỗi thời gian của mỗi hệ số (a_k, b_k, c_k, …) được khớp một đường thẳng theo t_k, cùng trọng số với phép khớp
   vận tốc. Khi đó R = **R_trend** (t_k × một mặt cố định) + **R_rest**.

### 3.2 Phần còn lại: bỏ

R_rest thay đổi giữa các lần chụp, nên không phải biến dạng đều, và được bỏ. Đây chính là phần còn thiếu ở Mexico.
Bỏ nó còn giúp unwrap lần 2 và SCLA, vì nếu không, một ramp tương quan với B⊥ sẽ lẫn vào sai số góc nhìn.

Chốt an toàn: biến dạng *theo mùa* trên toàn khung (cả lưu vực "thở" theo bơm hút nước) cũng nằm trong R_rest. Mình
khớp một hình sin chu kỳ năm cho chuỗi hệ số. Nếu hình sin giải thích > 50% phương sai và chuỗi dài ≥ 1 năm, thì giữ
lại phần theo mùa và ghi cảnh báo. D0 sẽ kiểm xem trường hợp này có bao giờ xảy ra không.

**Đã sửa trong code (2026-11-05): chốt này không còn bật do ngẫu nhiên với chuỗi ngắn.** Cách cũ (`seasonal_fit`:
sin, cos và hằng số trên phần còn lại *đã bỏ xu thế*, từ 5 ngày chụp, ngưỡng > 50% phương sai) bật khoảng một nửa số
lần trên nhiễu thuần khi n = 5 (E[R²] = 2/(n − 1)), kiểm hai gradient riêng rẽ, và để đường thẳng "ăn" một phần chu
kỳ. Nay `ramp.py::seasonal_test`, cho mỗi chuỗi gradient (đông–tây, bắc–nam):
- khớp **đồng thời** hằng số + xu thế + sin + cos chu kỳ năm (cùng trọng số với phép khớp vận tốc);
- kiểm định F cặp số hạng năm so với hằng số + xu thế (bậc tự do 2 và n − 4);
- giữ phần theo mùa khi p < α / 2 (Bonferroni cho 2 gradient; `RampAutoParams.seasonal_alpha` = 0,01); xu thế của
  gradient đó lấy theo độ dốc của phép khớp đồng thời.

Chốt chỉ chạy khi chuỗi dài ≥ 1 năm và có ≥ 12 ngày chụp (`seasonal_min_epochs`). Dưới 1 năm thì không áp dụng (không
có chu kỳ năm để tách; ghi "not applicable"). Từ 1 năm trở lên nhưng < 12 ngày chụp thì không kiểm được, và `auto`
chọn cách thận trọng: giữ phần chu kỳ năm của phép khớp đồng thời mà không kiểm (bỏ ít hơn), kèm cảnh báo "seasonal
safeguard not tested". Trên nhiễu thuần (n = 24) phép kiểm bật khoảng 1% số chuỗi (unit test). Bản ghi có các giá trị
p (`seasonal_p`) và cách chốt đã chạy (`seasonal_note`).

### 3.3 Phần xu thế: chỉ bỏ khi có nền ổn định trải rộng khắp khung ảnh

Chỉ dựa vào pha thì không tách được R_trend khỏi biến dạng đều. Vì vậy chỉ bỏ R_trend khi cảnh có một nền ổn định đủ
rộng để neo một mặt phẳng:

1. Tính vận tốc từ pha lần 1 (sau APS, đã bỏ R_rest, còn giữ R_trend), lấy trung vị trên ô 500 m.
2. Khớp mặt phẳng bền vững trên các ô: khớp, giữ các ô có |phần dư| < 2,5 × 1,4826 × MAD, khớp lại; tối đa 10 vòng.
   Phễu lún và trượt lở cục bộ có biên sắc nên bị loại ra; ramp thì trơn nên vẫn ở trong phép khớp.
3. Ô ổn định: các ô được giữ lại có |phần dư| < max(5 mm/năm, 2 σ_ô).
4. **Kiểm tra độ phủ.** Đạt khi thoả cả ba điều kiện:
   - ô ổn định chiếm ≥ 30% số ô;
   - ô ổn định nằm ở ≥ 3 trong 4 góc phần tư của khung;
   - theo hướng gradient đã khớp, ô ổn định trải ≥ 60% chiều dài khung.
5. **Đạt:** khớp lại mặt xu thế chỉ trên các ô ổn định rồi bỏ đi. Các ô đang biến dạng giữ nguyên độ nghiêng của
   chúng.

   **Không đạt:** giữ R_trend, tức là giống `"n"` hiện nay cho phần xu thế. QC ghi "chưa xác định được ramp xu thế",
   kèm gợi ý dùng hiệu chỉnh GNSS kiểu `plane` (≥ 3 trạm; `geoeyes gnss`) hoặc một polygon do người dùng chỉ định.
6. **Người dùng ghi đè:** `[ps] deramp_non_defo = [[lon, lat], …]` (một polygon, giống `aps_non_defo`) thay cho bước
   2–3 bằng "ổn định = nằm trong polygon". Kiểm tra độ phủ vẫn được chạy và báo cáo.

Khung nhỏ hơn 5 km theo cả hai chiều thì bỏ qua bước 3 và giữ R_trend. Ở quy mô đó, ramp không tách được khỏi chuyển
động cục bộ.

**Đã sửa trong code (2026-11-05): xu thế phẳng cần một ràng buộc độc lập.** Phép kiểm theo nửa khung thay cho bước
3–4 (§5.1, `ramp.py::frame_test`) chỉ hỏi một mặt phẳng có khớp được cả khung hay không. Nó phát hiện độ cong, không
phát hiện nhiễu: một trường biến dạng *phẳng* (gradient liên địa chấn, §2.2; gradient LOS của chuyển động mảng; độ
nghiêng khu vực) qua phép kiểm, còn một nhiễu đều nhưng *cong* (tầng điện ly bước sóng dài) không qua và được giữ.
Phép kiểm chỉ an toàn khi nó **giữ** xu thế; khi qua, nó mới chỉ chứng tỏ xu thế là phẳng. Quy tắc nay trong
`auto_ramp`:
- chỉ bỏ xu thế khi có ràng buộc độc lập:
  - (a) GNSS: chưa nối. Engine PS không truy cập được các trạm GNSS (chúng chỉ vào ở bước kiểm chứng, `geoeyes gnss`);
    kiểm tra GNSS `plane` vẫn là bước thủ công sau lần chạy;
  - (b) vùng ổn định của người dùng `[ps] deramp_non_defo` (polygon lon/lat, dùng lại, không thêm tham số mới): mặt
    xu thế được khớp trên các ô nằm trong đó rồi bỏ đi, bất kể phép kiểm nửa khung nói gì;
  - (c) tham số ghi đè tường minh `[ps] ramp_auto_allow_planar = "y"` (mặc định `"n"`): chỉ cần phép kiểm nửa khung là
    bỏ xu thế, như trước;
- nếu không thì xu thế qua phép kiểm nửa khung vẫn được giữ, với lý do "planar trend kept: no independent constraint
  (GNSS / stable area)". Bản ghi giữ `frame_test_passed` và số liệu các nửa, hình QC ghi lý do.

`RAMP_AUTO_VERSION` = 2, nên các checkpoint bước 6 cũ của `auto` không được dùng lại.

### 3.4 Những gì được ghi lại

- Trong `params.json` / manifest của lần chạy:
  - hệ số ramp của từng interferogram, và cách tách thành xu thế và phần còn lại;
  - kết quả kiểm tra theo mùa;
  - các số liệu độ phủ, quyết định và lý do.
- Hình QC `figures/ramp.png`: gradient đông–tây và bắc–nam theo từng ngày (tổng, xu thế, phần còn lại), và bản đồ ô
  ổn định.
- Một dòng trong báo cáo sản phẩm: "ramp: đã bỏ phần còn lại; phần xu thế đã bỏ / giữ (lý do)".

### 3.5 Những gì không đổi

- Kết quả của `"y"` / `"n"` và các parity test hiện có.
- Giá trị mặc định trong preset, cho tới bước D4.
- SCN, bộ lọc thông cao vận tốc và phép so GNSS.

## 4. Các bước và điểm duyệt

Mỗi bước kết thúc ở một điểm duyệt: kết quả ghi vào §5 của ghi chú này, chủ dự án duyệt rồi mới sang bước sau.

| Bước | Công việc | Tiêu chí duyệt |
|---|---|---|
| **D0** | Nghiên cứu offline trên 4 state PS đang có: `mexico_g3` v3, `mexico_s1`, `quangnam_l2b_a55`, `quangnam_l5_d120`. Script `code/ramp_auto.py` tính ramp theo ngày, cách tách, kiểm tra theo mùa, kiểm tra độ phủ, và quyết định mà `auto` sẽ đưa ra. Không đổi engine. | Các quyết định hợp lý về mặt vật lý: Mexico dự kiến giữ hoặc chỉ bỏ một phần xu thế (phễu lún trải hết khung); Quảng Nam dự kiến đạt (trượt lở cục bộ trên nền núi ổn định). Xác nhận hoặc chỉnh các ngưỡng ở §3.3. |
| **D1** | Hàm thuần (`steps/ramp.py`) và unit test trên cảnh tổng hợp: (a) phễu cục bộ + ramp ngẫu nhiên + ramp xu thế; (b) phễu rộng hơn khung + ramp ngẫu nhiên; (c) không có ramp; (d) tín hiệu theo mùa trên toàn khung. | (a) ramp xu thế khôi phục sai < 2 mm/năm mỗi 10 km, tốc độ phễu sai < 5%; (b) kiểm tra không đạt, giữ nguyên xu thế, phần còn lại được bỏ; (c) ramp bị bỏ ≈ 0 (< 0,5 mm/năm mỗi 10 km); (d) giữ phần theo mùa kèm cảnh báo. |
| **D2** | Nối vào engine: `scla_deramp = "auto"` trong `params.py` / schema, `deramp_non_defo`, bản ghi QC và hình. Chỉ thay đổi cách tính `ph_ramp`. | Toàn bộ unit test đạt; `"y"` / `"n"` khớp từng bit trên parity test; chạy `mexico_g3` một lần với `auto` (từ checkpoint bước 6 nếu còn, không thì chạy đầy đủ). |
| **D3** | Kiểm định: G3.2 Mexico 18 tháng, so `n` / `y` / `auto` với GNSS (bỏ-một, hệ số); Quảng Nam so `n` / `auto` theo độ tản vận tốc trên nền ổn định. | `auto` không kém `n` quá 10% về RMS bỏ-một với GNSS, và không kém `y` ở nơi kiểm tra độ phủ đạt; ở Quảng Nam, độ tản trên nền ổn định không tăng. |
| **D4** | Giá trị mặc định: dùng `auto` cho các preset được D3 ủng hộ; cập nhật tài liệu (skills/insar-processing, guides, ADR). | Chủ dự án quyết định. |

## 5. Kết quả

### 5.1 D0, nghiên cứu offline (2026-11-04)

Script [code/ramp_auto.py](../../en/research/code/ramp_auto.py), chạy trên 4 state PS đang có (pha unwrap lần 2; mỗi
interferogram khớp một mặt phẳng trên 400 nghìn PS ngẫu nhiên; ô 500 m có ≥ 5 PS).

| Dự án | Chuỗi | Khung | Gradient ramp theo ifg, độ lệch chuẩn (mm/10 km) | Xu thế của ramp (mm/năm mỗi 10 km, Đ-T / B-N) | Phần còn lại, độ lệch chuẩn |
|---|---|---|---|---|---|
| `mexico_g3` | 16 ảnh, 0,49 năm | 45 × 40 km | 7,9 / 7,2 | −16,4 / +2,2 | 7,4 / 7,2 |
| `mexico_s1` | 16 ảnh, 0,49 năm | 29 × 30 km | 6,8 / 7,5 | +14,6 / −22,1 | 6,3 / 6,5 |
| `quangnam_l2b_a55` | 7 ảnh, 0,21 năm | 44 × 16 km | 5,4 / 4,8 | +60,0 / +3,6 | 2,4 / 4,8 |
| `quangnam_l5_d120` | 24 ảnh, 0,95 năm | 74 × 49 km | 1,8 / 1,8 | −0,3 / −0,7 | 1,8 / 1,8 |

Phát hiện:

1. **Phép kiểm độ phủ viết ở §3.3 không dùng được.**
   - Với ngưỡng "2 × độ lệch chuẩn bền vững của các ô", ngưỡng chạy theo chính độ tản của biến dạng (73–134 mm/năm ở
     Mexico), nên gần như ô nào cũng bị coi là ổn định và dự án nào cũng đạt.
   - Với ngưỡng theo nhiễu, max(5, 2 × trung vị độ tản của PS trong ô), Mexico chỉ còn 22–29% ô ổn định và chỉ trượt
     vì tiêu chí 30%, vốn chọn tuỳ ý. Các ô ổn định vẫn có mặt ở cả 4 góc phần tư và trải 85% khung.
   - Góc phần tư và độ trải không chống được phễu lún trơn: sườn của một phễu rộng hơn khung nhìn cục bộ giống một
     mặt phẳng.
2. **Phép kiểm quyết định là: mặt phẳng có phụ thuộc vào khung hay không.** Ramp nhiễu là một mặt phẳng trên cả khung,
   nên cùng dữ liệu cắt theo cách khác phải cho cùng gradient. Vì vậy mỗi nửa khung (T, Đ, N, B) tự chọn lại ô ổn
   định từ đầu:

   | Dự án | Mặt phẳng trên ô ổn định, cả khung (Đ-T / B-N) | Các nửa khung, gradient Đ-T | Nhất quán? |
   |---|---|---|---|
   | `mexico_g3` | −15,7 / +2,9 | −60, −8, −5, −30 | **không** (lệch 45 so với 5) |
   | `mexico_s1` | +33,7 / −5,4 | −49, +28, −11, +59 | **không** (92 so với 10) |
   | `mexico_g3` trên phần chồng với `mexico_s1` | +77,5 / −89,3 | — | **không** |
   | `quangnam_l2b_a55` | +60,7 / +9,6 | +75, −5, +81, +43 | **không** (65 so với 18) |
   | `quangnam_l5_d120` | −0,5 / −1,1 | −4, +1, +1, −1 | **có** (3,7 so với 5) |

   - Mexico: cùng các interferogram mà cho −16, +34 hoặc +78 mm/năm mỗi 10 km tuỳ khung. Như vậy "ramp xu thế" ở đây
     là phễu lún, không phải nhiễu, và giữ nó là quyết định đúng.
   - Quảng Nam a55: chỉ 2,5 tháng, nhiễu vận tốc trong ô tới 51 mm/năm; không neo được xu thế.
   - Quảng Nam d120: một năm dữ liệu, trượt lở cục bộ trên nền núi ổn định; nhất quán, và xu thế không đáng kể.
3. **Lưu ý về GNSS.** Trên `mexico_g3`, bỏ mặt phẳng −15,7 làm RMS bỏ-một so với MIDAS giảm từ 37,8 xuống 15,3 mm/năm
   (so với GNSS cửa sổ: 62,5 → 45,8). Nhưng mặt phẳng đó phụ thuộc vào khung (phát hiện 2), nên sự khớp ở ba trạm
   là trùng hợp do khung, không phải bằng chứng ủng hộ mặt phẳng. Không dùng kết quả này.
4. **Mặt bậc hai của engine thiếu số hạng bậc nhất.** Engine dùng `x² + y² + xy + c`, giống `ps_deramp` của StaMPS.
   Với dạng đó, mặt bậc hai không bao giờ tốt hơn mặt phẳng (trung vị mức cải thiện từ −129% đến +1%), nên bậc 2
   không bao giờ được chọn. Mặt bậc hai đầy đủ (`x, y, x², y², xy`) cải thiện 15–18% ở Mexico, chủ yếu do độ cong
   của phễu nằm trong phần xu thế. Không đổi ở chế độ `y`. Với `auto`, phần còn lại vẫn khớp mặt phẳng cho tới khi D1
   cho thấy mặt bậc hai có ích.
5. **Kiểm tra theo mùa chưa được thử.** Chưa state nào dài ≥ 1 năm (d120 là 0,95 năm). G3.2 (18 tháng) sẽ là trường
   hợp đầu tiên.

**Quy tắc đã sửa để duyệt (thay cho bước 3–4 ở §3.3):**
- ngưỡng = max(5 mm/năm, 2 × trung vị độ tản của PS trong ô);
- chỉ bỏ xu thế khi thoả cả ba điều kiện:
  - mỗi nửa trong 4 nửa khung, tự chọn ô ổn định (≥ 30 ô), cho gradient lệch không quá max(5 mm/năm mỗi 10 km, 30%
    gradient cả khung) so với mặt phẳng cả khung;
  - ô ổn định nằm ở ≥ 3 góc phần tư;
  - ô ổn định trải ≥ 60% khung;
- bỏ tiêu chí tỉ lệ 30%.

Theo quy tắc này:
- Mexico (cả hai khung) và Quảng Nam a55 giữ xu thế;
- Quảng Nam d120 bỏ xu thế (−0,5 / −1,1 mm/năm mỗi 10 km, vô hại);
- mọi dự án đều bỏ phần còn lại.

Lưu ý (2026-11-05): riêng quy tắc này sẽ bỏ mọi xu thế phẳng trên khung, kể cả biến dạng; nó được hiệu chỉnh trên các
khung không có gradient kiến tạo. Đã sửa trong code: nay chỉ bỏ xu thế khi có vùng ổn định hoặc tham số ghi đè
(§3.3), nên với mặc định Quảng Nam d120 giữ xu thế (rất nhỏ) của nó. Nghiên cứu D0 này dùng pha lần 2 đã bỏ SCLA;
engine nay cũng làm vậy ở lần 2 (§5.3).

Hình (gradient theo ngày, bản đồ ô ổn định): `ramp_auto_<dự án>.png` trong thư mục scratchpad của phiên. Sẽ chuyển vào
workspace khi code được đưa vào engine. Đã chạy lại với quy tắc sửa đổi trong script (2026-11-05): bốn quyết định
không đổi; ở cả ba trường hợp giữ xu thế, lý do đều là "mặt phẳng phụ thuộc khung".

### 5.2 D1, hàm thuần và test tổng hợp (2026-11-05)

Code: `src/geoeyes/processing/ps/steps/ramp.py` (`auto_ramp`, `RampAutoParams`, `RampAuto.summary()` để ghi lại
quyết định), test `tests/unit/processing/test_ps_ramp_auto.py` (11 test, ~3 giây). Cảnh tổng hợp: 40 × 40 km,
60.000 PS, 24 ngày chụp trong 0,9 năm, nhiễu PS 2 mm, ramp ngẫu nhiên 7 mm mỗi 10 km mỗi lần chụp (như Mexico).

| Trường hợp | Tiêu chí | Kết quả |
|---|---|---|
| (a) phễu cục bộ −100 mm/năm + ramp ngẫu nhiên + ramp xu thế, 3 seed | xu thế sai ≤ 2 mm/năm mỗi 10 km, phễu sai ≤ 5% | xu thế sai ≤ 0,06; phễu −98,6 so với −98,5 (≤ 0,2%) |
| (b) phễu rộng hơn khung + ramp ngẫu nhiên | phép kiểm không qua, giữ nguyên xu thế, bỏ phần còn lại | "mặt phẳng phụ thuộc khung" (các nửa −36 / −1 / −21 / −20 đông–tây); sai số phần còn lại ≤ 0,02 mm mỗi 10 km |
| (c) không có ramp | ramp bị bỏ < 0,5 | xu thế 0,05, phần còn lại ≤ 0,02 mm/năm mỗi 10 km |
| (d) theo mùa 10 mm mỗi 10 km, 1,5 năm | giữ phần theo mùa, có cảnh báo | tỷ lệ 96%, được giữ và có cảnh báo; chỉ 0,6 mm mỗi 10 km của số hạng năm bị bỏ |
| khung 4 × 4 km | giữ xu thế | "khung < 5 km" |
| pha theo rad, có hàng NaN | cùng ramp như tính theo mm | đúng; hàng NaN vẫn là NaN |

Phát hiện:

1. **Bước khớp lại trên ô ổn định là cần thiết.** Xu thế khớp trên toàn bộ PS bị phễu lún làm lệch ~1 mm/năm mỗi
   10 km. Khớp lại trên ô ổn định giảm sai lệch xuống ≤ 0,06.
2. **Chuỗi ramp ngẫu nhiên tự có một đường thẳng theo t.** Chuỗi hữu hạn không phân biệt được đường này với xu thế,
   nên trong test, xu thế "thật" là xu thế đưa vào cộng với đường thẳng đó. Độ lớn của nó là σ_rest / √Σ(t − t̄)²:
   - khoảng 5,6 mm/năm mỗi 10 km trong cảnh test;
   - khoảng **13 mm/năm mỗi 10 km với `mexico_g3`** (phần còn lại 7,4 mm mỗi 10 km, 0,49 năm);
   - khoảng 2,5–3 với G3.2 dài 18 tháng.

   Ở nơi giữ xu thế (Mexico), phần nhiễu ramp này nằm lại trong vận tốc: khoảng ±30 mm/năm trên khung 45 km với sáu
   tháng dữ liệu. Chỉ chuỗi dài hơn hoặc GNSS mới giảm được nó. Đây thêm một lý do để chạy G3.2.
3. **Bậc của mặt.** `auto` dùng mặt phẳng cho phần còn lại. Mặt bậc hai của engine không được dùng, vì nó thiếu số
   hạng bậc nhất (§5.1 phát hiện 4).

### 5.3 D2, nối vào engine (2026-11-05): đã viết nháp, chưa commit, đang chờ duyệt

Những gì đang có trong cây làm việc (chưa commit; `steps/ramp.py` và file test của nó chưa được git theo dõi):

- `params.py`: nhận `scla_deramp = "auto"` bên cạnh `"y"` / `"n"`; đọc `deramp_non_defo` (polygon lon/lat) giống
  `aps_non_defo`; `engine_params` đặt `deramp_auto` / `deramp_non_defo`. Chưa có mục trong schema cấu hình.
- `runner.py::process`: tạo một `DerampAuto` (t tính bằng năm từ master, mm trên rad, trọng số 1/ifg_std² như phép
  khớp vận tốc, các PS nằm trong `deramp_non_defo`) và truyền vào `calc_scla` ở cả hai lần. Khoá checkpoint bước 6
  chỉ thêm `deramp_auto` (`RAMP_AUTO_VERSION`) và polygon khi dùng `auto`, nên khoá của `y` / `n` không đổi.
- `scla.py::calc_scla`: với `auto`, `auto_ramp` thay cho `deramp`; `SclaResult.ramp_auto` giữ quyết định
  (`RampAuto.record()`), được chuyển tiếp qua `smooth_scla`.
- `runner.py`: một dòng log ghi quyết định, `summary()` trong bản ghi lần chạy, và `figures/ramp.png`
  (`ramp.py::ramp_figure`; nếu lỗi thì chỉ ghi cảnh báo).

**Lần chạy `auto` cho `mexico_g3` (2026-11-05, code đã duyệt, `RAMP_AUTO_VERSION` 2).** Biến thể c (ERA5 cho mọi
giao thoa đồ), dùng lại bước 1–5 của lần chạy v3, ghi vào thư mục riêng `ps_runs/sentinel1-asc-078_auto` (bản `n`
không bị đụng tới); 3,63 triệu điểm, 1770 giây.

- Quyết định: bỏ phần còn lại, **giữ xu thế** ("mặt phẳng phụ thuộc khung"), khớp với D0. Các nửa khung (trục x / y
  của engine): +19/+31, +36/−9, +23/−20, +2/+17 mm/năm mỗi 10 km, lệch tối đa 31 so với dung sai 5. Ngưỡng ổn định
  12,1 mm/năm (độ tản trong ô 6,1; trước khi bỏ SCLA sơ bộ là 6,9), 1134 ô ổn định trên 4981.
- Theo mùa: không áp dụng (0,49 năm).
- So với GNSS, cùng tham số với phân tích v3 (vertical, offset, GNSS cửa sổ). Đường LOS lấy từ sản phẩm v3, điểm gần
  nhất (lần chạy PS chưa có cột LOS):

  | | `n` (v3) | `auto` |
  |---|---|---|
  | `disp_scn_mm`: RMSE đã bỏ xu thế ICMX / MMX1 / MXTX (mm) | 2,6 / 1,5 / 3,8 | 2,5 / 1,5 / 3,9 |
  | `disp_scn_mm`: LOO (mm/năm) | 66,0 | 74,2 |
  | `disp_mm` (thô): RMSE đã bỏ xu thế ICMX / MMX1 / MXTX (mm) | 10,0 / 4,9 / 14,6 | **3,5** / 6,1 / 14,9 |
  | `disp_mm` (thô): LOO (mm/năm) | 63,4 | 70,9 |
  | Tốc độ InSAR ICMX / MMX1 / MXTX (`disp_scn_mm`, mm/năm) | +26,0 / −131,4 / −13,0 | +21,8 / −128,7 / −23,7 |

  Đọc bảng:
  - Bỏ phần còn lại làm sạch chuỗi thô ở ICMX (10,0 → 3,5 mm), nhưng không ở MXTX: nhiễu theo ngày ở đó không có
    dạng mặt phẳng. SCN vẫn bắt được nó (3,9 mm).
  - Sau SCN, hai bản gần như trùng nhau, vì SCN vốn đã bỏ ramp theo ngày.
  - LOO tăng 8 mm/năm (12%). Mức này nằm trong nhiễu của xu thế ramp (~13 mm/năm mỗi 10 km trên 6 tháng, §5.2 phát
    hiện 2). Với ba trạm, chưa thể nói `auto` tốt hơn hay kém hơn `n`; D3 (18 tháng) mới trả lời được.
  - Sai lệch tốc độ lớn ở ICMX và MMX1 không đến từ ramp.
- Lần chạy đầu (code trước khi duyệt, `RAMP_AUTO_VERSION` 1) cho cùng quyết định và cùng số liệu GNSS trong phạm vi
  0,2 mm/năm.
- Bộ nhớ: lần chạy đầu hết RAM ở bước 8 (29,7 GB) vì một ramp float64 (n, n_ifg). Nay ramp của `auto` được lưu
  float32.
- Nhãn: hệ toạ độ cục bộ của engine được xoay theo hướng bay, nên gradient và các nửa khung trong bản ghi / hình là
  theo trục x / y, không phải đông / bắc. Đã sửa nhãn trong hình.
- Kiểm parity `y` / `n`: các fixture legacy không có trên máy này (các test parity bị bỏ qua). Hai nhánh `y` / `n`
  không đổi trong code (`auto=None`) và khoá checkpoint của chúng không đổi; một phép kiểm bit-identical vẫn còn
  phải làm khi có fixture.
- Ghi chú vận hành: với `resume_from`, checkpoint được đọc từ thư mục cũ, nên một lần chạy dừng giữa chừng trong thư
  mục mới sẽ tính lại từ bước 6.
- **Hoa văn vòng cung (chủ dự án phát hiện, 2026-11-05): `auto` làm thay đổi kết quả gỡ pha, và phần lớn theo hướng
  xấu đi.** Bản đồ vận tốc của `auto` có những vòng cung mà bản `n` không có. Hiệu `auto − n` (3,56 triệu PS, ghép
  theo line/sample) không phải một mặt phẳng. Nó gồm các mảng giá trị hằng, mép sắc, có chỗ thẳng (±20–40 mm/năm).
  Theo từng ngày, sau khi bỏ một mặt phẳng, hiệu là số nguyên lần λ/2 (27,7 mm), tức ±1 chu kỳ. Ngày 19/08/2024 có
  tới 27% số PS lệch; ngày 27/05/2024 là 15%, ngày 07/08/2024 là 13%. Các mảng nằm ở những vùng nối yếu: đồi phía
  tây bắc, vùng thưa điểm phía đông, hai bên sân bay và hồ. Ở những chỗ hai bản khác nhau (13 nghìn trên 30 nghìn PS
  lấy mẫu), cộng các bước nhảy chu kỳ của `auto` vào `n` làm chuỗi gồ ghề hơn ở 68% số PS (sai số còn lại sau khi
  khớp bậc hai tăng từ 11,1 lên 11,9 mm). Vậy đây là lỗi gỡ pha của `auto`.
  Cơ chế: mặt phẳng của mỗi interferogram được khớp bình phương tối thiểu thường trên toàn bộ PS của pha đã gỡ ở lượt
  1. Vì thế nó hút luôn các mảng lệch chu kỳ của lượt 1: những ngày có phần ramp ngẫu nhiên lớn nhất, ví dụ −24 mm
  trên 10 km ngày 27/05/2024, cũng là những ngày có mảng lệch lớn nhất. Lượt 2 trừ mặt phẳng đó khỏi pha quấn trước
  khi gỡ pha (`steps/unwrap.py`). Trên một liên kết yếu dài hàng km, việc này dịch hiệu pha đi một phần lớn của chu
  kỳ, và bộ gỡ pha chọn sang chu kỳ khác. Bản thân một mặt phẳng không vẽ được vòng tròn; vòng cung là mép của một
  mảng bị đổi một chu kỳ. Chế độ `y` cũng làm như vậy (cùng mặt phẳng, trừ ở cùng chỗ). Mức cải thiện ở ICMX nêu trên
  là có thật nhưng nhỏ hơn tác hại này. Nhận xét D2 "sau SCN hai bản gần như giống nhau" là sai với bản đồ.
  Đã sửa (2026-11-05, `RAMP_AUTO_VERSION` 3):
  (1) Ở chế độ `auto`, ramp chỉ được bỏ sau khi gỡ pha (bước vận tốc và SCN). Lượt 2 không còn trừ ramp khỏi pha quấn
  (`runner.py`); chế độ `y` giữ thứ tự của StaMPS.
  (2) Mặt phẳng của mỗi interferogram được khớp bền vững (`robust_epoch_planes`): lấy trung vị theo ô 500 m, bỏ đường
  thẳng theo thời gian của từng ô, khớp mặt phẳng trên phần còn lại và loại ngoại lai bằng MAD, rồi cộng lại mặt phẳng
  của các đường thẳng đó. Unit test: một góc khung lệch 1 chu kỳ trong một interferogram làm mặt phẳng thường nghiêng
  2,7 mm/10 km, còn mặt phẳng bền vững nghiêng dưới 1.
  Chạy lại (`ps_runs/sentinel1-asc-078_auto3`), quyết định không đổi: bỏ phần ramp ngẫu nhiên, giữ xu thế. Hiệu
  `auto3 − n` giờ là một mặt phẳng trơn (đường thẳng theo thời gian của chính phần ramp ngẫu nhiên) cộng vài dải hẹp.
  Tỷ lệ PS lệch 1 chu kỳ: ≤ 2,4% ở 14 trên 15 ngày (trước đây tới 27%). Riêng ngày 26/07/2024 (12 ngày sau ảnh master)
  vùng lún vẫn lệch +1 chu kỳ trong `auto3`: +11 mm so với xung quanh, tức trồi lên giữa vùng lún, nên `auto3` sai ở
  đó (bản `n` là −8 mm). Ở ngày này SCLA của hai bản chỉ khác 1–6 mm. Vậy đây là một chỗ gỡ pha lưng chừng (hai lời
  giải gần ngang nhau) mà thay đổi nhỏ nào cũng có thể làm lật, không phải do ramp. So với GNSS (cùng thiết lập như
  trên):

  | | `n` (v3) | `auto` (v2) | `auto3` |
  |---|---|---|---|
  | `disp_scn_mm`: RMSE sau bỏ xu hướng ICMX / MMX1 / MXTX (mm) | 2,6 / 1,5 / 3,8 | 2,5 / 1,5 / 3,9 | 2,6 / 1,5 / 3,8 |
  | `disp_scn_mm`: sai số bỏ-một (mm/năm) | 66,0 | 74,2 | **56,5** |
  | `disp_mm` (thô): RMSE sau bỏ xu hướng ICMX / MMX1 / MXTX (mm) | 10,0 / 4,9 / 14,6 | 3,5 / 6,1 / 14,9 | 4,9 / 6,0 / 10,9 |
  | `disp_mm` (thô): sai số bỏ-một (mm/năm) | 63,4 | 70,9 | **48,0** |

  Còn mở: một phép kiểm cho các chỗ gỡ pha lưng chừng (ví dụ đánh dấu mảng mà đổi 1 chu kỳ ở một ngày làm chuỗi mượt
  hơn) sẽ giúp cả `n` lẫn `auto`. Đây là một hạng mục riêng, không thuộc quy tắc chọn ramp.

Các sửa đổi ngày 2026-11-05 (khi duyệt D2, code và unit test; 17 test): xu thế phẳng chỉ bỏ khi có ràng buộc (§3.3),
kiểm định F cho chốt theo mùa (§3.2), SCLA sơ bộ (dưới đây). Thêm `[ps] ramp_auto_allow_planar` vào `params.py` (bảng
`[ps]` không nằm trong schema cấu hình).

**Đã sửa trong code (2026-11-05): engine nay kiểm trên đúng pha mà D0 đã hiệu chỉnh (lần 2).** `auto_ramp` chạy bên
trong `calc_scla`, trước khi ước lượng SCLA, nên số hạng sai số DEM (tương quan với B⊥) vẫn còn trong đầu vào, trong
khi D0 (`code/ramp_auto.py`) dùng pha unwrap − APS − SCLA. Sai số DEM làm tăng độ tản của PS trong ô, mà độ tản này
quyết định ngưỡng ổn định (max(5, 2 × độ tản)). Nay có `calc_scla(scla_k_prior=…)`: ở lần 2, runner truyền K đã làm
trơn của lần 1, và K·B⊥ được trừ khỏi pha dùng để ước lượng ramp (bản thân SCLA vẫn khớp trên pha đầy đủ). Lần 1 chưa
có SCLA nào trước đó nên phép kiểm vẫn thấy sai số DEM; ramp của lần 1 chỉ dùng cho bước unwrap lần 2, còn quyết định
được giữ là của lần 2. Khi tắt `subtr_tropo` (chỉ một lần) thì giới hạn này vẫn còn.

## 6. Giới hạn

- **Nhiễu tăng đều nằm dưới một phễu lún trải hết khung thì vẫn không giải được.** Một ramp tăng tuyến tính theo thời
  gian là vô hình với mọi phép kiểm chỉ dựa vào pha khi biến dạng phủ cả khung. Phép kiểm sẽ báo trường hợp này thay
  vì đoán. Cách khắc phục là GNSS (`plane`, ≥ 3 trạm) hoặc một khung rộng hơn có viền ổn định.
- **Phép kiểm nửa khung phát hiện độ cong, không phát hiện nhiễu (đã sửa trong code 2026-11-05, §3.3).** Nay xu thế
  phẳng được giữ trừ khi người dùng cho vùng ổn định hoặc bật tham số ghi đè; cái giá là một nhiễu phẳng thật sẽ nằm
  lại trong vận tốc nếu không có chúng. Tầng điện ly bước sóng dài có độ cong vẫn được giữ. GNSS chưa nối vào engine.
  D4 vẫn chờ kiểm parity `y` / `n` và lần chạy `mexico_g3`.
- Chốt an toàn theo mùa (đã sửa trong code 2026-11-05, §3.2) không chạy được khi dưới 12 ngày chụp; khi đó phần chu kỳ
  năm được giữ mà không kiểm.
- Phép kiểm khung ở lần 1 vẫn thấy sai số DEM (chưa có SCLA trước đó); lần 2 thì không (§5.3).
- Mặt phẳng / bậc hai chỉ là mô hình. Màn tầng điện ly vào năm cực đại Mặt Trời có thể có bước sóng ngắn hơn; phần đó
  thuộc về hiệu chỉnh tách phổ (TODO mục 2 cho băng L; S1 sẽ lên kế hoạch sau), không thuộc về deramp.
- Ô 500 m và các ngưỡng mới được chốt ở D0 trên bốn bộ dữ liệu (§5.1); D3 sẽ kiểm lại trên G3.2.
- Với chuỗi ngắn, khi giữ xu thế thì phần đường thẳng của ramp ngẫu nhiên không bỏ được (§5.2 phát hiện 2).

## 7. Tài liệu tham khảo

- Hooper, A., Segall, P., Zebker, H. (2007). Persistent scatterer InSAR for crustal deformation analysis, with
  application to Volcán Alcedo, Galápagos. *JGR* 112, B07407.
- Fattahi, H., Amelung, F. (2014). InSAR uncertainty due to orbital errors. *GJI* 199, 549–560.
- Yunjun, Z., Fattahi, H., Amelung, F. (2019). Small baseline InSAR time series analysis: unwrapping error
  correction and noise reduction. *Computers & Geosciences* 133, 104331.
- Liang, C., Agram, P., Simons, M., Fielding, E. (2019). Ionospheric correction of InSAR time series analysis of
  C-band Sentinel-1 TOPS data. *IEEE TGRS* 57, 6755–6773.
