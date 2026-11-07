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
4. [Bài 4: Ngập úng và sụt lún ở Hà Nội, có độ bất định](#4-bài-4-ngập-úng-và-sụt-lún-ở-hà-nội-có-độ-bất-định)
5. [Các hướng chưa nên viết riêng](#5-các-hướng-chưa-nên-viết-riêng)
6. [Việc cần làm](#6-việc-cần-làm)

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
  - Đối chiếu số liệu (2026-11-05): 26,9 mm/năm là biên độ (max − min) của mặt phẳng khớp trên vùng chung 12.658 ô
    của phép tách (v1, two-geometries-and-soft-soil.md §4.2). Con số 23,5 mm/năm ở mục 3 là của cùng sản phẩm v1
    nhưng đo khác: độ lớn gradient × 14 km, √(0,75² + 1,50²) × 14 ≈ 23,5. Hai số không mâu thuẫn; khi viết bài chỉ
    dùng một cách đo (gradient, mm/năm/km).
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
- Hiệu chỉnh tầng điện ly bằng tách phổ theo phương nhìn ngang (D5), rồi tách thành phần lại.
- Kiểm chứng độc lập: GNSS (vận tốc đứng và ngang), thuỷ chuẩn, gương phản xạ góc.
- Đối chiếu ngày khởi phát lún với ngày thi công thật (giấy phép xây dựng, ảnh vệ tinh quang học).
- Khảo sát hư hại vài tuyến phố để kiểm chứng mức rủi ro.
- So sánh với các nghiên cứu InSAR Hà Nội trước đây (tốc độ, vùng lún).

**Đánh giá 2026-11-05.**
- Sản phẩm quỹ đạo lên vẫn chưa sạch: tầng điện ly còn sót 15,3 mm/năm trên 14 km ở v4 (v6: gx −0,49, gy −0,77
  mm/năm/km, khoảng 13 mm/năm trên 14 km), gradient Bắc–Nam khoảng −0,8 mm/năm/km mà quỹ đạo xuống không có, và bản
  sửa chỗ nối dải con mới có từ v4/v6 (mục 3).
- Chuỗi chỉ một năm nên phần theo mùa lẫn vào vận tốc. Vì vậy phép tách thành phần **chưa thể là kết quả chính** cho
  tới khi kiểm bằng GNSS hoặc gương phản xạ góc.
- Các mục rủi ro công trình và hạ tầng tuyến chưa được công bố dưới dạng "hư hại": β hiện là độ nghiêng (công trình)
  hoặc tốc độ thay đổi độ dốc (tuyến), đang so với giới hạn góc biến dạng (behaviour-and-risk.md §3.1,
  lines-and-consolidation.md §2.3). Phải sửa sang độ cong / độ võng trước.

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

**Đánh giá 2026-11-05.** Tính mới yếu nếu chưa có số liệu lỗ khoan Hà Nội.
- Chênh lệch giữa kiểm định chéo ngẫu nhiên và kiểm định chéo không gian đã được công bố nhiều (Roberts và cs. 2017;
  Ploton và cs. 2020; Meyer & Pebesma 2021).
- Vai trò của bề dày lớp sét đối với sụt lún ở Mexico City cũng đã được biết (Chaussard và cs. 2014; Cigna & Tapete
  2021).
- Bài chỉ có đóng góp riêng khi có lớp đất yếu thật cho Hà Nội (lỗ khoan BGS / Đại học Mỏ – Địa chất) và kết quả
  tổng quát hoá được sang vùng thứ ba.

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
   biến hằng số đó thành bậc thẳng. Giải chập pha và chuỗi thời gian lại biến nó thành vận tốc, vì các ngày lệch dồn vào
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
  bình có trọng số độ nhất quán. Độ đồng thuận giữa các khối 0,83–0,97; ước lượng tự động khớp đo tay (−2,224 so với
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
    −4,4 … +4,6 rad, cả ở 15 ngày không có bậc, và đổi gradient theo phương nhìn ngang của ngày 2025-10-04 từ −0,030 sang +0,126
    rad/km. Với mô hình mặt phẳng cục bộ, hằng số theo dải con gần như trùng với gradient theo phương nhìn ngang.
  - v6 trừ thẳng bậc đã đo trên toàn băng khỏi băng thấp của từng dải con trước khi giải chập pha. Băng tương quan chéo
    không cần sửa vì bậc giống nhau ở hai băng con. Gradient theo phương nhìn ngang của 2025-10-04 thành +0,001 ± 0,014 rad/km (v4:
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
    là đối lưu chiều tối (`docs/vi/guide/ionosphere.md` §6). Đây là việc của bài 1 (hai quỹ đạo) hơn là bài này
    (sửa 2026-11-05: trước ghi nhầm "bài 2", là bài học máy).

**Điểm mới dự kiến (cần rà tài liệu).**
- Ghi nhận và định lượng bậc pha giữa các dải con trong chuỗi Sentinel-1 gần đây (có S1D), kèm dấu hiệu chẩn đoán
  bằng hiệu ESD giữa các dải con.
- Một bước sửa đơn giản, tự động, theo từng ngày trong khâu ghép, với tiêu chí chất lượng (độ đồng thuận, số khối).
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

## 4. Bài 4: Ngập úng và sụt lún ở Hà Nội, có độ bất định

Ghi ngày 2026-10-28. Gợi ý từ preprint Chen, Yang, Weng, Wang (2026), *Integrating predictive uncertainty into
satellite-based flood mapping*, EGUsphere, doi:10.5194/egusphere-2026-4233, đang phản biện cho NHESS. Bài đó gắn
Evidential Deep Learning vào UNet++ trên WorldFloods (ảnh quang học, phải xử lý mây) để có bản đồ ngập kèm độ bất
định từng pixel, so với Deep Ensemble và MC Dropout. Mới đọc trang tóm tắt; toàn văn (23 MB) chưa đọc.

**Câu hỏi.** Ở Hà Nội, nơi đang lún nhanh có ngập thường xuyên hơn, sâu hơn hoặc lâu rút hơn không? Bản đồ nguy cơ
ngập có nên dùng tốc độ lún làm một biến, và độ tin cậy của bản đồ đó đến đâu?

**Vì sao hợp với GeoEyes.**
- Radar nhìn xuyên mây, đúng lúc mưa bão, khắc phục điểm yếu của bài trên; chuỗi SLC Sentinel-1 đã có sẵn.
- Trong đô thị, nước khó thấy qua biên độ (phản xạ kép từ nhà cửa); độ nhất quán InSAR sụt bất thường so với các cặp
  trước là dấu hiệu đã được dùng (Chini và cs. 2019, Houston; Pulvirenti và cs. 2021 dùng điểm PS; một nghiên cứu
  Jakarta 2018/2020 cũng dựa vào cách này). Chưa tìm thấy công trình nào ghép bản đồ ngập SAR với sụt lún InSAR
  cho Hà Nội (tìm nhanh, chưa rà kỹ).
- GeoEyes đã có: tốc độ lún theo ô 100 m (hai quỹ đạo), phân vùng nguy cơ có lượng mưa CHIRPS, mô hình mức độ
  nhạy cảm, khoảng conformal cho dự báo.

**Vướng mắc chính: thời điểm chụp.** Ngập nội thành do mưa ở Hà Nội thường rút trong vài giờ, còn Sentinel-1 qua
Hà Nội 12 ngày một lần mỗi quỹ đạo (vào lúc 05:51 và 18:06 giờ Việt Nam). Tìm trên ASF (vùng nội thành và ven
sông Hồng):

| Sự kiện | Ngập | Ảnh gần nhất | Nhận xét |
|---|---|---|---|
| Bão Yagi (2024) | lũ sông Hồng, nhiều ngày | desc 091, 05:51 ngày 13/9/2024 | đáng thử: bãi sông và vùng ven có thể còn ngập |
| Bão Wipha (2025) | mưa ngập 21–22/7/2025; Sentinel Asia có bản đồ ngày 21/7 | desc 091, 05:51 ngày 22/7/2025 (S1A); asc 128, 18:06 ngày 24/7 | đáng thử |
| Bão Bualoi (2025) | nội thành 30/9/2025, khoảng 65 điểm ngập, có nơi 50 cm | desc 091, 05:51 ngày 2/10/2025 | ~1,5 ngày sau: nội thành nhiều khả năng đã rút |
| Bão Matmo (2025) | nội thành 7/10/2025 | asc 128, 18:06 ngày 4/10 (trước); không có ảnh ngay sau | không bắt được |

Lưu ý: ASF ghi giờ UTC; 22:51 UTC ngày 1/10 là 05:51 sáng 2/10 giờ Việt Nam.

**Vì vậy, hai cách làm, nên làm cả hai.**
1. **Ngập quan sát được từ radar** (các trận kéo dài như Yagi, Wipha): biên độ cho vùng trống, độ nhất quán cho đô
   thị, so với các cặp trước trận; đối chiếu bản đồ Sentinel Asia / Copernicus EMS / UNOSAT nếu có. Có độ bất định
   (xác suất kiểu Bayes như Chini và cs., hoặc evidential như bài gợi ý).
2. **Điểm ngập không cần ảnh đúng lúc:** danh sách điểm úng ngập do thành phố công bố hằng năm và các điểm báo chí ghi
   nhận (Bualoi, Matmo, các trận mưa lớn), đem đối chiếu với tốc độ lún, cao độ, khoảng cách tới cống và kênh. Mô
   hình mức độ nhạy cảm ngập có tốc độ lún là một biến, kèm độ bất định (ensemble, conformal, evidential): đây là
   chỗ bài gợi ý được dùng trực tiếp.

**Kết quả kiểm tra Yagi (2026-10-28).** Dự án `hanoi_flood_yagi`: Sentinel-1 desc 091, 2 burst, 7 ngày chụp
26/7–6/10/2024 (12 ngày một ảnh), ảnh chủ 31/8, B⊥ từ −110 đến +204 m; chỉ chạy acquire và build_stack (AOI như
`hanoi_s1`). Pha chụp 12/9/2024 22:51 UTC (05:51 sáng 13/9 giờ Việt Nam) rơi vào lúc lũ sông Hồng.
- **Biên độ thấy rõ ngập.** Tỷ số biên độ 12/9 so với trung bình nhân của 19/8 và 31/8: một dải tối −4 đến −6 dB
  chạy dọc sông Hồng (bãi bồi, bãi giữa, phía đông bắc AOI), đúng dấu hiệu mặt nước phẳng phản xạ gương; nội đô gần
  như không đổi. Trên cả AOI chỉ 3,8 % pixel tối đi hơn 3 dB (các cặp không có lũ: 1–2 %), nên con số toàn vùng che
  mất tín hiệu, phải nhìn bản đồ.
- **Độ nhất quán ít giúp ở đây.** Lòng sông và bãi bồi đã mất tương quan từ trước sự kiện (nước, đất canh tác); cặp
  31/8–12/9 so với cặp 19/8–31/8: chỉ 2,4 % diện tích giảm hơn 0,3. Với lũ ven sông, biên độ là chỉ báo tốt hơn;
  độ nhất quán vẫn là hướng cho ngập trong đô thị (phản xạ kép).
- Độ nhất quán trung vị các cặp liên tiếp 0,44–0,59 (cửa sổ 5 × 20 pixel), không có cặp nào sụt bất thường.
- Hình và kịch bản tái lập: `<workspace>/projects/hanoi_flood_yagi/analysis/flood_check/` (`yagi_change.png`,
  `flood_check.py`).

**Bước tiếp cho Yagi.** (a) Bản đồ ngập: ngưỡng tỷ số biên độ (thử Otsu hoặc mô hình hỗn hợp hai lớp, kèm xác suất
kiểu Chini và cs.), bỏ nước thường xuyên bằng ảnh trước sự kiện (biên độ thấp ở cả 26/7, 7/8, 19/8, 31/8); (b) đối
chiếu bản đồ độc lập: Copernicus EMS / UNOSAT nếu có kích hoạt cho Hà Nội, hoặc Sentinel-2 không mây gần 13/9;
(c) xem ảnh 24/9 để thấy nước rút; (d) so vùng ngập với tốc độ lún của `hanoi_s1` (câu hỏi chính của bài).

**Điểm mới dự kiến (phải rà tài liệu).**
- Ghép sụt lún InSAR hai quỹ đạo với ngập quan sát và điểm ngập lịch sử ở Hà Nội.
- Định lượng phần đóng góp của sụt lún vào nguy cơ ngập, có độ bất định.
- Cảnh báo "đất đang lún ở nơi đã từng ngập" cho quy hoạch thoát nước.

**Còn thiếu.**
1. Kiểm tra ảnh 13/9/2024 và 22/7/2025: tải, tính biên độ và độ nhất quán so với các cặp trước; xem có thấy nước không.
   **Yagi 13/9/2024: đã làm (2026-10-28), thấy rõ ngập trên biên độ dọc sông Hồng** (xem "Kết quả kiểm tra Yagi").
   Wipha 22/7/2025: chưa làm.
2. Danh sách điểm úng ngập Hà Nội (Sở Xây dựng hoặc Công ty Thoát nước Hà Nội), có toạ độ.
3. Bản đồ ngập tham chiếu: Sentinel Asia (21/7/2025), Copernicus EMS / UNOSAT cho Yagi nếu có hoạt động trên Hà Nội.
4. Rà tài liệu: ngập đô thị bằng độ nhất quán SAR; liên hệ sụt lún – ngập (Jakarta, Bangkok, TP.HCM); các nghiên cứu ngập
   Hà Nội.
5. Đọc toàn văn bài gợi ý: cách họ đo chất lượng độ bất định (calibration, độ ổn định giữa các trận).

**Đánh giá 2026-11-05.** Yagi chưa trả lời được câu hỏi của bài.
- Ngập Yagi là lũ sông Hồng ở bãi sông, ngoài đê, không phải úng ngập do mưa trong đô thị. Nó không kiểm được "nơi
  đô thị đang lún có ngập do mưa nhiều hơn không".
- Các trận úng ngập nội thành rút trong vài giờ, nên Sentinel-1 12 ngày một lần thường bỏ lỡ (Bualoi, Matmo ở bảng
  trên).
- Một năm sụt lún (`hanoi_s1`) chưa đủ để gắn với thay đổi tần suất ngập.
- Hướng 2 (điểm ngập lịch sử của thành phố đối chiếu với tốc độ lún) là phần khả thi; hướng 1 chỉ là minh hoạ.

**Nơi đăng gợi ý.** *Natural Hazards and Earth System Sciences*, *International Journal of Disaster Risk
Reduction*, *Remote Sensing*.

## 5. Các hướng chưa nên viết riêng

| Hướng | Lý do | Dùng ở đâu |
|---|---|---|
| Lún cố kết (hướng 4) | chỉ 4–30 ô đạt điều kiện, chuỗi 0,5–1 năm; phép kiểm tra c_v cho thấy nhiều khả năng không phải cố kết cả lớp đất | chờ chuỗi ≥ 3 năm |
| Hạ tầng tuyến (hướng 3) | Mexico City đã được nghiên cứu nhiều (Metro tuyến A, Zaragoza), chuỗi 6 tháng; ở Hà Nội chỉ 21 % chiều dài đê có điểm InSAR | một mục trong bài 1 |
| Rủi ro công trình (hướng 2) | phương pháp đã có (Peduto và cs. 2017); chưa có khảo sát hư hại | một mục trong bài 1 |
| Kiểu chuyển dịch (hướng 1) | cách phân loại tương tự các nghiên cứu trước; điểm riêng là phát hiện ngày thay đổi chung do dữ liệu | phần phương pháp của bài 1 |
| Dự báo bằng học máy | kết quả âm: chưa thắng mô hình giữ nguyên trên chuỗi ngắn | ghi chú ngắn, sức hút thấp |

## 6. Việc cần làm

1. Rà tài liệu InSAR Hà Nội, tài liệu về học máy dự báo vùng dễ lún, tài liệu về bậc pha giữa các dải con
   Sentinel-1, và tài liệu về ngập đô thị bằng SAR và liên hệ sụt lún – ngập, để xác định chính xác điểm mới của
   bốn bài.
2. Hoàn tất tách thành phần Hà Nội (D1 trong two-geometries-and-soft-soil.md).
3. Thu thập số liệu kiểm chứng: GNSS, thuỷ chuẩn, ngày thi công, khảo sát hư hại.
4. Liên hệ để có bản đồ bề dày đất yếu hoặc lỗ khoan Hà Nội (G1).
5. Dựng đề cương bài 1, kèm danh sách hình và bảng lấy từ các kết quả đã có.
