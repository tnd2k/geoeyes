# Skill: điểm ngập được báo cáo so với sụt lún, và dự báo ngập trong ngày

> Bản dịch của [docs/en/skills/flood-reports.md](../../en/skills/flood-reports.md). Dịch ngày 2026-11-01.

> Nơi thành phố ngập có phải nơi nền đất đang lún? Lưu các điểm ngập được công bố chính thức ở TP.HCM và Hà Nội thành
> một bản kiểm kê đã định vị, đọc vận tốc của sản phẩm quanh từng điểm, và xem dự báo 24 giờ minh bạch từ mưa dự báo,
> triều và sụt lún. Trạng thái: vận hành (bản kiểm kê, bản đồ, dự báo); dự báo chỉ để tham khảo, không phải dự báo
> ngập. Kiểm tra lần cuối 2026-11-01. CLI: `geoeyes floods import | locate | list`. Web app: Explorer → nút
> **Reported floods** trên thanh công cụ (bản đồ, chú thích khi rê chuột, khung **FLOOD OUTLOOK · 24 H**); có cả trong
> trình biên tập bản đồ.

## 1. Khi nào dùng

- Để đặt các điểm mà thành phố công bố là ngập (CSGT PC08, Sở Xây dựng TP.HCM; bản tin của Công ty Thoát nước Hà Nội)
  cạnh chuyển dịch InSAR: điểm ngập có nằm trên nền lún nhanh hơn xung quanh không?
- Để giữ một bản kiểm kê chung cho cả không gian làm việc, sửa được bằng Excel, dựng và định vị lại sau mỗi danh sách
  mới.
- Để có một chỉ số "điểm này hôm nay dễ ngập đến đâu" giải thích được, từ các nguồn dự báo miễn phí.
- Không dùng để lập bản đồ phạm vi hay độ sâu ngập (điểm báo cáo chỉ là một vị trí, thường là chỗ trũng trên đường),
  và không dùng như dịch vụ cảnh báo: không có mô hình thuỷ lực, không có hệ thống thoát nước, không có trạm đo. Muốn
  biết diện tích ngập và số dân bị ảnh hưởng, xem [exposure-and-flood-layers.md](exposure-and-flood-layers.md).

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Văn bản công bố | có | chép danh sách từ bài chính thức (PC08 Công an TP.HCM, Sở Xây dựng; Công ty Thoát nước Hà Nội) | tệp văn bản UTF-8 đặt ở đâu cũng được, truyền cho `geoeyes floods import <file>` | giữ nguyên tiêu đề ("mưa", "triều") và gạch đầu dòng `-` / `+`; bản tin Hà Nội viết thành câu: dùng `--prose` |
| Thông tin của danh sách | nên có | bài báo | `--reported YYYY-MM-DD`, `--source "<đơn vị>"`, `--url <bài>` | là một phần của mã dòng: nhập lại cùng danh sách không thêm gì |
| Vùng | có | `hcmc` (mặc định) hoặc `hanoi` | `--region` | chỉ có hai vùng được khai báo (`REGIONS`: khung tìm kiếm và tên thành phố) |
| Bản kiểm kê | được tạo ra | `geoeyes floods import` | `<workspace>/inventories/flood/<region>.csv` (UTF-8 có BOM, mở được bằng Excel) | sửa được; `geom_wkt` ghi đè cách định vị |
| Bản kiểm kê đã định vị | được tạo ra | `geoeyes floods locate` | `<workspace>/inventories/flood/<region>.geojson` | cache các trả lời của OSM và Nominatim trong `<workspace>/cache/osm/flood/` |
| Sản phẩm InSAR | tuỳ chọn | `geoeyes run` | hiển thị trên bản đồ Explorer (sản phẩm trên cùng) | vận tốc quanh mỗi điểm; điểm cộng sụt lún của dự báo |
| Mạng | có | Overpass (`overpass-api.de`), Nominatim (1 yêu cầu/giây), Open-Meteo forecast và Marine | — | chỉ cần cho `locate` và dự báo |

Không đọc các nguồn cấm việc này (nuoclen.com cấm truy cập tự động trong `robots.txt`).

Danh sách kiểm tra:

- [ ] Tệp văn bản là UTF-8, giữ tiêu đề và gạch đầu dòng.
- [ ] Với Hà Nội dùng `--region hanoi` (và `--prose` cho bản tin của Công ty Thoát nước); TP.HCM là mặc định.
- [ ] Đã có `--reported`, `--source`, `--url`.
- [ ] Sau khi nhập, chạy `locate` **với cùng `--region`** (lệnh này cũng mặc định `hcmc`).
- [ ] Đã xem các dòng `ambiguous` hoặc `none`; điền `geom_wkt` nơi đã biết vị trí.

## 3. Phương pháp

