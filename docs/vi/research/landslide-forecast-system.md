# Hệ thống dự báo sạt lở đất miền Trung Việt Nam — thiết kế và kế hoạch

> Tài liệu thiết kế. Trạng thái: **đang làm F0–F2** (kế hoạch 2026-11-03; F0–F2 bắt đầu 2026-11-03, §9.1; rà soát
> 2026-11-05). Tài liệu này biến phần nghiên cứu của
> [`landslide-susceptibility.md`](landslide-susceptibility.md) (các bước L0–L9) thành một bản dự báo mà người dùng
> sử dụng được.
> Yêu cầu của chủ dự án (2026-11-03): *phải thật sự thành công và thành một hệ thống dự báo sử dụng được, có độ tin
> cậy, có đầy đủ độ bất định, đảm bảo góc nhìn chuyên gia, thật chuyên nghiệp. Các vấn đề khác để sau.*
> Mỗi bước (§9) kết thúc bằng một lần duyệt của chủ dự án trước khi sang bước sau.

> **Rà soát 2026-11-05: định hướng.**
> - *Sự kiện hiếm*: A1–A5 được kiểm định ở cấp huyện / vùng cảnh báo hoặc theo cửa sổ nhiều ngày; xã chỉ để hiển thị.
> - *Mệt mỏi vì cảnh báo*: ngân sách cảnh báo sai được thống nhất cho cả vùng dưới dạng tỷ lệ cảnh báo sai (FAR), không
>   chỉ theo từng xã.
> - *Sai lệch báo cáo*: giữ riêng một mùa trọn vẹn và một tỉnh (tốt nhất có vết sạt Sentinel-2 đã định ngày) làm phép
>   thử cuối cùng trước F9.
> - *InSAR*: thiết kế vận hành ở §8.3 tạm đóng băng cho tới khi L5 cho thấy có ích (độ phủ < 15 %; độ kết hợp băng C
>   ~0,1 sau 36 ngày dưới rừng).
> - *Trạm đo KTTV* là đường găng: đẩy việc xin số liệu ngay; dự phòng là trạm của tỉnh / radar của Trung tâm Dự báo
>   KTTV quốc gia.
> - *Độ trễ*: đo thời gian thực, hằng giờ, trong mùa 2026 (IMERG nửa giờ, GSMaP hằng giờ).

## Mục lục

