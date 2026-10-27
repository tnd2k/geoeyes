# Ý tưởng viết báo

Trạng thái: ghi chú ngày 2026-10-27, cập nhật khi có kết quả mới.
Mục đích: ghi lại các hướng phân tích của GeoEyes đủ sức thành bài báo, những gì còn thiếu, và hướng nào chỉ nên làm
một mục trong bài khác.
Đánh giá dựa trên kết quả đã có trong workspace. Tính mới **chưa được rà kỹ** với tài liệu đã công bố; đó là việc
đầu tiên trước khi viết.

## Mục lục

1. [Bài 1: Hà Nội 2025–2026 với hai quỹ đạo](#1-bài-1-hà-nội-20252026-với-hai-quỹ-đạo)
2. [Bài 2: Học máy dự báo vùng dễ lún, vai trò của địa chất và cách đánh giá](#2-bài-2-học-máy-dự-báo-vùng-dễ-lún-vai-trò-của-địa-chất-và-cách-đánh-giá)
3. [Bài 3: Bậc pha giữa các dải con TOPS và tầng điện ly chạng vạng](#3-bài-3-bậc-pha-giữa-các-dải-con-tops-và-tầng-điện-ly-chạng-vạng)
4. [Các hướng chưa nên viết riêng](#4-các-hướng-chưa-nên-viết-riêng)
5. [Việc cần làm](#5-việc-cần-làm)

## 1. Bài 1: Hà Nội 2025–2026 với hai quỹ đạo

Đây là hướng có triển vọng nhất.

**Nội dung.**
- **Trục chính:** Sentinel-1 quỹ đạo xuống 91 và quỹ đạo lên 128, cùng giai đoạn 2025-10 → 2026-10. Bài đưa ra thành
  phần thẳng đứng và đông–tây thật, và đo phép chiếu một hướng nhìn (v_LOS / l_u) sai bao nhiêu
  ([two-geometries-and-soft-soil.md](two-geometries-and-soft-soil.md)).
- **Các mục ghép thêm:**
  - kiểu chuyển dịch của các ô (bảy mô hình chọn theo BIC), ngày khởi phát lún, phát hiện các ngày thay đổi chung do
    dữ liệu ([behaviour-and-risk.md](behaviour-and-risk.md));
  - rủi ro công trình theo từng toà nhà (nguy cơ × phơi nhiễm × dễ tổn thương) (cùng tài liệu);
  - trắc dọc đê, đường sắt, đường chính, góc biến dạng β ([lines-and-consolidation.md](lines-and-consolidation.md)).

**Điểm mới dự kiến.**
- Giai đoạn gần nhất.
- Hai hình học trong cùng một năm.
- Định lượng sai số của cách làm một hướng nhìn mà nhiều nghiên cứu Hà Nội trước đây dùng.
- Chuỗi phân tích từ chuyển dịch tới rủi ro công trình và hạ tầng tuyến.

**Lợi thế.** Dữ liệu hai quỹ đạo cùng giai đoạn; gương phản xạ góc CR-VP (dự án `hanoi_s1_desc`) để kiểm chứng.

**Kết quả tách thành phần đã có** (two-geometries-and-soft-soil.md §4.2, ngày 2026-10-27):
- Sản phẩm quỹ đạo lên 128 có mặt nghiêng khoảng 27 mm/năm trên vùng; sau khi khử, thẳng đứng −10,3 … +5,9 mm/năm
  (p2–p98), lún tối đa −27 mm/năm.
- Phép chiếu một hướng nhìn sai khoảng 5 mm/năm ở 90 % số ô. Đây là cận trên, vì gồm cả nhiễu của phép tách.
- Không đo được chuyển dịch ngang thật: phần đông–tây còn lại không hướng về các phễu lún. σ_e thực khoảng
  2,7 mm/năm, gấp bốn lần giá trị hình thức.
- Bài 1 vì vậy nên nhấn vào thành phần thẳng đứng và sai số của cách làm một hướng nhìn, không hứa chuyển dịch
  ngang. Riêng phần phát hiện mặt nghiêng giữa hai quỹ đạo và kiểm định "hướng về phễu lún" là đóng góp phương
  pháp nhỏ.

- **Nguồn gốc mặt nghiêng đã xác định** (§4.2): tầng điện ly lúc chạng vạng. Hà Nội nằm dưới đỉnh dị thường ion
  hoá xích đạo, quỹ đạo lên chụp lúc 18:06 gần cực đại chu kỳ mặt trời 25. Bằng chứng: ERA5, sai số DEM và quỹ đạo
  bị loại trừ; TEC lúc chụp quỹ đạo lên gấp khoảng 6 lần quỹ đạo xuống; độ dịch ESD tương quan với mặt nghiêng
  (r = −0,56, p = 0,003) chỉ ở quỹ đạo lên.
- Phần tầng điện ly và bậc pha giữa các dải con được tách thành **bài 3** (mục 3).
- Sản phẩm quỹ đạo lên còn có một bậc thẳng 6–10 mm/năm dọc chỗ nối IW2/IW3. Đây là lỗi xử lý, không phải đứt gãy
  (mục 3). Mọi kết quả tách thành phần ở dải phía tây rộng khoảng 3,5 km phải làm lại với sản phẩm đã cân pha.

**Còn thiếu.**
- Hiệu chỉnh tầng điện ly bằng tách phổ theo cự ly (D5), rồi tách thành phần lại.
- Kiểm chứng độc lập: GNSS (vận tốc đứng và ngang), thuỷ chuẩn, gương phản xạ góc.
- Đối chiếu ngày khởi phát lún với ngày thi công thật (giấy phép xây dựng, ảnh vệ tinh quang học).
- Khảo sát hư hại vài tuyến phố để kiểm chứng mức rủi ro.
- So sánh với các nghiên cứu InSAR Hà Nội trước đây (tốc độ, vùng lún).

**Nơi đăng gợi ý.** *Remote Sensing* (MDPI), *Vietnam Journal of Earth Sciences*, *International Journal of Applied
Earth Observation and Geoinformation*.

## 2. Bài 2: Học máy dự báo vùng dễ lún, vai trò của địa chất và cách đánh giá

Đây là hướng có kết quả định lượng rõ nhất ([two-geometries-and-soft-soil.md](two-geometries-and-soft-soil.md) §4.4).

**Kết quả đã có.**
- Thêm bề dày trầm tích làm AUC theo kiểm định chéo không gian ở Mexico City tăng từ 0,869 lên 0,918 (gradient
  boosting).
- Ở Mexico City, bề dày thành biến dự báo quan trọng nhất (0,15, so với 0,06 của biến kế tiếp).
- Ở Hà Nội, mức tăng chỉ từ 0,718 lên 0,734, vì lưới mở chạm giới hạn 50 m ở 92 % số ô.
- Kiểm định chéo ngẫu nhiên cho AUC cao hơn hẳn kiểm định chéo không gian (Mexico City, random forest: khoảng 0,98 so
  với 0,89). Nhiều nghiên cứu vẫn báo cáo con số ngẫu nhiên, nên đây là thông điệp phương pháp có ích.

**Còn thiếu.**
- Một lớp đất yếu thật cho Hà Nội: bản đồ bề dày Holocen hoặc số liệu lỗ khoan.
- Thêm ít nhất một vùng thứ ba để kết luận có tính khái quát.

**Hợp tác nên tính.**
- BGS: 271 lỗ khoan và mô hình 3D Hà Nội.
- Trường Đại học Mỏ – Địa chất: khoảng 160 lỗ khoan.
- Bản đồ của Phi & Strokova (2017).

Có số liệu này, bài 2 mạnh lên nhiều.

## 3. Bài 3: Bậc pha giữa các dải con TOPS và tầng điện ly chạng vạng

Đây là một bài phương pháp, ghi ngày 2026-10-27 theo đề nghị của người dùng. Bài gom hai lỗi tìm thấy trên Hà Nội
quỹ đạo lên 128: mặt nghiêng do tầng điện ly và bậc pha ở chỗ nối hai dải con.

**Câu chuyện của bài.**
1. Bản đồ vận tốc quỹ đạo lên có một đường cắt thẳng dài hơn 15 km, bậc 6–10 mm/năm. Đường này dễ bị đọc nhầm là đứt
   gãy hoạt động hoặc đứt gãy lộ trên mặt.
2. Đường cắt bị loại trừ là tín hiệu thật vì:
   - nó trùng đúng cột nối IW2/IW3 (góc tới 41,78°) và song song hướng bay (−12°);
   - quỹ đạo xuống (chỉ một dải con) không có bậc ở cùng chỗ (< 1 mm/năm);
   - nó lệch 35–50° so với hướng các đứt gãy Sông Hồng, Sông Chảy;
   - độ lớn của nó đổi theo cách xử lý.
3. Nguyên nhân là pha interferogram của hai dải con lệch nhau một hằng số ở một số ngày. Khâu ghép kiểu cắt rồi dán
   biến hằng số đó thành bậc thẳng. Mở pha và chuỗi thời gian lại biến nó thành vận tốc, vì các ngày lệch dồn vào
   nửa cuối chuỗi.
4. Cách sửa: đo bậc pha qua chỗ nối cho từng ngày và khử trước khi ghép.

**Kết quả đã có** (Hà Nội, quỹ đạo lên 128, tham chiếu 2026-04-02):
- Bậc pha chỉ có hai mức: khoảng 0 (−0,2 … +0,2 rad) hoặc khoảng −2,2 rad (−2,14 … −2,84).
  - Đo trực tiếp: 2025-10-04 và 2026-07-02 → 08-31 là năm ngày S1D. Riêng 2026-07-26 không lệch.
  - Theo ESD, các ngày 09-12, 09-24, 10-18 cũng lệch, còn 10-06 thì không.
- Mức −2,2 rad trùng hoàn toàn với các ngày ESD của hai dải con lệch nhau +0,012 dòng (các ngày khác ±0,002). Đây
  là một dấu hiệu chẩn đoán rẻ, có sẵn trong mọi quy trình TOPS.
- Bậc không theo vệ tinh (S1A có, S1D có ngày không), không theo phiên bản IPF, không theo cách cắt burst, không theo
  độ lệch thời gian giữa hai dải hay Doppler. Bản thân sai lệch ESD 0,012 dòng chỉ gây vài phần mười radian, nên cả
  hai nhiều khả năng là triệu chứng của cùng một nguyên nhân trong sản phẩm SLC. **Nguyên nhân gốc chưa rõ.**
- Phương pháp đo bậc: hai dải 40 cột (khoảng 100 m) hai bên chỗ nối, bỏ 4 cột sát vết cắt, khối 32 dòng, lấy trung
  bình có trọng số độ kết hợp. Độ nhất quán giữa các khối 0,83–0,97; ước lượng tự động khớp đo tay (−2,224 so với
  −2,22 rad).
  - Mã: `seam_step` trong `processing/stack/native/s1_stack.py`.
  - Giá trị theo ngày lưu ở thuộc tính `subswath_phase_offsets` của stack.
  - Test: `tests/unit/processing/test_subswath_seam.py`.
- Hình minh hoạ đã dựng: interferogram 2026-07-02 trước/sau cân pha và mặt cắt pha qua chỗ nối (bậc −2,3 rad biến
  mất, đường cong liền mạch); bản đồ vận tốc ba sản phẩm có đường cắt. Hình và script nằm ở
  `geoeyes_workspace/projects/hanoi_s1/analyses/paper3_subswath_seam/`.
- Tầng điện ly (two-geometries-and-soft-soil.md §4.2): mặt nghiêng vận tốc trên 14 km là 23,5 mm/năm khi chưa hiệu
  chỉnh, 12,5 với mặt phẳng chỉ trên vùng cắt (v2), 11,3 với mặt phẳng cục bộ trên toàn burst (v3). Sai số vận tốc
  trung vị 3,9 → 5,6 → 4,4 mm/năm. Quỹ đạo xuống đối chứng: 2,9 mm/năm.
- **v4 = v3 + cân pha dải con** (2026-10-27). Đủ 25 ngày: 15 ngày bậc −0,11 … +0,16 rad, 10 ngày bậc −2,11 … −2,86
  rad, khớp đúng nhóm ngày ESD lệch.
  - Bậc vận tốc qua chỗ nối giảm từ +10,4 xuống +1,8 mm/năm; đường cắt biến mất trên bản đồ.
  - Độ lệch chuẩn vận tốc 6,34 → 5,75 mm/năm, sai số trung vị 4,38 → 4,08.
  - Mặt nghiêng còn 15,3 mm/năm trên 14 km (gx −0,58, gy −0,92 mm/năm/km). Con số này cao hơn v3 (11,3) vì ở v3 bậc
    nhảy đã che bớt phần nghiêng theo hướng đông–tây. Đây là phần tầng điện ly chưa khử hết, có thể gồm cả phần bậc
    lọt vào ước lượng tách phổ.
  - Tách thành phần với quỹ đạo xuống v4, có khử mặt phẳng: tỉ lệ ô có chuyển dịch ngang "đáng kể" giảm từ 17,8 % (v1)
    xuống 5,6 %; tương quan E–U từ −0,59 xuống −0,26; thẳng đứng p2–p98 −8,1 … +5,3 mm/năm. Phần lớn "chuyển dịch
    ngang" trước đây là do bậc ở chỗ nối. Không khử mặt phẳng thì vẫn còn mặt nghiêng 18,5 mm/năm và tỉ lệ 17,1 %.
- **v5 và v6: bậc ra khỏi tách phổ** (2026-10-27/28). Cả hai lấy dải rộng nhất (IW3) làm mốc.
  - v5 thêm một hằng số tự do cho mỗi dải con vào mô hình tầng điện ly. **Không dùng được:** hằng số ước lượng ra
    −4,4 … +4,6 rad, cả ở 15 ngày không có bậc, và đổi gradient cự ly của ngày 2025-10-04 từ −0,030 sang +0,126
    rad/km. Với mô hình mặt phẳng cục bộ, hằng số theo dải con gần như trùng với gradient cự ly.
  - v6 trừ thẳng bậc đã đo trên toàn băng khỏi băng thấp của từng dải con trước khi mở pha. Băng tương quan chéo
    không cần sửa vì bậc giống nhau ở hai băng con. Gradient cự ly của 2025-10-04 thành +0,001 ± 0,014 rad/km (v4:
    −0,030); chênh lệch khoảng 0,03 rad/km đúng là phần a·c của bậc. Mã: `WideArea.shift` trong
    `processing/stack/native/iono.py`. Test: `test_subswath_step_is_shifted_out_of_the_ionosphere`.
  - So sánh (cùng một script; bậc = trung vị vận tốc trong 0,08° góc tới hai bên chỗ nối; gx, gy = mặt phẳng khớp
    toàn vùng, mm/năm/km):

    | | Bậc (mm/năm) | gx | gy | Độ lệch chuẩn | Sai số trung vị | Tách E–U, khử phẳng: ngang / tương quan | Không khử phẳng: ngang / tương quan |
    |---|---|---|---|---|---|---|---|
    | v1 | +8,0 | +0,75 | −1,50 | 8,17 | 3,92 | 17,8 % / −0,59 | 41 % / −0,80 |
    | v4 | +0,9 | −0,58 | −0,92 | 5,75 | 4,08 | 5,6 % / −0,26 | 17,1 % / −0,59 |
    | v5 | +0,7 | −0,56 | −1,01 | 5,84 | 3,81 | 5,0 % / −0,22 | 17,3 % / −0,60 |
    | v6 | +1,4 | −0,49 | −0,77 | 5,21 | 3,89 | 4,2 % / −0,16 | 11,5 % / −0,51 |
    | desc v4 | — | −0,02 | −0,20 | 3,92 | 2,64 | | |

  - v6 tốt nhất ở gần mọi chỉ số: mặt nghiêng quỹ đạo lên trong phép tách giảm từ 19,2 (v5) xuống 16,3 mm/năm,
    tương quan E–U khi không khử phẳng giảm từ −0,60 xuống −0,51. Phần bậc lọt vào tách phổ là có thật và đo được.
  - Vẫn còn gradient Bắc–Nam khoảng −0,8 mm/năm/km mà quỹ đạo xuống không có (−0,2). Chuyển dịch Bắc–Nam gần như không
    vào hướng nhìn, nên phần này là sai số của quỹ đạo lên. Phân tích từng ngày cho thấy nó **không** phải tầng điện
    ly còn sót (r = 0,18 với gradient đã khử, dao động gấp 10 lần sai số hình thức, lớn nhất mùa hè), nhiều khả năng
    là đối lưu chiều tối (`docs/vi/guide/ionosphere.md` §6). Đây là việc của bài 2 hơn là bài này.

**Điểm mới dự kiến (cần rà tài liệu).**
- Ghi nhận và định lượng bậc pha giữa các dải con trong chuỗi Sentinel-1 gần đây (có S1D), kèm dấu hiệu chẩn đoán
  bằng hiệu ESD giữa các dải con.
- Một bước sửa đơn giản, tự động, theo từng ngày trong khâu ghép, với tiêu chí chất lượng (độ nhất quán, số khối).
- **Tương tác với hiệu chỉnh tầng điện ly bằng tách phổ.** Một hằng số pha không phụ thuộc tần số có trong cả hai băng
  con sẽ lọt khoảng một nửa (c·f_L·f_H / (f0·(f_L + f_H))) vào ước lượng tầng điện ly. Vì vậy cân pha dải con phải
  làm **trước** tách phổ. Cần chứng minh bằng mô phỏng và số liệu.
- Chọn dải con làm mốc không ảnh hưởng kết quả sau khi quy về tham chiếu: chỉ khác một hằng số toàn ảnh mỗi ngày.
  Nên giữ dải rộng nhất làm mốc để ít dữ liệu bị sửa nhất.
- Bối cảnh vĩ độ thấp: chụp lúc 18:06 dưới đỉnh dị thường ion hoá xích đạo, gần cực đại chu kỳ 25. Hà Nội là trường
  hợp chịu cả hai lỗi cùng lúc.
- Thông điệp cho người dùng: một đường thẳng dọc hướng bay trên bản đồ vận tốc phải được kiểm tra với vị trí chỗ nối
  dải con và với quỹ đạo kia trước khi diễn giải là kiến tạo.

**Còn thiếu.**
1. Rà tài liệu về bậc pha giữa các dải con hoặc burst của Sentinel-1: hiệu chỉnh pha giản đồ anten (EAP), thay đổi
   IPF, các báo cáo của ESA, cách ISCE2 topsStack, SNAP, GMTSAR và Dolphin xử lý. Bước này quyết định bài có mới
   hay không.
2. Tìm nguyên nhân gốc:
   - so sánh annotation của các ngày lệch và không lệch (mọi trường, không chỉ thời gian, Doppler);
   - đo bậc trên vùng chồng lấn giữa hai dải con (cùng mặt đất được chụp hai lần) để loại hẳn ảnh hưởng của mặt đất;
   - kiểm tra bậc ở chỗ nối IW1/IW2;
   - xem bậc có theo phân cực VH không.
3. Mở rộng: các quỹ đạo khác ở Việt Nam và một vùng vĩ độ trung bình. Xem bậc có gắn với S1D, với chạng vạng, hay xuất
   hiện ở mọi nơi.
4. ~~Đưa cân pha lên trước tách phổ và lấy dải rộng nhất làm mốc, rồi chạy lại~~ (xong: v6). Còn lại: định lượng
   phần tầng điện ly bị ước lượng sai do bậc theo từng ngày (gradient v4 so với v6 cho cả 25 ngày).
5. ~~So v1–v4~~ (xong đến v6, bảng ở trên). Còn lại: mặt nghiêng theo thời gian của từng interferogram.
6. Nếu nguyên nhân nằm ở sản phẩm SLC: liên hệ nhóm chất lượng Sentinel-1 (ESA/MPC) trước khi công bố.

**Nơi đăng gợi ý.** *IEEE Geoscience and Remote Sensing Letters* (bài ngắn), *Remote Sensing* (MDPI), hoặc một
mục phương pháp lớn trong bài 1 nếu rà tài liệu cho thấy hiện tượng đã được biết.

## 4. Các hướng chưa nên viết riêng

| Hướng | Lý do | Dùng ở đâu |
|---|---|---|
| Lún cố kết (hướng 4) | chỉ 4–30 ô đạt điều kiện, chuỗi 0,5–1 năm; phép kiểm tra c_v cho thấy nhiều khả năng không phải cố kết cả lớp đất | chờ chuỗi ≥ 3 năm |
| Hạ tầng tuyến (hướng 3) | Mexico City đã được nghiên cứu nhiều (Metro tuyến A, Zaragoza), chuỗi 6 tháng; ở Hà Nội chỉ 21 % chiều dài đê có điểm InSAR | một mục trong bài 1 |
| Rủi ro công trình (hướng 2) | phương pháp đã có (Peduto và cs. 2017); chưa có khảo sát hư hại | một mục trong bài 1 |
| Kiểu chuyển dịch (hướng 1) | cách phân loại tương tự các nghiên cứu trước; điểm riêng là phát hiện ngày thay đổi chung do dữ liệu | phần phương pháp của bài 1 |
| Dự báo bằng học máy | kết quả âm: chưa thắng mô hình giữ nguyên trên chuỗi ngắn | ghi chú ngắn, sức hút thấp |

## 5. Việc cần làm

1. Rà tài liệu InSAR Hà Nội, tài liệu về học máy dự báo vùng dễ lún, và tài liệu về bậc pha giữa các dải con
   Sentinel-1 để xác định chính xác điểm mới của ba bài.
2. Hoàn tất tách thành phần Hà Nội (D1 trong two-geometries-and-soft-soil.md).
3. Thu thập số liệu kiểm chứng: GNSS, thuỷ chuẩn, ngày thi công, khảo sát hư hại.
4. Liên hệ để có bản đồ bề dày đất yếu hoặc lỗ khoan Hà Nội (G1).
5. Dựng đề cương bài 1, kèm danh sách hình và bảng lấy từ các kết quả đã có.
