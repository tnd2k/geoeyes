# Xử lý gia tăng và giám sát

Hướng dẫn này dành cho người duy trì một dự án cập nhật liên tục khi có ảnh Sentinel-1 mới. Nó giải thích lần
chạy làm lại những gì khi thêm một ngày, cách cập nhật điểm gia tăng hoạt động và khi nào không dùng, cảnh báo
sớm, và các định dạng xuất cho người không dùng phần mềm GIS.

## Mục lục

1. [Một ảnh mới tốn bao nhiêu](#1-một-ảnh-mới-tốn-bao-nhiêu)
2. [Stack gia tăng](#2-stack-gia-tăng)
3. [Cập nhật điểm gia tăng](#3-cập-nhật-điểm-gia-tăng)
4. [Cảnh báo sớm](#4-cảnh-báo-sớm)
5. [Quy trình giám sát](#5-quy-trình-giám-sát)
6. [Xuất: Google Earth và 3D Tiles](#6-xuất-google-earth-và-3d-tiles)
7. [Tầng đối lưu: đặt hàng GACOS](#7-tầng-đối-lưu-đặt-hàng-gacos)

## 1. Một ảnh mới tốn bao nhiêu

Hà Nội, Sentinel-1 quỹ đạo lên 128, 26 ngày, khoảng 730.000 điểm, có hiệu chỉnh tầng điện ly:

| Bước | Chạy đầy đủ | Một ngày mới |
|---|---|---|
| acquire | tải mọi burst | chỉ burst mới |
| build_stack | 71 phút | ~3 phút (ước tính: 71 phút / 26 ngày): khớp ảnh ngày mới, chép các ngày khác |
| ps | 12 phút | **45 giây** (cập nhật gia tăng) |
| build_product, export, report | 2 phút | 2 phút |

## 2. Stack gia tăng

`[stack] incremental = true` (mặc định). Lần dựng mới giữ các ngày đã khớp của stack cũ khi:

- ngày tham chiếu, AOI, DEM và các dải con không đổi (với `[network] reference = "auto"`, ngày tham chiếu của lần
  dựng đầu được giữ chừng nào nó còn là một ngày chụp);
- các tệp của ngày đó mà stack đọc không đổi, và quỹ đạo của nó không được nâng cấp (quỹ đạo chính xác mới công bố
  thì ngày đó được khớp lại).

Thư mục ảnh gốc (archive) dùng chung cho mọi dự án. Từ 2026-10, một cảnh chỉ được so trên các burst mà stack dùng:
dự án khác tải thêm burst của cùng ngày chụp (AOI hoặc dải con khác) không còn làm các ngày bị coi là đã đổi. Danh
sách burst của cảnh (`bursts.json`) được ghép thêm, không còn bị ghi đè, sau mỗi lần tải.

`geoeyes plan <dự án>` cho biết sẽ làm lại những gì và vì sao ("2 new scene(s): …; incremental: 26 coregistered
date(s) kept").

## 3. Cập nhật điểm gia tăng

```toml
[ps_update]
enabled = true        # mặc định
full_every = 4        # chạy đầy đủ sau khi đã cập nhật thêm chừng này ngày
```

Khi chỉ có ngày mới được nối vào sau ngày cuối của lần chạy `ps` trước, bước `ps` thêm chúng vào lần chạy đó thay
vì chạy lại engine trên toàn bộ stack. Kế hoạch chạy ghi rõ: `ps  run  …; incremental update: 1 new date(s)`.

Giữ nguyên từ lần chạy trước: tập điểm (chọn và lọc), sai số DEM của chúng, sai số ảnh chủ, vùng tham chiếu và mô
hình vận tốc. Với mỗi ngày mới và mỗi điểm:

1. pha chập của ảnh tham chiếu so với ngày mới, như engine tạo;
2. trừ pha địa hình theo sai số DEM của điểm, và chuyển dịch dự báo theo đường thẳng khớp chuỗi của nó;
3. phần còn lại (khí quyển, chuyển dịch bất ngờ, nhiễu) được giải chập pha trong không gian trên lưới giải chập pha (IRLS), rồi
   mỗi điểm gắn về pha chập của chính nó + 2πk;
4. khử khí quyển: mô hình thời tiết (ERA5 / GACOS) hoặc khớp tuyến tính pha – độ cao, cái nào để lại phần dư nhỏ hơn;
5. quy về tham chiếu như engine (các điểm tham chiếu hoặc trung bình toàn cảnh); khớp lại vận tốc, gia tốc và RMSE
   trên toàn bộ các ngày.

Chạy đầy đủ thay vì cập nhật khi: tham số thay đổi (`[ps]`, `[selection]`, `[atmosphere]`, phiên bản engine), stack
được dựng lại (đổi ngày tham chiếu, khớp lại các ngày), có ngày mới nằm trước ngày cuối của lần chạy, bật
phase linking, đã cập nhật đủ `full_every` ngày, hoặc dùng `--force ps`.

**Độ chính xác** (kiểm định giữ lại, Hà Nội quỹ đạo lên 128: lần chạy đầy đủ bỏ các ngày cuối, rồi cập nhật lại):

| Số ngày thêm | Thời gian | Chuyển dịch của các ngày mới so với chạy đầy đủ | Vận tốc so với chạy đầy đủ |
|---|---|---|---|
| 1 | 45 giây | r 0,92, độ lệch chuẩn 2,7 mm, 0,5 % số điểm lệch quá nửa chu kỳ | 0,6 mm/năm |
| 3 | 62 giây | r 0,83–0,93, độ lệch chuẩn 2,7–3,6 mm, tới 1,2 % | 1,4 mm/năm |

Một phần chênh lệch không phải sai số của bước cập nhật: lần chạy đầy đủ ước lượng lại tập điểm, sai số DEM và APS
của mọi ngày khi có dữ liệu mới. Bước cập nhật không thể tìm điểm ổn định mới hay bỏ điểm đã mất, và không tách
được nhiễu tương quan không gian của các ngày mới (SCN của chúng là 0: chưa có cửa sổ thời gian phía sau). Vì vậy
mới cần `full_every`.

## 4. Cảnh báo sớm

Các luật cảnh báo (`[postprocess.alerts]`, thẻ Giám sát của trang dự án) được đánh giá trên sản phẩm mới nhất:

| Loại | Kích hoạt khi có ít nhất `min_points` điểm … |
|---|---|
| `velocity_below` / `velocity_above` | có vận tốc vượt `threshold` (mm/năm) |
| `deviation_below` / `deviation_above` | ở **ngày mới nhất** lệch khỏi xu hướng tuyến tính của các ngày trước quá `threshold` (mm) |

Luật theo độ lệch phản ứng ngay với một ảnh mới, trước khi vận tốc kịp đổi. Cần ít nhất 7 ngày. Một ngày đơn lẻ có
thể là do khí quyển: đọc cảnh báo cùng với ảnh kế tiếp và với quỹ đạo kia.

```toml
[postprocess.alerts]
rules = [
  { name = "lún đột ngột", kind = "deviation_below", threshold = -10.0, min_points = 30 },
]
```

## 5. Quy trình giám sát

1. Thẻ Giám sát: đặt lịch `geoeyes run` (hằng ngày hoặc hằng tuần, Windows Task Scheduler).
2. Mỗi lần chạy: `acquire` tải burst mới; `build_stack` thêm ngày mới; `ps` cập nhật; sau đó là phiên bản sản phẩm
   mới, xuất và báo cáo.
3. Sau mỗi `full_every` ngày, hoặc khi đổi tham số, lần chạy là chạy đầy đủ (thêm khoảng 15 phút).
4. Đọc mục kiểm tra chất lượng của báo cáo (mục 4.1) và các cảnh báo trên mỗi sản phẩm mới.

## 6. Xuất: Google Earth và 3D Tiles

```toml
[export]
formats = ["gpkg", "pmtiles", "kmz", "3dtiles"]
```

- `kmz` (Google Earth): vận tốc dưới dạng ảnh phủ mặt đất theo đúng các lớp màu của style QGIS, chú giải, và các
  điểm nhanh nhất (1.500 điểm, cả hai chiều) dạng placemark kèm số liệu và vài ngày trong chuỗi thời gian.
- `3dtiles` (Cesium, ArcGIS, deck.gl): đám mây điểm 3D Tiles 1.0 ở độ cao elipxoit, tô màu theo lớp, kèm vận tốc,
  độ cao và độ nhất quán của từng điểm; `viewer.html` hiển thị trên nền OpenStreetMap. Mở qua ứng dụng web
  (`…/api/projects/<dự án>/exports/<sản phẩm>/3dtiles/viewer.html`): trang mở trực tiếp từ đĩa không đọc được các tile.

## 7. Tầng đối lưu: đặt hàng GACOS

ERA5 (0,25°, mỗi giờ, nội suy về thời điểm chụp) không bắt được đối lưu chiều tối mùa mưa ở Hà Nội
(docs/vi/guide/ionosphere.md §6). GACOS (~90 m, từ mô hình phân giải cao của ECMWF) tốt hơn ở vùng nhiệt đới nhưng
không có API: sản phẩm được đặt trên http://www.gacos.net và gửi về qua email.

```
geoeyes gacos-order <dự án> [--track ID]
```

in ra nội dung cần điền vào đơn: vùng (AOI + 0,1°), giờ UTC và các ngày chưa có sản phẩm trong
`[atmosphere.gacos] dir`. Sau đó:

```toml
[atmosphere]
method = "gacos"
gacos = { dir = "D:/data/gacos/hanoi_asc128" }
```

Với `select = "auto"` (mặc định), mỗi ngày chỉ dùng GACOS khi nó giải thích phần pha dư tốt hơn khớp tuyến tính;
ngày chưa có sản phẩm giữ APS tuyến tính.
