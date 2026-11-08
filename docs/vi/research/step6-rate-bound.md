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

## Kết quả S0 (2026-11-08): giả thuyết bị bác

Tôi chạy lại bước 6–8 của `hcm_d18` với cấu hình v6 và ghi lại mọi quyết định của periodogram
(`ps_exp/S0/s0_rates.npz`, đã xóa sau khi duyệt).

- **Các cạnh lưới không tạo ra đuôi.** Chỉ 2,6 % trong 110 nghìn cạnh được nhận một vận tốc. Chỉ 23 cạnh có vận
  tốc trên 40 mm/năm.
- **Mô hình ps_rate quyết định vận tốc của đuôi.** Với 95 % số PS nhanh hơn −40 mm/năm, vận tốc cuối cùng lệch
  dưới 10 mm/năm so với vận tốc mô hình ps_rate của chính PS đó (tương quan trên toàn bộ PS là −0,988, ngược dấu
  vì tính theo pha).
- **Các cung nối tới PS nhanh nhất không phải đỉnh ngẫu nhiên.** 57 % số cung chạm một PS nhanh hơn −60 mm/năm
  có vận tốc trên 20 mm/năm, trong khi tỷ lệ này trên mọi cung chỉ là 0,42 %. Độ kết hợp periodogram của các cung
  này cao hơn ngưỡng ngẫu nhiên 0,17. Nó cũng **cao hơn 0,21 so với vận tốc tốt nhất trong khoảng ±20 mm/năm**,
  nên periodogram có phạt (ý tưởng B) sẽ không thay đổi chúng.
- **Các PS nhanh đi thành cụm chặt.** 48 PS nhanh hơn −60 mm/năm tạo thành 17 cụm (nối nhau trong 60 m), mỗi cụm
  3–6 PS có vận tốc gần như bằng nhau. Ví dụ:
  - 6 PS tại 106,6972 E, 10,6833 N, −93 … −78 mm/năm;
  - 5 PS tại 106,6821 E, 10,6951 N, −68 … −65 mm/năm.

  Chỉ 2 trong 48 PS đứng riêng lẻ. 629 PS nhanh hơn −40 mm/năm tạo thành 133 cụm, cụm lớn nhất có 28 PS.

**Kết luận.** Chính pha cuộn cho thấy các PS này chuyển động nhanh hơn các PS xung quanh một cách nhất quán: đó
là từng công trình hoặc từng khối nhà nhỏ, nhiều khả năng mới xây trên nền đất yếu. Bước 6 không tự tạo ra chúng,
và chặn vận tốc ở bước 6 sẽ xóa mất tín hiệu thật. Vì vậy các ý tưởng A–C không được cài đặt.

Đuôi được xử lý ở các bước sau:
- bộ lọc không gian của sản phẩm loại các PS đứng riêng lẻ (0,55 % tổng số PS);
- các lớp chú giải trải trên khoảng P0.1–P99.9.

## Rủi ro

Chuyển động cục bộ nhanh thật (một công trình trên nền đất mới đắp) tự nó có gradient dốc. B chỉ giữ chuyển
động đó khi nó có độ kết hợp cao. S0 và S3 phải cho biết mất bao nhiêu PS loại này.
