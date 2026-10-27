# Hạ tầng tuyến và lún cố kết

Trạng thái: bản v1 đã triển khai ngày 2026-10-26.
Mã nguồn: `geoeyes.ml.lines` (`geoeyes lines`), `geoeyes.ml.consolidation` (`geoeyes consolidation`),
`geoeyes.api.behaviour`.
Ứng dụng web: lớp "Hạ tầng tuyến" và "Lún còn lại" trên trang Phân tích chuyên đề; trang Nguyên lý, chương 4.
Liên quan: [rainfall-insar-hazard.md](rainfall-insar-hazard.md) (phân vùng và các giới hạn hư hại dùng ở đây) và
[behaviour-and-risk.md](behaviour-and-risk.md) (các kiểu chuyển dịch; "chậm dần" là dạng mà cố kết mô tả chính xác).

## Mục lục

1. [Câu hỏi](#1-câu-hỏi)
2. [InSAR dọc hạ tầng tuyến](#2-insar-dọc-hạ-tầng-tuyến)
3. [Lún cố kết](#3-lún-cố-kết)
4. [Kết quả đầu tiên](#4-kết-quả-đầu-tiên)
5. [Hạn chế](#5-hạn-chế)
6. [Trình tự nghiên cứu](#6-trình-tự-nghiên-cứu)
7. [Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

## 1. Câu hỏi

- **Q3. Đê, đường sắt và đường chính bị uốn ở đâu?** Đây là các công trình dài và liên tục. Điều gây hại cho chúng
  không hẳn là bản thân độ lún, mà là lún thay đổi dọc tuyến:
  - chỗ trũng trên đỉnh đê là nơi nước tràn qua đầu tiên;
  - chỗ trũng dưới đường ray làm cong ray.
- **Q4. Nền đất sẽ còn lún ở đâu, và bao nhiêu?** Đất yếu dưới tải mới lún tiến dần tới một điểm dừng. Khai thác
  nước ngầm thì làm nền lún chừng nào còn bơm. Hai trường hợp này đòi hỏi hai cách ứng xử khác nhau.

## 2. InSAR dọc hạ tầng tuyến

### 2.1 Các tuyến

Các tuyến trong vùng sản phẩm lấy từ OpenStreetMap qua Overpass API. Kết quả được lưu đệm trong workspace, tại
`cache/osm/overpass_<hash>.json`. Có bốn loại tuyến:

| Loại | Thẻ OSM |
|---|---|
| đê | `man_made=dyke`, hoặc đường có tên bắt đầu bằng "Đê " (đê sông Hồng ở Hà Nội được vẽ như phố) |
| nền đắp | đường có `embankment=yes` |
| đường sắt | `railway=rail` |
| đường chính | `highway=motorway / trunk / primary` (khi `roads = true`) |

Các đoạn cùng loại, cùng tên (hoặc `ref`) và chung nút đầu mút được nối thành một tuyến.

### 2.2 Trạm

Đặt trạm cách nhau `step_m` = 50 m dọc mỗi tuyến. Mỗi trạm lấy trung vị vận tốc thẳng đứng của các điểm tán xạ
bền vững trong bán kính `buffer_m` = 30 m, khi có ít nhất `min_points` = 3 điểm:

    v_đứng = v_LOS / l_u        (quy ước GeoEyes: âm = lún)

Phép chiếu thẳng đứng giả định không có chuyển dịch ngang. Ở nơi ghép hai hình học quỹ đạo, thành phần thẳng đứng
tách ra từ hai hình học sẽ tốt hơn.

### 2.3 Lún lệch

Giữa hai trạm cách nhau `span_m` = 100 m, góc biến dạng sau khoảng thời gian T = `horizon_yr` = 10 năm là:

    β = |v(x + L) − v(x)| · T / L

β được so với các giới hạn hư hại của phân vùng (Skempton & MacDonald 1956; Bjerrum 1963):

| β | Ý nghĩa |
|---|---|
| < 1/500 | dưới giới hạn an toàn |
| 1/500 – 1/300 | vượt giới hạn an toàn |
| 1/300 – 1/150 | nứt |
| ≥ 1/150 | hư hại kết cấu |

Với đê, cao trình đỉnh đê mất đi sau T năm là |min v|·T. Độ cao an toàn so với lũ thiết kế giảm đúng chừng ấy.

Kết quả, trong `analyses/lines/<sản phẩm>/`:

- `stations.parquet`: tuyến, lý trình, vị trí, số điểm, v_đứng, β, cấp β;
- `lines.parquet`: loại, tên, chiều dài, tỷ lệ có dữ liệu, vận tốc thấp nhất và trung vị, β lớn nhất, số trạm vượt
  ngưỡng, đỉnh đê hạ;
- `lines.json`: tóm tắt theo loại và 20 tuyến có β lớn nhất.

## 3. Lún cố kết

### 3.1 Mô hình

Cố kết sơ cấp (Terzaghi 1925) lún nhanh lúc đầu, rồi chậm dần. Ở bậc một:

    s(t) = c + A · (1 − e^(−t/τ))

- lún cuối cùng = c + A;
- lún còn lại sau ngày chụp cuối T: A · e^(−T/τ);
- đạt 90 % của A tại τ · ln 10.

Độ lún của mỗi ô là s = −d, đặt bằng 0 tại ngày đầu. τ được thử trên lưới 80 giá trị từ 0,05 đến 30 năm (cấp số
nhân), và (c, A) được tìm bằng bình phương tối thiểu cho mỗi τ.

Một ô được coi là **cố kết** khi thoả cả các điều kiện sau:

- ô lún ít nhất `min_rate_mm_yr` = 2 mm/năm, ở chế độ sụt lún;
- đường cong tốt hơn đường thẳng với ΔBIC ≥ `min_delta_bic` = 6 ("bằng chứng mạnh", Kass & Raftery 1995);
- A > 0;
- τ nhỏ hơn `max_tau_factor` = 5 lần độ dài chuỗi dữ liệu. Lớn hơn thế, τ không xác định được.

### 3.2 Asaoka

Asaoka (1978) đọc cùng đường cong đó bằng đồ thị. Các số đọc cách đều Δt thoả sᵢ = β₀ + β₁ · sᵢ₋₁, với
β₁ = e^(−Δt/τ). Đường thẳng này cắt đường sᵢ = sᵢ₋₁ tại độ lún cuối cùng β₀ / (1 − β₁).

Ứng dụng web vẽ biểu đồ này cho mỗi ô, với số đọc lấy lại cách đều (một phần tám độ dài chuỗi, từ 12 đến 60 ngày). Đây là một cách nhìn độc lập trên cùng dữ
liệu, không phải một lần khớp thứ hai dùng để phân loại.

### 3.3 Kiểm chứng

Kiểm chứng là một dự báo. Đường cong và đường thẳng cùng được khớp trên `train_share` = 70 % số ngày đầu, và cùng
dự báo phần còn lại. `consolidation.json` ghi:

- sai số tuyệt đối trung bình của mỗi cách;
- tỷ lệ ô mà đường cong thắng.

Các ô được chọn vì đường cong khớp tốt, nên kiểm chứng có lợi cho đường cong. Nó cho biết đường cong có dự báo được
hay không, chứ không cho biết việc chọn là đúng.

Kết quả, trong `analyses/consolidation/<sản phẩm>/`:

- `consolidation.parquet`: với mỗi ô, có cố kết hay không, τ, đã lún, lún cuối cùng, lún còn lại, thời gian tới
  90 % tính từ nay, c, A, ΔBIC;
- `consolidation.json`: tóm tắt.

## 4. Kết quả đầu tiên

### 4.1 Các tuyến

| Sản phẩm | Tuyến | Trạm | Đê | Đường sắt | Nền đắp | Đường chính |
|---|---|---|---|---|---|---|
| Hà Nội S1 desc 091, 2025-10 → 2026-10 | 582 | 13.696 | 15,7 km, 21 % có dữ liệu, 0 vượt | 71,4 km, 41 %, 0 | 60,7 km, 44 %, 0 | 507,9 km, 52 %, 1 |
| Mexico City S1 asc 078, 2024-05 → 2024-10 | 570 | 20.001 | không có trên bản đồ | 83,2 km, 39 %, 65 | 22,4 km, 26 %, 7 | 866 km, 50 %, 612 |

"Vượt" là số trạm vượt 1/500.

**Hà Nội.** Chỉ một trạm vượt 1/500, trên đường Đỗ Mười (β 1/446, vận tốc thấp nhất −17,7 mm/năm). Đê trên bản đồ
chỉ dài 15,7 km, và chỉ 21 % trong đó có điểm InSAR. Muốn đọc đê sông Hồng, trước hết phải bổ sung tuyến đê (tuyến
đê chính thức, hoặc số hoá đỉnh đê), và bổ sung cả độ phủ radar (gương phản xạ góc, hoặc hình học thứ hai).

**Mexico City.** Đây là vùng sụt lún kinh điển trên sét hồ. Các tuyến có góc biến dạng lớn nhất cắt qua mép phễu
lún:

| Tuyến | Loại | β lớn nhất | Vận tốc thấp nhất | Trạm vượt |
|---|---|---|---|---|
| Autopista México – Puebla | đường | 1/127 | −62 mm/năm | 16 |
| Calzada General Ignacio Zaragoza | đường | 1/148 | −217 mm/năm | 34 |
| Calzada Ermita Iztapalapa | đường | 1/150 | −93 mm/năm | 31 + 34 (hai chiều đường) |
| Línea VK | đường sắt | 1/154 | −204 mm/năm | 39 |

Các vị trí này phù hợp với hư hại đã được ghi nhận dọc Zaragoza, Ermita Iztapalapa và trên tuyến Metro số A. Việc
so sánh với hồ sơ hư hại là bước L4 (§6).

### 4.2 Cố kết

| Sản phẩm | Số ngày | Ô đang lún | Ô cố kết | Lún còn lại (trung vị / lớn nhất) | τ trung vị | Kiểm chứng: đường cong / thẳng |
|---|---|---|---|---|---|---|
| Hà Nội S1 | 26 (1 năm) | 4.355 | 4 | 0,2 / 0,3 mm | 0,25 năm | 2,5 / 6,5 mm |
| Hà Nội CSK | 18 (3,5 năm) | 745 | 4 | 0 / 0 mm | 0,24 năm | 2,7 / 6,0 mm |
| Mây Chai S1 | 24 (1 năm) | 3.485 | 0 | – | – | – |
| Mexico City S1 | 16 (0,5 năm) | 43.277 | 30 | 25 / 45 mm | 0,27 năm | 14,1 / 26,4 mm |

Như dự kiến, rất ít ô đạt điều kiện. Phần lớn quá trình cố kết kéo dài nhiều năm đến nhiều chục năm, và một năm dữ
liệu chỉ thấy phần đầu. Khi τ lớn hơn nhiều so với độ dài chuỗi, đường cong không phân biệt được với đường thẳng.

Các ô ở Hà Nội đạt điều kiện với τ ngắn, và độ lún gần như đã xong. Có thể đọc chúng là các khu đắp mới đã gần kết
thúc lún.

30 ô ở Mexico City đến từ chuỗi sáu tháng. τ ≈ 0,27 năm, khoảng một nửa độ dài đó. Hai cách giải thích khác cũng
khả dĩ như cố kết:

- lún do khai thác nước chậm lại theo mùa;
- một tải trọng mới.

Cần kiểm tra với chuỗi dài hơn trước khi diễn giải.

Ở mọi sản phẩm, kiểm chứng đều nghiêng về đường cong trên tất cả các ô được chọn. Điều này là do cách chọn (§3.3).

## 5. Hạn chế

- **Độ đầy đủ của OSM.** Đường sắt và đường chính được vẽ đầy đủ. Đê thì không: nhiều đoạn đê không có, hoặc chỉ
  có con đường trên đỉnh đê.
- **Độ phủ.** Mái đê (cỏ, cây) và nhiều nền đắp cho ít điểm tán xạ bền vững. Đoạn xám là thiếu dữ liệu, không phải
  ổn định.
- **Vận tốc tương đối.** Vận tốc là tương đối so với điểm tham chiếu của sản phẩm. Chúng chỉ là thẳng đứng khi giả
  định không có chuyển dịch ngang.
- **β mang tính cục bộ.** β giữa hai trạm cách nhau 100 m phát hiện các chỗ uốn ở thang đó. Một chỗ uốn dài, thoải
  trên nhiều km không bị đánh dấu, kể cả khi nó hạ đỉnh đê; trường hợp đó đã có đại lượng đỉnh đê hạ.
- **Chuỗi ngắn.** Muốn nhận ra cố kết, chỗ uốn của đường cong phải nằm trong dữ liệu. Lún cuối cùng và t90 sẽ chắc
  chắn hơn sau mỗi năm chụp thêm.
- **Nén thứ cấp.** Từ biến sau cố kết sơ cấp vẫn tiếp diễn, gần tuyến tính theo log thời gian. Mô hình chưa tính
  phần này, nên ở nơi từ biến đáng kể, lún cuối cùng là cận dưới.

## 6. Trình tự nghiên cứu

| Bước | Nội dung |
|---|---|
| L1 | Bổ sung tuyến đê: tuyến đê chính thức của sông Hồng (Sở Nông nghiệp Hà Nội), hoặc số hoá đỉnh đê từ DEM |
| L2 | Đo thuỷ chuẩn dọc một tuyến đê và một tuyến đường sắt: kiểm chứng vận tốc trạm và β |
| L3 | Trắc dọc từ thành phần thẳng đứng tách từ hai hình học, ở nơi đã ghép |
| L4 | Hồ sơ hư hại (bảo trì đường ray, sửa đường) so với β của từng tuyến |
| C1 | Chuỗi dài hơn (3 năm trở lên của Sentinel-1 hoặc COSMO-SkyMed) trên các khu đô thị mới: phía tây Hà Nội, Gia Lâm |
| C2 | Ngày thi công và chiều cao đắp gần các ô cố kết; lỗ khoan để biết bề dày sét yếu |
| C3 | Phương pháp hyperbol (Tan 1971) và thành phần từ biến, so với mô hình hàm mũ trên cùng các ô |

## 7. Tài liệu tham khảo

- Asaoka, A. (1978). Observational procedure of settlement prediction. *Soils and Foundations*, 18(4), 87–101.
- Bjerrum, L. (1963). Allowable settlement of structures. *Proc. 3rd European Conf. Soil Mech. Found. Eng.*,
  Wiesbaden, 2, 135–137.
- Kass, R. E., & Raftery, A. E. (1995). Bayes factors. *Journal of the American Statistical Association*, 90(430),
  773–795.
- OpenStreetMap contributors. Dữ liệu theo giấy phép Open Database License (ODbL); © OpenStreetMap contributors.
- Skempton, A. W., & MacDonald, D. H. (1956). The allowable settlements of buildings. *Proc. Instn Civ. Engrs*,
  5(6), 727–768.
- Tan, S. B. (1971). An empirical method for estimating secondary and total settlement. *Proc. 4th Asian Regional
  Conf. Soil Mech. Found. Eng.*, Bangkok, 2, 147–151.
- Terzaghi, K. (1925). *Erdbaumechanik auf bodenphysikalischer Grundlage*. Deuticke, Vienna.
