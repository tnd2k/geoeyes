# Sườn dốc đang hoạt động dọc QL6 — khoanh vùng tự động từ InSAR: thiết kế và kế hoạch

> Kế hoạch, 2026-11-13. Câu hỏi của chủ dự án: *với kết quả của ql6_km124_141, có thể tự động khoanh vùng có nguy
> cơ trượt lở không?* Trả lời cùng ngày: được một phần — InSAR khoanh được **những sườn đang chuyển động chậm và vệ tinh
> nhìn thấy**; nó không nói gì ở chỗ không nhìn thấy, và trượt đá / sập taluy nhanh thường chuyển động quá ít trước khi
> xảy ra. Kế hoạch dựng một sản phẩm nói rõ cả hai: sườn *đang hoạt động* theo InSAR, và sườn *không đo được* theo hình
> học và địa hình, kiểm chứng với các điểm trượt đã khảo sát. Các bước Q0–Q7, mỗi bước kết thúc bằng duyệt của chủ dự
> án. Q1 bắt đầu ngày 2026-11-13.

## Mục lục

1. [Hiện trạng](#1-hiện-trạng)
2. [Sản phẩm là gì, không là gì](#2-sản-phẩm-là-gì-không-là-gì)
3. [Phương pháp](#3-phương-pháp)
4. [Tiêu chí chấp nhận](#4-tiêu-chí-chấp-nhận)
5. [Kế hoạch Q0–Q7](#5-kế-hoạch-q0q7)
6. [Rủi ro và giới hạn](#6-rủi-ro-và-giới-hạn)
7. [Tài liệu tham khảo](#7-tài-liệu-tham-khảo)

## 1. Hiện trạng

- **Dữ liệu.** Dự án `ql6_km124_141`: S1 asc 128 frame 64, 103 ngày 2023-01..2026-10, PSDS (phase linking [3, 9],
  DA 0,6, DS coherence 0,5, ERA5, GLO-30), sản phẩm v7 (`scla_deramp = auto`, đã bỏ mặt phẳng xu hướng): khoảng
  1,24 triệu điểm. Track descending 91 frame 522 đã khai báo, chưa xử lý trước 2026-11-13.
- **Phân tích sườn hiện có.** `hazard.terrain`: độ dốc và hướng dốc nhất từ GLO-30, độ nhạy của LOS với chuyển động
  xuôi dốc, vùng nhìn thấy (dốc ≥ 10°, |độ nhạy| ≥ 0,3, không layover / shadow), vận tốc xuôi dốc. Bản đồ web: loại
  vận tốc "slope". Một phân tích tạm (`analyses/slope_v7_zones.csv`) cho 18 vùng ≥ 10 điểm với vận tốc xuôi dốc ≥ 5
  mm/năm; tất cả đều yếu (5–8 mm/năm, khoảng 2 lần nhiễu).
- **Số liệu thực địa.** Khảo sát VIPHAP ngày 2026-06-03 (`inventories/landslide/surveys/ql6_viphap_2026.geojson`):
  7 điểm Km118+600..147+450, 4 điểm nằm trên đoạn đã phân tích (Km124+300, 125+940, 128+400, 129+500). Km chính thức
  = lý trình OSM + 14,2 km.
- **Kiểm tra đầu tiên (2026-11-13), các vùng được tạo mà không nhìn số liệu khảo sát.** Khoảng cách từ mỗi điểm khảo
  sát tới vùng gần nhất: 30 m (Km129+500), 98 m (Km124+300), 210 m (Km128+400), 617 m (Km125+940). Trong 100 m: 2/4
  điểm, so với 7 % các điểm ngẫu nhiên trên đường (nhị thức p ≈ 0,03); trong 300 m: 3/4 so với 34 %. Có tín hiệu
  thật, nhưng chỉ 4 điểm: chưa phải bằng chứng.

## 2. Sản phẩm là gì, không là gì

**Là** bản đồ các đơn vị sườn dọc đường, chia bốn lớp, mỗi lớp kèm lý do:

| Lớp | Ý nghĩa |
|---|---|
| **Đang hoạt động** | InSAR đo được chuyển động xuôi dốc vượt nhiễu (§3.4), đủ điểm, nhất quán theo thời gian và, nơi cả hai track cùng thấy, nhất quán ở cả hai hình học |
| **Không đo được, dễ trượt** | sườn dốc hoặc taluy cắt (§3.5) mà không track nào thấy (layover, shadow, chuyển động vuông góc LOS) hoặc không có điểm coherent (rừng) |
| **Đo được, ổn định** | nhìn thấy, đủ điểm, không có chuyển động vượt nhiễu |
| **Thấp** | dốc thoải, xa taluy |

**Không là** dự báo sạt, thời điểm sạt hay phạm vi trượt. Trượt nhanh (đá rơi, sập taluy) vẫn có thể xảy ra ở đơn vị
"đo được, ổn định". Chiều thời gian thuộc về hệ thống dự báo
([`landslide-forecast-system.md`](landslide-forecast-system.md)); sản phẩm này sau có thể làm một yếu tố điều chỉnh
cho hệ thống đó.

## 3. Phương pháp

### 3.1 Hai hình học (Q1)

Track descending 91 (burst 091_194267/194268 IW3, khoảng 110 ngày) xử lý với thiết lập của asc v7 (PSDS, cùng cửa sổ
phase linking, ERA5, `scla_deramp auto`, geolocation off). Hai track thấy những sườn khác nhau: Km124+300 (hướng sườn
253°) cho LOS ascending 21 % chuyển động xuôi dốc, LOS descending 78 %. QC: ramp dư, geolocation so với mô phỏng biên
độ / DEM, độ lệch giữa hai track trên vùng ổn định chung.

### 3.2 Vùng nhìn thấy (Q2)

Với mỗi ô địa hình 30 m và mỗi track: độ nhạy LOS với chuyển động xuôi dốc, góc tới cục bộ (layover / shadow), mật độ
điểm coherent. Hợp lại thành bản đồ "asc / desc / cả hai / không track nào thấy"; đơn vị không track nào thấy không thể
là "đo được, ổn định".

### 3.3 Vận tốc xuôi dốc từ hai track (Q3)

Điểm của hai track gộp trên lưới chung 50 m (cỡ một taluy). Giả thiết chuyển động theo hướng dốc nhất (một ẩn d), mỗi
track cho v_LOS = s · d (s = độ nhạy): có cả hai thì d là nghiệm bình phương tối thiểu có trọng số, và phần dư kiểm tra
giả thiết (dư lớn = chuyển động không theo sườn, hoặc nhiễu giả). Một track: d = v_LOS / s khi |s| ≥ 0,3, gắn cờ
"một hình học". Phân tách đứng / đông-tây (`geoeyes decompose`) cũng được tính cho báo cáo.

### 3.4 Vùng hoạt động (Q4)

Theo phương pháp vùng biến dạng hoạt động (ADA; Barra et al. 2017; Tomás et al. 2019):
- **nhiễu**: σ của d trên các ô nhìn thấy, coherent, dốc thoải xa đường (hoặc thị trấn Mai Châu), theo từng track;
- **ngưỡng**: |d| ≥ k·σ, k cố định ở Q0 (đề xuất 2), và sai số của chính ô đó nhỏ hơn ngưỡng;
- **gom cụm**: các ô hoạt động kề nhau (≤ 50 m) gộp lại; một vùng cần ≥ N điểm (đề xuất 10) và ≥ 3 ô;
- **chỉ số chất lượng** 1–4: nhiễu, mức cô lập, mức đồng thuận hai track, độ nhất quán chuỗi thời gian;
- **chuỗi thời gian**: tuyến tính / tăng tốc / bước nhảy (các lớp của `geoeyes behaviour`), ngày thay đổi.

Đầu ra: `zones.gpkg` (đa giác, diện tích, trung vị d kèm khoảng tin cậy, số điểm, hình học nhìn thấy, chất lượng, kiểu
chuyển động, km chính thức, khoảng cách tới đường).

### 3.5 Lớp tĩnh (Q5)

Trên cùng các ô: độ dốc, taluy cắt (vùng đệm đường 50 m và dốc ≥ 35°, hoặc chỗ gãy dốc sát đường), độ cong, diện tích
thượng lưu, lớp phủ (WorldCover), địa chất (GLiM; bản đồ 1:50.000 nếu có), và độ nhạy trượt của nghiên cứu trượt lở
([`landslide-susceptibility.md`](landslide-susceptibility.md)) nơi mô hình chuyển giao được. Các lớp này quyết định
"dễ trượt" cho những đơn vị InSAR không đo được.

### 3.6 Kết hợp (Q5)

Bốn lớp của §2 từ (nhìn thấy, vùng hoạt động, dễ trượt). Không chỉnh trọng số theo số liệu khảo sát: bốn điểm không đủ
để khớp một mô hình.

## 4. Tiêu chí chấp nhận

Cố định ngay bây giờ, trước khi chạy Q4; báo cáo kèm số điểm đứng sau mỗi tiêu chí.

| # | Tiêu chí | Mục tiêu |
|---|---|---|
| Q-A1 | Điểm khảo sát trên đoạn nằm trong đơn vị "đang hoạt động" hoặc "không đo được, dễ trượt" (trong 100 m) | ≥ 3/4, và cao hơn ngẫu nhiên (hoán vị các điểm dọc đường, p < 0,05) |
| Q-A2 | Tỉ lệ chiều dài đường bị gắn "đang hoạt động" | ≤ 15 % (cảnh báo phủ cả con đường thì không nói lên điều gì) |
| Q-A3 | Vùng "đang hoạt động" được xác nhận bằng kiểm tra thực địa hoặc ảnh (một mẫu các vùng ngoài khảo sát) | ≥ 50 % có dấu hiệu (nứt, vách trượt, tường nghiêng, chỗ đã sửa) |
| Q-A4 | Hai track đồng thuận nơi cả hai cùng thấy một vùng (cùng dấu, độ lớn trong 2σ) | ≥ 70 % các vùng đó |
| Q-A5 | Tái lập: cùng đầu vào cho cùng các vùng; thời gian chạy trên đoạn | có; ≤ 10 phút khi đã có sản phẩm |

Nếu một tiêu chí không đạt, báo cáo nói rõ và sản phẩm phát hành kèm giới hạn đó, không chỉnh cho đến khi đạt.

## 5. Kế hoạch Q0–Q7

| Bước | Nội dung | Đầu ra | Cổng duyệt |
|---|---|---|---|
| **Q0** Cơ sở | Cố định §4 và các ngưỡng §3.4; rà soát dữ liệu trượt (7 điểm VIPHAP với kiểu và ngày; thêm danh mục tin tức của nghiên cứu dự báo, vết trượt Sentinel-2 sau mưa 2025, hồ sơ của chủ dự án); mức ngẫu nhiên bằng hoán vị | `q0_baseline.md` | chủ dự án ký §4 |
| **Q1** Descending | Track 91 PSDS như asc v7; QC (ramp, geolocation, độ lệch giữa hai track) | sản phẩm desc v1, ghi chú QC | QC đạt |
| **Q2** Vùng nhìn thấy | bản đồ asc / desc / cả hai / không track nào ở 30 m; số điểm mỗi ô | `visibility.tif`, tỉ lệ đoạn đường được nhìn thấy | chủ dự án duyệt |
| **Q3** Vận tốc xuôi dốc | lưới chung 50 m; bình phương tối thiểu hai track kèm phần dư; dự phòng một track; phân tách | `downslope.gpkg` | duyệt bản đồ phần dư |
| **Q4** Vùng hoạt động | nhiễu, ngưỡng, gom cụm, chỉ số chất lượng, kiểu chuyển động | `zones.gpkg`, `q4_zones.md` | Q-A1, Q-A2, Q-A4 |
| **Q5** Lớp tĩnh và phân lớp | taluy cắt, địa hình, lớp phủ, địa chất, độ nhạy trượt; bốn lớp | `slope_units.gpkg` | chủ dự án duyệt bản đồ |
| **Q6** Kiểm chứng | Q-A1..A4 kèm khoảng tin cậy; danh sách kiểm tra thực địa / ảnh cho các vùng chưa khảo sát; báo cáo độ nhạy theo k và N (không chỉnh) | `q6_verification.md` | chủ dự án quyết định sử dụng |
| **Q7** Tự động hoá | `geoeyes slopes <project>` (vùng + phân lớp + báo cáo), lớp web, cập nhật khi có ngày mới; sau đó cả hành lang (xử lý hành lang K2–K3) | lệnh, tài liệu | A5, chủ dự án |

## 6. Rủi ro và giới hạn

- **Trượt nhanh.** Đá rơi và sập taluy thường không có dấu hiệu báo trước đo được ở băng C; "đo được, ổn định" không
  bao giờ có nghĩa là an toàn. Ghi trên mọi bản đồ.
- **Rừng.** 86 % che phủ cây: nhiều sườn không có điểm coherent → "không đo được", không phải "ổn định".
- **Hình học.** Một track chỉ thấy một phần chuyển động của sườn (21 % ở Km124+300 với ascending); sườn chạy dọc hướng
  bay thì cả hai track đều thấy kém.
- **Ít điểm kiểm chứng.** Bốn điểm trên đoạn: Q-A1 có độ mạnh kiểm định thấp; Q-A3 (kiểm tra thực địa / ảnh) gánh phần
  chính, và thêm dữ liệu trượt (Q0) là con đường tới kiểm định mạnh hơn.
- **Ramp và tầng đối lưu.** Các vùng yếu (5–8 mm/năm) gần với ramp dư và trễ phân tầng trên khoảng 900 m chênh cao; σ
  nhiễu ở §3.4 đo sau khi đã xử lý chúng, và sự đồng thuận hai track (Q-A4) là hàng rào chặn chúng.
- **Ổ đĩa.** Dữ liệu thô descending khoảng 32 GB cộng stack; ổ D còn 112 GB ngày 2026-11-13.

## 7. Tài liệu tham khảo

Trích từ trí nhớ ngày 2026-11-13; số tập và trang sẽ kiểm tra trên Crossref ở Q0.

- Barra, A. et al. (2017). A methodology to detect and update active deformation areas based on Sentinel-1 SAR images.
  *Remote Sensing* 9(10), 1002.
- Tomás, R. et al. (2019). Semi-automatic identification and pre-screening of geological–geotechnical deformational
  processes using persistent scatterer interferometry datasets. *Remote Sensing* 11(14), 1675.
- Notti, D. et al. (2014). A methodology for improving landslide PSI data analysis. *International Journal of Remote
  Sensing* 35(6), 2186–2214 (R-index, khả năng nhìn thấy sườn).
- Cascini, L. et al. (2010). Advanced low- and full-resolution DInSAR map generation for slow-moving landslide
  analysis at different scales. *Engineering Geology* 112, 29–42.
