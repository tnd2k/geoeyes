# Điểm ngập được báo cáo: danh mục để đối chiếu với chuyển dịch

Tình trạng ngập ở TP.HCM được công bố dưới dạng danh sách tên địa điểm. Mỗi mùa mưa, Phòng CSGT (PC08) và Sở Xây dựng phát hành các danh sách này, chia theo nguyên nhân (mưa lớn, triều cường). GeoEyes lưu các danh sách đó thành một danh mục dùng chung cho cả workspace, định vị từng vị trí trên OpenStreetMap và hiển thị chúng trên bản đồ kết quả. Nhờ vậy có thể đặt nơi thành phố bị ngập cạnh nơi mặt đất chuyển dịch.

## Các file

```
<workspace>/inventories/flood/<vùng>.csv       mỗi dòng là một vị trí được báo cáo, giữ nguyên lời công bố (sửa được)
<workspace>/inventories/flood/<vùng>.geojson   các dòng đó đã được định vị trên bản đồ
```

Mỗi dòng gồm các cột:

| Cột | Nội dung |
|---|---|
| `text` | Nguyên văn lời công bố |
| `cause` | `rain` (mưa), `tide` (triều cường) hoặc `rain_tide` (cả hai) |
| `kind` | `segment` (đoạn đường), `junction` (giao lộ), `street` (cả tuyến), `address` (số nhà) hoặc `place` (địa danh) |
| `street`, `from`, `to`, `cross`, `place`, `ward` | Các thành phần tách ra từ lời công bố |
| `reported`, `source`, `url` | Ngày công bố, cơ quan công bố và nơi đăng |
| `depth_m`, `notes` | Độ sâu ngập nếu có, và các ghi chú khác |
| `geom_wkt` | Hình học nhập tay (xem [Sửa một dòng](#sửa-một-dòng)) |

File CSV mở được bằng Excel mà không lỗi tiếng Việt (lưu dạng UTF-8 có BOM).

Hiện có hai vùng:

- **`hcmc`** phủ toàn bộ thành phố sau sáp nhập, gồm cả Bình Dương và Bà Rịa–Vũng Tàu cũ.
- **`hanoi`** phủ toàn bộ Thủ đô sau sáp nhập. Hà Nội nằm sâu trong nội địa nên phần dự báo chỉ tính mưa.

Công ty Thoát nước Hà Nội viết bản tin thành câu văn, ví dụ `Lưu vực sông Nhuệ: Dương Đình Nghệ – Nam Trung Yên (sau Keangnam), Hoa Bằng (ngõ 99), …`. Nhập loại bản tin này bằng cờ `--prose`:

```
geoeyes floods import ban_tin.txt --prose --region hanoi --reported 2026-09-17 --source "Thoát nước Hà Nội"
```

Ở chế độ `--prose`:

- tên lưu vực đứng trước dấu ":" được ghi vào `notes`;
- tên trơn được hiểu là tên đường;
- "A – B" được hiểu là giao lộ;
- đoạn ghi trong ngoặc dạng "(từ … đến …)" biến dòng đó thành một đoạn đường;
- địa danh trong ngoặc, như "(trường Chu Văn An)", dùng để đặt vị trí lên đúng đường đó, cạnh địa danh.

Tên đường có ở nhiều quận sẽ được đặt gần các điểm khác cùng bản tin và cùng lưu vực, nếu các điểm đó nằm trong phạm vi 3 km quanh một trong các đường trùng tên.

Chỉ dùng những nguồn cho phép thu thập. Ví dụ, nuoclen.com cấm truy cập tự động vào API trong file `robots.txt` của họ, nên GeoEyes không đọc nguồn này.

## Thêm một danh sách

1. Chép danh sách từ thông báo vào một file văn bản. Giữ nguyên tiêu đề và các gạch đầu dòng `-` / `+` như khi công bố.
2. Nhập file vào danh mục:

   ```
   geoeyes floods import danh_sach.txt --reported 2026-10-06 --source "PC08 Công an TP.HCM" --url <bài báo>
   ```

3. Định vị các dòng mới trên bản đồ (lệnh này được giải thích ở [Định vị trên bản đồ](#định-vị-trên-bản-đồ)):

   ```
   geoeyes floods locate
   ```

Cách lệnh import đọc văn bản:

- **Nguyên nhân.** Tiêu đề có chữ "mưa" gán nguyên nhân mưa cho các mục bên dưới, "triều" gán triều cường, có cả hai chữ thì gán cả hai. Muốn gán một nguyên nhân cho cả file thì dùng `--cause`.
- **Các mục thuộc một tuyến đường.** Dòng dạng `- Đường X:` mở một nhóm. Các dòng `+` theo sau, và các dòng `-` bắt đầu bằng "Đoạn" hoặc "Giao", được hiểu là vị trí trên đường X.
- **Các dạng câu được nhận ra trong một mục:**

  | Dạng câu | Được đọc là |
  |---|---|
  | "Đường A, (đoạn) từ B đến C" | `segment` trên đường A |
  | "Giao lộ A - B", "Đường A - B", "Giao B" (dưới đường A) | `junction` |
  | "Số 69 Trịnh Thị Dối", "Trước số 139" | `address` |
  | "Đường X" | `street` |
  | Các dạng khác ("Ngã tư Bảy Hiền", "Chân cầu Lò Gốm") | `place` |

- **Phường, xã.** Phường/xã ghi trong ngoặc, như "(phường Tam Bình)", được lưu vào `ward`. Thông tin này dùng để chọn đúng đường khi có nhiều đường trùng tên.
- **Nhập trùng.** Nhập lại cùng một danh sách thì không thêm dòng nào, vì mã của mỗi dòng được tạo từ nội dung, nguyên nhân, ngày và nguồn.

## Định vị trên bản đồ

`geoeyes floods locate` lấy hình học đường phố từ OSM qua Overpass và tìm địa danh bằng Nominatim. Cả hai đều được lưu đệm trong `cache/osm/flood`. Cách mỗi dòng được định vị ghi ở cột `located`:

| `located` | Ý nghĩa |
|---|---|
| `exact` | Đúng đoạn được báo cáo, cắt giữa hai chỗ giao với đường B và C, hoặc đúng giao lộ nơi hai đường gặp nhau (cách nhau dưới 40 m) |
| `place` | Định vị theo địa danh tìm được qua Nominatim (chợ, cầu, vòng xoay), đặt lên đường nếu địa danh cách đường dưới 400 m |
| `approx` | Chỉ ở gần vị trí được báo cáo: cả tuyến đường, hoặc một đoạn chỉ tìm được một đầu |
| `ambiguous` | Tên đường có ở nhiều nơi trong thành phố mà không ghi phường, nên dòng này không được đặt lên bản đồ |
| `none` | Không tìm thấy trên OSM |
| `manual` | Lấy từ cột `geom_wkt` |

GeoEyes không âm thầm đoán vị trí. Dòng nào không định vị được vẫn nằm trong danh sách nhưng không có hình học, và bảng điều khiển trên bản đồ có đếm số dòng này.

## Sửa một dòng

Để đặt vị trí bằng tay, ghi một hình học WKT vào cột `geom_wkt` của dòng đó rồi chạy lại `locate`. Ví dụ:

- `POINT (106.7012 10.7769)`
- `LINESTRING (106.70 10.77, 106.71 10.78)`

Dòng đó sau đó được đánh dấu `manual`.

## Trên bản đồ kết quả

Nút **Điểm ngập** trên thanh công cụ của trang bản đồ hiển thị danh mục chồng lên các sản phẩm:

- **Đường kẻ** là các đoạn đường, **chấm tròn** là giao lộ và địa danh. Màu xanh dương là ngập do mưa, tím là do triều cường, xanh lục lam là cả hai.
- **Hình nhạt màu** là vị trí chỉ định vị gần đúng. Đánh dấu ô *chỉ các vị trí định vị chính xác* để ẩn chúng.
- **Bảng điều khiển** cho biết vận tốc của sản phẩm trên cùng quanh mỗi vị trí: trung vị vận tốc của các điểm trong bán kính đã chọn, của vành xung quanh (từ bán kính đó đến 500 m), và tỉ lệ điểm của sản phẩm đang ra xa vệ tinh nhanh hơn. Bấm vào một dòng để phóng tới vị trí đó và xem nguồn công bố.

Các số liệu này cũng lấy được qua `GET /api/projects/{name}/products/{pid}/floods?radius=100`.

## Dự báo ngập 24 giờ tới

Khi bật lớp điểm ngập, khung **Dự báo ngập · 24 giờ** mở ra ở bên trái bản đồ. Mặc định khung hiển thị toàn thành phố; khi bấm vào một vị trí thì chuyển sang vị trí đó. Đây chỉ là thông tin tham khảo. Phía sau không có mô hình thuỷ lực hay trạm đo nào, và thẻ đầu tiên của khung nói rõ điều đó.

**Dữ liệu đầu vào:**

- **Mưa:** dự báo theo giờ tại từng vị trí, lấy từ Open-Meteo (tổng hợp nhiều mô hình thời tiết).
- **Triều:** mực nước biển theo giờ ngoài cửa sông, lấy từ Open-Meteo Marine. Đây là giá trị mô hình ngoài biển, không phải số đo tại trạm Phú An; nước trên sông theo sau vài giờ.
- **Lún:** khi có sản phẩm trên bản đồ, đó là trung vị vận tốc theo hướng nhìn vệ tinh (LOS) của các điểm quanh vị trí.

**Điểm rủi ro (0–100), được thiết kế để minh bạch:**

1. Phần mưa *R* kết hợp lượng mưa 24 giờ (tối đa khi đạt 50 mm) và giờ mưa lớn nhất (tối đa khi đạt 25 mm). Phần này sau đó được nhân theo xác suất mưa cao nhất.
2. Phần triều *T* đặt đỉnh triều sắp tới trên thang từ trung vị đỉnh triều hằng ngày của 30 ngày qua (0) đến đỉnh cao nhất trong tháng (1, tức triều cường).
3. Hai phần được gán trọng số theo nguyên nhân ngập đã báo cáo của vị trí:

   | Nguyên nhân | Trọng số mưa | Trọng số triều |
   |---|---|---|
   | Mưa | 0,8 | 0,2 |
   | Triều cường | 0,2 | 0,8 |
   | Cả hai | 0,5 | 0,5 |

4. Lún cộng thêm 3, 6 hoặc 10 điểm khi mặt đất ra xa vệ tinh từ 5, 10 hoặc 20 mm/năm trở lên. Với cả thành phố, vận tốc là trung vị tại các điểm ngập được báo cáo nằm trong sản phẩm (ít nhất 3 điểm).

**Mức nguy cơ và độ sâu ước tính:**

| Điểm | Mức | Độ sâu ước tính |
|---|---|---|
| Dưới 20 | Thấp | Khó xảy ra ngập |
| Từ 20 đến 44 | Cần lưu ý | Có thể dưới 20 cm |
| Từ 45 đến 69 | Cao | Có thể 20–40 cm |
| Từ 70 trở lên | Rất cao | Có thể trên 40 cm |

Độ sâu ở đây chỉ là nhãn phân cấp thô đi kèm mức nguy cơ.

**Khung giờ nguy cơ.** Gồm các giờ trong 24 giờ tới có ý nghĩa với nguyên nhân ngập của vị trí: mưa từ 2 mm với xác suất từ 40 % trở lên, hoặc triều nằm trong 40 % trên cùng của biên độ trong tháng.

**Màu trên bản đồ.** Các vị trí được tô màu theo mức nguy cơ hôm nay (ô *tô màu các vị trí theo nguy cơ hôm nay*). Bỏ chọn ô này để tô theo nguyên nhân ngập.

Dữ liệu lấy qua `GET /api/floods/outlook?project=&product=`.

**Lưu đệm (cache).** Tải lại trang không làm tính lại các kết quả sau:

| Kết quả | Nơi lưu | Khi nào tính lại |
|---|---|---|
| Vận tốc quanh các vị trí | Trên đĩa, `cache/web/<sản phẩm>/floods_r<bán kính>.json` | Khi danh mục điểm ngập hoặc sản phẩm thay đổi |
| Dự báo | Trên đĩa, `cache/floods/` | Sau 30 phút |
| Danh mục, thống kê và dự báo | Trong trình duyệt (bộ nhớ cục bộ) | Trình duyệt hiển thị ngay khi tải lại trang, rồi tự làm mới khi dữ liệu đã cũ |

## Đọc kết quả đối chiếu

- **Vị trí so với cả tuyến.** Vị trí được báo cáo là nơi người ta thấy ngập, thường là chỗ trũng trên một con đường. Đó không phải ranh giới vùng ngập. Cả tuyến đường (`approx`) lẫn cả đoạn có ngập và đoạn không ngập, nên khi tính toán hãy ưu tiên các dòng `exact`.
- **Vận tốc tính theo hướng nhìn của vệ tinh (LOS).** Giá trị âm là ra xa vệ tinh. Trên địa hình bằng phẳng như phần lớn TP.HCM, đó chủ yếu là lún. Dùng `decompose` với một hướng chụp thứ hai để tách chuyển dịch đứng và ngang.
- **So với vành xung quanh.** Một vị trí lún nhanh hơn vành quanh nó có ý nghĩa hơn một vị trí chỉ lún như cả khu vực. Ngập còn có những nguyên nhân InSAR không thấy được: khả năng thoát nước, mực triều và lớp phủ bê tông.