### 3.1 Nhập (`parse_list`, `parse_prose`, `parse_item`)

- **Nguyên nhân**: dòng tiêu đề (không có gạch đầu dòng) chứa "mưa" → `rain`, "triều" → `tide`, cả hai → `rain_tide`;
  `--cause` đặt một nguyên nhân cho cả tệp; `--prose` mặc định `rain`.
- **Nhóm**: `- Đường X:` mở một nhóm; các dòng `+` tiếp theo, và các dòng `-` bắt đầu bằng "Đoạn", "Giao", "Từ",
  "Hướng", "Trước", "Số", đều thuộc đường X.
- **Loại**: "Đường A, (đoạn) từ B đến|về|ra|tới C" → `segment`; "Giao lộ A - B", "Ngã tư A - B", "Đường A - B", "Giao
  B" dưới đường A → `junction`; "Số 69 Trịnh Thị Dối", "Trước số 139" → `address`; "Đường X", "Quốc lộ 50" →
  `street`; còn lại → `place`. Phường trong ngoặc ("(phường Tam Bình)") ghi vào `ward`; ngoặc khác ghi vào `notes`.
- **Văn xuôi** (Hà Nội): phần trước dấu ":" (lưu vực, nếu ngắn hơn 60 ký tự) ghi vào `notes`; các mục tách theo "," và
  ";" ngoài ngoặc; tên trơn là một đường phố; "A – B" là nút giao; "(từ … đến …)" thành đoạn đường; địa danh trong
  ngoặc đặt dòng lên đường đó, gần địa danh; mục "phường/xã …" được gộp vào mục trước.
- **Mã dòng** = 10 ký tự hex đầu của SHA-1 của `region|cause|text|reported|source`; mã đã có thì bỏ qua.

### 3.2 Định vị (`locate`, `Locator`)

- Tên đường (và các biến thể: "30-4" → "30 tháng 4", "ĐT744" → "đt 744", "tỉnh lộ 744", "QL1" → "quốc lộ 1", "35" ↔
  "số 35") được hỏi Overpass theo lô 25 tên (`name`, `alt_name`, `old_name`, `ref` của đường, có tiền tố
  "Đường/Phố/Ngõ"), lưu cache theo tên; địa danh hỏi Nominatim (giới hạn trong vùng, `countrycodes=vn`, cách nhau
  1,1 giây), lưu cache theo câu hỏi.
- **junction**: chỗ hai đường gặp nhau gần nhất trong `JUNCTION_TOL_M` = 40 m → `exact`; nếu không, hỏi Nominatim "A
  B" → `place`; nếu không → `none`.
- **segment**: mỗi đầu là nút giao với đường, nếu không thì là địa danh Nominatim cách đường không quá
  `ENDPOINT_TOL_M` = 400 m, chiếu lên đường. Có đủ hai đầu (cách nhau ≥ 5 m) thì lấy đoạn giữa chúng trên mọi phần của
  đường đó (cả hai chiều xe chạy; các phần cách nhau không quá `SAME_STREET_GAP_M` = 2 km là một đường) → `exact` nếu
  cả hai đầu là nút giao, ngược lại `approx`. Chỉ có một đầu → điểm đó, `approx`. Không đầu nào → cả tuyến đường.
- **street**: mọi phần của đường → `approx`. Khi tên có ở nhiều nơi: nếu một nhóm dài ≥ 2 km và ≥ `DOMINANT` = 4 lần
  nhóm kế tiếp thì lấy nhóm đó; nếu không thì lấy nhóm gần `ward` nhất (qua Nominatim), hoặc `ambiguous`.
- **address / place**: hỏi Nominatim "địa danh đường"; nếu cách đường không quá 400 m thì đặt lên đường → `place`;
  nếu không thì cả tuyến → `approx`.
- **geom_wkt** trong CSV → `manual`, không tìm kiếm.
- **Lượt thứ hai** cho `ambiguous`: lấy đường trùng tên gần trung vị các điểm đã định vị khác của cùng bản tin (cùng
  `reported`, `source` và ghi chú đầu, ít nhất 2 điểm), nếu trong 3 km → `approx`.

### 3.3 Vận tốc quanh một điểm (`near_product`)

Đường được làm dày điểm mỗi 10 m. Các điểm InSAR trong bán kính `radius_m` (mặc định API 100 m, chặn trong 20–1000 m;
Explorer dùng 100 m) cho `n`, `vel_median`, `vel_p10` và `rank` = tỉ lệ điểm của sản phẩm có vận tốc nhỏ hơn trung vị
(âm hơn = ra xa vệ tinh nhanh hơn). Vành `radius_m`…`ring_m` (500 m) cho `ring_median` và
`contrast = vel_median − ring_median`. Vận tốc là LOS (mm/năm) lấy từ cache điểm web của sản phẩm.

### 3.4 Dự báo (`flood_outlook`)

