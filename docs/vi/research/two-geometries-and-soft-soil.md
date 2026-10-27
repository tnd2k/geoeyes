# Hai hình học và đất yếu

Trạng thái: bản v1 đã triển khai ngày 2026-10-27.
Mã nguồn: `geoeyes.ml.decompose` (`geoeyes decompose`), `geoeyes.ancillary.geology` và `geoeyes.ml.geology`
(`geoeyes geology`), lớp `soft_soil_m` của `geoeyes.ml.layers` (tính nhạy cảm), `geoeyes.api.behaviour`.
Ứng dụng web: lớp "Chuyển dịch thẳng đứng", "Chuyển dịch đông–tây" và "Bề dày đất yếu" trên trang Phân tích chuyên
đề; trang Nguyên lý, chương 5.
Liên quan: [lines-and-consolidation.md](lines-and-consolidation.md) (quá trình cố kết mà bề dày đất yếu dùng để kiểm
tra), [groundwater-insar.md](groundwater-insar.md) (nước mà lớp đất yếu nhả ra).

## Mục lục

1. [Câu hỏi](#1-câu-hỏi)
2. [Chuyển dịch thẳng đứng và đông–tây](#2-chuyển-dịch-thẳng-đứng-và-đông-tây)
3. [Bề dày đất yếu](#3-bề-dày-đất-yếu)
4. [Kết quả đầu tiên](#4-kết-quả-đầu-tiên)
5. [Hạn chế](#5-hạn-chế)
6. [Trình tự nghiên cứu](#6-trình-tự-nghiên-cứu)
7. [Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

## 1. Câu hỏi

- **Q5. Bao nhiêu phần của chuyển dịch theo hướng nhìn là thẳng đứng?** Mọi phân tích dựa trên một sản phẩm (phân
  vùng, tuyến, công trình, cố kết) đều coi v_LOS / l_u là thẳng đứng. Điều đó chỉ đúng khi nền đất không dịch ngang.
  Quanh phễu lún và trên sườn dốc, nền có dịch ngang.
- **Q6. Nền có lún ở nơi lớp đất yếu dày không?** Mô hình tính nhạy cảm đã biết lớp phủ và công trình, nhưng chưa
  biết lớp đất bị nén.

## 2. Chuyển dịch thẳng đứng và đông–tây

### 2.1 Nguyên lý

Một sản phẩm đo v_LOS = e·l_e + n·l_n + u·l_u, trong đó (l_e, l_n, l_u) là véc-tơ đơn vị từ mặt đất lên vệ tinh
(`los_e`, `los_n`, `los_u` của `points.parquet`).

Quỹ đạo lên của Sentinel-1 nhìn từ phía tây (l_e ≈ −0,6), quỹ đạo xuống nhìn từ phía đông (l_e ≈ +0,6). Vì vậy hai
sản phẩm có l_e trái dấu tách được e và u.

Thành phần bắc–nam được giả định bằng 0. Quỹ đạo gần cực hầu như không thấy nó: |l_n| ≈ 0,1–0,15 với Sentinel-1.

### 2.2 Phương pháp

1. **Sản phẩm ghép cặp.** Đó là các sản phẩm trong workspace, lấy phiên bản mới nhất của mỗi quỹ đạo, thoả cả các
   điều kiện sau:
   - phạm vi chồng lên sản phẩm;
   - thời gian chung ít nhất `min_overlap_share` = 50 % của chuỗi ngắn hơn;
   - hướng nhìn khác nhau |Δl_e| ≥ `min_east_contrast` = 0,5.

   Sản phẩm ghép cặp có thể thuộc dự án khác (Mexico City: Sentinel-1 và Capella).
2. **Nền ghép chung.** Hai sản phẩm thấy những điểm tán xạ khác nhau ở những vị trí khác nhau, nên phải ghép chúng
   tại đâu đó. Với `support = "points"`, không có lưới: tại mỗi điểm của sản phẩm, mỗi sản phẩm cho trung vị các
   điểm của nó trong bán kính `radius_m` (20 m). Mexico City với 15 m: 60.027 vị trí thay vì 1.731 ô 100 m, σ_up
   trung vị 4,1 mm/năm thay vì 1,5. Với `support = "cells"` (mặc định, ghi được ra GeoTIFF), lưới gồm các ô
   `cell_m` = 100 m, tính theo độ để có thể ghi ra GeoTIFF. Với mỗi ô, mỗi sản phẩm cho
   trung vị v_LOS và véc-tơ hướng nhìn của các điểm, khi có ít nhất `min_points` = 3 điểm. Độ bất định của ô là
   giá trị lớn nhất trong các giá trị sau:
   - 1,4826·MAD/√n;
   - σ hình thức trung vị/√n;
   - `sigma_floor_mm_yr` = 0,5.
3. **Tham chiếu chung.** Mỗi sản phẩm được quy lại về trung vị vận tốc của chính nó trên các ô mà mọi sản phẩm cùng
   thấy. Vì vậy kết quả là tương đối so với chuyển dịch trung vị của vùng chung.
4. **Lời giải.** Bình phương tối thiểu có trọng số của [l_e, l_u]·[e, u] = v_LOS trên các sản phẩm, từng ô một, kèm
   hiệp phương sai của (e, u).
5. **Sai số của một hình học.** Với mỗi sản phẩm, v_LOS / l_u được giữ cạnh u: đó là giá trị mà riêng sản phẩm ấy
   coi là thẳng đứng.

Một ô có chuyển dịch đông–tây **đáng kể** khi |e| ≥ `horizontal_mm_yr` = 5 và |e| ≥ 2σ_e.

Kết quả, trong `analyses/decompose/<sản phẩm>/`:
- `decompose.parquet`;
- `up.tif`, `east.tif` (mm/năm, dương là lên, dương là về phía đông);
- `decompose.json`: các sản phẩm, thời gian, khoảng giá trị, độ bất định, tỷ lệ ô có chuyển dịch ngang đáng kể, và
  sai số thẳng đứng của từng hình học đơn lẻ.

## 3. Bề dày đất yếu

### 3.1 Nguồn

Dùng nguồn đầu tiên có sẵn:

| Nguồn | Khai báo | Ý nghĩa |
|---|---|---|
| Bản đồ | `[postprocess.geology] raster = "geom/soft_soil.tif"` | bề dày lớp đất yếu (m), hệ toạ độ bất kỳ |
| Lỗ khoan | `[postprocess.geology] boreholes = "geom/boreholes.csv"` | cột `lon, lat, thickness_m`; nội suy nghịch đảo khoảng cách (luỹ thừa 2, 8 lỗ gần nhất) trong phạm vi `max_borehole_km` = 3 km |
| Lưới mở | mặc định (`open_fallback = true`) | Pelletier và cs. (2016), bề dày trầm tích trên đá gốc ở vùng thấp, 1 km, giới hạn 50 m; NASA ORNL DAAC (Earthdata) |

Lưới mở không phải là lớp đất yếu. Nó là chiều sâu tới đá gốc theo mô hình. Ở vùng châu thổ, phần lớn ô chạm giới
hạn 50 m, và phân tích ghi rõ điều này trong cảnh báo.

Với Hà Nội, lớp cần quan tâm là sét và than bùn Holocen của các hệ tầng Hải Hưng và Thái Bình, dày tới khoảng 35 m.
Bản đồ bề dày và bộ số liệu lỗ khoan có trong các công trình đã công bố nhưng chưa ở dạng dữ liệu mở:
- BGS và các đối tác Việt Nam: 271 lỗ khoan và một mô hình 3D;
- Phi & Strokova (2017).

### 3.2 Phân tích

Với mỗi ô của phân vùng (`analyses/geology/<sản phẩm>/`):

- **Bề dày** của ô theo nguồn.
- **Tốc độ theo lớp bề dày** (phân vị): tốc độ trung vị của các ô đang lún và tỷ lệ ô dịch chuyển nhanh hơn
  `moving_mm_yr` = 5. Hệ số Spearman ρ giữa bề dày và tốc độ lún tóm tắt mối quan hệ.
- **Kiểm tra cố kết.** Với các ô cố kết (`geoeyes consolidation`), số hạng đầu của lời giải Terzaghi cho
  τ = 4·H_dr² / (π²·c_v), suy ra c_v = 4·H_dr² / (π²·τ). H_dr = H/2 khi lớp thoát nước hai mặt. Sét yếu có
  c_v ≈ 0,1–10 m²/năm (Holtz & Kovacs 1981). Giá trị nằm xa ngoài khoảng này nghĩa là:
  - bề dày không phải của lớp đang cố kết; hoặc
  - ô đó không thực sự cố kết.

### 3.3 Trong mô hình tính nhạy cảm

Bề dày là biến dự báo `soft_soil_m` của mô hình tính nhạy cảm (nhóm "địa chất"). Đổi nguồn trong dự án thì các lớp
được dựng lại.

## 4. Kết quả đầu tiên

### 4.1 Tách thành phần, Mexico City (Sentinel-1 asc 078 + Capella asc)

| | Sentinel-1 asc 078 | Capella asc |
|---|---|---|
| Thời gian | 2024-05-03 → 2024-10-30 | 2024-06-26 → 2024-08-15 (50 ngày) |
| LOS (l_e, l_n, l_u) | (−0,69; −0,15; 0,71) | (+0,47; −0,46; 0,75) |

Hai cảm biến nhìn từ hai phía ngược nhau nên cặp này tách được. Kết quả trên vùng chung:

- 1.731 ô chung 100 m;
- thẳng đứng −295 đến +79 mm/năm;
- đông–tây −121 đến +92 mm/năm;
- σ trung vị: 1,5 mm/năm (thẳng đứng), 2,1 mm/năm (đông–tây).

**Kết quả này không đáng tin.** Bản đồ thẳng đứng chia vùng làm hai: phía bắc lún nhanh hơn −30 mm/năm, phía nam
"nâng" hơn +30 mm/năm. Bản đồ đông–tây cũng có một gradient quy mô lớn tương tự. Cả hai đều là dấu hiệu điển hình
của một mặt nghiêng (do quỹ đạo hoặc khí quyển) trong vận tốc ước tính từ 50 ngày dữ liệu Capella. Chúng không phải
chuyển dịch của nền đất.

σ hình thức không tính các sai số như vậy, nên con số "chuyển dịch đông–tây đáng kể ở 88 % số ô" không nói gì về nền
đất. Cặp Mexico City chỉ cho thấy phương pháp chạy được, chưa phải là một kết quả. Cần một chuỗi Capella phủ cùng
thời gian với Sentinel-1.

Hướng nhìn của Capella còn có thành phần bắc lớn (l_n = −0,46). Với cặp này, giả định n = 0 yếu hơn so với hai quỹ
đạo Sentinel-1.

### 4.2 Tách thành phần, Hà Nội (Sentinel-1 desc 091 + asc 128)

Quỹ đạo lên 128, cùng vùng và cùng thời gian với quỹ đạo xuống 91, đã được thêm vào dự án `hanoi_s1`:

| | Sentinel-1 desc 091 (v4) | Sentinel-1 asc 128 (v1) |
|---|---|---|
| Thời gian | 2025-10-01 → 2026-10-15 | 2025-10-04 → 2026-10-18 |
| Số điểm | 729.552 | 718.106 |
| LOS (l_e, l_u) | (+0,62; 0,78) | (−0,65; 0,76) |

**Mặt nghiêng trong sản phẩm quỹ đạo lên.** Mặt phẳng khớp với vận tốc của mỗi sản phẩm trên vùng chung chênh
3,9 mm/năm với desc 091 và **26,9 mm/năm** với asc 128 (R² 0,11 so với 0,60). Một độ nghiêng thật của nền sẽ hiện
giống nhau ở cả hai hướng nhìn (l_u ≈ 0,77 ở cả hai), nên độ nghiêng chỉ có ở asc 128 là sai số: do quỹ đạo, hoặc
khí quyển còn sót sau hiệu chỉnh ERA5. Nếu tách thành phần nguyên trạng, mặt nghiêng này biến thành chuyển dịch
đông–tây:
- đông–tây từ −11,7 đến +11,4 mm/năm (p2–p98);
- "đáng kể" ở 41 % số ô;
- E và U tương quan −0,80.

GeoEyes giờ tự phát hiện mặt nghiêng như vậy và cảnh báo. Với Hà Nội, mặt phẳng được khử trước khi tách
(`deramp = "plane"` trong dự án). Kết quả trên 12.658 ô chung 100 m:

| | Không khử mặt nghiêng | Có khử mặt nghiêng |
|---|---|---|
| Thẳng đứng, p2 … p98 (nhỏ nhất) | −11,8 … +12,4 | **−10,3 … +5,9** (−27,5) mm/năm |
| Đông–tây, p2 … p98 | −11,7 … +11,4 | −6,9 … +7,6 mm/năm |
| Ô có đông–tây "đáng kể" | 41 % | 18 % |
| Tương quan E / U | −0,80 | −0,59 |
| Phép chiếu thẳng đứng một hình học lệch (90 % số ô) | 7,7 / 8,4 mm/năm | 4,8 / 5,2 mm/năm |

**Phần đông–tây còn lại có thật không?** Hai phép thử:
- Nó tập trung quanh các ô lún nhanh: 41 % số ô lún nhanh hơn 10 mm/năm, so với 7 % số ô ổn định. Điều này sẽ
  phù hợp với nền đất dịch về phía tâm phễu lún.
- Nhưng nó **không** hướng về các ô lún. Trong khoảng 0,1–1,5 km quanh một ô lún nhanh, 48–53 % số ô dịch về phía
  ô đó, tức là ngẫu nhiên.

Vì vậy đây là phần bất đồng còn lại giữa hai sản phẩm (khí quyển không phẳng, mở pha). Một sai số ở một hướng nhìn
lan vào cả e và u, nên nó cũng tập trung ở nơi chuyển dịch lớn.

Nhiễu thực của e nên đọc từ các ô ổn định: trung vị |e| = 1,8 mm/năm, tức σ_e ≈ 2,7 mm/năm, gấp khoảng bốn lần
giá trị hình thức 0,64. Chỉ nên đọc chuyển dịch đông–tây lớn hơn khoảng 5–8 mm/năm.

**Những gì giữ lại cho Hà Nội:**
- Thành phần thẳng đứng sau khi tách: lún tối đa −27 mm/năm, các vùng lún khớp với sản phẩm quỹ đạo xuống.
- Phép chiếu thẳng đứng của một sản phẩm sai khoảng 5 mm/năm (90 % số ô). Đây là cận trên, vì nó gồm cả nhiễu
  của phép tách.
- Không đo được chuyển dịch ngang ở độ chính xác này.
- Mặt nghiêng của asc 128 có nguồn gốc tầng điện ly (xem dưới); chưa hiệu chỉnh thì không nên dùng riêng sản phẩm
  này.

**Nguồn gốc mặt nghiêng: tầng điện ly lúc chạng vạng.** Năm phép kiểm tra (script trong phiên làm việc, dữ liệu
trong workspace):

| Kiểm tra | Kết quả | Ý nghĩa |
|---|---|---|
| Tham số xử lý của hai lần chạy PS | giống hệt nhau | không phải do thiết lập |
| Mặt nghiêng của từng thành phần pha, quy ra vận tốc (asc 128) | pha đã mở ~20 mm/năm; hiệu chỉnh ERA5 1,7; sai số DEM 2,7; nhiễu tương quan 0,7 | có sẵn trong giao thoa đồ; không do ERA5, không do sai số DEM |
| Mặt nghiêng của từng giao thoa đồ | asc 2,0 mm/km (trung vị), desc 0,8; chủ yếu theo hướng bắc–nam; giảm dần từ thu 2025 đến thu 2026 | sai số nằm ở các lần chụp quỹ đạo lên, theo hướng bay |
| Giờ chụp; TEC thẳng đứng trên Hà Nội từ GIM (CODE IONEX, CDDIS) | asc 11:06 UTC = **18:06 giờ địa phương**, 39–111 TECU; desc 22:50 UTC = 05:50, 8–19 TECU | quỹ đạo lên gặp tầng điện ly mạnh gấp khoảng 6 lần |
| Độ dịch phương vị ESD theo ngày (chồng ảnh) | asc trung bình 0,035 dòng, desc 0,013; ESD so với mặt nghiêng bắc–nam: asc **r = −0,56 (p = 0,003)**, desc r = +0,19 (p = 0,37) | gradient tầng điện ly theo phương vị (bắc–nam) vừa làm lệch các burst TOPS vừa uốn pha |

Hà Nội nằm dưới đỉnh phía bắc của dị thường ion hoá xích đạo (EIA). Sau hoàng hôn, gần cực đại của chu kỳ mặt trời
25, lượng điện tử ở đây cao và thay đổi nhanh theo vĩ độ. Các lần chụp quỹ đạo lên (18:06) gặp đúng lúc này, quỹ đạo
xuống (05:50) thì không.

Mặt nghiêng của từng ngày thay đổi trong năm (TEC cao hơn vào thu 2025, thấp hơn trong 2026). Xu thế của chúng trở
thành mặt nghiêng trong vận tốc. Loại trừ được nguyên nhân quỹ đạo: cả hai quỹ đạo đều dùng quỹ đạo chính xác, trừ
ngày chụp lên cuối cùng (quỹ đạo phục hồi).

GIM với ô 2,5° × 5° không phân giải được gradient trên 15 km: mặt nghiêng nó dự đoán nhỏ hơn 15 lần và không tương
quan với mặt nghiêng đo được. Nó chỉ cho biết mức TEC.

**Hiệu chỉnh.** Cách làm đúng là tách phổ theo cự ly (range split-spectrum; Gomba và cs. 2016; Liang & Fielding
2017): hai giao thoa đồ băng con tách được phần pha tán sắc (tầng điện ly). Chồng ảnh lưu SLC đã khử pha hình học,
nên phải tính lại chính xác pha hình học từ quỹ đạo trước khi tách: khoảng một nửa sai số của nó sẽ lọt vào ước tính
tầng điện ly. Trong lúc chờ, khử một mặt phẳng theo từng ngày hoặc trên vận tốc (`deramp = "plane"`) loại được phần
dạng mặt phẳng, cùng với mọi độ nghiêng thật của vùng.

**Xử lý lại (2026-10-26 … 28).** Sau đó tách phổ được đưa vào khâu dựng chồng ảnh (`ionosphere = "split"`), và quỹ
đạo lên 128 được xử lý lại nhiều lần:
- v2: mặt phẳng chỉ trên vùng cắt;
- v3: mặt phẳng cục bộ trên toàn burst (trọng số Gauss 10 km quanh vùng cắt).

Khi đã khử tầng điện ly, lộ ra lỗi thứ hai: một **bậc thẳng 6–10 mm/năm dọc chỗ nối IW2/IW3** (góc tới 41,78°, song
song hướng bay). Quỹ đạo xuống chỉ có IW2 và không có bậc ở đó. Đây không phải đứt gãy lộ trên mặt. Ở 9/25 ngày,
giao thoa đồ của IW3 lệch một hằng số khoảng −2,2 rad so với IW2 (các ngày khác ±0,2 rad). Đó đúng là các ngày ESD
của hai dải con lệch nhau +0,012 dòng. Khâu ghép kiểu cắt rồi dán biến hằng số đó thành bậc, và chuỗi thời gian biến
nó thành vận tốc.

Nguyên nhân gốc chưa rõ. Bậc không theo vệ tinh (S1A/S1D), phiên bản IPF, cách cắt burst, thời gian hay Doppler.

Cách sửa, trong khâu ghép:
- **v4:** đo bậc pha qua từng chỗ nối theo từng ngày (hai dải 40 cột, trọng số độ kết hợp, khối 32 dòng) và khử
  trước khi ghép.
- **v6:** lấy dải con rộng nhất làm mốc, và trừ cùng bậc đã đo đó khỏi băng con thấp của từng dải trước khi tách phổ
  (`WideArea.shift`). Nếu không, một hằng số c không phụ thuộc tần số sẽ lọt a·c (a ≈ 0,5) vào ước tính tầng điện ly.
- **v5 (bỏ):** ước lượng bậc như một hằng số tự do cho mỗi dải con trong mô hình tầng điện ly. Kết quả ±4,6 rad, cả ở
  những ngày không có bậc, vì hằng số này trao đổi với gradient cự ly.

Cùng một script cho mọi sản phẩm; bậc = trung vị vận tốc trong 0,08° góc tới mỗi bên chỗ nối; gx, gy = mặt phẳng
khớp trên toàn vùng (mm/năm/km); E–U = tách thành phần với desc 091 v4:

| | Bậc ở chỗ nối | gx | gy | Độ lệch chuẩn | σ trung vị | E–U có khử phẳng: ngang / tương quan | E–U không khử: ngang / tương quan |
|---|---|---|---|---|---|---|---|
| v1 (chưa hiệu chỉnh) | +8,0 | +0,75 | −1,50 | 8,17 | 3,92 | 17,8 % / −0,59 | 41 % / −0,80 |
| v3 (tầng điện ly) | +9,6 | +0,22 | −0,79 | 6,34 | 4,38 | | |
| v4 (+ chỗ nối) | +0,9 | −0,58 | −0,92 | 5,75 | 4,08 | 5,6 % / −0,26 | 17,1 % / −0,59 |
| v6 (+ trừ bậc khỏi băng con) | +1,4 | −0,49 | −0,77 | 5,21 | 3,89 | **4,2 % / −0,16** | 11,5 % / −0,51 |
| desc 091 v4 | — | −0,02 | −0,20 | 3,92 | 2,64 | | |

Nên dùng v6. Vẫn còn khoảng −0,8 mm/năm/km theo hướng Bắc–Nam mà quỹ đạo xuống không có. Chuyển dịch Bắc–Nam gần như
không vào hướng nhìn của cả hai quỹ đạo, nên đây vẫn là sai số của quỹ đạo lên. Nó không phải tầng điện ly còn sót:
theo từng ngày, nó gần như không tương quan với gradient tầng điện ly đã khử (r = 0,18), dao động gấp mười lần sai số
hình thức của ước lượng đó, và lớn nhất vào mùa hè. Nhiều khả năng là đối lưu chiều tối mà ERA5 không bắt được
([guide/ionosphere.md §6](../guide/ionosphere.md#6-trường-hợp-hà-nội)). Giữ `deramp = "plane"` khi tách thành phần.

Với `support = "points"` (20 m), có 572.309 vị trí với phân bố tương tự (trước khi khử mặt nghiêng: σ_up 1,0,
σ_e 1,2 mm/năm hình thức).

### 4.3 Bề dày đất yếu (lưới mở) so với tốc độ lún

| Sản phẩm | Ô chạm giới hạn 50 m | Spearman ρ (bề dày – tốc độ lún) | Tốc độ trung vị theo lớp bề dày |
|---|---|---|---|
| Mexico City S1 | 59 % | **0,51** | 0–9 m: −97; 9–49 m: −116; 49–50 m: −204 mm/năm |
| Hà Nội S1 | 92 % | −0,11 | một lớp (27–50 m): −2,6 mm/năm |
| Hà Nội CSK | 82 % | 0,01 | một lớp |

**Mexico City.** Ngay cả lưới mở thô cũng tách được lòng hồ (dày, chạm giới hạn) khỏi các dãy núi lửa (mỏng). Các ô
lún nhanh gấp đôi ở nơi trầm tích dày nhất.

**Hà Nội.** Lưới gần như chạm giới hạn ở mọi nơi nên không cho thông tin gì. Cần một bản đồ bề dày Holocen.

**Kiểm tra cố kết.** c_v suy ra của các ô cố kết là 830–1.000 m²/năm ở mọi sản phẩm, gấp khoảng 100 lần khoảng giá
trị của sét yếu. Với H là chiều sâu tới đá gốc (50 m), τ ngắn (0,25 năm) của các ô này không thể là cố kết của cả
cột đất. Có hai cách hiểu:
- chúng cố kết một lớp mỏng gần mặt (đất đắp, vài mét);
- chúng không thực sự cố kết.

Phép kiểm tra hoạt động đúng như mong muốn: nó loại một bề dày không thể là lớp đang cố kết.

### 4.4 Tính nhạy cảm có bề dày đất yếu

AUC theo kiểm định chéo không gian, có và không có lớp `soft_soil_m` (lưới mở). Mọi lớp và thiết lập khác giữ
nguyên.

| Sản phẩm | Mô hình | Không có | Có |
|---|---|---|---|
| Mexico City S1 | gradient boosting (được chọn) | 0,869 | **0,918** |
| | random forest | 0,777 | 0,894 |
| | logistic | 0,729 | 0,851 |
| Hà Nội S1 | gradient boosting (được chọn) | 0,718 | **0,734** |
| | random forest | 0,717 | 0,732 |
| | logistic | 0,698 | 0,708 |

- **Mexico City:** bề dày trở thành biến dự báo quan trọng nhất (độ quan trọng hoán vị 0,15, so với 0,06 của biến
  kế tiếp).
- **Hà Nội:** mức tăng nhỏ. Nó đến từ rìa lưới, nơi bề dày xuống dưới giới hạn, và không phản ánh lớp đất yếu.

## 5. Hạn chế

- **Thời gian.** Phép tách giả định các sản phẩm thấy cùng một chuyển dịch. Thời gian của chúng phải chồng nhau; nếu
  không, vận tốc được giả định không đổi và có cảnh báo.
- **Bắc–nam.** Chuyển dịch bắc–nam bị bỏ qua; với cảm biến nhìn xiên (Capella), một phần của nó lọt vào e và u.
- **Kết quả tương đối.** Kết quả là tương đối so với trung vị của vùng chung. Cần gắn với một trạm GNSS để có giá trị
  tuyệt đối; phép gắn GNSS của phân vùng là theo từng sản phẩm và chưa được chuyển sang đây.
- **Độ bất định hình thức.** Độ bất định không tính mặt nghiêng hay khí quyển khác nhau giữa các sản phẩm, và chuỗi
  ngắn bị ảnh hưởng nhiều nhất.
- **Lưới mở.** Bề dày từ lưới mở chỉ giữ chỗ. Quan hệ ở Mexico City cho thấy bề dày quan trọng, không cho thấy lưới
  là đúng; ở Hà Nội nó không mang thông tin.
- **Nội suy lỗ khoan.** Nội suy nghịch đảo khoảng cách không vẽ được địa chất giữa các lỗ khoan: lòng sông cổ và mép
  thềm cần có bản đồ.

## 6. Trình tự nghiên cứu

| Bước | Nội dung |
|---|---|
| D1 | Hà Nội asc 128 + desc 091: thẳng đứng và đông–tây trong cùng một năm; sai số một hình học của phân vùng |
| D2 | Dùng thành phần thẳng đứng sau khi tách cho phân vùng, tuyến và công trình ở nơi có hai hình học |
| D3 | Gắn GNSS cho phép tách (vận tốc ngang của trạm), và thành phần bắc từ hình học thứ ba |
| D4 | Tách chuỗi thời gian trên các mốc tháng chung |
| D5 | Hiệu chỉnh tầng điện ly bằng tách phổ theo cự ly trong bước dựng chồng ảnh (pha hình học chính xác từ quỹ đạo); trước tiên cho Hà Nội asc 128, sau đó cho mọi sản phẩm chụp lúc chạng vạng gần dị thường xích đạo |
| G1 | Bề dày đất yếu Holocen của Hà Nội: số hoá một bản đồ đã công bố (ví dụ Phi & Strokova 2017) hoặc xin số liệu lỗ khoan (mô hình 3D của BGS, Trường Đại học Mỏ – Địa chất) |
| G2 | Tốc độ lún so với bề dày trên bản đồ thật; c_v của các ô cố kết so với số liệu thí nghiệm |
| G3 | Số liệu quan trắc mực nước ngầm (mạng quan trắc quốc gia) cùng bề dày: độ lún trên mỗi mét hạ cột nước |

## 7. Tài liệu tham khảo

- Gomba, G., Parizzi, A., De Zan, F., Eineder, M., & Bamler, R. (2016). Toward operational compensation of
  ionospheric effects in SAR interferograms: the split-spectrum method. *IEEE Transactions on Geoscience and Remote
  Sensing*, 54(3), 1446–1461.
- Liang, C., & Fielding, E. J. (2017). Measuring azimuth deformation with L-band ALOS-2 ScanSAR interferometry.
  *IEEE Transactions on Geoscience and Remote Sensing*, 55(5), 2725–2738.
- Fuhrmann, T., & Garthwaite, M. C. (2019). Resolving three-dimensional surface motion with InSAR: constraints
  from multi-geometry data fusion. *Remote Sensing*, 11(3), 241.
- Holtz, R. D., & Kovacs, W. D. (1981). *An Introduction to Geotechnical Engineering*. Prentice-Hall.
- Pelletier, J. D., và cs. (2016). A gridded global data set of soil, intact regolith, and sedimentary deposit
  thicknesses for regional and global land surface modeling. *Journal of Advances in Modeling Earth Systems*, 8,
  41–65. Dữ liệu: ORNL DAAC, doi:10.3334/ORNLDAAC/1304.
- Phi Hồng Thịnh, & Strokova, L. A. (2017). [Trầm tích Đệ tứ, mặt cắt địa chất công trình và bản đồ bề dày đất yếu
  của Hà Nội; tiếng Nga]. *Izvestiya Tomskogo Politekhnicheskogo Universiteta*, 328(4).
- Terzaghi, K. (1925). *Erdbaumechanik auf bodenphysikalischer Grundlage*. Deuticke, Vienna.
- Wright, T. J., Parsons, B. E., & Lu, Z. (2004). Toward mapping surface deformation in three dimensions using
  InSAR. *Geophysical Research Letters*, 31, L01607.
