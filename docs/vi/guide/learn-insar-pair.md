# Lộ trình học: một cặp giao thoa, từng bước một

Trang **Nguyên lý** của ứng dụng web có hai chương:

- **Chương 1 · Một cặp giao thoa** (hướng dẫn này) dẫn người mới từ hai cảnh SLC đơn lẻ đến vận tốc. Chương dùng một
  cặp ảnh của một chồng ảnh có sẵn và một vùng nhỏ (1–5 km), rồi cho thấy mỗi bước xử lý làm gì với dữ liệu.
- **Chương 2 · Phân vùng nguy cơ** (`#/learn-hazard/<bước>`) giải thích qua tám bước cách lập bản đồ của trang Phân
  tích chuyên đề: ô phân tích, địa hình và loại quá trình, chuyển dịch theo hướng nguy cơ, cường độ, tổn hại tiềm tàng, ma
  trận nguy cơ, liên hệ với mưa và liên hệ với nước ngầm. Phương pháp và nguồn:
  [rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md) và
  [groundwater-insar.md](../research/groundwater-insar.md).

- **Trước khi giải chập pha**, trang đi theo các bước của công cụ cũ `flat_earth_gui`:
  - giao thoa đồ thô;
  - pha mặt đất phẳng và pha địa hình;
  - độ kết hợp;
  - lọc Goldstein.
- **Phần còn lại dùng thuật toán của GeoEyes:**
  - đồng đăng ký ảnh như bộ tạo chồng ảnh đã làm;
  - giải chập pha bằng bộ giải IRLS của chuỗi PS;
  - vận tốc lấy từ chuỗi thời gian của sản phẩm.

Mã nguồn: `geoeyes.learn.pair` (tính toán), `geoeyes.api.learn` (API), `webapp/src/pages/Learn.tsx` (giao diện).

## Cách mở

1. Chọn **Nguyên lý** trên thanh trên cùng, rồi chọn dự án và một chồng ảnh ở cột trái. Dự án cần có ít nhất một chồng
   ảnh; bước cuối cần thêm một sản phẩm điểm.
2. Bước 0 chọn cặp ảnh và vùng:
   - biểu đồ đường đáy vẽ mọi ngày chụp theo đường đáy vuông góc, bấm hai điểm để tạo một cặp;
   - ảnh biên độ của cảnh tham chiếu cho thấy toàn bộ chồng ảnh, bấm vào đó để dời vùng;
   - cặp mặc định là ảnh tham chiếu của chồng ảnh và ngày chụp gần nó nhất (độ kết hợp tốt nhất cho lần xem đầu).

Đường dẫn `#/learn/<dự án>/<chồng ảnh>/<bước>` mở thẳng một bước.

## Các bước

Mọi ảnh là vùng cắt đã multilook, **ở hình học radar**: hàng là phương vị, cột là cự ly, nên phía trên ảnh
không phải hướng bắc. Ảnh được hiển thị đúng tỉ lệ khoảng cách trên mặt đất. Con trỏ liên kết giữa các ảnh, và
thanh bên dưới đọc giá trị mọi lớp tại vị trí con trỏ.

| # | Bước | Ảnh | Nội dung tính | Thử nghiệm |
|---|---|---|---|---|
| 0 | Cặp ảnh và vùng | biểu đồ đường đáy, biên độ của chồng ảnh | cặp và số look mặc định (khoảng 400 pixel mỗi chiều) | cặp ảnh, kích thước cửa sổ, số look |
| 1 | Hai cảnh SLC | biên độ từng cảnh (dB) | công suất sau multilook | SLC sau liên kết pha (CSK) |
| 2 | Đồng đăng ký | ảnh tổ hợp màu (cảnh 1 đỏ, cảnh 2 lục lam), nhấp nháy | độ lệch còn lại (stripmap) hoặc độ dịch ESD (Sentinel-1) lấy từ chồng ảnh | – |
| 3 | Giao thoa đồ thô | pha thô, biên độ | s₁·s₂* cộng lại pha hình học (xem dưới) | – |
| 4 | Mặt đất phẳng | mô hình, pha sau khi loại bỏ | ∫ kₕ cos θ dr; so sánh số vân dự tính với số vân đo được | – |
| 5 | Địa hình | DEM, mô hình kₕ·h, giao thoa đồ vi phân | độ cao nhập nhằng 2π/kₕ | – |
| 6 | Độ kết hợp | độ kết hợp, pha vi phân bị làm mờ dưới ngưỡng | \|Σ s₁s₂*\| / √(Σ\|s₁\|² Σ\|s₂\|²) | cửa sổ, ngưỡng |
| 7 | Lọc Goldstein | pha trước và sau khi lọc, điểm dư pha dạng chấm | `processing.unwrap.goldstein`; số điểm dư pha | α, cửa sổ, số lượt |
| 8 | Giải chập pha | pha cuộn và pha đã giải chập, mặt cắt theo hàng dưới con trỏ | `processing.ps.unwrap.irls.irls_unwrap_weighted`, trọng số γ² | điểm tham chiếu; bài tập (xem dưới) |
| 9 | Chuyển dịch | chuyển dịch theo LOS (mm), độ kết hợp | d = −φλ/4π; một vân = λ/2 | điểm tham chiếu |
| 10 | Vận tốc | vận tốc các điểm PS của sản phẩm trong vùng | chuỗi của điểm được bấm, đường thẳng khớp, tốc độ chỉ từ cặp ảnh | bấm vào một điểm |