Cho 24 giờ tới tính từ giờ hiện tại (giờ địa phương, `Asia/Bangkok`):

- Mưa từ Open-Meteo (lượng mưa và xác suất theo giờ, dùng chung trên lưới 0,05°):
  `R = (0.5·min(rain_24h/50 mm, 1) + 0.5·min(max_hourly/25 mm, 1)) · (0.5 + 0.5·max_probability)`.
- Triều (chỉ TP.HCM, mực nước biển Open-Meteo Marine tại 107,08° E, 10,33° N, giá trị mô hình ngoài cửa sông):
  `T = clip((peak − median daily high of the last 30 days) / (highest of the last 30 days and next 3 − that median), 0, 1)`
  (mẫu số tối thiểu 0,1 m).
- `score = min(100, 100·(w_R·R + w_T·T) + bonus)`, trọng số theo nguyên nhân: mưa 0,8 / 0,2, triều 0,2 / 0,8, cả hai
  hoặc không rõ 0,5 / 0,5; Hà Nội (không có điểm triều) chỉ mưa 1,0 / 0. Điểm cộng +3 / +6 / +10 khi vận tốc trung vị
  quanh điểm ≤ −5 / −10 / −20 mm/năm. Cấp thành phố: mưa tại tâm thành phố, nguyên nhân `rain_tide` (Hà Nội
  `rain_only`), và vận tốc trung vị trên các điểm ngập của thành phố mà sản phẩm phủ tới (ít nhất 3).
- Mức: < 20 `low`, < 45 `watch`, < 70 `high`, còn lại `very_high`; lớp độ sâu `unlikely`, `< 20 cm`, `20–40 cm`,
  `> 40 cm` chỉ đi theo mức.
- Khung giờ rủi ro: các giờ mưa ≥ 2 mm với xác suất ≥ 40 % (nếu w_R ≥ 0,5) hoặc triều ≥ trung vị + 0,6·(biên độ)
  (nếu w_T ≥ 0,5).

## 4. Các bước triển khai

1. **Nhập danh sách.** `geoeyes floods import list.txt --reported 2026-10-06 --source "PC08 Công an TP.HCM" --url <article>`
   (TP.HCM), hoặc `geoeyes floods import bulletin.txt --prose --region hanoi --reported 2026-09-17 --source "Thoát nước Hà Nội"`.
   Chạy tức thì. Thêm dòng vào `inventories/flood/<region>.csv`; in số vị trí đọc được, số dòng mới, tổng số.
2. **Kiểm tra CSV** bằng Excel: `kind`, `street`, `from`, `to`, `cross` đúng như mong đợi; sửa câu chữ hoặc thêm
   `geom_wkt` (ví dụ `POINT (106.7012 10.7769)`, `LINESTRING (106.70 10.77, 106.71 10.78)`).
3. **Định vị.** `geoeyes floods locate --region <hcmc|hanoi>` → `inventories/flood/<region>.geojson`; in số dòng theo
   `located`. Lần đầu: các lô Overpass cộng khoảng một giây cho mỗi câu hỏi Nominatim mới; các lần sau đọc cache (vài
   giây).
4. **Liệt kê.** `geoeyes floods list`: mọi dòng đã định vị của mọi vùng (mã, nguyên nhân, cách định vị, ngày, văn bản).
5. **Web app.** Explorer → hiển thị một sản phẩm → **Reported floods**. Đường = đoạn đường, chấm = nút giao và địa
   danh; xanh dương là mưa, tím là triều, xanh ngọc là cả hai; mờ = định vị gần đúng. Rê chuột: số điểm trong 100 m,
   vận tốc trung vị, trung vị của vành. Khung **FLOOD OUTLOOK · 24 H** hiện cả thành phố hoặc điểm được bấm; tích "colour
   the spots by today's risk (else by cause)". Kết quả được lưu cache: vận tốc ở `cache/web/<product>/floods_r<radius>.json`
   (tính lại khi bản kiểm kê hoặc sản phẩm đổi), dự báo ở `cache/floods/` (30 phút).
6. **API.** `GET /api/floods`, `GET /api/projects/{name}/products/{pid}/floods?radius=100`,
   `GET /api/floods/outlook?project=&product=&radius=`.

## 5. Kết quả và cách đọc

- Cột của `<region>.csv`: `id, region, cause, kind, street, from, to, cross, place, ward, text, reported, source, url,
  depth_m, geom_wkt, notes`. `text` là câu chữ công bố, giữ nguyên văn.
- `<region>.geojson`: cùng các dòng với hình học (hoặc null) và `located` = `exact` | `place` | `approx` | `ambiguous`
  | `none` | `manual`.
- Mỗi điểm (API): `n`, `vel_median`, `vel_p10`, `rank`, `ring_n`, `ring_median`, `contrast`; cho cả tập:
  `product_median`, `n_located`, `n_with_points`, `median_of_rows`.
