Văn phong cho lần biên tập lại (bắt buộc đọc trước khi sửa)

Mục tiêu: người đọc là kỹ sư/nhà nghiên cứu viễn thám người Việt. Văn bản phải đọc như được VIẾT bằng tiếng Việt,
không như được dịch. Giữ đúng và đủ nội dung, số liệu, thuật ngữ (docs/vi/GLOSSARY.md), mã, đường dẫn, tham chiếu.

Được phép (và nên):
- Đổi cấu trúc câu, tách câu dài, gộp câu ngắn, đảo trật tự mệnh đề cho thuận tiếng Việt.
- Thay danh từ hoá kiểu Anh bằng động từ: "việc thực hiện việc so sánh" → "so sánh".
- Bớt bị động "được": "được thay thế bằng ghi log" → "thay bằng ghi log"; "được liệt kê trong" → "nêu ở".
- Bỏ ngoặc lồng nhau: "các điểm tán xạ bền vững (PS) và điểm tán xạ phân bố (DS)" ổn, nhưng "(... (PS) ...)" thì
  viết lại câu.
- Dùng từ nối tự nhiên: "Tuy vậy", "Do đó", "Nói cách khác", "Cụ thể", thay vì dịch "However/Hence" máy móc.

Các lỗi đã gặp và cách sửa (ví dụ):
- "có thể cho một phân vùng nguy cơ ... đáp ứng ba điều sau hay không: (a) truy nguyên được về thực hành đã công bố"
  → "Liệu có thể kết hợp chuỗi thời gian chuyển dịch InSAR với lượng mưa để phân vùng nguy cơ ... sao cho: (a) mỗi
  bước đều dựa trên phương pháp đã công bố"
- "đúng chế độ mà InSAR đo được" → "đúng dải tốc độ mà InSAR đo được"
- "Ở đây chỉ ghi lại những điểm định hình thiết kế" → "Phần này chỉ nêu những điểm ảnh hưởng đến thiết kế"
- "không cho chu kỳ lặp lại hay xác suất phá huỷ" → "chưa ước tính chu kỳ lặp hay xác suất phá huỷ"
- "nằm ngoài v1" → "chưa thuộc phạm vi v1"
- "Được thay thế bằng ghi log đầy đủ." → "Thay bằng ghi log đầy đủ."
- Trong bảng: viết cụm ngắn gọn, không cần câu đầy đủ.

Không được:
- Bỏ, tóm tắt hay thêm nội dung; đổi số liệu, công thức, tên tham số, tên tệp, liên kết, tài liệu tham khảo.
- Đổi cấu trúc Markdown (tiêu đề, bảng, danh sách, khối mã, mục lục). Nếu sửa chữ của tiêu đề, cập nhật lại anchor
  trong mục lục tương ứng.
- Dịch tên giao diện/CLI trong backtick.

Cách làm: đọc song song bản tiếng Anh gốc và bản dịch hiện tại theo từng đoạn ~100 dòng, viết lại đoạn đó, rồi
ghi đè tệp bản dịch. Cuối cùng kiểm tra số tiêu đề / dòng bảng / mục danh sách / khối mã vẫn khớp bản gốc.
Đổi dòng ngày trong phần đầu tệp thành: "Dịch ngày 2026-10-26, biên tập lại 2026-10-26."