1. [Thế nào là "sử dụng được"](#1-thế-nào-là-sử-dụng-được)
2. [Hiện trạng](#2-hiện-trạng)
3. [Khung chuyên môn](#3-khung-chuyên-môn)
4. [Thiết kế hệ thống](#4-thiết-kế-hệ-thống)
5. [Độ bất định](#5-độ-bất-định)
6. [Kiểm định](#6-kiểm-định)
7. [Thẩm định chuyên gia, vận hành và quản trị](#7-thẩm-định-chuyên-gia-vận-hành-và-quản-trị)
8. [Chiến lược vận hành: nhịp cập nhật, độ sẵn sàng, tính kịp thời, chỉ số](#8-chiến-lược-vận-hành-nhịp-cập-nhật-độ-sẵn-sàng-tính-kịp-thời-chỉ-số)
   (8.7: kịch bản, rủi ro và cách xử lý)
9. [Kế hoạch F0–F9](#9-kế-hoạch-f0f9)
10. [Dữ liệu và quyết định cần từ chủ dự án](#10-dữ-liệu-và-quyết-định-cần-từ-chủ-dự-án)
11. [Rủi ro](#11-rủi-ro)
12. [Tài liệu tham khảo](#12-tài-liệu-tham-khảo)

---

## 1. Thế nào là "sử dụng được"

**Người dùng và quyết định.**
- Ban chỉ huy PCTT & TKCN cấp tỉnh và cấp xã quyết định có cảnh báo, cấm đường hay sơ tán hay không.
- Cơ quan khí tượng thuỷ văn ban hành bản tin cảnh báo chính thức và cấp độ rủi ro (Quyết định 18/2021/QĐ-TTg).
- Hệ thống hỗ trợ những người này. Nó không thay thế bản tin chính thức.

**Bản dự báo.** Với mỗi *đơn vị cảnh báo* (một xã; bên trong là các đơn vị sườn dốc để xem chi tiết) và mỗi hạn dự
báo (hôm nay, +24 h, +48 h, +72 h):
- xác suất có ít nhất một vụ sạt lở trong đơn vị, kèm khoảng tin cậy;
- cấp cảnh báo, tương ứng một-một với cấp độ rủi ro của Điều 46, Quyết định 18/2021;
- các yếu tố dẫn đến cảnh báo: mưa bao nhiêu, sườn dốc nào, so với những ngày sạt lở trước đây ra sao;
- mức tin cậy (cao / trung bình / thấp) và lý do.

Bản đồ tính nhạy 30 m là lớp hỗ trợ. Nó cho biết nên chú ý chỗ nào trong đơn vị, chứ không phải là bản dự báo.

**Tiêu chí nghiệm thu.** Tất cả được chốt trước khi chạy dự báo ngược (§6) và không thay đổi sau đó.
*Đã sửa sau lần rà soát ngày 2026-11-05, trước khi chạy bất kỳ dự báo ngược nào* (A1–A6: sự kiện hiếm, kết quả nhị
phân, xác suất mốc so sánh, kho dự báo); bản đầu ngày 2026-11-03 có A1 và A2 chỉ theo xã, A5 là độ phủ khoảng của kết quả nhị phân, và A6 trên kho ENS mở 2024–2025.

| # | Tiêu chí | Mục tiêu |
|---|---|---|
| A1 | Phát hiện sự kiện: tỷ lệ ngày có sạt lở (dự báo ngược 2015–2025) mà đơn vị kiểm định của nó (huyện / vùng cảnh báo, hoặc cửa sổ nhiều ngày) ở cấp cảnh báo trở lên | ≥ 0,75, kèm khoảng 95 % và số sự kiện |
| A2 | Cảnh báo sai: (a) tỷ lệ cảnh báo sai trên cả vùng ở cấp cảnh báo (số cảnh báo sai / tổng số cảnh báo); (b) số ngày cảnh báo mỗi xã mỗi mùa mưa | (a) ≤ ngân sách FAR thống nhất ở F0; (b) ≤ 5; cả hai báo cáo kèm sai lệch báo cáo (§11) |
| A3 | Hơn quy tắc chính thức (Điều 46 với vùng thay thế, mỗi cấp gán với tần suất quan sát của nó trong dự báo ngược, tính kiểm định chéo) và hơn chỉ dùng mưa | Brier skill score > 0, khoảng 95 % trên 0; báo cáo thêm PR-AUC, CSI / ETS và SEDI so với cùng các mốc |
| A4 | Độ tin cậy xác suất: xác suất dự báo so với tần suất quan sát | nằm trong dải nhất quán 90 %, trên các nhóm có ít nhất 10 sự kiện (nhóm thưa được gộp lại); nêu số sự kiện mỗi nhóm |
| A5 | Độ bất định trung thực: số ngày sạt lở dự báo so với quan sát theo đơn vị-mùa (hoặc theo nhóm xác suất), và PIT ngẫu nhiên hoá của kết quả nhị phân | khoảng 80 % của số đếm chứa 75–85 %; PIT ngẫu nhiên hoá không khác phân bố đều |
| A6 | Hạn dự báo: A1 và A3 vẫn đạt ở +24 h với mưa dự báo (ECMWF ENS, kho TIGGE 2015–2025) | có |
| A7 | Vận hành: chạy một bản dự báo sau khi có số liệu mưa | ≤ 5 phút mỗi tỉnh; cùng đầu vào cho cùng kết quả |
| A8 | Thẩm định chuyên gia: hội đồng thẩm định độc lập (§7) chấp nhận phương pháp và bản đồ | có văn bản chấp nhận |

Nếu không đạt được một tiêu chí, báo cáo phải nói rõ. Khi đó sản phẩm được phát hành với phạm vi hẹp hơn (ví dụ chỉ
vùng thí điểm, hoặc chỉ 0–24 h). Không được tinh chỉnh cho tới khi "đạt".

**Sự kiện hiếm và độ mạnh của phép thử (2026-11-05).** Danh mục F1 có 97 ngày-xã dương trên 61 ngày khác nhau trong
11 mùa (§9.1), so với hàng triệu ngày-xã: tần suất nền cỡ 10⁻⁴ hoặc thấp hơn. Do đó:
- nếu chỉ có A2 (b), A1 có thể đạt trong khi FAR trên 0,99 (≤ 5 cảnh báo sai × hàng trăm xã, so với ~9 sự kiện mỗi
  mùa); A2 (a) chặn trường hợp này;
- ROC AUC bị thổi phồng bởi các ca âm đúng; vì vậy báo cáo thêm PR-AUC, CSI / ETS và SEDI (Ferro & Stephenson 2011),
  là các chỉ số không "thưởng" cho ca âm đúng;
- các nhóm xác suất trên ~0,01 gần như trống, nên A4 không thể trượt; các nhóm được gộp tới khi mỗi nhóm có ≥ 10 sự
  kiện;
- mỗi tiêu chí ghi số sự kiện làm căn cứ và độ mạnh của phép thử (với 61 ngày độc lập, khoảng 95 % của POD 0,75 là
  khoảng ± 0,11).

## 2. Hiện trạng

| Phần | Kết quả đến nay | Ý nghĩa với hệ thống |
|---|---|---|
| Danh mục sạt lở | polygon Das 2024 cho Ketsana (2009) và Molave (2020); cờ độ tin cậy; vết sạt lở Sentinel-2 | tốt cho *ở đâu*; ít cho *khi nào* |
| Tính nhạy (L3, L3b, L3c) | RF gộp AUC 0,73 trên block 5 km; chuyển giao 0,66–0,72; tinh chỉnh tham số (C1), thêm 18 lớp địa hình (C3) và đổi nhãn hay ô âm (C5) đều chỉ thêm < 0,01 | dùng được như lớp tương đối; cần hiệu chỉnh và có độ bất định; còn thiếu địa chất và đứt gãy |
| Mưa làm biến không gian (L4) | không có ích hơn yếu tố vị trí (p = 0,23) | mưa thuộc phần *thời gian*, không thuộc bản đồ |
| Ngưỡng mưa (L6) | code xong, tạm dừng (tải CHIRPS) | là trung tâm của hệ thống; phải tính trên sản phẩm mưa vận hành |
| InSAR (L3b.7, L5) | sau sự kiện: không có tín hiệu trên vết sạt; trước sự kiện L5 đang chạy | yếu tố điều chỉnh tuỳ chọn, không phải đầu vào cốt lõi |

Điểm yếu không nằm ở bản đồ mà ở chiều thời gian:
- có ít vụ sạt lở có ngày rõ ràng;
- chưa chọn và chưa kiểm tra sản phẩm mưa;
- chưa kiểm định bất kỳ bản dự báo nào.

Vì vậy kế hoạch ưu tiên mô hình kích hoạt và phần kiểm định.

## 3. Khung chuyên môn

**Thuật ngữ** (Fell và cs. 2008):
- *tính nhạy* (susceptibility) = ở đâu;
- *nguy cơ* (hazard) = ở đâu và khi nào, có xác suất;
- *rủi ro* (risk) = nguy cơ, thêm mức phơi nhiễm và tính dễ bị tổn thương.

Hệ thống dự báo **nguy cơ**: xác suất xảy ra sạt lở trong một đơn vị và một khoảng thời gian. Nó không dự báo quãng
trượt, kích thước, thiệt hại, hay việc một sườn cụ thể có trượt hay không.

**Khung pháp lý.** Theo Điều 46, Quyết định 18/2021/QĐ-TTg, cấp độ rủi ro lũ quét và sạt lở (cấp 1–3) được xác định
từ:
- lượng mưa dự báo trong 24 giờ (100–200, 200–400, > 400 mm);
- lượng mưa các ngày trước đó (1–2 ngày, hơn 2 ngày);
- mức nguy cơ của vùng (thấp, trung bình, cao, rất cao), lấy từ bản đồ phân vùng 1:50.000;
- khu vực (1–4). Quảng Nam, Kon Tum và Thừa Thiên Huế thuộc khu vực 3 (Phụ lục XII).

Hệ thống làm việc bên trong khung này:
- các lớp tính nhạy được hiệu chỉnh để có thể thay cho vùng nguy cơ ở nơi chưa có bản đồ 1:50.000, và được so sánh
  với bản đồ đó ở nơi đã có;
- đầu vào mưa là cùng các đại lượng (mưa dự báo 24 h, mưa trước đó);
- xác suất của hệ thống cho biết *khả năng* sạt lở cao đến đâu trong cùng một cấp. Đây chính là điều Điều 46 còn
  thiếu: cấp độ mà không có xác suất, cũng không có độ bất định.

Bản thân quy tắc Điều 46, áp dụng với vùng của ta, là **mốc so sánh** mà mọi mô hình phải vượt (A3).

**Thực tiễn cảnh báo sớm theo vùng** (Piciullo và cs. 2018; Guzzetti và cs. 2020). Các hệ thống hoạt động tốt đều:
- làm việc trên đơn vị cảnh báo, không phải trên điểm ảnh;
- kết hợp mô hình kích hoạt bằng mưa với bản đồ tính nhạy tĩnh;
- kiểm định mỗi mùa với danh mục sạt lở;
- giữ người dự báo trong vòng quyết định.

Dịch vụ của Na Uy (Krøgli và cs. 2018) là hình mẫu vận hành trưởng thành: ngưỡng khí tượng thuỷ văn, đánh giá
chuyên gia hằng ngày và công bố kết quả kiểm định. NASA LHASA 2 (Stanley và cs. 2021; bản đầu, Kirschbaum & Stanley 2018, kết hợp bản đồ tính nhạy với phân vị mưa trong
một ma trận quyết định) là hướng học máy trên dữ liệu
toàn cầu, với đầu ra xác suất.

**Những gì hệ thống không tuyên bố.** Nó không dự đoán sườn nào sẽ trượt. Xác suất theo ngày-xã là độ phân giải
trung thực của dữ liệu: vị trí các báo cáo có ngày chỉ chính xác tới vài km, sản phẩm mưa quan trắc có ô 5–11 km, và
mưa dự báo ECMWF ENS có ô 0,25° (~28 km).

## 4. Thiết kế hệ thống

Hệ thống gồm bốn thành phần, nối với nhau theo thứ tự:

| Thành phần | Loại | Đầu vào | Đầu ra |
|---|---|---|---|
| **S** Tính nhạy | tĩnh, cập nhật hằng năm | địa hình, rừng, địa chất, danh mục sạt lở | tổ hợp bản đồ 30 m → mật độ tính nhạy theo đơn vị, kèm khoảng |
| **R** Mưa | động, hằng ngày (hằng giờ khi có bão) | quan trắc (GSMaP / IMERG), dự báo (ECMWF ENS, 51 thành viên) | các trường mưa đã hiệu chỉnh sai số, dạng tổ hợp |
| **T** Mô hình kích hoạt | động | S và R | P(sạt lở trong đơn vị, trong ngày \| mưa, tính nhạy) |
| **H** Đầu ra | động | T | theo đơn vị và hạn dự báo: xác suất + khoảng, cấp Điều 46, yếu tố, mức tin cậy |

Sau H: người dự báo duyệt → bản tin, bản đồ, nhật ký (dùng cho kiểm định).

**S — Tính nhạy (tĩnh).**
- Mô hình vô địch của L3c, bổ sung địa chất và đứt gãy (C4) và nhãn của C5, huấn luyện lại trên mọi sự kiện.
- Một tổ hợp (§5): các lượt bốc ô âm × bootstrap polygon theo block × hai họ mô hình (random forest, logistic). Mỗi
  thành viên đều được hiệu chỉnh xác suất.
- Tổng hợp theo đơn vị cảnh báo thành *mật độ tính nhạy*: tỷ lệ ô sườn dốc dự kiến sẽ trượt trong một trận mưa như
  các sự kiện hiệu chỉnh, kèm khoảng tin cậy.
- Phân lớp thấp / trung bình / cao / rất cao theo các phân vị cố định của các sự kiện hiệu chỉnh, để thay cho vùng
  nguy cơ của Điều 46.

**R — Mưa.**
- Quan trắc: một sản phẩm vận hành (GSMaP NRT hoặc IMERG Early, chọn ở F2 sau khi so với trạm đo); CHIRPS dùng cho
  khí hậu.
- Dự báo: dữ liệu mở ECMWF, tổ hợp 51 thành viên ở 0,25° (mở từ tháng 2/2024), hạn 15 ngày. Hiệu chỉnh phân vị
  (quantile mapping) về sản phẩm quan trắc theo từng ô và từng hạn.
- Các đại lượng:
  - tổng mưa 24 h và 72 h;
  - mưa trước đó A3 / A7 / A30, tính theo phân vị khí hậu;
  - tổng lượng E và thời gian D của đợt mưa (L6).
- Mưa quan trắc cũng có sai số, nên cũng được mang theo dưới dạng tổ hợp: sai số của sản phẩm so với trạm đo (F2)
  sinh ra các trường mưa nhiễu. *Không tính hai lần (2026-11-05):* nếu T được huấn luyện trên chính mưa vệ tinh có
  nhiễu, sai số đó đã nằm trong các hệ số của T (độ dốc bị kéo nhỏ lại). Chỉ làm nhiễu trường mưa khi T được huấn
  luyện trên một trường mưa tham chiếu (trạm đo hoặc sản phẩm đã ghép trạm); nếu không, sai số đi vào T dưới dạng
  mô hình sai số trong biến (errors-in-variables).

**T — Mô hình kích hoạt.** Xác suất có ít nhất một vụ sạt lở trong một đơn vị trong một ngày, khi biết mưa và tính
nhạy của đơn vị. Có ba ứng viên, độ phức tạp tăng dần, cùng được huấn luyện trên các ngày-đơn vị và kiểm định theo
cùng một cách:
1. **Quy tắc Điều 46** với vùng của ta (mốc so sánh, không cần huấn luyện).
2. **Mô hình ngưỡng Bayes:**
   - hồi quy logistic theo log E, log D, phân vị A7 và mật độ tính nhạy của đơn vị;
   - có các số hạng theo miền (Bắc / Trung) và tiên nghiệm yếu (các đường E–D trong tài liệu);
   - hậu nghiệm của mô hình cho trực tiếp độ bất định của ngưỡng.
3. **Gradient boosting trên ngày-đơn vị** (kiểu LHASA 2), có ràng buộc đơn điệu: mưa nhiều hơn hay tính nhạy cao
   hơn thì nguy cơ không bao giờ giảm.

Giữ lại ứng viên đơn giản nhất đạt A1–A6. Chuyên gia đọc được và đối chiếu được mô hình ngưỡng với tài liệu. Mô hình
boosting chỉ được chọn nếu kiểm định cho thấy lợi ích rõ ràng.

**Quan hệ với L6, L7 và L9 của nghiên cứu tính nhạy (2026-11-05).** F5 và F8 thay thế L7 và L9 của
[`landslide-susceptibility.md`](landslide-susceptibility.md).
- L7 không nhân xác suất tính nhạy với xác suất mưa, vì hai mô hình được hiệu chỉnh trên hai tập khác nhau. T tránh
  được vấn đề này vì cả hai số hạng được huấn luyện cùng lúc, trong một mô hình, trên cùng các ngày-đơn vị (ứng viên
  2 và 3).
- Các lựa chọn của L9 (IFS tất định tới 10 ngày; InSAR 12 ngày một lần nâng lớp) được thay bằng các thành viên ENS
  của R và quy tắc InSAR ở §8.3.
- Ngưỡng L6 (E–D ở xác suất không vượt 5 %, A7 tại TSS lớn nhất) đi vào F5 như một mốc so sánh và một biến; hai cách
  hiệu chỉnh được đối chiếu và thống nhất ở F5.

**Nhãn cho T.** Một ngày-đơn vị là dương khi có sạt lở đã biết trong đơn vị vào ngày đó (± độ chính xác của ngày).
Nguồn:
- các báo cáo có ngày (`vietnam.csv`, báo chí, hồ sơ của VIGMR nếu có);
- các sự kiện Das 2024 với các trận mưa có ngày;
- vết sạt lở Sentinel-2 được `scars.py` định ngày (theo mùa, rồi theo trận mưa bằng Sentinel-1).

Mỗi nguồn giữ cờ độ chính xác riêng. Sai lệch báo cáo được mô hình hoá, không bị bỏ qua (§11).

**H — Đầu ra.**
- **Xác suất** theo đơn vị và hạn dự báo: trung bình trên các lần rút Monte Carlo (một xác suất nhất quán), và khoảng
  10–90 % thể hiện độ phân tán (2026-11-05: dùng trung bình, không dùng trung vị).
- **Cấp:** gồm hai cấp, cùng tính từ một đầu vào:
  - cấp Điều 46;
  - cấp của hệ thống, suy từ xác suất. Ngưỡng xác suất của các cấp do kiểm định đặt, theo ngân sách số lần phát hiện
    và cảnh báo sai chọn cùng người dùng ở F0. Ngưỡng được chọn bên trong từng lượt bỏ-một-mùa, để mùa đang chấm
    không tự đặt ngưỡng cho chính nó (2026-11-05).

  Khi hai cấp khác nhau, bản tin ghi cả hai và giải thích vì sao.
- **Yếu tố:** mưa 24 / 72 h vừa qua và mưa dự báo, chu kỳ lặp lại của lượng mưa đó, lớp tính nhạy, và những ngày sạt
  lở trong quá khứ giống hôm nay nhất (ngày tương tự).
- **Mức tin cậy:** cao / trung bình / thấp, dựa trên độ rộng của khoảng và tình trạng dữ liệu (thiếu mưa, độ phân tán
  của tổ hợp, đơn vị nằm ngoài vùng hiệu chỉnh).

## 5. Độ bất định

Mọi nguồn đều được gọi tên, định lượng và đưa vào bản dự báo. Không nguồn nào bị bỏ vì khó.

| Nguồn | Loại | Định lượng thế nào | Đi vào dự báo thế nào |
|---|---|---|---|
| Danh mục: sườn nào đã trượt, phạm vi đã lập bản đồ | nhận thức | biến thể vùng phủ (chính / thu nhỏ), polygon đáng tin hay tất cả, ô âm tránh vết chưa lập bản đồ | thành viên của tổ hợp S |
| Danh mục: ngày của báo cáo | ngẫu nhiên | độ chính xác ngày của từng bản ghi; cửa sổ ± 1 ngày | nhãn T dạng khoảng; chạy độ nhạy |
| Sai lệch báo cáo (gần đường, làng, có thương vong) | nhận thức | biến phơi nhiễm (đường, dân số) trong T; đối chiếu tần suất với các mùa Sentinel-2 | A2 nêu như cận trên; báo cáo số hạng sai lệch |
| Biến dự báo (DEM, rừng, địa chất) | nhận thức | GLO-30 so với AW3D30; bản đồ địa chất so với GLiM | thành viên của tổ hợp S (biến thể DEM) |
| Mô hình tính nhạy: lấy mẫu, tham số | ngẫu nhiên + nhận thức | các lượt bốc ô âm, bootstrap polygon theo block, hai họ mô hình | tổ hợp S (≥ 50 thành viên) |
| Chuyển giao không gian và thời gian | nhận thức | chuyển giao Ketsana ↔ Molave; bỏ-một-mùa trong T | khoảng rộng hơn ngoài vùng hiệu chỉnh; tin cậy "thấp" |
| Mưa quan trắc | ngẫu nhiên | sản phẩm so với trạm đo (F2): mô hình sai số theo cấp cường độ | các thành viên mưa nhiễu, chỉ khi T được huấn luyện trên trường mưa tham chiếu; nếu không, sai số trong biến ở T (không tính hai lần, §4) |
| Mưa dự báo | ngẫu nhiên | ECMWF ENS, 51 thành viên, sau hiệu chỉnh phân vị | các thành viên mưa theo hạn |
| Ngưỡng / hệ số kích hoạt | nhận thức | hậu nghiệm Bayes (ứng viên 2) hoặc bootstrap (ứng viên 3) | các mẫu hậu nghiệm của T |

**Lan truyền.** Dùng Monte Carlo, cho mỗi đơn vị và mỗi hạn:
1. rút một thành viên tính nhạy, một thành viên mưa và một bộ hệ số kích hoạt;
2. tính xác suất;
3. lặp lại khoảng 1.000 lần.

Kết quả là một phân bố của xác suất; bản tin ghi trung bình (xác suất nhất quán) và khoảng 10–90 % thể hiện độ phân
tán. Chi phí nhỏ: vài trăm đơn vị × 1.000 lần rút mỗi lần chạy.

**Hiệu chỉnh chính độ bất định.** Một khoảng chỉ có ích nếu nó đúng với tần suất nó tuyên bố. Một kết quả riêng lẻ chỉ
là 0 hoặc 1, nên "độ phủ" của một khoảng xác suất bởi kết quả đó, hay PIT thông thường, đều vô nghĩa (2026-11-05).
Thay vào đó, trên dự báo ngược:
- A5 kiểm tra (a) số đếm: số ngày sạt lở dự báo so với quan sát theo đơn vị-mùa, hoặc theo nhóm xác suất, với khoảng
  80 % của số đếm dự báo; (b) PIT ngẫu nhiên hoá của các kết quả nhị phân;
- A4 kiểm tra độ tin cậy của xác suất trung bình.

Nếu khoảng quá hẹp, một hệ số thổi phồng phương sai được ước lượng trên dự báo ngược và ghi trong thẻ mô hình.

**Truyền đạt.**
- Không bao giờ chỉ đưa một con số trơn, ví dụ: "xác suất 0,18 (0,09–0,31), cấp 2, tin cậy trung bình: dự báo mưa
  lớn, các thành viên phân tán rộng".
- Dùng chữ và số cùng nhau, theo một bộ từ cố định, để cùng một số luôn đi với cùng một chữ. Bộ từ gắn với các cấp
  cảnh báo và ngưỡng xác suất của chúng (mỗi cấp một cụm từ, chốt ở F0 cùng người dùng), không dùng thang khả năng của
  IPCC: trên thang đó 0,1–0,3 là "khó xảy ra", sai với một cảnh báo có tần suất nền cỡ 10⁻⁴ (2026-11-05).

## 6. Kiểm định

**Thiết kế dự báo ngược.**
- Các mùa 2015–2025 (thời kỳ của danh mục báo cáo sạt lở, F1; còn sản phẩm mưa IMERG V07 và GSMaP có từ năm 2000),
  mùa mưa miền Trung (tháng 9–12). Miền Bắc chỉ dùng để kiểm tra chuyển giao.
- Hoàn toàn ngoài mẫu:
  - bỏ-một-mùa cho T, với ngưỡng xác suất của các cấp được chọn bên trong từng lượt (2026-11-05);
  - S được huấn luyện lại không có các sự kiện của mùa đang chấm, nếu các sự kiện đó nằm trong dữ liệu huấn luyện.
- Phép thử cuối (2026-11-05): giữ riêng một mùa trọn vẹn và một tỉnh (tốt nhất có vết sạt Sentinel-2 đã định ngày),
  không dùng cho bất kỳ lần huấn luyện hay chọn ngưỡng nào, chỉ chấm một lần trước F9.
- Hai chế độ:
  - dùng mưa *quan trắc* (trường hợp tốt nhất: "nowcast");
  - dùng dự báo ECMWF ENS đã lưu trữ (A6): kho TIGGE (ECMWF ENS từ 2006, dùng cho nghiên cứu) cho 2015–2025; kho dữ
    liệu mở (0,25° từ 2/2024) chỉ để kiểm tra vận hành. Hiệu chỉnh phân vị ENS được gộp theo vùng và cấp cường độ,
    không làm theo từng ô và từng hạn trên hai mùa (quá mỏng cho cực trị).

**Đơn vị kiểm định.**
- Ngày-đơn vị (chấm ở cấp huyện / vùng cảnh báo hoặc theo cửa sổ nhiều ngày; xã chỉ để hiển thị):
  - Brier score;
  - Brier skill score so với khí hậu, so với chỉ dùng mưa và so với quy tắc Điều 46 (các cấp gán với tần suất quan
    sát tính kiểm định chéo);
  - ROC AUC;
  - PR-AUC, CSI / ETS và SEDI (cho sự kiện hiếm);
  - TSS, POD và tỷ lệ cảnh báo sai ở từng cấp;
  - biểu đồ tin cậy.
- Theo sự kiện: với mỗi ngày có sạt lở đã biết, đơn vị có được cảnh báo không, và trước bao nhiêu ngày? Báo cáo chỉ
  ghi ngày (± 1), nên thời gian cảnh báo trước được tính theo ngày, không theo giờ.
- Theo mùa: số lần cảnh báo mỗi xã mỗi mùa, tức "ngân sách cảnh báo" người dùng chấp nhận được.

**Mốc so sánh:**
- khí hậu (tần suất theo mùa của từng đơn vị);
- chỉ dùng mưa (không có tính nhạy);
- quy tắc Điều 46 với vùng của ta;
- vùng 1:50.000 của VIGMR ở nơi có.

Mô hình nào không hơn Điều 46 về A3 thì không được triển khai.

**Báo cáo.** Mỗi mùa một báo cáo kiểm định, với cùng các bảng và hình, bảng A1–A6, và các trường hợp hệ thống bỏ sót.
Mỗi trường hợp bỏ sót được xem xét thủ công: sản phẩm mưa lỗi, sự kiện không được báo cáo, hay vùng sai.

## 7. Thẩm định chuyên gia, vận hành và quản trị

**Các tài liệu giúp hệ thống kiểm tra được.**
- *Thẻ mô hình* cho mỗi phiên bản: mục đích, dữ liệu huấn luyện và sai lệch của nó, điểm số §6, các kiểu lỗi đã biết,
  hệ số thổi phồng phương sai, phiên bản code và mã băm dữ liệu.
- *Phiếu dữ liệu* cho mỗi đầu vào: nguồn, giấy phép, độ trễ, sai số so với trạm đo hay dữ liệu tham chiếu, phương án
  dự phòng.
- *Quy trình vận hành chuẩn (SOP)*: lịch hằng ngày, người dự báo kiểm tra gì, khi nào và cách ghi đè, cách phát bản
  tin, làm gì khi thiếu đầu vào.
- *Hồ sơ quyết định (ADR)* cho mọi lựa chọn làm thay đổi bản dự báo.

**Người dự báo trong vòng quyết định.**
- Lần chạy hằng ngày đề xuất một cấp cho mỗi đơn vị; người dự báo xác nhận hoặc thay đổi.
- Mỗi lần ghi đè cần lý do từ một danh sách cố định (báo cáo địa phương, quan sát thực địa, lỗi sản phẩm mưa, khác)
  và được ghi nhật ký.
- Các lần ghi đè được kiểm định như mô hình, để biết ở đâu kiến thức chuyên gia làm tăng chất lượng.

**Hội đồng thẩm định độc lập** (A8) gồm:
- một kỹ sư địa chất công trình hiểu miền Trung;
- một dự báo viên khí tượng thuỷ văn;
- một chuyên gia thống kê;
- một người dùng từ ban chỉ huy PCTT tỉnh.

Hội đồng duyệt phương pháp (F0), bản đồ tính nhạy ngoài thực địa trên một mẫu đơn vị (F3), và báo cáo kiểm định
trước khi vận hành (F8).

**Kiểm tra bản đồ ngoài thực địa.** Chọn một mẫu đơn vị phân tầng theo lớp và theo mức đồng thuận giữa các mô hình.
Nhà địa chất đi thực địa hoặc kiểm tra trên ảnh độ phân giải rất cao, rồi báo cáo tỷ lệ đơn vị "rất cao" mà họ đồng
ý.

**Vận hành.**
- *Vô địch / thách đấu:* phiên bản mới chạy song song (chế độ bóng) với phiên bản đang dùng trong trọn một mùa, và
  chỉ thay thế khi tốt hơn theo §6.
- *Giám sát:* độ trễ và khoảng trống của đầu vào; tỷ lệ đơn vị ở mỗi cấp so với khí hậu; độ trôi của các biến dự báo.
- *Dự phòng:* khi thiếu sản phẩm mưa quan trắc, dùng sản phẩm trước hoặc ngày đầu của dự báo, và hạ mức tin cậy
  xuống "thấp". Không bao giờ âm thầm.
- *Tái lập (A7):* mỗi lần chạy ghi một manifest (đầu vào, mã băm, phiên bản mô hình, phiên bản code); chạy lại cho
  cùng kết quả.

## 8. Chiến lược vận hành: nhịp cập nhật, độ sẵn sàng, tính kịp thời, chỉ số

Một hệ thống dự báo thường hỏng vì dữ liệu cũ hoặc đến muộn hơn là vì mô hình yếu. Mục này chốt, cho từng đầu vào và
từng sản phẩm:
- *khi nào* cập nhật hoặc xử lý lại;
- *sẵn sàng* đến mức nào;
- hệ thống phải phản ứng *nhanh* đến đâu;
- *chỉ số* nào đo từng phần đó.

Các mục tiêu được chốt ở F0 cùng A1–A8 và được đo từ nhật ký chạy (mỗi lần chạy ghi một manifest, §7). Chúng được báo
cáo hằng tuần trong mùa mưa và trong báo cáo cuối mùa.

### 8.1 Năm vận hành và các chế độ vận hành

Mùa mưa chính của miền Trung là tháng 9–12. Cả năm được tổ chức quanh mùa này:

| Tháng | Giai đoạn | Công việc |
|---|---|---|
| 1 – 2 | sau mùa | báo cáo kiểm định mùa (§6); đưa các báo cáo sạt lở của mùa vào danh mục; lập bản đồ vết sạt Sentinel-2 đầu tiên khi có ảnh tổng hợp đủ trong |
| 3 – 6 | bảo trì | huấn luyện lại S và T trên danh mục mới (thách đấu); các lớp hằng năm (rừng, ảnh tổng hợp NDVI, ảnh chụp đường giao thông); dựng lại stack InSAR theo cửa sổ mới; hiệu chỉnh lại sai số mưa |
| 7 – 8 | sẵn sàng | rà soát sẵn sàng (§8.6); chạy thử trên mùa trước; chốt mô hình vô địch trước 15/8; diễn tập SOP (phát lại một trận bão cũ, ví dụ tháng 10/2020) |
| 9 – 12 | vận hành | chế độ thường và chế độ bão, như dưới đây |

**Các chế độ trong mùa.**

| Chế độ | Bắt đầu khi | Chạy | Bản tin |
|---|---|---|---|
| **Thường** | vào mùa | 2 lần/ngày, theo các lượt ECMWF ENS 00 và 12 UTC và mưa quan trắc mới nhất | 2 bản/ngày, vào giờ cố định (giờ địa phương) chốt ở F0 |
| **Bão** | bất kỳ điều kiện nào sau: xác suất tổ hợp của mưa > 100 mm / 24 h ≥ 30 % ở một đơn vị; có cảnh báo chính thức mưa lớn hoặc bão cho vùng; dự báo cấp Điều 46 ≥ 1 | 3 giờ/lần, trên mưa quan trắc hằng giờ (GSMaP NRT; GSMaP_NOW là dự báo tức thời có độ bất định lớn hơn) | 6 giờ/lần, và ngay khi đổi cấp (QĐ 18, Điều 16: tin cảnh báo sạt lở ban hành ngay khi phát hiện khả năng xảy ra) |
| **Sau sự kiện** | có một ngày ở cấp ≥ 2, hoặc có báo cáo sạt lở | các lượt chạy thường vẫn tiếp tục | trong 7 ngày: thu thập báo cáo; bản đồ biến đổi Sentinel-1 từ lần chụp đầu tiên sau bão (≤ 12 ngày; 6 ngày nếu được xác nhận, §8.3); vết sạt Sentinel-2 khi trời trong; quyết định InSAR theo §8.3; đưa sự kiện vào kiểm định |

Bản thân các ngưỡng chuyển chế độ cũng được kiểm tra mỗi mùa: chế độ bão bật bao lâu, và các ngày sạt lở có rơi vào
khoảng đó không.

### 8.2 Chính sách cập nhật và xử lý lại theo từng lớp

Mỗi lớp có ba thông số:
- nhịp cập nhật bình thường;
- các sự kiện bắt buộc cập nhật sớm;
- **tuổi tối đa**.

Một lớp cũ hơn tuổi tối đa là *quá hạn*: lượt chạy vẫn diễn ra, nhưng mức tin cậy bị hạ và bản tin ghi rõ lớp nào quá
hạn.

| Lớp | Nhịp bình thường | Bắt buộc cập nhật khi | Tuổi tối đa |
|---|---|---|---|
| Mưa quan trắc (sản phẩm vận hành) | hằng giờ | — | 6 h cho một lượt chạy (nếu không, dùng dự phòng và hạ tin cậy xuống "thấp") |
| Mưa dự báo (ECMWF ENS) | các lượt 00 và 12 UTC | — | 18 h |
| Hiệu chỉnh và mô hình sai số mưa | làm lại trước mỗi mùa; kiểm tra hằng tháng với trạm đo | sai lệch tháng vượt ± 20 % hoặc tương quan thấp hơn giá trị đã hiệu chỉnh 0,1 | 12 tháng |
| Khí hậu mưa (CHIRPS, phân vị) | thêm một năm mỗi tháng 1 | CHIRPS ra phiên bản mới | 15 tháng |
| DEM và các lớp địa hình | tĩnh | có DEM mới; trận mưa làm thay đổi địa hình (vết sạt > 1 ha: cập nhật cục bộ các ô đó) | — |
| Rừng / lớp phủ | hằng năm (ảnh tổng hợp Sentinel-2 mùa khô; Hansen khi phát hành) | thấy chặt phá lớn trong bản đồ sau sự kiện | 18 tháng |
| Đường giao thông (cho số hạng sai lệch báo cáo) | ảnh chụp hằng năm, có ngày, trước mùa | — | 12 tháng |
| Địa chất, đứt gãy | khi có bản đồ mới | — | — |
| Đơn vị cảnh báo (xã) | khi ranh giới chính thức thay đổi | — | — |
| Danh mục sự kiện | báo cáo hằng ngày trong mùa; bản đồ Sentinel-2 sau mùa và sau các trận lớn | trận mưa cấp ≥ 2 | một mùa |
| Mô hình tính nhạy S | huấn luyện lại hằng năm sau khi cập nhật danh mục (thách đấu, §7) | ô dương mới > 20 % tập huấn luyện (sự kiện lớn) | 2 mùa |
| Mô hình kích hoạt T | huấn luyện lại hằng năm sau mùa | A1 hoặc A3 không đạt trong mùa đang chạy | 2 mùa |
| Hoạt động InSAR | mỗi lần chụp Sentinel-1 (§8.3) | §8.3 | 24 ngày (2 chu kỳ lặp 12 ngày) |

Một mô hình mới huấn luyện không bao giờ thay mô hình đang chạy giữa mùa. Nó chờ đến lần rà soát sẵn sàng. Ngoại lệ:
mô hình đang chạy không qua được một cổng; khi đó khôi phục mô hình vô địch trước đó, không dùng một mô hình chưa thử.

### 8.3 InSAR: khi nào cập nhật, khi nào xử lý lại

**Vai trò.** InSAR cho thấy những sườn đang chuyển động. Nó chỉ đi vào dự báo như một yếu tố điều chỉnh nếu L5 (H3)
cho thấy nó tăng chất lượng. Trước đó, nó là một lớp để người dự báo xem, không phải đầu vào của T. Chiến lược dưới
đây áp dụng cho cả hai trường hợp. *Đóng băng (2026-11-05):* thiết kế này không làm tiếp cho tới khi L5 cho thấy có
ích (độ phủ < 15 % số ô sườn dốc; độ kết hợp băng C ~0,1 sau 36 ngày dưới rừng).

**Dữ liệu chụp.** Sentinel-1C và 1D hoạt động từ 24/6/2026 (Sentinel-1A ngừng hoạt động 29–30/6/2026). Chu kỳ lặp 6
ngày trên Việt Nam chưa có nguồn xác nhận: ngay cả thời 1A + 1B, vùng này cũng chỉ có 12 ngày. Kế hoạch giả định
**12 ngày**, trừ khi kịch bản chụp (observation scenario) của Sentinel-1C/1D xác nhận 6 ngày cho vùng này
(2026-11-05). Ưu tiên track 120 quỹ đạo xuống, sau đó track 55 quỹ đạo lên.

**Ba mức xử lý** (engine `ps` của GeoEyes và phần cập nhật tăng dần, `[ps_update]`):

| Mức | Làm gì | Khi nào | Chi phí |
|---|---|---|---|
| **1 Tăng dần** | thêm lần chụp mới vào các điểm hiện có (`ps_update`) | mỗi lần chụp (12 ngày; 6 ngày nếu được xác nhận) | vài phút |
| **2 Chạy lại đầy đủ engine** | chạy lại mọi bước trên stack hiện tại (chọn điểm, sai số DEM, APS ước lượng lại) | sau mỗi 4 ngày ảnh được thêm (`full_every = 4`, ~48 ngày với chu kỳ 12 ngày), hoặc khi một chỉ số QC dưới đây không đạt | vài giờ |
| **3 Dựng lại stack** | stack mới: cửa sổ mới, ngày tham chiếu mới, phase linking lại | hằng năm vào tháng 3–6 trên cửa sổ trượt 2 năm; sau một sự kiện làm mất tương quan; khi đổi vệ tinh, quỹ đạo hoặc tham số xử lý | ~1 ngày mỗi track |

**Điều kiện kích hoạt mức 2.** Đo ở mỗi lần cập nhật tăng dần, trên các điểm ổn định và các đơn vị sườn dốc; chỉ cần
một điều kiện:
- độ kết hợp thời gian trung vị trên các đơn vị sườn dốc giảm hơn 0,05 so với lần chạy đầy đủ gần nhất;
- RMS của chênh lệch vận tốc giữa bản tăng dần và bản đầy đủ gần nhất, trên các điểm ổn định, vượt 2 mm/năm;
- số điểm giảm hơn 20 %;
- phần dư vận tốc trung vị giữa các điểm lân cận tăng quá 3 mm/năm (lượt L5b là 1,9 mm/năm);
- vùng tham chiếu bị dịch chuyển (vận tốc của nó so với GNSS hoặc các điểm lân cận vượt 2 mm/năm).

**Điều kiện dựng lại stack (mức 3) sau sự kiện:** hơn 30 % số đơn vị sườn dốc mất tương quan trong cặp ảnh qua trận
mưa, hoặc bản đồ sau sự kiện thấy vết sạt ở hơn 5 % số đơn vị. Khi đó chuỗi thời gian bị cắt: một đoạn mới bắt đầu
sau sự kiện, và hoạt động trước và sau được so sánh với nhau (L5b), không bao giờ ghép thành một chuỗi.

**InSAR sẵn sàng cho dự báo** khi lớp hoạt động "còn hiệu lực":
- lần chụp cuối không cũ hơn 24 ngày;
- phủ ít nhất 10 % số ô sườn dốc của đơn vị (cổng độ phủ của L5).

Nếu không, đơn vị hiển thị "không có thông tin InSAR". Điều đó không có nghĩa là "ổn định".

### 8.4 Độ sẵn sàng của dữ liệu

**Sáu chiều, giống nhau cho mọi đầu vào.**

| Chiều | Câu hỏi | Chỉ số |
|---|---|---|
| Có sẵn | có dữ liệu cho vùng và thời kỳ của ta không? | có / một phần / không |
| Độ trễ | dữ liệu đến sau thời điểm quan trắc bao lâu? | p50 và p95 của độ trễ, đo thực tế |
| Đầy đủ | mọi file cần có đến trước giờ chốt của lượt chạy không? | tỷ lệ đúng hạn trong mùa |
| Liên tục | có khoảng trống không (ngày, thành viên tổ hợp, burst)? | số ngày trống mỗi mùa |
| Chất lượng | gần với dữ liệu tham chiếu đến đâu? | sai lệch và tương quan so với trạm đo / GNSS / thực địa |
| Dự phòng | thiếu thì dùng gì thay? | tên sản phẩm thay thế, và số lần đã phải dùng |

**Đánh giá hiện tại (2026-11-03).** Độ trễ danh nghĩa lấy từ nhà cung cấp. F2 đo độ trễ thực tế trên đường truyền của
ta trong trọn một mùa, trước khi ký bất kỳ mục tiêu nào.

| Đầu vào | Có sẵn | Độ trễ danh nghĩa | Trạng thái | Còn thiếu |
|---|---|---|---|---|
| GSMaP NRT (hằng giờ, 0,1°) | có | 4 h | một phần | so với trạm đo ở vùng núi (F2) |
| GSMaP_NOW (vùng Himawari) | có | ~0 h | một phần | kém chính xác hơn NRT: chỉ dùng dự báo tức thời, khoảng rộng hơn |
| IMERG Early / Late / Final | có | 4 h / ~14 h / ~3,5 tháng theo danh nghĩa (thực tế lâu hơn: ngày 2026-11-04 bản Final tháng 10–12/2025 vẫn chưa phát hành, §9.1) | một phần | cùng phép kiểm tra; Final chỉ dùng cho lưu trữ |
| CHIRPS (ngày, 0,05°) | có, từ 1981 | vài tuần (bản cuối) | sẵn sàng | chỉ dùng cho khí hậu |
| Dữ liệu mở ECMWF ENS (0,25°, 51 thành viên) | từ 2/2024 ở 0,25° | giờ phát hành cần đo | một phần | kho mở ngắn (2024–2025: 34 ngày-xã dương, quá ít cho A6); A6 được kiểm trên kho TIGGE của ECMWF ENS (từ 2006, dùng cho nghiên cứu) cho 2015–2025 (2026-11-05) |
| Trạm đo mưa (KTTV) | mới có bản sao phục vụ nghiên cứu (imech.info, 2026-11-05): 220 trạm trong vùng lõi | chưa rõ | dùng để hiệu chỉnh, chưa dùng vận hành | nguồn chính thức (chủ dự án, §10) |
| Sentinel-1 (burst, ASF) | có, lặp 12 ngày (6 ngày nếu kịch bản S1C/S1D xác nhận, §8.3) | cần đo (vài giờ đến một ngày) | sẵn sàng | — |
| Sentinel-2 | có | ~1 ngày | một phần | mây trong mùa mưa: chỉ lập bản đồ sau mùa |
| Báo cáo sạt lở có ngày | thưa | vài ngày | một phần | hồ sơ VIGMR / các tỉnh (§10) |
| Phân vùng 1:50.000 (VIGMR) | chưa có | — | thiếu | chủ dự án (§10) |
| Địa chất, đứt gãy | chỉ có GLiM | — | một phần | chủ dự án (§10) |
| Ranh giới xã sau 2025 | cần thu thập | — | một phần | nguồn chính thức |

**Quy tắc sẵn sàng.** Một đầu vào chỉ được dùng trong vận hành khi "sẵn sàng", nghĩa là đạt đủ:
- có sẵn: có;
- độ trễ p95 trong ngân sách (§8.5);
- tỷ lệ đúng hạn ≥ 98 % trong 30 ngày cuối của đợt chạy thử;
- đã nêu chất lượng;
- đã có tên và đã thử phương án dự phòng.

### 8.5 Tính kịp thời: hệ thống có đủ nhanh không?

**Ngân sách thời gian của một bản dự báo** (chế độ thường; chế độ bão trong ngoặc). T0 là thời điểm kết thúc giờ mưa
được quan trắc.

| Công đoạn | Ngân sách |
|---|---|
| có mưa quan trắc | T0 + 4 h (độ trễ sản phẩm) |
| tải và kiểm tra | ≤ 10 phút |
| chạy dự báo (mọi đơn vị, Monte Carlo, bản đồ) | ≤ 5 phút mỗi tỉnh (A7) |
| người dự báo duyệt | ≤ 30 phút (≤ 15 phút) |
| phát bản tin | ≤ T0 + 5 h (≤ T0 + 4,5 h) |

**Phản ứng với một trận bão.**
- Chế độ bão bật trong vòng 1 h sau điều kiện kích hoạt (§8.1).
- Một thay đổi cấp được công bố trong vòng 30 phút sau lượt chạy phát hiện ra nó.

**Thời gian cảnh báo trước**, đo trên mọi vụ sạt lở đã biết (dự báo ngược, rồi mùa chạy bóng):
- là số ngày từ bản tin đầu tiên ở cấp cảnh báo đến ngày sạt lở. Báo cáo chỉ ghi ngày (± 1), nên thời gian cảnh
  báo trước tính theo ngày tròn, không theo giờ (2026-11-05);
- mục tiêu: ít nhất 50 % số ngày sạt lở được cảnh báo trước ≥ 1 ngày, tức là trong bản tin của ngày hôm trước hoặc
  sớm hơn (dùng mưa dự báo, A6).

Cảnh báo đến sau khi sạt lở xảy ra được tính là bỏ sót trong A1 ở hạn dự báo đó.

### 8.6 Chỉ số: đo từng phần như thế nào

Các chỉ số được tính tự động từ manifest và nhật ký chạy. Mỗi chỉ số có ba mức:
- mục tiêu (xanh);
- mức báo động (vàng: đưa ra bàn ở lần rà soát hằng tuần kế tiếp);
- mức hỏng (đỏ: xử lý ngay, ghi vào nhật ký).

| Nhóm | Chỉ số | Mục tiêu | Vàng | Đỏ |
|---|---|---|---|---|
| Sẵn sàng dữ liệu | tỷ lệ đúng hạn của mỗi đầu vào quan trọng (mưa quan trắc, ENS) | ≥ 98 % | < 98 % | < 95 % |
| | độ trễ p95 của mỗi đầu vào quan trọng | trong ngân sách | ngân sách + 1 h | ngân sách + 3 h |
| | độ đầy đủ không gian (đơn vị có mưa hợp lệ) | 100 % | < 100 % | < 95 % |
| | tỷ lệ dùng dự phòng (lượt chạy trên đầu vào dự phòng) | ≤ 2 % | > 2 % | > 10 % |
| | lớp quá hạn (cũ hơn tuổi tối đa, §8.2) | 0 | 1 lớp không quan trọng | bất kỳ lớp quan trọng nào |
| | sai lệch mưa so với trạm đo (hằng tháng) | trong ± 20 % | ± 20–35 % | ngoài ± 35 % |
| Tính kịp thời | bản tin phát đúng giờ | ≥ 99 % | < 99 % | < 95 % |
| | độ trễ từ quan trắc đến bản tin, p95 | ≤ 5 h | ≤ 6 h | > 6 h |
| | thời gian chạy mỗi tỉnh | ≤ 5 phút | ≤ 15 phút | > 15 phút |
| | độ trễ bật chế độ bão | ≤ 1 h | ≤ 2 h | > 2 h |
| | thời gian cảnh báo trước (tỷ lệ ngày sạt lở đã biết được cảnh báo trước ≥ 1 ngày) | ≥ 50 % | 30–50 % | < 30 % |
| Độ tin cậy dịch vụ | tỷ lệ lượt chạy theo lịch thành công | ≥ 99,5 % | < 99,5 % | < 98 % |
| | lỗi âm thầm (lượt chạy hỏng mà không báo động) | 0 | — | ≥ 1 |
| | thời gian khôi phục sau sự cố | ≤ 2 h | ≤ 6 h | > 6 h |
| | chạy lại kiểm tra tái lập hằng tuần (cùng mã băm đầu ra) | trùng khớp | — | khác |
| Chất lượng dự báo | A1–A5 trên phần mùa đã qua (cuốn chiếu) | như A1–A5 | một tiêu chí dưới mức | hai tiêu chí dưới mức |
| | tỷ lệ ngày-đơn vị ở mỗi cấp so với khí hậu | trong ± 50 % | ± 50–100 % | vượt quá |
| InSAR | độ trễ từ lần chụp đến lớp hoạt động được cập nhật | ≤ 2 ngày | ≤ 4 ngày | > 6 ngày |
| | số đơn vị sườn dốc có thông tin InSAR | nêu theo mùa | − 10 % | − 25 % |
| | các điều kiện QC của §8.3 | không có | một | từ hai trở lên |
| Người trong vòng | số lần ghi đè có lý do | 100 % | — | < 100 % |
| | số lần ghi đè làm dự báo tốt hơn (đã kiểm định) | báo cáo | — | — |

**Các lần rà soát.**
- Hằng ngày trong mùa: nhật ký chạy và mọi chỉ số đỏ.
- Hằng tuần trong mùa: mọi chỉ số trên một trang. Trang `Hazard` của web app sẽ có một tab vận hành.
- Sau mùa: báo cáo mùa, gồm kiểm định (§6) và các chỉ số này, kèm hành động cho mùa sau.
- **Rà soát sẵn sàng tháng 8 (chạy / không chạy).** Điều kiện để chạy:
  - mọi đầu vào quan trọng "sẵn sàng" (§8.4) trong 30 ngày cuối;
  - chạy thử trên mùa trước đạt A1–A6;
  - đã ký thẻ mô hình và SOP;
  - đã diễn tập phát lại trận bão.

  Mục nào "không chạy" thì hoặc được sửa, hoặc mùa đó vận hành với phạm vi hẹp hơn và ghi rõ.

### 8.7 Kịch bản, rủi ro và cách xử lý

Ngày tệ nhất với hệ thống lại chính là ngày nó quan trọng nhất: bão làm mất điện và mất mạng, sản phẩm mưa đến muộn
hoặc sai, người dự báo đang ở hiện trường, và nguy cơ ở mức cao nhất. Thiết kế phải bảo đảm ngày đó vẫn có một sản
phẩm dùng được. Mục này gồm:
- phương pháp: sổ đăng ký rủi ro;
- nguyên tắc: thang suy giảm;
- cách xử lý: các kịch bản;
- bằng chứng: diễn tập.

**Bài học đã gặp ngay trong dự án này** (mỗi bài học là một dòng trong sổ đăng ký):
- đĩa đầy giữa lúc chạy, vì việc chuyển dự án vào thùng rác đã sao chép thay vì đổi tên (2026-11-03);
- một mật khẩu bị in ra log và đã phải đổi;
- dịch vụ burst của ASF ngừng nhiều ngày (L3b.7);
- máy chủ CHIRPS từ chối tải song song (L6).

#### Sổ đăng ký rủi ro

Mỗi rủi ro được chấm khả năng xảy ra L và mức tác động I, thang 1–5 (tác động 5 = bỏ sót cảnh báo vào một ngày có
thương vong). Điểm = L × I. Mỗi dòng ghi:
- cách *phát hiện* (dùng chỉ số §8.6 khi có thể);
- cách *phòng ngừa*;
- cách *xử lý* (một kịch bản bên dưới).

Sổ được rà soát ở lần rà soát sẵn sàng và sau mỗi sự cố. Điểm ban đầu chờ chủ dự án xác nhận ở F0.

| # | Rủi ro | L | I | Điểm | Phát hiện | Phòng ngừa | Xử lý |
|---|---|---|---|---|---|---|---|
| R1 | Mất điện hoặc mất mạng tại nơi vận hành trong lúc bão | 4 | 5 | 20 | tín hiệu nhịp tim từ máy dự phòng | chuỗi vận hành chạy trên máy chủ đám mây, có máy thứ hai ở vùng khác; máy trạm cá nhân không phải nơi vận hành | P1 |
| R2 | Mưa vệ tinh thấp hơn nhiều so với thực tế trong một trận mưa địa hình cực đoan (lỗi âm thầm: không báo lỗi, chỉ cho cấp thấp sai) | 4 | 5 | 20 | trạm đo báo cao hơn sản phẩm; mưa dự báo 24 h vừa qua cao hơn nhiều so với mưa quan trắc | so với trạm đo (F2); cấp không bao giờ thấp hơn cấp tính từ mưa dự báo của lượt trước; bật chế độ bão theo cảnh báo chính thức, bất kể mưa của ta nói gì | P2 |
| R3 | Mưa vượt khỏi phạm vi dữ liệu huấn luyện (trận mưa kỷ lục, ví dụ tháng 10/2020) | 3 | 5 | 15 | đầu vào nằm ngoài phạm vi của dự báo ngược | mô hình đơn điệu; xác suất giới hạn ở lớp cao nhất đã hiệu chỉnh, kèm nhãn "vượt kinh nghiệm" | P3 |
| R4 | Cảnh báo sai quá nhiều khiến người dùng không còn tin | 4 | 4 | 16 | số cảnh báo mỗi xã mỗi mùa so với ngân sách (A2) | ngân sách thống nhất ở F0; ngưỡng cấp đặt theo kiểm định; thông báo mức tin cậy | P4 |
| R5 | Sạt lở có thương vong ở một đơn vị không được cảnh báo | 3 | 5 | 15 | báo cáo, báo chí | A1; người dự báo ghi đè; cấp Điều 46 hiển thị cạnh cấp của ta | P5 |
| R6 | Mưa quan trắc đến muộn hoặc thiếu | 4 | 3 | 12 | tỷ lệ đúng hạn, độ trễ p95 | hai sản phẩm (GSMaP và IMERG): độc lập khi một nhà cung cấp gặp sự cố, nhưng không độc lập về sai số (dùng chung cảm biến vi ba thụ động và ảnh hồng ngoại địa tĩnh) | bậc 1 |
| R7 | Mưa dự báo (ENS) đến muộn hoặc thiếu | 3 | 3 | 9 | tỷ lệ đúng hạn | tổ hợp GFS làm nguồn thứ hai | bậc 2 |
| R8 | Dự báo sai quỹ đạo bão | 3 | 4 | 12 | độ phân tán tổ hợp; bản tin quỹ đạo chính thức | lấy xác suất từ tổ hợp, không lấy trung bình; bật chế độ bão theo cảnh báo chính thức | P2 |
| R9 | Đầy đĩa, tiến trình sập, đầu ra hỏng | 3 | 4 | 12 | kiểm tra dung lượng trống trước mỗi lượt chạy; mã kiểm tra đầu ra | tách ổ dữ liệu và ổ vận hành; dung lượng trống ≥ 3 × lượt chạy lớn nhất; thùng rác không bao giờ sao chép (đã sửa 2026-11-03) | P6 |
| R10 | Một bản phát hành phần mềm làm hỏng chuỗi xử lý | 3 | 4 | 12 | chạy lại kiểm tra tái lập hằng tuần; test trong CI | không phát hành trong mùa trừ bản sửa lỗi; luôn giữ sẵn phiên bản trước để khôi phục | P6 |
| R11 | Nhà cung cấp đổi định dạng, phiên bản, cách truy cập hoặc thông tin đăng nhập (token hết hạn, tài khoản Earthdata) | 3 | 3 | 9 | lỗi tải; xem thông báo của nhà cung cấp ở lần rà soát sẵn sàng | phiếu dữ liệu có nguồn thứ hai; thông tin đăng nhập cất trong kho bí mật, gia hạn trước mùa, không bao giờ in ra log | P6 |
| R12 | Lộ thông tin đăng nhập hoặc máy chủ bị xâm nhập | 2 | 4 | 8 | nhật ký truy cập | bí mật nằm ngoài code và log; quyền tối thiểu; đổi mỗi mùa | P6 |
| R13 | Sai thời gian (ngày theo UTC hay giờ địa phương, ranh giới khi tính tổng 24 h) | 3 | 4 | 12 | test đơn vị trên ranh giới ngày; test phát lại | một quy ước duy nhất (bên trong dùng UTC, bản tin dùng giờ Việt Nam), có test | P6 |
| R14 | Không có người dự báo (ban đêm, đang ở hiện trường, ốm) | 3 | 4 | 12 | chưa duyệt trước giờ chốt | lịch trực có người thay; quá giờ chốt + 30 phút thì bản tin tự phát với nhãn "chưa duyệt" | P1 |
| R15 | Bản tin không đến được các xã | 3 | 5 | 15 | xác nhận đã nhận | hai kênh (kênh chính thức của tỉnh và danh sách SMS / Zalo), ghi nhật ký xác nhận | P1 |
| R16 | Người dùng hiểu sai xác suất (0,2 hiểu thành "an toàn") | 3 | 4 | 12 | phản hồi người dùng, diễn tập | cấp là thông tin chính, xác suất là thông tin bổ trợ; bộ từ cố định cho các mức số; tập huấn trước mùa | P4 |
| R17 | Cấp của ta mâu thuẫn với bản tin chính thức | 4 | 3 | 12 | so sánh tự động ở mỗi lượt chạy | luôn hiển thị cả hai, kèm lý do khác nhau; cấp chính thức vẫn là căn cứ pháp lý | P4 |
| R18 | Lớp tính nhạy lỗi thời sau một sự kiện lớn (vết sạt mới, đường mới) | 3 | 3 | 9 | bản đồ sau sự kiện (§8.1) | các cập nhật bắt buộc của §8.2 | cập nhật lớp |
| R19 | Mô hình trôi (sử dụng đất, khí hậu thay đổi) | 2 | 3 | 6 | A1–A5 cuốn chiếu; tần suất các cấp so với khí hậu | huấn luyện lại hằng năm, cơ chế vô địch / thách đấu | huấn luyện lại |
| R20 | Trách nhiệm: một quyết định dựa trên sản phẩm của ta dẫn đến hậu quả | 2 | 5 | 10 | — | sản phẩm chỉ mang tính tham khảo; điều khoản sử dụng và các giới hạn ghi trong bản tin và thẻ mô hình; thống nhất ở F0 | — |

#### Thang suy giảm

Hệ thống không bao giờ dừng. Nó hạ bậc và nói rõ đang ở bậc nào. Mỗi bậc đều được thử trong diễn tập.

| Bậc | Điều kiện | Phát hành gì | Mức tin cậy |
|---|---|---|---|
| 0 Đầy đủ | mọi đầu vào sẵn sàng | sản phẩm đầy đủ của §4 | theo tính toán |
| 1 Không có mưa quan trắc | sản phẩm quan trắc đến muộn hoặc thiếu | mưa trước đó lấy từ ngày đầu của dự báo và lần quan trắc cuối; khoảng tin cậy nới rộng | tối đa "trung bình" |
| 2 Không có ENS | thiếu tổ hợp ECMWF | dùng tổ hợp GFS; nếu cả GFS cũng hỏng, dùng mưa dự báo tất định chính thức của cơ quan khí tượng | tối đa "trung bình" / "thấp" |
| 3 Không có máy tính | nơi vận hành và máy dự phòng đều hỏng | **bảng tra tính sẵn**: với mỗi đơn vị, cấp tương ứng từng khoảng mưa 24 h và mưa trước đó, in trong SOP và lưu ngoại tuyến; người dự báo tra bằng tay với mưa dự báo chính thức | "thấp" |
| 4 Không còn gì của ta | không có bảng, không có dữ liệu | chỉ dùng cấp Điều 46 chính thức | — |

Bảng tra của bậc 3 được tính lại mỗi khi có phiên bản mô hình mới và là một phần của bản phát hành. Nhờ nó, hệ thống
vẫn dùng được khi mất điện.

#### Các kịch bản xử lý

Mỗi kịch bản là một trang trong SOP, ghi các việc làm ngay, người cần gọi và các bước kiểm tra.

| # | Tình huống | 30 phút đầu | Sau đó | Trở lại bình thường |
|---|---|---|---|---|
| P1 | Nơi vận hành, người dự báo hoặc kênh phát tin hỏng trong lúc bão | chuyển sang máy dự phòng (tự động) hoặc bảng tra (bậc 3); gọi người dự báo thay thế; gửi qua kênh thứ hai | phát bản tin 6 giờ/lần ở bậc đang có; ghi nhật ký mọi bước | khôi phục máy chính, kiểm tra bằng một lượt chạy lại; rà soát sự cố trong 7 ngày |
| P2 | Mưa có thể sai (trạm đo, báo cáo hoặc dự báo cho thấy mưa lớn hơn nhiều) | nâng lên cấp tính từ nguồn cao hơn; đánh dấu "sản phẩm mưa đáng ngờ" | đối chiếu với trạm đo và radar của cơ quan khí tượng nếu có; giữ cấp cao hơn cho tới khi hai sản phẩm khớp nhau | đưa trường hợp này vào phép so với trạm đo; hiệu chỉnh lại mô hình sai số sau mùa |
| P3 | Mưa vượt kinh nghiệm | phát cấp cao nhất kèm "vượt phạm vi các sự kiện đã biết"; báo người dùng rằng xác suất chỉ là cận dưới | chế độ bão; ưu tiên lập bản đồ sau sự kiện | đưa sự kiện vào dữ liệu huấn luyện sau mùa |
| P4 | Cảnh báo quá dày, hoặc cấp của ta mâu thuẫn với cấp chính thức | hiển thị cả hai cấp và lý do; người dự báo quyết định và ghi lý do | xem lại ngân sách cảnh báo với người dùng sau trận bão | đặt lại ngưỡng các cấp theo kiểm định cuối mùa |
| P5 | Sạt lở có thương vong mà không được cảnh báo | thu thập dữ kiện (thời gian, địa điểm, mưa, các bản tin của ta) trong 24 h | rà soát trường hợp: dữ liệu, mô hình, truyền tin | đưa hành động vào sổ đăng ký; công bố trong báo cáo mùa |
| P6 | Sự cố kỹ thuật (đĩa, bản phát hành, nhà cung cấp, thông tin đăng nhập, thời gian) | khôi phục phiên bản hoặc đầu vào trước đó; chạy các kiểm tra trước khi chạy; chạy lại | tìm nguyên nhân gốc; sửa kèm một test tái hiện lỗi | chạy lại kiểm tra tái lập đạt; cập nhật sổ đăng ký |

#### Diễn tập và rà soát sự cố

- **Trước mỗi mùa (tháng 8):**
  - diễn tập trên bàn với người dùng, phát lại một trận bão cũ (tháng 10/2020 cho miền Trung);
  - diễn tập chuyển dự phòng: tắt máy chính, chạy trên máy dự phòng, rồi chạy bằng bảng tra;
  - kiểm tra mọi thông tin đăng nhập và mọi thông báo của nhà cung cấp.
- **Trong mùa:** một lần thử chuyển dự phòng không báo trước, vào một tuần yên ả.
- **Sau mỗi sự cố:** rà soát trong 7 ngày, không đổ lỗi cá nhân: chuyện gì xảy ra, vì sao, thay đổi gì. Kết quả ghi
  vào sổ đăng ký. Cùng một lỗi không được lặp lại lần hai.
- **Chỉ số** (bổ sung vào §8.6):
  - diễn tập trước mùa: đủ tất cả;
  - sự cố được rà soát trong 7 ngày: 100 %;
  - sự cố lặp lại: 0.

## 9. Kế hoạch F0–F9

Mỗi bước kết thúc bằng một báo cáo ngắn và lần duyệt của chủ dự án. Các bước InSAR (L5, L5b) tiếp tục chạy nền như
một mô-đun tuỳ chọn và không chặn hệ thống.

| Bước | Nội dung | Dựa trên | Đầu ra | Cổng duyệt |
|---|---|---|---|---|
| **F0** Yêu cầu | người dùng, đơn vị cảnh báo (xã sau sắp xếp 2025), các hạn dự báo, ngân sách cảnh báo, chốt A1–A8 cùng các mục tiêu vận hành của §8 (giờ phát bản tin, ngân sách độ trễ, các mức chỉ số); chấm điểm sổ đăng ký rủi ro §8.7; điều khoản sử dụng; liên hệ hội đồng thẩm định | §1, §3, §8 | `f0_requirements.md`, `risk_register.md` | chủ dự án ký A1–A8, mục tiêu §8 và sổ đăng ký rủi ro |
| **F1** Danh mục sự kiện | mọi vụ sạt lở có ngày trong một lược đồ, kèm độ chính xác vị trí và ngày (O2): `vietnam.csv`, sự kiện Das, vết Sentinel-2 định ngày theo trận mưa, hồ sơ VIGMR nếu có; nhãn ngày-đơn vị | L0, L3b, O2 | `catalogue.parquet`, báo cáo rà soát | đủ ngày-đơn vị dương cho T (mục tiêu ≥ 150 ở miền Trung) |
| **F2** Mưa | lưu trữ 2015–2025 GSMaP NRT và IMERG Early cho miền Trung; so với trạm đo (KTTV nếu có, nếu không thì GHCN-D / GSOD, vốn không độc lập với các sản phẩm, §9.1); chọn sản phẩm vận hành; mô hình sai số; lưu trữ ECMWF ENS (TIGGE) và hiệu chỉnh phân vị gộp theo vùng và cường độ; đo độ trễ và tỷ lệ đúng hạn của từng sản phẩm trên đường truyền của ta (§8.4) | code L6, O3 | kho `rain/`, `f2_rain_check.md`, phiếu dữ liệu | đã chọn sản phẩm, đã nêu mô hình sai số, bảng sẵn sàng điền số đo thực |
| **F3** Tính nhạy cuối cùng | C4 (địa chất, đứt gãy, sông, đường trước sự kiện), C5 (nhãn), C6 (vô địch); tổ hợp; hiệu chỉnh về mật độ; phân lớp; so với vùng 1:50.000; mẫu kiểm tra thực địa | L3c | thẻ mô hình v1, `susceptibility_<năm>.tif` + khoảng | hội đồng duyệt bản đồ |
| **F4** Kho lớp tĩnh | mọi ô của các tỉnh (O1), tổng hợp theo đơn vị (xã và đơn vị sườn dốc) | O1 | `base/static/`, `units.gpkg` | phủ toàn bộ, thời gian chạy |
| **F5** Mô hình kích hoạt | ngưỡng L6 trên sản phẩm F2; các ứng viên 1–3 của §4 trên ngày-đơn vị; bỏ-một-mùa | L6, F1, F2, F3 | `trigger/`, `f5_report.md` | A1, A3 với mưa quan trắc |
| **F6** Độ bất định | chuỗi Monte Carlo của §5; kiểm tra độ phủ; thổi phồng phương sai | F3, F5 | `uncertainty.md`, chuỗi đã hiệu chỉnh | A4, A5 |
| **F7** Dự báo ngược và kiểm định | 2015–2025 với mưa quan trắc và với mưa dự báo; mọi mốc so sánh; phân tích trường hợp bỏ sót | F5, F6 | `verification_2015_2025.md` | A1–A6 |
| **F8** Chuỗi vận hành | `geoeyes landslide forecast`: chạy hằng ngày, bản tin theo đơn vị, bản đồ, nhật ký; các chế độ và chính sách cập nhật lớp của §8.1–8.3; các chỉ số của §8.6 và tab vận hành; máy chủ đám mây và máy dự phòng, thang suy giảm và bảng tra, các kịch bản §8.7; trang `Hazard` của web app; SOP, thẻ mô hình, phiếu dữ liệu | L9 | dịch vụ, tài liệu | A7, hội đồng duyệt (A8), lần rà soát sẵn sàng đầu tiên kèm diễn tập chuyển dự phòng |
| **F9** Mùa chạy bóng | trọn một mùa mưa ở chế độ bóng (tháng 9–12/2027), ghi và kiểm định mọi bản dự báo, đo mọi chỉ số §8.6, trước khi dùng chính thức | F8 | báo cáo kiểm định và vận hành mùa | chủ dự án quyết định đưa vào dùng |

**Thứ tự và thời gian.**
- F0, F1 và F2 làm trước, vì chúng quyết định có xây được mô hình thời gian hay không. F3 chạy song song với F2.
- Sau đó F5–F7; F8 làm cuối.
- F9 không thể bắt đầu trước tháng 9/2027. Mùa mưa 2026 đang diễn ra (tháng 11) có thể dùng làm phép thử đầu tiên cho
  F5 ngay khi có kho mưa.

### 9.1 Chi tiết F0–F2 (bắt đầu 2026-11-03)

**F0.** Để ký:
- [`landslide-forecast/f0-requirements.md`](landslide-forecast/f0-requirements.md): phạm vi, A1–A8 (đã duyệt về
  nguyên tắc, sửa ngày 2026-11-05 trước mọi dự báo ngược, chờ ký), mục tiêu vận hành, hạ tầng, dữ liệu cần;
- [`landslide-forecast/risk-register.md`](landslide-forecast/risk-register.md): sổ rủi ro "sống", gồm điểm số, trạng
  thái phòng ngừa và nhật ký sự cố.

**F1 — Danh mục sự kiện.** Điểm xuất phát: `vietnam.csv` có 72 vụ sạt lở có ngày ở miền Trung từ 2015, rơi vào 54
ngày khác nhau. Các năm 2016–2019 chỉ có 2–3 vụ mỗi năm, do sót báo cáo chứ không phải do không có sạt lở. Mục tiêu:
≥ 150 ngày-đơn vị dương.
1. *Báo chí và báo cáo tình hình* 2015–2025, thu thập theo từng trận bão và từng tỉnh, chia ba đợt chạy song song
   (2015–2018, 2019–2021, 2022–2025). Mỗi bản ghi có đường dẫn nguồn và một câu trích nêu ngày và địa điểm.
2. *Gộp* với `vietnam.csv`; cùng một xã trong vòng ± 1 ngày tính là một sự kiện.
3. *Gán toạ độ* theo xã (ranh giới trước 2025). Bản ghi giữ tên xã, tâm xã và kích thước xã làm độ chính xác vị trí.
   Bản ghi chỉ biết tới huyện vẫn ở trong danh mục để tính ngưỡng theo vùng, nhưng không dùng làm nhãn ngày-xã.
4. *Kiểm tra lại*: đọc lại ngẫu nhiên 20 % số bản ghi so với nguồn; báo cáo tỷ lệ được xác nhận.
5. *Nhãn ngày-đơn vị*: đếm so với mục tiêu; nêu khoảng trống theo năm và theo tỉnh.
6. *Bổ sung* (sau, nếu vẫn thiếu): vết sạt Sentinel-2 định ngày theo trận mưa bằng chuỗi Sentinel-1; hồ sơ VIGMR và
   các tỉnh do chủ dự án cung cấp.

**Kết quả tạm của F1 (2026-11-03, lệnh `geoeyes landslide catalogue`; file `<study>/catalogue/f1_report.md`).**
- Thu thập báo chí: 215 bản ghi (2015–2018: 29; 2019–2021: 83; 2022–2025: 103), mỗi bản ghi có nguồn và câu trích.
- Gán vị trí: mọi bản ghi đều gán được. Dùng xã GADM, và OpenStreetMap cho đèo và xã sau 2025. Phần OpenStreetMap có
  kiểm tra tên và loại đối tượng, vì kiểm tra thủ công đã thấy kết quả sai với tên đường và địa danh trùng tên.
- Danh mục: 291 bản ghi → 258 sự kiện; **97 ngày-xã dương trên 61 ngày khác nhau** (trước khi thu thập: 54 ngày).
  Mục tiêu 150: **chưa đạt**.
- Khoảng trống: năm 2015 (không có), năm 2019 (2), và các tỉnh Gia Lai, Ninh Thuận, Phú Yên, Đà Nẵng, Bình Định.
- Nhãn theo trận bão từ danh mục polygon: Ketsana 22 xã (8.053 vụ sạt lở), Molave 20 xã (11.011 vụ).
  - Mọi xã đã lập bản đồ đều có sạt lở, vì vùng lập bản đồ được vẽ bao quanh chúng.
  - Vì vậy dữ liệu này cho *mật độ* (số vụ trên mỗi km² đã lập bản đồ) để dựng quan hệ liều – đáp ứng với mưa của
    trận bão, chứ không cho "có / không".
- Hệ quả cho F5:
  - mô hình kích hoạt theo ngày phải gộp các vùng, với tiên nghiệm có thông tin (ứng viên 2);
  - mật độ theo trận bão dùng để hiệu chỉnh đáp ứng tính nhạy × mưa;
  - hồ sơ của VIGMR / các tỉnh (§10) là con đường để đạt mục tiêu.

**F2 — Mưa.**
0. *GSMaP v8* (tài khoản JAXA của chủ dự án, 2026-11-03): NRT và Gauge-NRT theo ngày ở 0,1°, cùng tâm ô với IMERG.
   Ngày 28/10/2020 trên vùng miền Trung, GSMaP NRT cho tối đa 307 mm/ngày, còn IMERG Early cho 164 mm/ngày. Như
   vậy chọn sản phẩm nào sẽ làm thay đổi cấp cảnh báo, nên phải so với trạm đo trước khi chọn (R2).
   *Kết quả so IMERG Early với Final* (2026-11-04, lệnh `geoeyes landslide raincheck`).
   - Phạm vi: tháng 9–12 các năm 2015–2025, 6,5 triệu ô-ngày. Bản Final tháng 10–12/2025 chưa phát hành, dù độ trễ
     danh nghĩa chỉ ~3,5 tháng: thực tế bản Final đã chậm hơn nhiều, cần đối chiếu với thông báo của GES DISC.
   - Tổng lượng 1,03; tương quan 0,93; phân vị 99 bằng 1,005. Hai bản cùng thang đo, nên ngưỡng tính trên kho dữ
     liệu dùng được cho bản Early khi vận hành.
   - Ngày mưa lớn bị đặt sai chỗ: ở ngưỡng ≥ 100 mm, POD 0,72 / FAR 0,29; ở ngưỡng ≥ 200 mm, POD 0,60 / FAR 0,58.
     Vì vậy cần làm mượt theo không gian và dùng các thành viên sai số mưa của §5.
   - Final là cùng thuật toán, chỉ hiệu chỉnh theo trạm hằng tháng, nên không phải mốc độc lập. Trạm đo (và GSMaP)
     mới là căn cứ quyết định.
   *Kết quả so bốn sản phẩm* (2026-11-04, lệnh `geoeyes landslide rainproducts`; cùng mùa và cùng các năm; cả bốn
   kho đủ ngày, trừ Final tháng 10–12/2025; `rain_f2/f2_products.md`):

   | so với IMERG Final | tổng lượng | tương quan | p99 | POD / FAR ≥ 100 mm | POD / FAR ≥ 200 mm | lệch tần suất ≥ 200 mm |
   |---|---|---|---|---|---|---|
   | IMERG Early | 1,03 | 0,93 | 1,01 | 0,72 / 0,29 | 0,60 / 0,58 | 1,4 |
   | GSMaP NRT | 0,90 | 0,80 | 1,21 | 0,67 / 0,54 | 0,58 / 0,80 | 2,9 |
   | GSMaP Gauge | 1,00 | 0,82 | 1,29 | 0,72 / 0,56 | 0,63 / 0,81 | 3,3 |

   Vùng lõi (Quảng Nam – Kon Tum) cho kết quả tương tự. Mưa lớn nhất trong vùng lõi vào ngày bão (mm/ngày):
   Ketsana 29/9/2009: Early 412, GSMaP NRT 397, Final 489; Podul 15/11/2013: Early **774**, GSMaP 484, Final 375;
   Molave 28/10/2020: Early 164, GSMaP **307**, Final 169.
   Nhận định:
   - GSMaP cho tổng lượng hơi thấp hơn nhưng **cực trị nhọn hơn**: số ô-ngày ≥ 200 mm gấp ba lần Final.
   - Trong từng ngày bão, các sản phẩm lệch nhau tới gấp đôi, và không cùng một chiều: bão Podul thì IMERG cao nhất,
     bão Molave thì GSMaP cao nhất.
   - Hai sản phẩm đã hiệu chỉnh theo trạm (Final, GSMaP Gauge) cũng lệch nhau nhiều như hai bản thô. Ở vùng núi
     này, "đã hiệu chỉnh theo trạm" không có nghĩa là "đúng".
   Hệ quả cho thiết kế:
   1. Ngưỡng **gắn với từng sản phẩm**: ngưỡng tính trên Final không được áp cho GSMaP, và ngược lại. Mỗi sản phẩm
      vận hành có hiệu chỉnh T riêng, hoặc được hiệu chỉnh phân vị về sản phẩm tham chiếu.
   2. Độ chênh giữa các sản phẩm là một phần đo được của độ bất định mưa quan trắc. Nó đi vào các thành viên mưa ở
      §5, không chỉ sai số bên trong một sản phẩm.
   3. Chưa chọn sản phẩm. IMERG Early vẫn là ứng viên (cùng thang đo với kho, ít báo nhầm hơn); GSMaP NRT là nguồn
      thứ hai (R6: độc lập khi một nhà cung cấp gặp sự cố, nhưng không độc lập về sai số, vì cả hai dùng chung các
      cảm biến vi ba thụ động GMI, AMSR2, SSMIS, MHS và ảnh hồng ngoại địa tĩnh) và nguồn mưa hằng giờ khi có bão. Việc chọn chờ phép so với trạm đo (bước 3), nay là
      đường găng của F2.
1. *Kho IMERG V07 theo ngày*, gồm Early (ứng viên vận hành) và Final (bản tham chiếu đã hiệu chỉnh theo trạm),
   2015–2025, vùng 104,5–110° Đ × 10,5–20° B (`landslide/satrain.py`, lệnh `geoeyes landslide rainarchive`). Dữ liệu
   được cắt vùng trên máy chủ qua OPeNDAP đám mây, khoảng 40 kB mỗi ngày. Ngày tính theo UTC (07–07 giờ Việt Nam),
   chỉ quy đổi ở nơi sử dụng (R13).
2. *GSMaP NRT và Gauge*: **xong** (2026-11-04): kho theo ngày 2015–2025, 2009 và 2013, không thiếu ngày nào
   (chạy `rainarchive` với `gsmap_nrt`, `gsmap_gauge`).
3. *Chất lượng*: trước hết so Early với Final (sai lệch, tương quan, cực trị theo cấp cường độ); sau đó so với trạm
   đo (trạm GHCN-D / GSOD, ít ở vùng núi; mạng KTTV nếu có). *Trùng nguồn (2026-11-05):* trạm GHCN-D / GSOD là đầu
   vào của GPCC và CPC, hai bộ dùng để hiệu chỉnh IMERG Final và GSMaP Gauge, còn CHIRPS dùng trực tiếp các trạm này;
   vì vậy chúng không phải phép kiểm tra độc lập cho các sản phẩm đó. Chỉ các trạm KTTV không chia sẻ lên GTS mới độc
   lập.
   *Trạm KTTV, kết quả đầu tiên (2026-11-05).* Nguồn: solieukttv.imech.info, bản sao của bên thứ ba đăng lại số liệu
   KTTV ("mang tính tham khảo, phục vụ nghiên cứu"). Số liệu được tải chậm, lịch sự (một phiên, nghỉ 4 s giữa các
   trạm, lưu đệm theo trạm) vào `cache/gauges/kttv_imech/`. Vùng lõi có 371 trạm trong danh sách, 232 trạm có số
   liệu mưa:
   - 31 trạm thủ công: tổng 6 giờ lúc 01/07/13/19 giờ địa phương, 2015–2025. Giá trị 19 giờ là phần còn lại của
     tổng ngày, và là chỗ duy nhất có giá trị âm.
   - 198 trạm tự động: theo giờ, **cộng dồn** từ 20 giờ địa phương, 2023–2025; đã lấy hiệu để ra tổng từng giờ.

   Ngày được dựng lại theo UTC (07–07 giờ địa phương). Kiểm tra độ trễ: tương quan cao nhất ở độ trễ 0 (0,71 với
   trạm tự động, 0,44 với trạm thủ công). Kiểm tra chất lượng:
   - bỏ các ngày có giá trị âm hoặc sụt không giải thích được;
   - bỏ 1 trạm trùng;
   - bỏ 2 trạm-ngày bị phép thử lân cận đánh dấu (≥ 150 mm trong khi trung vị của ≥ 3 trạm trong bán kính 15 km
     < 15 %).

   Còn lại 72.019 trạm-ngày ở 220 trạm, tháng 9–12, so với mưa vệ tinh tại ô chứa trạm:

   | so với trạm | tổng | tương quan | POD / FAR ≥ 100 mm | POD / FAR ≥ 200 mm | vệ tinh / trạm vào ngày trạm ≥ 100 mm (trung vị) |
   |---|---|---|---|---|---|
   | IMERG Early | 1,00 | 0,53 | 0,43 / 0,58 | 0,23 / 0,68 | 0,51 |
   | GSMaP NRT | 0,77 | 0,51 | 0,35 / 0,61 | 0,21 / 0,72 | 0,44 |
   | GSMaP Gauge | 0,85 | 0,52 | 0,41 / 0,61 | 0,26 / 0,72 | 0,50 |
   | IMERG Final | 0,92 | 0,56 | 0,42 / 0,55 | 0,17 / 0,55 | 0,52 |

   Các kết quả khác:
   - **Trung bình ô có ≥ 3 trạm** (giảm lệch giữa điểm và diện; 3.872 ô-ngày): tương quan 0,70–0,75; POD ≥ 100 mm
     0,36–0,53; tỷ số vệ tinh / trạm vào ngày mưa lớn 0,54–0,67.
   - **Theo độ cao**, bức tranh không đổi: dưới 200 m có 169 trạm, 200–600 m có 44 trạm, trên 600 m chỉ có 7 trạm.
   - **Ngày mưa lớn nhất toàn mạng:**
     - 2017-11-04: trung bình trạm 250 mm, các sản phẩm 136–196 mm;
     - 2018-12-09: trạm 233 mm, các sản phẩm 60–92 mm.
   - **Bão Molave, 2020-10-28:** trung bình trạm 55 mm (cao nhất 229 mm); GSMaP 95–101 mm, IMERG 53–63 mm.
   - **Riêng Trà My** (mưa địa hình): mọi sản phẩm chỉ cho khoảng một nửa tổng lượng mưa của trạm.

   Đọc kết quả:
   - (a) **Tổng mùa gần đúng** (0,77–1,00) nhưng **ngày mưa lớn bị giảm một nửa**. Sai số phụ thuộc cường độ mưa
     chứ không phải một hệ số cố định, nên nhân một hệ số duy nhất sẽ không sửa được.
   - (b) Ở quy mô điểm, không sản phẩm nào bắt được quá một phần tư số ngày ≥ 200 mm. Hơn một nửa số ngày ≥ 200 mm
     của chính sản phẩm là báo sai.
   - (c) IMERG Early không kém Final; GSMaP NRT thấp nhất.

   Hệ quả:
   - (1) R2 đã thành rủi ro thật, đo được.
   - (2) Ngưỡng phải khớp trên chính sản phẩm dùng khi vận hành, để một phần độ lệch nằm sẵn trong T. Mô hình sai
     số của mưa quan trắc phải **phụ thuộc cường độ** (§5).
   - (3) Bản thân số liệu trạm là một ứng viên đầu vào (trạm tự động theo giờ từ 2023), chờ nguồn chính thức.

   Giới hạn:
   - Bản sao này không phải dịch vụ chính thức của KTTV: chưa rõ giấy phép và độ trễ, nên chưa dùng được cho vận
     hành.
   - Trạm tự động mới có ba mùa số liệu, và có ít trạm trên 600 m.
   - Script đang nằm trong thư mục tạm của phiên. Cần chuyển vào `landslide/gauges.py`, kèm test, trước khi dùng ở
     F3.
4. *Độ trễ*: đo giờ có dữ liệu của từng ngày Early trong trọn một mùa (§8.4); trong mùa 2026, đo thời gian thực mỗi
   giờ (IMERG nửa giờ, GSMaP hằng giờ).
5. *ECMWF ENS*: kho TIGGE (từ 2006, dùng cho nghiên cứu) cho dự báo ngược 2015–2025, kho dữ liệu mở từ 2024 cho
   nguồn vận hành; hiệu chỉnh phân vị về sản phẩm quan trắc, gộp theo vùng và cấp cường độ.
6. *Phiếu dữ liệu* cho mọi đầu vào (§7).

## 10. Dữ liệu và quyết định cần từ chủ dự án

| Cần | Để làm gì | Phương án dự phòng |
|---|---|---|
| Bản đồ phân vùng 1:50.000 (VIGMR) cho Quảng Nam, Kon Tum, Thừa Thiên Huế | vùng nguy cơ của Điều 46, mốc so sánh, đối chiếu | dùng lớp của ta thay thế, ghi rõ là thay thế |
| Bản đồ địa chất 1:200.000 / 1:50.000 và đứt gãy | C4: biến dự báo quan trọng nhất đang thiếu | đường dạng tuyến từ DEM + đứt gãy GEM, ghi là đại lượng thay thế |
| Số liệu trạm mưa (KTTV), theo ngày, 2015–2025 — đường găng, cần đẩy ngay (2026-11-05); bản sao nghiên cứu (imech.info) đã cho 220 trạm để kiểm tra lần đầu (§9.1, bước 3), vẫn cần nguồn và giấy phép chính thức | mô hình sai số của sản phẩm mưa (F2) | trạm của tỉnh / radar của Trung tâm Dự báo KTTV quốc gia; trạm GHCN-D / GSOD (ít ở vùng núi, và không độc lập với IMERG Final, GSMaP Gauge, CHIRPS) |
| Hồ sơ sạt lở có ngày (VIGMR, các tỉnh, lưu trữ báo chí) | ngày-đơn vị dương (F1) | `vietnam.csv` + định ngày bằng Sentinel-2 |
| Ranh giới xã sau sắp xếp 2025 | đơn vị cảnh báo | ranh giới 2024, ánh xạ sang |
| Ngân sách cảnh báo người dùng chấp nhận (số cảnh báo sai mỗi mùa) | đặt ngưỡng xác suất cho các cấp | chủ dự án chọn, ghi trong F0 |
| Danh sách hội đồng thẩm định | A8 | chủ dự án tự duyệt, ghi rõ như vậy |
| Xác nhận điểm số (L, I) của sổ đăng ký rủi ro §8.7 | thứ tự ưu tiên phòng ngừa; ký ở F0 | điểm ban đầu trong §8.7 |
| Nơi vận hành: máy chủ đám mây (có máy dự phòng ở vùng khác) hay máy chủ đặt tại cơ quan | R1: mất điện, mất mạng trong bão; chi phí; quy định về dữ liệu | đề xuất: đám mây làm nơi chính, máy tại cơ quan làm dự phòng; máy trạm cá nhân không dùng để vận hành |
| Kênh phát tin tới xã (kênh chính thức của tỉnh, SMS, Zalo…) và người nhận | R15: bản tin phải đến được xã, có xác nhận đã nhận | hai kênh song song, danh sách người nhận do tỉnh cung cấp |
| ~~Tài khoản GSMaP (JAXA, miễn phí)~~ **đã có 2026-11-03** | sản phẩm mưa thứ hai, độ trễ 4 h (R6) | — |
| Điều khoản trách nhiệm và sử dụng | R20: sản phẩm chỉ mang tính tham khảo; cấp chính thức theo QĐ 18/2021 vẫn là căn cứ pháp lý | dùng câu này, ghi trong mọi bản tin và trong thẻ mô hình |

## 11. Rủi ro

- **Quá ít vụ sạt lở có ngày cho T** (rủi ro chính). Cách giảm:
  - định ngày vết sạt lở Sentinel-2 theo trận mưa;
  - gộp theo vùng với gộp một phần (tiên nghiệm phân cấp);
  - quy tắc Điều 46 làm phương án dự phòng luôn có sẵn.
- **Sai lệch báo cáo.** Báo cáo tập trung theo đường giao thông và theo thương vong, nên bản dự báo thực chất là dự báo
  sạt lở *được báo cáo*. Độ lớn của sai lệch được đo bằng hai cách:
  - số hạng sai lệch trong T;
  - các mùa Sentinel-2, vốn đầy đủ về không gian và không lệch theo đường.
- **Sai số mưa vệ tinh ở vùng núi.** Mưa vệ tinh đánh giá thấp mưa cực trị do địa hình. Cách giảm: so với trạm đo ở
  F2, tổ hợp sai số, và ngưỡng được tính trên chính sản phẩm dùng khi vận hành.
- **Chuyển giao.** Mô hình tính nhạy được huấn luyện ở Quảng Nam – Kon Tum. Ra ngoài vùng này, mức tin cậy là "thấp"
  cho tới khi có thêm danh mục địa phương (miền Bắc cần danh mục riêng; L8).
- **Sắp xếp tỉnh (2025).** Các khu vực trong Phụ lục XII ghi tên tỉnh trước sáp nhập. Cách ánh xạ đơn vị mới sang các
  khu vực phải được kiểm tra với mọi văn bản sửa đổi Quyết định 18.
- **Kho dự báo ngắn.** Dữ liệu mở ECMWF ENS ở 0,25° bắt đầu từ 2/2024 (hai mùa, 34 ngày-xã dương: quá ít cho A6).
  Vì vậy A6 được kiểm trên kho TIGGE của ECMWF ENS (từ 2006, dùng cho nghiên cứu) cho 2015–2025 (2026-11-05). Báo
  cáo ghi rõ số trường hợp làm căn cứ cho A6.
- **Dịch vụ dữ liệu thay đổi.** Các sản phẩm có thể đổi phiên bản, độ trễ hoặc cách truy cập (ví dụ Sentinel-1A ngừng
  năm 2026; ECMWF chuyển từ 0,4° sang 0,25° năm 2024). Mỗi phiếu dữ liệu ghi một phương án dự phòng, và lần rà soát
  sẵn sàng kiểm tra thông báo của mọi nhà cung cấp trước mùa.
- **Tinh chỉnh quá mức.** Bốn lớp chặn:
  - A1–A8 được chốt ở F0 (sửa một lần ngày 2026-11-05, trước mọi dự báo ngược);
  - dự báo ngược làm ngoài mẫu, ngưỡng các cấp chọn bên trong từng lượt;
  - giữ riêng một mùa và một tỉnh làm phép thử cuối;
  - mùa chạy bóng (F9) là phép thử sau cùng.

## 12. Tài liệu tham khảo

Xem bản tiếng Anh [`../../en/research/landslide-forecast-system.md`](../../en/research/landslide-forecast-system.md)
§12. Mọi DOI đã được kiểm tra trên Crossref ngày 2026-11-03. Bổ sung 2026-11-05: Ferro & Stephenson (2011), chỉ số
SEDI cho sự kiện hiếm (*Weather and Forecasting* 26, 699–713); kho TIGGE của ECMWF (dùng cho nghiên cứu). Văn bản pháp lý: Quyết định 18/2021/QĐ-TTg (Điều 46;
Phụ lục XII, Bảng 5–6), hiệu lực từ 01/7/2021, thay thế Quyết định 44/2014/QĐ-TTg.
