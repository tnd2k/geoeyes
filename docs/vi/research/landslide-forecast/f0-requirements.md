# F0 — Yêu cầu và tiêu chí của hệ thống dự báo sạt lở (để ký)

> Bước F0 của [`../landslide-forecast-system.md`](../landslide-forecast-system.md) §9. Trạng thái: **A1–A8 đã duyệt
> về nguyên tắc, chờ ký** (bản nháp 2026-11-03; A1–A6 sửa sau lần rà soát ngày 2026-11-05, trước khi chạy bất kỳ dự
> báo ngược nào).
> Các giá trị còn lại là **đề xuất mặc định**. Anh chỉ cần sửa cột "Quyết định" ở những dòng muốn đổi. Khi ký, các
> giá trị được chốt và không đổi sau khi đã chạy dự báo ngược (§1 của tài liệu thiết kế).

## 1. Phạm vi của phiên bản đầu (v1)


| Mục              | Đề xuất                                                                                                                                                                  | Quyết định |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| Vùng             | các tỉnh miền Trung có Quảng Nam – Kon Tum làm lõi (vùng hiệu chỉnh); các tỉnh còn lại của khu vực 3 (Phụ lục XII) với tin cậy "thấp" cho tới khi có danh mục địa phương |            |
| Đơn vị cảnh báo  | xã (ranh giới sau sắp xếp 2025); đơn vị sườn dốc bên trong xã chỉ để xem chi tiết                                                                                        |            |
| Hạn dự báo       | hôm nay, +24 h, +48 h, +72 h                                                                                                                                             |            |
| Mùa vận hành     | tháng 9–12 (miền Trung)                                                                                                                                                  |            |
| Người dùng chính | Ban chỉ huy PCTT & TKCN cấp tỉnh và xã; cơ quan khí tượng thuỷ văn tỉnh                                                                                                  |            |
| Vai trò pháp lý  | sản phẩm chỉ mang tính tham khảo; cấp chính thức theo QĐ 18/2021 là căn cứ pháp lý                                                                                       |            |
| Mùa chạy bóng    | tháng 9–12/2027                                                                                                                                                          |            |




## 2. Tiêu chí nghiệm thu A1–A8


| #   | Tiêu chí                                                       | Đề xuất                                          | Quyết định  |
| --- | -------------------------------------------------------------- | ------------------------------------------------ | ----------- |
| A1  | Tỷ lệ ngày có sạt lở mà đơn vị kiểm định (huyện / vùng cảnh báo, hoặc cửa sổ nhiều ngày) ở cấp cảnh báo trở lên | ≥ 0,75, kèm khoảng 95 % và số sự kiện | Duyệt về nguyên tắc; sửa 2026-11-05 |
| A2  | Cảnh báo sai: (a) tỷ lệ cảnh báo sai trên cả vùng; (b) số ngày cảnh báo mỗi xã mỗi mùa | (a) ≤ ngân sách FAR (chờ thống nhất); (b) ≤ 5 | Duyệt về nguyên tắc; thêm (a) 2026-11-05 |
| A3  | Hơn quy tắc Điều 46 (các cấp gán với tần suất quan sát tính kiểm định chéo) và hơn chỉ dùng mưa | Brier skill score > 0, khoảng 95 % trên 0; báo cáo PR-AUC, CSI / ETS, SEDI | Duyệt về nguyên tắc; sửa 2026-11-05 |
| A4  | Độ tin cậy của xác suất                                        | trong dải nhất quán 90 %, nhóm có ≥ 10 sự kiện   | Duyệt về nguyên tắc; sửa 2026-11-05 |
| A5  | Số ngày sạt lở dự báo so với quan sát theo đơn vị-mùa (hoặc nhóm xác suất); PIT ngẫu nhiên hoá | khoảng 80 % của số đếm chứa 75–85 %; PIT đều | Duyệt về nguyên tắc; sửa 2026-11-05 (độ phủ trên kết quả nhị phân là vô nghĩa) |
| A6  | A1 và A3 vẫn đạt ở +24 h với mưa dự báo (ECMWF ENS, TIGGE 2015–2025) | có | Duyệt về nguyên tắc; đổi kho 2026-11-05 |
| A7  | Thời gian chạy; tái lập                                        | ≤ 5 phút mỗi tỉnh; cùng đầu vào cho cùng kết quả | Duyệt về nguyên tắc |
| A8  | Hội đồng thẩm định chấp nhận                                   | có văn bản                                       | Duyệt về nguyên tắc (tuỳ) |

*Vì sao sửa (2026-11-05):* 97 ngày-xã dương trên 61 ngày trong 11 mùa cho tần suất nền cỡ 10⁻⁴. Nếu chỉ có A2 (b), A1
có thể đạt trong khi FAR trên 0,99; ROC AUC bị thổi phồng bởi ca âm đúng; A4 không thể trượt trên các nhóm trống. Chi
tiết ở §1 của tài liệu thiết kế. Ngưỡng các cấp được chọn bên trong từng lượt bỏ-một-mùa.


