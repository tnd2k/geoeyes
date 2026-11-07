# Sổ đăng ký rủi ro — hệ thống dự báo sạt lở

> Sổ "sống": cập nhật sau mỗi sự cố, mỗi lần rà soát sẵn sàng (tháng 8), và mỗi khi một biện pháp được thực hiện.
> Phương pháp, cách phát hiện và các kịch bản xử lý P1–P6: [`../landslide-forecast-system.md`](../landslide-forecast-system.md)
> §8.7. Thang điểm L (khả năng) và I (tác động) 1–5; điểm = L × I; tác động 5 = bỏ sót cảnh báo vào ngày có thương
> vong.
> Trạng thái phòng ngừa: **xong** / **đang làm** / **chưa** (bước F thực hiện). Điểm ban đầu: 2026-11-03, chờ chủ dự
> án xác nhận (F0).

| # | Rủi ro | L | I | Điểm | Phòng ngừa: trạng thái | Việc tiếp theo | Bước |
|---|---|---|---|---|---|---|---|
| R1 | Mất điện / mạng nơi vận hành trong bão | 4 | 5 | 20 | chưa: hệ thống đang chạy trên một máy trạm | chọn nơi vận hành (F0); máy đám mây + dự phòng | F8 |
| R2 | Mưa vệ tinh báo thấp trong mưa cực đoan (lỗi âm thầm) | 4 | 5 | 20 | **đang làm**: đã so bốn sản phẩm vệ tinh (2026-11-04); ngày bão lệch nhau tới gấp đôi, không cùng chiều (Podul: IMERG cao nhất; Molave: GSMaP cao nhất); **đã đo được với 220 trạm KTTV** (bản sao imech.info, 2026-11-05): tổng mùa 0,77–1,00 nhưng ngày trạm ≥ 100 mm vệ tinh chỉ cho khoảng một nửa, POD ≥ 200 mm 0,17–0,26 | mô hình sai số phụ thuộc cường độ; nguồn trạm chính thức (KTTV); đưa độ chênh giữa các sản phẩm vào độ bất định; quy tắc "không thấp hơn mưa dự báo" | F2, F5 |
| R4 | Cảnh báo sai quá nhiều, người dùng mất tin | 4 | 4 | 16 | chưa | chốt ngân sách cảnh báo (F0), thống nhất cho cả vùng dưới dạng tỷ lệ cảnh báo sai, không chỉ theo từng xã (2026-11-05) | F0, F7 |
| R3 | Mưa vượt phạm vi huấn luyện | 3 | 5 | 15 | chưa | mô hình đơn điệu, nhãn "vượt kinh nghiệm" | F5 |
| R5 | Sạt lở có thương vong mà không được cảnh báo | 3 | 5 | 15 | chưa | A1; hiển thị cấp Điều 46 cạnh cấp của ta | F7, F8 |
| R15 | Bản tin không đến được xã | 3 | 5 | 15 | chưa | chọn kênh (F0); xác nhận đã nhận | F8 |
| R6 | Mưa quan trắc muộn / thiếu | 4 | 3 | 12 | **phần lớn xong**: đã truy cập được hai nguồn — IMERG (NASA) và GSMaP (JAXA, tài khoản 2026-11-03), độc lập khi một nhà cung cấp gặp sự cố nhưng không độc lập về sai số (dùng chung cảm biến vi ba thụ động GMI, AMSR2, SSMIS, MHS và ảnh hồng ngoại địa tĩnh; 2026-11-05); kho 2015–2025 đã đủ cho cả bốn sản phẩm (2026-11-04) | đo độ trễ thực tế | F2 |
| R8 | Dự báo sai quỹ đạo bão | 3 | 4 | 12 | chưa | xác suất từ tổ hợp ENS | F5 |
| R9 | Đầy đĩa, tiến trình sập | 3 | 4 | 12 | **một phần xong**: kiểm tra dung lượng trước mỗi phase; thùng rác không sao chép (2026-11-03, sau sự cố) | tách ổ vận hành | F8 |
| R10 | Bản phát hành làm hỏng chuỗi | 3 | 4 | 12 | một phần: test golden đã bắt được thay đổi DCT float32 (2026-11-03) | CI, khoá phát hành trong mùa | F8 |
| R13 | Sai thời gian (UTC / giờ Việt Nam) | 3 | 4 | 12 | chưa; đã biết IMERG ngày theo UTC (lệch 7 h) | quy ước UTC bên trong, test ranh giới ngày | F2 |
| R14 | Không có người dự báo | 3 | 4 | 12 | chưa | lịch trực; bản tin tự phát "chưa duyệt" | F8 |
| R16 | Hiểu sai xác suất | 3 | 4 | 12 | chưa | bộ từ cố định; tập huấn | F8 |
| R17 | Cấp của ta mâu thuẫn cấp chính thức | 4 | 3 | 12 | chưa | hiển thị cả hai, có lý do | F8 |
| R20 | Trách nhiệm pháp lý | 2 | 5 | 10 | chưa | điều khoản sử dụng (F0) | F0 |
| R7 | Mưa dự báo (ENS) muộn / thiếu | 3 | 3 | 9 | chưa | GFS dự phòng | F2 |
| R11 | Nhà cung cấp đổi định dạng / truy cập | 3 | 3 | 9 | **đã xảy ra**: máy chủ OPeNDAP cũ `gpm1.gesdisc` không còn phản hồi; đã chuyển sang `opendap.earthdata.nasa.gov` (2026-11-03) | phiếu dữ liệu có nguồn thứ hai | F2 |
| R18 | Lớp tính nhạy lỗi thời sau sự kiện lớn | 3 | 3 | 9 | chưa | cập nhật bắt buộc §8.2 | F8 |
| R12 | Lộ thông tin đăng nhập | 2 | 4 | 8 | **đã xảy ra** (mật khẩu bị in ra log, đã đổi) | kho bí mật; không in ra log | F8 |
| R19 | Mô hình trôi | 2 | 3 | 6 | chưa | huấn luyện lại hằng năm | F8 |

## Nhật ký sự cố

| Ngày | Sự cố | Rủi ro | Nguyên nhân | Hành động | Đóng |
|---|---|---|---|---|---|
| 2026-11-04 | Ổ D lại đầy ngay trong phase PS (lúc lưu bước 7), L5 dừng sau khi đã gỡ pha | R9 | ngưỡng 5 GB chỉ kiểm tra giữa các phase; một phase PS ghi hơn 10 GB checkpoint | xoá hai bản trùng trong thùng rác (không mất dữ liệu), chạy tiếp từ bước 6; còn mở: kiểm tra ngưỡng trước mỗi lần ghi checkpoint và ổ đĩa riêng (F8) | chưa |
| 2026-11-03 | Ổ D đầy, lượt L5 dừng giữa chừng | R9 | xoá dự án vào thùng rác bằng sao chép (file `.pmtiles` bị khoá nên không đổi tên được) | thùng rác chỉ đổi tên; kiểm tra dung lượng trước mỗi phase; có test | có |
| 2026-11-03 | Test golden CSK lệch một điểm 1,65 mm/năm | R10 | DCT float32 trong IRLS | hoàn tác; test đạt lại | có |
| 2026-11-03 | Máy chủ OPeNDAP cũ của GES DISC không phản hồi | R11 | nhà cung cấp chuyển hạ tầng | dùng OPeNDAP trên cloud qua CMR | có |
| trước 2026-11-03 | Mật khẩu Earthdata bị in ra log | R12 | lệnh đọc file thông tin đăng nhập | đã đổi mật khẩu; quy tắc không in file thông tin đăng nhập | có |