**Bài tập giải chập pha (bước 8).** Sau khi loại bỏ pha hình học, một cặp ngắn ngày trên vùng đô thị thường gần
như không còn vân, nên việc giải chập thay đổi rất ít. Bài tập giải chập *pha thô* bằng cùng bộ lọc và bộ giải.
Vân mặt đất phẳng dày đặc làm đường răng cưa của pha cuộn trở thành một đường dốc liền nhìn thấy rõ.

## Giao thoa đồ thô được dựng lại

SLC trong chồng ảnh của GeoEyes đã được đồng đăng ký **và làm phẳng**:

- mỗi ảnh phụ được lưu dưới dạng `res · exp(j·geom)`, với `geom = 4π/λ (R_phụ − R_tham chiếu)` gồm mặt tham chiếu
  và DEM;
- vì vậy `slc_i · conj(slc_j)` đã là giao thoa đồ vi phân;
- dữ liệu thô và pha hình học không được giữ lại.

Để trình bày chuỗi xử lý kinh điển, trang dựng lại pha hình học của cặp từ các lớp đã lưu:

- **Địa hình:** `kₕ · h`, trong đó `kₕ = d geom / dh` được lưu theo từng ngày (rad trên m) và `h` là độ cao DEM
  của từng pixel (độ cao elipxoit). Với một cặp, `kₕ = kₕ,j − kₕ,i`.
- **Mặt đất phẳng:** ở độ cao không đổi, một thay đổi dr của cự ly nghiêng làm góc nhìn thay đổi giống như một
  thay đổi độ cao dh = dr · cos θ, nên `d geom / dr = kₕ · cos θ`. Đại lượng này được tích phân theo cự ly, bằng 0
  tại tâm vùng.

Pha thô bằng pha vi phân cộng hai thành phần trên. Đây là phần minh hoạ, với các gần đúng sau:

- Bỏ qua độ cong Trái Đất trong vùng.
- Mô hình là tương đối: các hằng số đã bị loại.
- Thành phần mặt đất phẳng không tính đến thay đổi nhỏ của đường đáy theo phương vị.

Cách kiểm tra là số vân. Với Hà Nội CSK (B⊥ = 102 m), mô hình dự tính 8,2 vân/km. Pha thô cho 8,3, và sau khi
loại bỏ còn 0,5.

## Dấu và đơn vị

- Cự ly tăng (dịch ra xa vệ tinh) cộng thêm +4πd/λ vào `slc_i · conj(slc_j)`.
- Chuyển dịch bằng −φλ/4π: dương là về phía vệ tinh. Trên ảnh chuyển dịch và vận tốc, đỏ là ra xa (lún), xanh
  là về phía vệ tinh.
- Thang màu vận tốc phủ toàn bộ khoảng giá trị của các điểm, đối xứng quanh 0.
- Biên độ được giãn theo khoảng 2–98 %.

## Hạn chế

- **Tham chiếu khác nhau.** Bước 10 dùng sản phẩm mới nhất của quỹ đạo tương ứng với chồng ảnh. Vận tốc của nó
  tương đối so với tham chiếu của sản phẩm, còn chuyển dịch của cặp ảnh tương đối so với điểm tham chiếu riêng.
  Hai tốc độ khác nhau là điều bình thường: cặp ảnh còn chứa khí quyển của cả hai ngày chụp.
- **Sai lệch của độ kết hợp.** Độ kết hợp ước lượng trong cửa sổ nhỏ bị lệch lên ở nơi độ kết hợp thật thấp.
- **Giải chập 2-D và 3-D.** Giải chập 2-D ở đây là của một giao thoa đồ. Chuỗi PS giải chập các điểm tán xạ bền
  vững theo cả không gian và thời gian.
- **Giới hạn kích thước.** Vùng cắt tối đa 4 triệu pixel độ phân giải gốc và 700 pixel mỗi chiều sau multilook.

## API

| Đường dẫn | Trả về |
|---|---|
| `GET /api/projects/{p}/learn` | các chồng ảnh, kèm ngày chụp, đường đáy, kích thước pixel, cặp và vùng mặc định |
| `GET /api/projects/{p}/learn/{stack}/thumb(.bin)` | biên độ ảnh tham chiếu của cả chồng ảnh (float32) |
| `GET /api/projects/{p}/learn/{stack}/pair(.bin)?first&second&row0&col0&rows&cols&looks_az&looks_rg&…` | thông tin và các lớp (float32, nối tiếp theo thứ tự `meta.layers`) |
| `GET /api/projects/{p}/learn/{stack}/points?…` | các điểm PS của sản phẩm trong vùng cắt, trên lưới đã multilook |
| `GET /api/projects/{p}/learn/series/{product}/{uid}` | chuỗi của một điểm và đường thẳng khớp |

Các tham số tuỳ chọn là `coh_win`, `alpha`, `fft`, `passes`, `linked`, `ref_row`, `ref_col` và `exercise`.
