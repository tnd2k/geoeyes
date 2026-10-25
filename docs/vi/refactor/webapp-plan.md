> Bản tiếng Việt của [`docs/en/refactor/webapp-plan.md`](../../en/refactor/webapp-plan.md); bản gốc tiếng Anh là bản chuẩn (ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.

# Kế hoạch ứng dụng web mới

**Trạng thái (2026-10-25): đã có MVP.** `geoeyes serve` → http://localhost:8765 (không bao giờ dùng 5173; dev server ở 8766).
Đã xong: `geoeyes.api` (cây không gian làm việc, thư mục, trạng thái dự án, kế hoạch, chạy / dừng, log các lần chạy, lớp sản phẩm, chuỗi
thời gian theo điểm và theo vùng, tệp); front end trong `webapp/` (cây dự án có thư mục và kéo thả, Overview, Explorer,
Project). Sau đó: biểu mẫu thiết lập sinh từ schema (ghi thay đổi bằng tomlkit, giữ nguyên chú thích, lưu bản cũ
vào `.state/`), trình sửa `project.toml` dạng thô, trình tạo dự án mới (vẽ AOI trên bản đồ, chọn vệt quỹ đạo Sentinel-1 đi qua,
xem trước các lần chụp bằng chính hàm tìm kiếm của pha acquire), so sánh sản phẩm (kéo trượt; hiệu B − A của
vận tốc trung vị theo ô, đã trừ độ lệch trung vị, cảnh báo khi hai sản phẩm khác hướng nhìn của vệ tinh (LOS)), báo cáo
gương phản xạ góc (dựng, bảng, hình, PDF), đăng nhập bằng token khi mở cổng ra ngoài máy (`GEOEYES_WEB_TOKEN`).
Đợt ba (2026-10-25): trình dàn trang bản đồ ("Map image": khổ A4/A3/trình chiếu, tiêu đề, chú giải theo các lớp của QGIS,
thước tỉ lệ, mũi tên chỉ bắc, thông tin sản phẩm, nguồn dữ liệu; xuất PNG hoặc PDF 150-300 dpi, kết xuất ngầm đúng khổ in);
PMTiles (`export/pmtiles.py`, tự viết bộ mã hoá MVT; pha export ghi ra mặc định, QGIS 3.32+ đọc được; bản đồ
đọc sản phẩm trên 2,5 triệu điểm dưới dạng tile, lớp nào cũng chuyển sang tile được); tab giám sát (lần chụp Sentinel-1
sắp tới suy từ kho lưu trữ, `geoeyes run` theo lịch qua Windows Task Scheduler, quy tắc cảnh báo biến dạng khai báo ở
`[postprocess.alerts]` và kiểm tra trên sản phẩm mới nhất, cảnh báo đã kích hoạt hiện ở trang tổng quan). Đợt bốn: dùng kế hoạch
chụp ESA công bố để kiểm tra dự báo 12 ngày (đã lên lịch / không có lịch / dự báo), mưa tháng CHIRPS v3
dưới chuỗi thời gian, chuỗi đã trừ SCN bên cạnh chuỗi chuyển dịch, danh mục không gian làm việc ("Products here"),
khung toạ độ và mũi tên hướng bay / hướng nhìn của vệ tinh trên ảnh bản đồ. Đợt năm (2026-10-25): trang **Hazard**,
phân vùng nguy cơ sụt lún / trượt lở có xét lượng mưa (`geoeyes hazard`, ADR-024): tô màu ô theo mức nguy cơ hoặc theo
từng thành phần (cường độ, góc biến dạng / độ dốc, tốc độ, liên hệ mưa – biến dạng, độ trễ, chế độ), chú giải kèm ma trận,
bảng thông tin ô (chuỗi theo hướng chuyển động, mô hình tuyến tính và mô hình mưa, lượng mưa tại điểm ảnh), tham số chạy và
vùng tham chiếu ổn định. Cột lượng mưa dưới chuỗi thời gian nay hiện theo mặc định.

Ứng dụng web cũ (FastAPI + React, 11 nhóm API, 5 trang) đã đóng băng và sẽ bị thay thế. Ứng dụng đó sửa
thẳng các tệp cũ (`in.json`, `control.json`, `.mat`), cần Node và hai tiến trình khi chạy, và chia
tính năng ra nhiều công cụ nhỏ lẻ. Ứng dụng mới chỉ là client mỏng của phần lõi GeoEyes.

## Nguyên tắc

1. **Lớp mỏng trên phần lõi**: mọi thao tác đều qua API công khai — bộ điều khiển `plan` / `run` / `status`,
   sản phẩm (GeoParquet, STAC, COG), báo cáo, hồ sơ lần chạy. Không đụng tệp nội bộ, không tự xử lý dữ liệu.
2. **Mỗi màn hình trả lời một câu hỏi**: việc gì cần xem ngay? dự án này còn phải chạy gì, vì sao? mặt đất dịch chuyển ở đâu,
   nhanh đến mức nào? kết quả có tin được không?
3. **Bản đồ là chính**: dữ liệu InSAR mang tính không gian; bảng phục vụ bản đồ chứ không ngược lại.
4. **Một lệnh là chạy**: `geoeyes serve` — FastAPI phục vụ ứng dụng một trang đã build trên một cổng; máy xử lý
   không cần Node. Mặc định chỉ truy cập cục bộ; mở ra ngoài thì đăng nhập bằng token.

## Bố cục

Bên trái là **cây dự án** luôn hiển thị (giống trình duyệt tệp của các ứng dụng SaaS, hay bảng browser / layers của QGIS); bên phải là bốn
khu vực.

### Cây dự án

```
Workspace
├─ Vietnam/                      thư mục: nhóm dự án do người dùng tự đặt (kéo để sắp xếp lại)
│  └─ Hanoi/
│     ├─ hanoi_csk               dự án: chấm trạng thái (đã cập nhật / có dữ liệu mới / đang chạy / lỗi)
│     │  ├─ cosmo_skymed-asc     vệt quỹ đạo
│     │  │  ├─ Data              các lần chụp (ngày, đường cơ sở), thư mục lưu trữ
│     │  │  ├─ Stack             chồng ảnh đã đồng đăng ký (ngày, ảnh tham chiếu, kích thước)
│     │  │  ├─ PS run            điểm, hình QC
│     │  │  ├─ Products          v1, v2 ... (phiên bản bất biến; nút con mắt = hiện trên bản đồ, như lớp QGIS)
│     │  │  └─ Exports           tải GeoPackage / CSV
│     │  ├─ Reports              báo cáo PDF
│     │  ├─ Validation           báo cáo gương phản xạ góc
│     │  └─ Settings             project.toml (biểu mẫu)
│     ├─ hanoi_s1
│     └─ hanoi_s1_desc
└─ Mexico/
   ├─ mexico_s1
   └─ mexico_capella
```

- Thư mục chỉ là siêu dữ liệu của không gian làm việc (`<workspace>/projects/.folders.json`: cây thư mục + thứ tự dự án); thư mục
  dự án trên đĩa vẫn là `projects/<name>/`, nên chuyển dự án sang thư mục khác không di chuyển gì trên đĩa.
- Menu chuột phải trên mỗi nút: chạy, lập kế hoạch, mở báo cáo, tải về, nhân bản dự án, lưu trữ dự án.
- Nút sản phẩm có nút con mắt bật/tắt và thanh trượt độ mờ: có thể chồng nhiều sản phẩm (ví dụ S1 và Capella trên cùng
  một thành phố, hoặc v2 và v3) lên bản đồ như các lớp QGIS.
- Ô tìm kiếm để lọc cây; nhãn đánh dấu chỗ thay đổi (lần chụp mới trên ASF, pha bị lỗi).

### Các khu vực

| Khu vực | Nội dung |
|---|---|
| **Overview** | Bản đồ mọi dự án, mỗi dự án một thẻ: trạng thái, sản phẩm mới nhất, mức tin cậy, vận tốc lớn nhất, lần chụp mới. Màn hình mở đầu mỗi ngày |
| **Project** | Quy trình xử lý thể hiện thành chuỗi pha, mỗi pha kèm trạng thái và lý do `geoeyes plan` đưa ra ("2 new acquisitions on ASF", "parameters changed"); nút Run; log trực tiếp (`runs/<id>/log.jsonl`); trục thời gian lần chụp và đường cơ sở; biểu mẫu thiết lập sinh từ schema `project.toml`, làm nổi bật chỗ khác preset |
| **Explorer** (màn hình chính) | Bản đồ WebGL hàng triệu điểm, thang jet_r Pretty Breaks giống QGIS và báo cáo; bấm điểm → chuỗi thời gian; vẽ vùng → chuỗi trung bình; so sánh hai sản phẩm (hiệu hoặc kéo trượt); bản đồ nền ảnh vệ tinh hoặc nền tối |
| **Results & validation** | Phiên bản sản phẩm, xem trước báo cáo PDF, tải GeoPackage / CSV, báo cáo gương phản xạ góc |

Bỏ hẳn: sigsolv, trình đọc `.mat`, bộ công cụ QC, xuất bản lên GeoServer. Để sau: cảnh báo biến dạng (Giai đoạn 6),
lịch giám sát, dự báo lượt bay qua của Sentinel-1, lớp phủ lượng mưa.

## Thiết kế giao diện

- Phong cách "Mission control": mặc định nền tối (có chế độ sáng), bản đồ toàn màn hình, bảng nổi bo góc, phông Inter.
- Màu trạng thái (xanh lá / vàng cam / đỏ) chỉ dùng cho trạng thái, luôn kèm biểu tượng và nhãn; thang màu
  biến dạng giống hệt QGIS và báo cáo PDF.
- Con số nào cũng có ngữ cảnh: chú thích khi rê chuột ("LOS, + toward the satellite, relative to the reference area"),
  nhãn mức tin cậy lấy từ báo cáo.

## Công nghệ

- Frontend: React + TypeScript + Vite, deck.gl + MapLibre, shadcn/ui (Radix) + Tailwind, TanStack Query,
  uPlot / ECharts cho chuỗi thời gian.
- Backend: `geoeyes.api` (FastAPI) đặt trên bộ điều khiển và sản phẩm; chạy nền bằng tiến trình con
  `geoeyes run`; log truyền trực tiếp qua SSE.
- Hàng triệu điểm: `build_product` ghi thêm điểm dạng PMTiles (bản đồ đọc theo từng tile); chuỗi thời gian
  của một điểm hay một vùng truy vấn thẳng trên GeoParquet bằng DuckDB (danh mục của Giai đoạn 7).

## Lộ trình

1. MVP: cây dự án, Overview, Explorer, trạng thái Project + Run, báo cáo.
2. Biểu mẫu thiết lập, trình tạo dự án mới (vẽ AOI trên bản đồ, chọn cảm biến, xem trước lần chụp trên ASF), báo cáo
   gương phản xạ góc, quản lý thư mục.
3. Cảnh báo, lịch giám sát, dự báo lượt bay qua.

Phần lõi cần có trước: `geoeyes.api` (dự án, trạng thái, sản phẩm, truy vấn điểm / chuỗi thời gian), PMTiles trong
sản phẩm, danh mục DuckDB, siêu dữ liệu thư mục.
