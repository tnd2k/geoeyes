# Bước 6: giới hạn vận tốc theo dữ liệu (kế hoạch, 2026-11-08)

## Vấn đề

Sản phẩm v6 của `hcm_d18` có một đuôi PS rất nhanh: nhanh nhất −93 mm/năm, và 617 PS nhanh hơn −40 mm/năm.
Khoảng một nửa số PS này trôi dần khỏi các PS xung quanh qua các năm. Bộ lọc không gian ở bước dựng sản phẩm
loại 0,55 % số PS, nhưng giữ lại cụm −93 vì các PS lân cận của nó cũng nhanh.

Chủ dự án muốn chính bước 6 không sinh ra các vận tốc này, để không phải chỉnh tay dải màu (với TP.HCM, ±20
mm/năm là đọc đúng).

## Bước 6 sinh vận tốc ở đâu

Cả hai chỗ đều tìm trong một khoảng cố định ±`unwrap_max_edge_velocity` (100 mm/năm):

1. `space_time.edge_rates`: vận tốc tuyến tính của từng cạnh lưới, tức là *hiệu* vận tốc giữa hai ô kề nhau
   cách nhau 50 m. Một vận tốc được nhận khi độ kết hợp periodogram của nó vượt ngưỡng ngẫu nhiên và hơn vận
   tốc 0 ít nhất `min_gain`.
2. `ps_rate.ps_rate_model`: vận tốc của từng cung Delaunay giữa các PS (tối đa 500 m). Các vận tốc này được
   tích phân bằng L1 thành một vận tốc cho mỗi PS.

Vận tốc của một cạnh hay một cung là một *gradient* vận tốc. Ngay ở mép phễu lún, nó hiếm khi vượt vài mm/năm
trên 50 m. Một cạnh nhiễu có đỉnh periodogram ở xa (ví dụ 60–90 mm/năm) vẫn có thể vượt phép kiểm tra ngẫu
nhiên. Khi tích phân, cả một cụm PS bị kéo theo vận tốc đó. Đuôi −93 nằm sát cận ±100, điều này ủng hộ giả
thuyết trên.

## Ý tưởng

Không dùng cùng một khoảng ±100 mm/năm cho mọi cạnh, mà giới hạn hoặc phạt vận tốc *dựa trên dữ liệu*.

- **A. Cận lấy từ dữ liệu.** Lượt đầu: tính vận tốc các cạnh như hiện nay. Lấy phân bố các vận tốc *tin cậy*,
  quy về độ dài cạnh. Đặt cận bằng `clip(c × P99(|vận tốc|), sàn, 100)` rồi tìm lại trong cận đó. Cạnh nào có
  vận tốc tốt nhất nằm ngoài cận thì nhận vận tốc 0 (mô hình legacy).
- **B. Periodogram có phạt (đề xuất thử trước).** Chọn vận tốc thử làm cực đại `coh(r) − λ·|r| / r_scale`, để
  một vận tốc lớn chỉ thắng khi kết hợp rõ ràng hơn một vận tốc nhỏ. `r_scale` lấy từ các vận tốc tin cậy (như
  ở A), nên không có gì phải chỉnh tay. Cách này loại các đỉnh ngẫu nhiên ở xa mà không chặn những gradient
  nhanh thật có độ kết hợp cao.
- **C. Vận tốc trên mét cho các cung PS.** Trong `ps_rate`, áp cận cho vận tốc chia độ dài cung, vì cung dài
  từ khoảng 10 m đến 500 m.

## Các bước (làm từng bước, duyệt sau mỗi bước)

- **S0. Chẩn đoán.** Chạy lại bước 6 của `hcm_d18` và lưu vận tốc các cạnh và các cung. Kiểm tra xem các PS ở
  đuôi (v < −40, nhất là cụm −93) có nằm sau những cạnh hoặc cung có vận tốc được nhận lớn (> 20 mm/năm) và chỉ
  vừa vượt ngưỡng ngẫu nhiên hay không. *Nếu không, nguyên nhân nằm ở chỗ khác và kế hoạch phải đổi.*
- **S1.** Cài B (kèm cận của A làm chốt chặn) trong `edge_rates`, dưới tham số `[ps] unwrap_rate_prior` =
  "auto" | "n". Thêm test giả lập: một phễu lún thật có mép dốc thì được giữ; một đỉnh ngẫu nhiên ở 80 mm/năm
  trên một cạnh nhiễu thì bị loại.
- **S2.** Áp dụng C trong `ps_rate_model`.
- **S3.** Chạy lại bước 6–8 của `hcm_d18` (checkpoint lean, khoảng 4 GB). So với kết quả hiện tại: đuôi (số PS
  < −40 và giá trị nhỏ nhất của v), số epoch ngoại lai, số PS bộ lọc không gian còn phải loại, và NMAD vùng ổn
  định. Kiểm tra ca golden CSK Hà Nội (17 ifg) và `hanoi_s1_desc`.
- **S4.** Chọn mặc định, cập nhật docs và advisor, ghi kết quả vào đây.

## Rủi ro

Chuyển động cục bộ nhanh thật (một công trình trên nền đất mới đắp) tự nó có gradient dốc. B chỉ giữ chuyển
động đó khi nó có độ kết hợp cao. S0 và S3 phải cho biết mất bao nhiêu PS loại này.
