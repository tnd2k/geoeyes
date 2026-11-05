# Skill: mỗi bài toán một quy trình tái lập được

> Bản dịch của [docs/en/skills/README.md](../../en/skills/README.md). Dịch ngày 2026-11-01.

Mỗi skill ứng với một bài toán GeoEyes giải. Nó nêu những gì cần có để giải lại bài toán đó trên một vùng khác
hoặc với một vệ tinh khác:

1. **dữ liệu cần chuẩn bị**: lấy từ đâu, định dạng gì, đặt ở đâu;
2. **phương pháp bên trong**, đúng như mã tính: công thức, ngưỡng và giá trị mặc định;
3. **các bước triển khai**: lệnh, đường dẫn trên web app, thời gian chạy, các tệp mỗi bước ghi ra;

tiếp theo là cách đọc kết quả, các bước kiểm tra chất lượng, hạn chế, và những gì cần đổi khi sang vùng mới. Các
ghi chú nghiên cứu ([../research/](../research/)) giải thích *vì sao* chọn phương pháp và đã tìm ra gì. Các hướng
dẫn ([../guide/](../guide/)) đi sâu vào từng công cụ. Skill là phiếu vận hành nối các tài liệu đó lại với nhau.

## Danh sách skill

| # | Skill | Bài toán | Lệnh chính |
|---|---|---|---|
| 1 | [insar-processing.md](insar-processing.md) | Từ chồng ảnh SAR (Sentinel-1, COSMO-SkyMed, Capella, ICEYE, Umbra; TerraSAR-X và ALOS mới có preset, chưa dựng được chồng ảnh) ra sản phẩm vận tốc | `geoeyes check / plan / run / status` |
| 2 | [opendata-stacks.md](opendata-stacks.md) | Tìm chồng ảnh băng X mở (ICEYE, Capella, Umbra) và tạo dự án từ một chồng | `geoeyes opendata` |
| 3 | [stack-qc.md](stack-qc.md) | Chồng ảnh đã đăng ký đủ tốt để xử lý chưa? | `geoeyes stack-qc` |
| 4 | [atmosphere.md](atmosphere.md) | Chọn và áp dụng hiệu chỉnh tầng đối lưu (ERA5, CERRA, GACOS) | `geoeyes atmosphere`, `gacos-order` |
| 5 | [ionosphere.md](ionosphere.md) | Nhận biết và hiệu chỉnh pha tầng điện ly (tách phổ, chồng ảnh Sentinel-1 IW dựng sẵn trong GeoEyes) | `[stack] ionosphere` |
| 6 | [gnss-calibration.md](gnss-calibration.md) | Kiểm định InSAR bằng GNSS và gắn vào hệ quy chiếu mặt đất | `geoeyes gnss`, `geoeyes tie` |
| 7 | [corner-reflector.md](corner-reflector.md) | Kiểm định bằng gương phản xạ góc (vị trí, RCS, tỷ số tín hiệu/nền, độ tương quan) | `geoeyes cr-report` |
| 8 | [incremental-monitoring.md](incremental-monitoring.md) | Thêm ngày chụp mới trong vài phút và cảnh báo sớm | `geoeyes run` (gia tăng), cảnh báo |
| 9 | [hazard-zoning.md](hazard-zoning.md) | Phân vùng nguy cơ sụt lún và trượt lở từ InSAR, mưa và nước ngầm | `geoeyes hazard` |
| 10 | [behaviour-and-risk.md](behaviour-and-risk.md) | Kiểu chuyển dịch của từng ô; vận tốc và độ nghiêng từng công trình; rủi ro công trình | `geoeyes behaviour / buildings / risk` |
| 11 | [lines-and-consolidation.md](lines-and-consolidation.md) | Lún lệch dọc đê, đường sắt, đường chính; độ lún còn lại | `geoeyes lines / consolidation` |
| 12 | [decompose-and-soft-soil.md](decompose-and-soft-soil.md) | Chuyển dịch đứng và đông–tây từ hai hướng chụp; bề dày đất yếu so với sụt lún | `geoeyes decompose / geology` |
| 13 | [susceptibility-and-forecast.md](susceptibility-and-forecast.md) | Nơi mặt đất có thể chuyển dịch (học máy); dự báo biến dạng | `geoeyes susceptibility / forecast` |
| 14 | [landslide-susceptibility.md](landslide-susceptibility.md) | Tính nhạy cảm trượt lở cấp vùng từ bản kiểm kê và các lớp địa hình | `geoeyes landslide` |
| 15 | [flood-reports.md](flood-reports.md) | Điểm ngập được báo cáo so với sụt lún; dự báo ngập trong ngày | `geoeyes floods` |
| 16 | [exposure-and-flood-layers.md](exposure-and-flood-layers.md) | Dân và công trình trên nền đang lún và trong vùng ngập (các lớp của Source Cooperative) | `geoeyes exposure`, `geoeyes coop` |

Thứ tự phụ thuộc: skill 1 làm trước. Các skill 3 đến 7 kiểm tra hoặc cải thiện sản phẩm của skill 1. Skill 9 là
đầu vào của các skill 10 đến 13. Skill 16 đọc được mọi sản phẩm, nhưng tốt hơn khi đã chạy 9 và 10.

## Khuôn mẫu một skill

Skill nào cũng có các mục sau, theo đúng thứ tự, để mọi skill đọc giống nhau:

```
# Skill: <tên>

> Một câu nêu bài toán. Trạng thái (vận hành / nghiên cứu), ngày kiểm tra gần nhất, lệnh CLI và đường dẫn web app.

## 1. Khi nào dùng
   Câu hỏi nó trả lời, quyết định nó hỗ trợ, khi nào không nên dùng.
## 2. Dữ liệu cần chuẩn bị
   Bảng: hạng mục | bắt buộc? | nguồn / cách lấy | định dạng, đặt ở đâu (đường dẫn hoặc khoá project.toml) | ghi chú.
   Sau đó là danh sách kiểm tra trước khi chạy.
## 3. Phương pháp
   Mã tính gì, từng bước, kèm công thức, ngưỡng và giá trị mặc định (tên tham số như trong project.toml), và các
   phương pháp đã công bố mà nó dựa vào.
## 4. Các bước triển khai
   Đánh số: lệnh (hoặc đường dẫn web app), việc nó làm, thời gian chạy, các tệp ghi ra.
## 5. Kết quả và cách đọc
   Tệp, trường, lớp bản đồ; ý nghĩa của từng giá trị.
## 6. Kiểm tra chất lượng
   Những gì cần kiểm tra trước khi tin hoặc công bố kết quả (số liệu, biểu đồ, tiêu chí chấp nhận).
## 7. Hạn chế và lỗi thường gặp
## 8. Áp dụng cho vùng hoặc vệ tinh mới
   Cần đổi gì (tham số, dữ liệu), giữ nguyên được gì, các thói quen đã biết ở từng vùng.
## 9. Tài liệu tham khảo
   Mã (đường dẫn tệp), hướng dẫn và ghi chú nghiên cứu, bài báo.
```

Tên tham số, tên tệp và lệnh viết đúng như trong mã. Skill mô tả những gì mã đang làm. Khi mã và skill khác nhau,
mã là chuẩn và skill phải sửa lại.