**Ngân sách cảnh báo** (quyết định ngưỡng xác suất của các cấp, A2): đề xuất **≤ 5 ngày cảnh báo sai mỗi xã mỗi
mùa**, kèm một **tỷ lệ cảnh báo sai trên cả vùng** sẽ thống nhất với người dùng (2026-11-05). Nếu người dùng chấp nhận nhiều hơn, A1 sẽ dễ đạt hơn; nếu ít hơn, sẽ bỏ sót nhiều hơn. Đây là quyết định đánh
đổi của người dùng, không phải của mô hình.

## 3. Mục tiêu vận hành (§8 của tài liệu thiết kế)


| Mục                                 | Đề xuất                                                                                                                   | Quyết định |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Giờ phát bản tin chế độ thường      | 07:00 và 19:00 (giờ Việt Nam). Ước tính: ENS 12 UTC có khoảng 03:00 giờ Việt Nam, ENS 00 UTC khoảng 15:00; F2 đo giờ thật |            |
| Chế độ bão                          | chạy 3 giờ/lần, bản tin 6 giờ/lần, và ngay khi đổi cấp                                                                    |            |
| Điều kiện bật chế độ bão            | P(> 100 mm / 24 h) ≥ 30 % ở một đơn vị; hoặc có cảnh báo chính thức; hoặc cấp Điều 46 ≥ 1                                 |            |
| Ngân sách thời gian                 | bản tin ≤ T0 + 5 h (chế độ bão ≤ T0 + 4,5 h)                                                                              |            |
| Thời gian cảnh báo trước            | tính theo ngày (báo cáo chỉ ghi ngày, ± 1): ≥ 50 % ngày sạt lở được cảnh báo trước ≥ 1 ngày (sửa 2026-11-05; trước đây: trung vị ≥ 12 h) |            |
| Các mức xanh / vàng / đỏ của chỉ số | như bảng §8.6                                                                                                             |            |
| Tuổi tối đa của các lớp             | như bảng §8.2                                                                                                             |            |
| Rà soát sẵn sàng                    | hằng năm trước 15/8                                                                                                       |            |




## 4. Quyết định về hạ tầng và tổ chức


| Mục                | Đề xuất                                                                                                               | Quyết định |
| ------------------ | --------------------------------------------------------------------------------------------------------------------- | ---------- |
| Nơi vận hành       | máy chủ đám mây làm nơi chính, máy chủ tại cơ quan làm dự phòng; không dùng máy trạm cá nhân                          |            |
| Kênh phát tin      | hai kênh song song: kênh chính thức của tỉnh và SMS / Zalo; danh sách người nhận do tỉnh cung cấp                     |            |
| Người trực         | một người dự báo chính và một người thay, theo lịch trực mùa mưa                                                      |            |
| Hội đồng thẩm định | kỹ sư địa chất công trình, dự báo viên KTTV, chuyên gia thống kê, đại diện ban chỉ huy PCTT tỉnh (tên: chờ anh đề cử) |            |
| Điều khoản sử dụng | câu ở §1 ghi trên mọi bản tin và trong thẻ mô hình                                                                    |            |




## 5. Dữ liệu cần anh hỗ trợ (§10 của tài liệu thiết kế)


| Dữ liệu                                         | Vì sao                                      | Trạng thái                        |
| ----------------------------------------------- | ------------------------------------------- | --------------------------------- |
| Bản đồ phân vùng 1:50.000 (VIGMR)               | vùng nguy cơ của Điều 46, mốc so sánh       | chưa có                           |
| Bản đồ địa chất 1:200.000 / 1:50.000 và đứt gãy | đòn bẩy cuối cùng cho bản đồ tính nhạy (C4) | chưa có                           |
| Số liệu mưa trạm KTTV theo ngày 2015–2025       | kiểm tra sai số mưa vệ tinh (F2, R2)        | chưa có                           |
| Hồ sơ sạt lở có ngày (VIGMR, các tỉnh)          | danh mục cho mô hình kích hoạt (F1)         | chưa có; đang thu thập từ báo chí |
| Tài khoản GSMaP (JAXA, miễn phí)                | sản phẩm mưa thứ hai, độ trễ 4 h            | **đã có** (2026-11-03)            |
| Ranh giới xã sau 2025                           | đơn vị cảnh báo                             | cần nguồn chính thức              |




## 6. Sổ đăng ký rủi ro

Xem [`risk-register.md`](risk-register.md): 20 rủi ro với điểm ban đầu. Anh xác nhận hoặc sửa cột L và I.

## Ký duyệt


|           | Họ tên | Ngày | Ghi chú |
| --------- | ------ | ---- | ------- |
| Chủ dự án |        |      |         |