- Dự báo: mỗi điểm và mỗi thành phố có `score`, `level`, `depth`, `window`, `rain_24h_mm`, `rain_max_mm_h`,
  `rain_prob_max`, `tide_peak_m`, `tide_peak_time`, `parts` (R, T, trọng số, điểm cộng), `velocity_mm_yr`, mưa theo giờ.

Cách đọc: một điểm lún nhanh hơn vành xung quanh (`contrast` < 0) nói lên nhiều hơn một điểm lún như cả quận. Trên
nền phẳng, vận tốc LOS chủ yếu là thành phần thẳng đứng; tách riêng bằng
[decompose-and-soft-soil.md](decompose-and-soft-soil.md).

Hiện trạng bản kiểm kê (tệp ngày 2026-10-30): TP.HCM 134 dòng (mưa 83, triều 39, mưa và triều 12): 37 `exact`, 12
`place`, 68 `approx`, 8 `ambiguous`, 9 `none`. Hà Nội 94 dòng: 6 `exact`, 13 `place`, 50 `approx`, 15 `ambiguous`,
10 `none`.

## 6. Kiểm tra chất lượng

- Tỉ lệ dòng `exact` + `place`: chỉ dùng các dòng này để tính số liệu; `approx` cả tuyến đường trộn đoạn ngập với
  đoạn khô.
- Đã xem mọi dòng `ambiguous` và `none`; có hình học `manual` nơi biết vị trí.
- Kiểm tra vài đoạn `exact` trên bản đồ so với "từ B đến C" được công bố.
- Cần `n` ≥ 3 điểm trong bán kính mới nêu vận tốc của một điểm; so `median_of_rows` với `product_median` và với trung
  vị của vành, không so với 0 (điểm tham chiếu của sản phẩm có ảnh hưởng).
- Thẻ đầu của khung dự báo nói rõ đây chỉ là tham khảo; kiểm tra đã lấy được dự báo (lỗi sẽ báo "weather forecast
  unreachable").

## 7. Hạn chế và lỗi thường gặp

- Điểm báo cáo là nơi người ta thấy ngập, không phải vùng ngập; danh sách thiên về đường chính.
- Tên trên OSM thay đổi (tiền tố, số, tên cũ): tên không khớp thì để `none` chứ không đoán.
- `locate` mặc định `hcmc`: nhập danh sách Hà Nội rồi chạy `locate` mà thiếu `--region hanoi` thì Hà Nội không được
  cập nhật (`GET /api/floods` trả `regions[].stale` = true khi CSV mới hơn GeoJSON; web app chưa hiển thị cờ này).
- Triều là mực nước biển mô hình ngoài cửa sông, không phải trạm Phú An; trên sông, triều đến trễ vài giờ. Hà Nội
  không có thành phần triều.
- Các ngưỡng của điểm số (50 mm, 25 mm/giờ, trọng số, điểm cộng) là lựa chọn thiết kế, chưa hiệu chỉnh theo các trận
  ngập thực tế.
- Ngập còn phụ thuộc năng lực thoát nước, mặt phủ và triều, những thứ InSAR không thấy.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- Thành phố mới cần sửa mã: một mục trong `REGIONS` (khung, tên dùng khi tìm địa danh) ở `ancillary/flood_reports.py`,
  và `CENTRE`, `NAME`, với thành phố ven biển thêm `TIDE_POINT` ở `ancillary/flood_outlook.py`.
- Danh sách viết theo kiểu khác: mở rộng `parse_item` / `parse_prose`; các quy tắc định vị giữ nguyên.
- Sản phẩm InSAR nào cũng dùng được (vận tốc LOS từ cache điểm web); sản phẩm băng X dày điểm hơn cho nhiều điểm ngập
  có `n` ≥ 3 trong 100 m hơn.
- Thói quen đã biết: danh sách TP.HCM gạch đầu dòng theo nguyên nhân; bản tin Hà Nội viết thành câu theo lưu vực.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/ancillary/flood_reports.py`, `src/geoeyes/ancillary/flood_outlook.py`,
  `src/geoeyes/cli/main.py` (`cmd_floods`), `src/geoeyes/api/app.py` (`/api/floods…`),
  `webapp/src/components/FloodReports.tsx`, `webapp/src/components/FloodHub.tsx`, `webapp/src/pages/Explorer.tsx`.
- Hướng dẫn: [../guide/flood-reports.md](../guide/flood-reports.md).
- Skill liên quan: [exposure-and-flood-layers.md](exposure-and-flood-layers.md), [hazard-zoning.md](hazard-zoning.md).
- API Open-Meteo forecast và Marine (https://open-meteo.com); dữ liệu OpenStreetMap (ODbL) qua Overpass và Nominatim.
