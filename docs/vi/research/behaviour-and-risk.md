> Bản dịch tiếng Việt của [`docs/en/research/behaviour-and-risk.md`](../../en/research/behaviour-and-risk.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-10-26.

# Kiểu chuyển dịch và rủi ro công trình

Trạng thái: đã triển khai v1 ngày 2026-10-26.
Mã nguồn: `geoeyes.ml.behaviour` (`geoeyes behaviour`), `geoeyes.ml.risk` (`geoeyes risk`), `geoeyes.api.behaviour`.
Ứng dụng web: các lớp "Kiểu chuyển dịch", "Thời điểm thay đổi" và "Rủi ro công trình" trên trang Phân tích chuyên đề;
chương 3 của trang Nguyên lý.
Liên quan: [rainfall-insar-hazard.md](rainfall-insar-hazard.md) (phân vùng nguy cơ mà các phân tích này xuất phát; bước
R6 "từ nguy cơ đến rủi ro" trong kế hoạch nghiên cứu của ghi chú đó).

## Mục lục

1. [Câu hỏi](#1-câu-hỏi)
2. [Kiểu chuyển dịch](#2-kiểu-chuyển-dịch)
3. [Rủi ro công trình](#3-rủi-ro-công-trình)
4. [Kết quả đầu tiên](#4-kết-quả-đầu-tiên)
5. [Hạn chế](#5-hạn-chế)
6. [Trình tự nghiên cứu](#6-trình-tự-nghiên-cứu)
7. [Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

## 1. Câu hỏi

Phân vùng nguy cơ đánh giá mỗi ô 100 m bằng một con số là tốc độ, kết hợp với hậu quả mà chuyển dịch có thể gây ra cho
công trình. Còn hai câu hỏi bỏ ngỏ:

- **Q1. Mỗi nơi chuyển dịch ra sao?** Lún đều, mới bắt đầu lún, dao động theo mùa hay lún chậm dần đều đòi hỏi cách xử
  lý khác nhau, dù có thể có cùng một tốc độ.
- **Q2. Nguy cơ đó có ý nghĩa gì với những gì nằm trên mặt đất?** Một bãi đất trống và một trường học cùng lún nhanh có
  cùng mức nguy cơ nhưng rủi ro rất khác nhau.

## 2. Kiểu chuyển dịch

### 2.1 Các mô hình

Chuỗi của mỗi ô (chuỗi của phân vùng, `cells_ts.npy`, theo quy ước dấu GeoEyes) được khớp bằng bình phương tối thiểu
với bảy mô hình, mỗi mô hình có một ý nghĩa vật lý:

| Kiểu | Mô hình | Ý nghĩa |
|---|---|---|
| ổn định | d = a | không chuyển dịch vượt ngưỡng ổn định của phân vùng |
| đều | d = a + b·t | tốc độ không đổi: nén chặt tầng chứa nước, từ biến |
| theo mùa | d = a + b·t + c·sin 2πt + e·cos 2πt | chu kỳ năm chồng lên xu thế: bổ cập và khai thác nước, giãn nở nhiệt |
| tăng tốc | d = a + b·t + c·t², \|tốc độ\| tăng | chuyển dịch mạnh lên |
| chậm dần | d = a + b·t + c·t², \|tốc độ\| giảm | cố kết sau khi chịu tải |
| khởi phát | d = a + b·t + h·(t − t₀)₊ | đổi tốc độ tại t₀: tải mới, giếng mới, kết thúc thi công |
| bước nhảy | d = a + b·t + δ·H(t − t₀) | cú nhảy tại t₀: sự kiện đột ngột, hoặc lỗi giải chập pha |

Cách tiếp cận dựa trên phương pháp tự động phân loại chuỗi thời gian PS của Berti et al. (2013), nhưng dùng lựa chọn mô
hình thay cho chuỗi phép kiểm định thống kê của các tác giả.

- Tăng tốc và chậm dần so sánh độ lớn tốc độ ở cuối chuỗi với ở đầu chuỗi, nên chúng theo chiều chuyển dịch của chính
  ô, dù là lún hay nâng.
- Mô hình theo mùa cần khoảng một năm dữ liệu (`min_span_seasonal_yr` = 0,9).

### 2.2 Lựa chọn mô hình

Mô hình nhiều tham số hơn luôn khớp tốt hơn một chút. Các mô hình được so sánh bằng tiêu chí thông tin Bayes
(Schwarz 1978):

    BIC = n · ln(RSS / n) + k · ln n

- Mô hình phức tạp hơn chỉ được chọn khi làm BIC giảm ít nhất `min_delta_bic` = 6 so với đường thẳng, mức mà Kass &
  Raftery (1995) gọi là bằng chứng mạnh.
- Nếu không, ô được xếp là đều, hoặc ổn định khi tốc độ tuyến tính dưới ngưỡng ổn định của phân vùng
  (max(2 mm/năm, 2σ)).
- Với khởi phát và bước nhảy, lần chụp xảy ra thay đổi là một tham số (k có tính tham số này). Mọi lần chụp đều được
  thử, chừa `edge_epochs` = 3 lần chụp ở mỗi đầu.
- Mọi ô được khớp cùng lúc (bình phương tối thiểu vector hoá): vài phần mười giây cho 45.000 ô.

### 2.3 Thay đổi chung cho nhiều ô

Mặt đất hiếm khi thay đổi khắp nơi vào cùng một ngày. Một lần chụp có khí quyển mạnh hoặc lỗi giải chập pha sẽ làm nhiều
ô dịch theo cùng lúc. Một ngày bị gắn cờ (`shared_change_dates`, kèm cảnh báo) khi số thay đổi (khởi phát hoặc bước
nhảy) vào ngày đó vừa đạt 5 lần trung vị số thay đổi mỗi ngày (và ít nhất 20 ô), vừa chiếm một phần tư tổng số thay
đổi. Khởi phát và bước nhảy vào ngày đó được coi là vấn đề dữ liệu trước đã. Ứng dụng web không dùng chúng làm ví dụ.

### 2.4 Đầu ra

`analyses/behaviour/<sản phẩm>/`:

- `behaviour.parquet`: mỗi ô của phân vùng một dòng, cùng thứ tự. Các cột: kiểu, thời điểm thay đổi, tốc độ trước
  và sau, gia tốc, biên độ theo mùa, bước nhảy, ΔBIC.
- `behaviour_fit.npy`: mô hình được chọn của từng ô.
- `behaviour.json`: số ô theo kiểu, số thay đổi theo tháng, các ngày bị gắn cờ, cảnh báo.

## 3. Rủi ro công trình

Rủi ro là sự kết hợp giữa nguy cơ, những gì phơi nhiễm với nó và mức tổn thất của chúng (theo thuật ngữ UNDRR 2016).

### 3.1 Nguy cơ H (0–4)

- **Từ điểm InSAR trên chính công trình** (geoeyes buildings), khi có ít nhất `min_points_own` = 5 điểm tán xạ bền
  vững trên nền phẳng:
  - cường độ tính từ tốc độ thẳng đứng của công trình, theo các lớp của phân vùng;
  - tổn hại tiềm tàng tính từ độ nghiêng β của chính công trình khi có ý nghĩa, nếu không thì từ góc biến dạng của ô
    chứa nó;
  - mức nguy cơ theo ma trận của phân vùng.
- **Từ ô phân tích** trong các trường hợp còn lại: mức của ô chứa tâm công trình.
- **Chưa đánh giá:** các công trình nằm ngoài mọi ô.
- Mỗi công trình ghi lại nguồn (`source`).

### 3.2 Mức phơi nhiễm E (1–3)

- Diện tích sàn = diện tích chiếm đất × số tầng, đại diện cho số người và giá trị bên trong.
- Số tầng lấy từ chiều cao trong Overture (3 m một tầng). Khi thiếu chiều cao, dùng số tầng trung vị của các công
  trình có chiều cao trong khu vực.
- E1 < 300 m² ≤ E2 < 3.000 m² ≤ E3.

### 3.3 Mức dễ tổn thương V (1–3)

Loại kết cấu và móng, vốn quyết định độ dễ hư hại của công trình (Peduto et al. 2017), không có trong dữ liệu mở. Các
đại lượng thay thế là kích thước và độ mảnh:

- **V3:** cao ≥ 21 m (7 tầng), hoặc dài (√diện tích chiếm đất) ≥ 30 m. Công trình dài nằm trên nhiều lún lệch hơn;
  công trình cao biến một độ nghiêng nhỏ thành độ lệch lớn ở đỉnh (Burland & Wroth 1974).
- **V1:** công trình nhỏ (< 60 m²) và thấp tầng.
- **V2:** các công trình còn lại.

### 3.4 Hậu quả và rủi ro

| C = HẬU_QUẢ[E][V] | V1 | V2 | V3 |
|---|---|---|---|
| E1 | 1 | 1 | 2 |
| E2 | 1 | 2 | 3 |
| E3 | 2 | 3 | 3 |

| R = RỦI_RO[H][C] | C1 | C2 | C3 |
|---|---|---|---|
| H0 rất thấp | 0 | 0 | 1 |
| H1 thấp | 0 | 1 | 1 |
| H2 trung bình | 1 | 2 | 2 |
| H3 cao | 2 | 3 | 4 |
| H4 rất cao | 3 | 4 | 4 |

Mọi ngưỡng đều là tham số (`[postprocess.risk]`). Các mức là mức sàng lọc, không phải đánh giá kết cấu.

### 3.5 Đầu ra

`analyses/risk/<sản phẩm>/`:

- `risk.parquet`: mỗi công trình Overture một dòng. Các cột: mã Overture (GERS), vị trí, diện tích chiếm đất, chiều
  cao, số tầng, nguồn, số điểm riêng, tốc độ thẳng đứng, β, H, E, V, C, R.
- `risk.json`: số công trình theo mức và theo nguồn, tỉ lệ có chiều cao, cảnh báo.

## 4. Kết quả đầu tiên

Các lần chạy ngày 2026-10-26 với tham số mặc định.

**Kiểu chuyển dịch** (ô 100 m):

| Sản phẩm | Số lần chụp | Ổn định | Đều | Theo mùa | Tăng tốc | Chậm dần | Khởi phát | Bước nhảy | Ngày bị gắn cờ |
|---|---|---|---|---|---|---|---|---|---|
| Hà Nội S1 v4, 2025-10 → 2026-10 | 26 | 11.639 | 2.732 | 308 | 5 | 25 | 194 | 168 | 2026-09-09 |
| Mây Chai S1 v1, 2025-10 → 2026-10 | 24 | 7.357 | 2.025 | 10 | 0 | 2 | 20 | 11 | – |
| Mexico S1 v7, 2024-05 → 2024-10 | 16 | 975 | 42.371 | 0 | 38 | 66 | 544 | 225 | 2024-06-08 |
| Hà Nội CSK v3, 2011-07 → 2014-12 | 18 | 4.896 | 872 | 46 | 105 | 67 | 88 | 288 | 2014-01-10 |

- **Thành phố Mexico lún đều gần như khắp nơi.** 42.371 trong số 44.219 ô được phân loại là lún đều, đúng như dự kiến
  với quá trình nén chặt lớp sét hồ. Không có ô theo mùa vì chuỗi chỉ dài sáu tháng.
- **Hà Nội S1 phần lớn ổn định**, có 308 ô theo mùa trong một năm.
- **Mỗi sản phẩm có một ngày bị gắn cờ**, chiếm phần lớn số thay đổi: 171 ô vào ngày 2026-09-09 ở Hà Nội S1, 466 ô
  vào ngày 2024-06-08 ở Mexico. Đây là những lần chụp cần kiểm tra trước tiên.

**Rủi ro công trình:**

| Sản phẩm | Số công trình | Điểm riêng | Từ ô | Rất cao | Cao | Trung bình | Thấp | Rất thấp | Có chiều cao |
|---|---|---|---|---|---|---|---|---|---|
| Hà Nội S1 v4 | 450.198 | 8.268 | 350.904 | 1 | 6 | 1.023 | 16.470 | 341.672 | 2 % |
| Mexico S1 v7 | 1.663.658 | 21.329 | 1.311.046 | 27.321 | 345.439 | 888.714 | 11.651 | 46.942 | 0 % |

- **Mexico:** phần lớn công trình ở mức rủi ro trung bình hoặc cao. Điều này do nguy cơ (lún đều 100–350 mm/năm sau
  khi gắn vào GNSS) nhiều hơn là do bản thân công trình.
- **Hà Nội:** vùng của sản phẩm ổn định so với trung bình toàn cảnh, nên gần như mọi công trình có rủi ro rất thấp.
- **Chiều cao:** Overture hầu như không có chiều cao nhà ở hai vùng này, nên mức phơi nhiễm chỉ dựa vào diện tích chiếm
  đất.

## 5. Hạn chế

- **Chuỗi ngắn.** Một năm không đủ để tách chu kỳ mùa khỏi thay đổi xu thế, và sáu tháng (Mexico) không thể hiện được
  mùa. Các kiểu sẽ chắc chắn hơn sau mỗi lần chụp mới.
- **Bộ mô hình.** Một ô chậm dần rồi đổi chiều (nửa chu kỳ) có thể bị đọc là chậm dần; một ô có hai lần thay đổi chỉ
  giữ lần mạnh nhất.
- **Bước nhảy.** Một bước nhảy vài milimét giữa hai ngày chụp thường là lỗi giải chập pha hơn là chuyển dịch thật.
- **Nguy cơ của công trình.** Công trình đánh giá theo ô mang giá trị trung bình của 100 m; chỉ những công trình có
  điểm riêng (2 % ở Hà Nội, 1 % ở Mexico) mới được đánh giá riêng.
- **Phơi nhiễm và dễ tổn thương.** Đây là các đại lượng thay thế: không có chiều cao, loại kết cấu, móng hay số người
  sử dụng. Bản đồ rủi ro cho biết nên kiểm tra ở đâu, không cho biết cái gì sẽ nứt.

## 6. Trình tự nghiên cứu

- **B1 — Khởi phát so với thi công.** Đối chiếu thời điểm khởi phát với giấy phép xây dựng và ngày thi công (công
  trình mới gây tải trên đất yếu: kỳ vọng thấy khởi phát rồi chậm dần). Tiêu chí: phần lớn khởi phát ở khu xây dựng xảy
  ra trong vòng một năm sau khi có giấy phép.
- **B2 — Chuỗi dài hơn.** Chạy lại trên chồng ảnh Sentinel-1 nhiều năm (từ 2016). Tiêu chí: kiểu theo mùa xuất hiện ở
  nơi mực nước dao động (bờ sông ở Hà Nội).
- **R1 — Chiều cao.** Bổ sung chiều cao từ Google Open Buildings 2.5D, mô hình đô thị hoặc lidar, để mức phơi nhiễm
  phân biệt được nhà thấp tầng với nhà cao tầng.
- **R2 — Kiểm chứng bằng hư hại.** Khảo sát vết nứt trên một số tuyến phố mẫu và so sánh với β và mức rủi ro. Tiêu
  chí: mức hư hại tăng theo mức rủi ro, như trong các đường cong dễ hư hại thực nghiệm (Peduto et al. 2017).
- **R3 — Loại kết cấu.** Bổ sung loại kết cấu từ hồ sơ địa chính hoặc khảo sát thực địa, và thay đại lượng thay thế
  của mức dễ tổn thương bằng đường cong dễ hư hại theo từng loại.

## 7. Tài liệu tham khảo

- Berti, M., Corsini, A., Franceschini, S., Iannacone, J. P. (2013). Automated classification of Persistent
  Scatterers Interferometry time series. *Natural Hazards and Earth System Sciences* 13, 1945–1958.
- Bjerrum, L. (1963). Allowable settlement of structures. *Proceedings of the 3rd European Conference on Soil
  Mechanics and Foundation Engineering*, Wiesbaden, 2, 135–137.
- Burland, J. B., Wroth, C. P. (1974). Settlement of buildings and associated damage. *Proceedings of the
  Conference on Settlement of Structures*, Cambridge, 611–654.
- Kass, R. E., Raftery, A. E. (1995). Bayes factors. *Journal of the American Statistical Association* 90(430),
  773–795.
- Peduto, D., Nicodemo, G., Maccabiani, J., Ferlisi, S. (2017). Multi-scale analysis of settlement-induced building
  damage using damage surveys and DInSAR data: a case study in The Netherlands. *Engineering Geology* 218,
  117–133.
- Schwarz, G. (1978). Estimating the dimension of a model. *The Annals of Statistics* 6(2), 461–464.
- Skempton, A. W., MacDonald, D. H. (1956). The allowable settlements of buildings. *Proceedings of the Institution
  of Civil Engineers* 5(6), 727–768.
- UNDRR (2016). Report of the open-ended intergovernmental expert working group on indicators and terminology
  relating to disaster risk reduction. United Nations General Assembly, A/71/644.
