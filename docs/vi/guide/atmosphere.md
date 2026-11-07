# Tầng đối lưu: chọn mô hình thời tiết

Ở lượt giải chập pha thứ hai, bộ xử lý `ps` trừ đi một màn pha khí quyển (APS). APS này là đường hồi quy tuyến tính
giữa pha và độ cao của chính bộ xử lý, hoặc một mô hình thời tiết (`[atmosphere] method`). Trang này liệt kê các mô
hình, cho biết mỗi mô hình dùng được ở đâu, và cách thử chúng trên một sản phẩm trước khi chạy lại dự án.

## Mục lục

1. [Các mô hình](#1-các-mô-hình)
2. [Ngoài châu Âu](#2-ngoài-châu-âu)
3. [Thử các mô hình trên một sản phẩm](#3-thử-các-mô-hình-trên-một-sản-phẩm)
4. [Áp dụng một mô hình](#4-áp-dụng-một-mô-hình)
5. [Phần mô hình không khử được](#5-phần-mô-hình-không-khử-được)

## 1. Các mô hình

| `method` | Mô hình | Lưới | Bản phân tích | Vùng | Cách lấy |
|---|---|---|---|---|---|
| `none` | APS tuyến tính của bộ xử lý (pha theo độ cao, từng giao thoa đồ) | – | – | mọi nơi | – |
| `era5` | ERA5 (tái phân tích ECMWF / C3S) | 0,25° (~31 km) | mỗi giờ | toàn cầu | CDS API, tự động |
| `cerra` | CERRA (tái phân tích khu vực châu Âu, SMHI / C3S) | 5,5 km, Lambert | mỗi 3 giờ | châu Âu, Bắc Phi, quần đảo Canary, Azores | CDS API, tự động |
| `gacos` | GACOS (ECMWF HRES + nội suy) | đầu ra ~90 m | theo ngày | toàn cầu | đặt qua e-mail ([hướng dẫn](incremental.md#7-tầng-đối-lưu-đặt-hàng-gacos)) |

ERA5 và CERRA dùng chung thông tin đăng nhập CDS (`~/.cdsapirc`). Cần chấp nhận giấy phép của từng bộ dữ liệu một lần
trên trang CDS. Cả hai được tính theo cùng một cách:
- tính hồ sơ độ trễ cho từng cột của mô hình (tích phân chiết suất đến độ cao 15 km);
- nội suy song tuyến đến từng điểm, tại đúng độ cao của điểm;
- nội suy tuyến tính theo thời gian giữa hai bản phân tích kẹp giờ chụp.

CERRA được công bố sau ngày chụp một đến hai tháng (cập nhật hằng tháng). CDS không cắt được lưới Lambert, nên mỗi mốc
phân tích là một file GRIB chứa toàn miền (~125 MB). Bộ nhớ đệm `<workspace>/cache/cerra` dùng chung cho mọi dự án ở
châu Âu. Với chồng ảnh chụp hằng ngày, mỗi ngày cần hai file (hai bản phân tích kẹp giờ chụp).

## 2. Ngoài châu Âu

Không có mô hình miễn phí nào mịn hơn ERA5 tải tự động được cho các ngày đã qua:

- ECMWF IFS 9 km (mô hình nền của GACOS) chỉ mở dưới dạng kho lưu trữ cuốn chiếu theo thời gian thực. Open-meteo cung
  cấp dữ liệu lịch sử của nó ở 0,25° (bằng lưới ERA5) và không có các mức áp suất 9 km;
- các mô hình phân giải cao quốc gia đều là mô hình khu vực:
  - HRRR (3 km, Hoa Kỳ, trên AWS);
  - CARRA (2,5 km, Bắc Cực, CDS);
  - BARRA2 (12 km, Úc).

  Tab Khí quyển liệt kê các mô hình này là chưa hỗ trợ.

Ở các nơi khác (Việt Nam, Mexico), dùng ERA5 hoặc đặt GACOS bằng tay. Bước tiếp theo có thể làm là hiệu chỉnh ERA5 gần
các trạm bằng độ trễ thiên đỉnh GNSS (Nevada Geodetic Laboratory).

## 3. Thử các mô hình trên một sản phẩm

Trên web app, mở trang dự án, tab **Khí quyển**. Tab này:
- liệt kê các mô hình cùng vùng phủ của chúng với sản phẩm (vùng và ngày);
- vẽ miền CERRA trên bản đồ;
- có nút **Thử các mô hình**, chạy lệnh:

```
geoeyes atmosphere <project> [--product ID] [--set models=["era5","cerra"]] [--set max_points=200000]
```

Lệnh này không xử lý lại gì. Nó lấy pha đã giải chập của lượt chạy `ps` tạo ra sản phẩm, trừ đi chuyển dịch tuyến
tính và sai số DEM của từng điểm. Phần còn lại chủ yếu là khí quyển và nhiễu. Từ phần này, nó trừ APS của từng mô hình
tại các điểm (đã đưa về trung bình 0 theo từng giao thoa đồ, như trong bộ xử lý). Tab hiển thị:

- độ tản mát (mm) còn lại theo từng giao thoa đồ và trung vị của nó, khi không hiệu chỉnh, với APS tuyến tính và với
  từng mô hình;
- tỉ lệ phương sai đã khử, và số giao thoa đồ mà mỗi mô hình tốt nhất;
- bản đồ của một giao thoa đồ: phần dư quan sát, APS của mô hình, phần dư sau khi trừ mô hình, cùng một thang màu
  (toàn dải).

Kết quả lưu ở `analyses/atmosphere/<product>/atmosphere.json` và `grids.npz`. Chỉ bộ xử lý `ps` kiểu StaMPS mới giữ
pha đã giải chập cần cho phép thử này.

## 4. Áp dụng một mô hình

Nút **Dùng** trên dòng của một mô hình sẽ đặt `[atmosphere] method` rồi chạy lại dự án. Bước 1-5 của bộ xử lý điểm
được lấy lại từ checkpoint: `ps_runs/<id>/checkpoints/step<N>.json` ghi khóa của tham số và stack mà checkpoint thuộc về. Vì vậy
chỉ phần giải chập pha và các bước sau phải chạy lại.

```toml
[atmosphere]
method = "cerra"
select = "auto"        # theo từng giao thoa đồ: chỉ dùng mô hình khi nó tốt hơn APS tuyến tính
cerra = { cache = "D:/geoeyes/cache/cerra" }    # tuỳ chọn
```

## 5. Phần mô hình không khử được

Mô hình chỉ khử phần độ trễ mà nó phân giải được: phần phân tầng theo độ cao, và nhiễu rối lớn hơn vài ô lưới của nó.
Các ô nhiễu rối vài km thường gặp ở vùng núi và khi thời tiết đối lưu. Chúng nhỏ hơn một ô CERRA (5,5 km), càng nhỏ
hơn nhiều so với một ô ERA5, nên vẫn còn lại trong pha. Với chồng ảnh ngắn, chúng lấn át vận tốc. Ví dụ ở Tenerife
(ICEYE, 15 ngày, tháng 2/2026), ±2,5 mm khí quyển thành ±60 mm/năm. Trong trường hợp đó, chồng ảnh dài hơn giúp nhiều
hơn một mô hình mịn hơn.
