> Bản dịch tiếng Việt của [`docs/en/research/gnss-insar-calibration.md`](../../en/research/gnss-insar-calibration.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.

# Dùng GNSS (Nevada Geodetic Laboratory) để kiểm định và hiệu chỉnh chuỗi thời gian InSAR

> Ghi chú nghiên cứu, đồng thời mô tả phương pháp của `geoeyes gnss` (gói `geoeyes.validation.gnss`; trên ứng dụng
> web: Xử lý → Kiểm định → GNSS, và mục "Gắn vào GNSS" trên trang Phân tích chuyên đề).
> Trạng thái: **đã triển khai v1 ngày 2026-10-25**; kết quả trên các dự án thử nghiệm của GeoEyes nêu ở §6.
> Liên quan: [rainfall-insar-hazard.md](rainfall-insar-hazard.md) (cường độ nguy cơ cần tham chiếu ổn định);
> bản ghi quyết định ADR-025.

## Mục lục

1. [Câu hỏi](#1-câu-hỏi)
2. [Tổng quan](#2-tổng-quan)
3. [Dữ liệu: NGL](#3-dữ-liệu-ngl)
4. [Phương pháp (v1, đã triển khai)](#4-phương-pháp-v1-đã-triển-khai)
5. [Tham số](#5-tham-số)
6. [Kết quả trên các dự án GeoEyes](#6-kết-quả-trên-các-dự-án-geoeyes)
7. [Trả lời: GNSS có hiệu chỉnh được chuỗi InSAR không?](#7-trả-lời-gnss-có-hiệu-chỉnh-được-chuỗi-insar-không)
8. [Hạn chế](#8-hạn-chế)
9. [Trình tự nghiên cứu](#9-trình-tự-nghiên-cứu)
10. [Triển khai](#10-triển-khai)
11. [Tài liệu tham khảo](#11-tài-liệu-tham-khảo)

---

## 1. Câu hỏi

1. **Kiểm định.** Chuỗi InSAR có khớp với vị trí GNSS đo độc lập không, cả về tốc độ lẫn hình dạng?
2. **Hiệu chỉnh.** GNSS có hiệu chỉnh được chuỗi InSAR không? Cụ thể:
   - **tham chiếu** (InSAR chỉ tương đối, so với một điểm hoặc so với trung bình cảnh);
   - **mặt nghiêng (ramp)** bước sóng dài;
   - sai số **chung (common-mode)** theo từng ngày.
3. **Ứng dụng.** Kết quả có đủ tốt để đưa cường độ nguy cơ về nền ổn định không (ghi chú mưa – InSAR – nguy cơ,
   §4.3)?

## 2. Tổng quan

- **InSAR là phép đo tương đối.** InSAR chỉ đo một thành phần chuyển dịch, theo hướng nhìn của vệ tinh (LOS), so với
  một điểm hoặc vùng tham chiếu và so với một ngày tham chiếu.
  - Sai số quỹ đạo để lại các mặt nghiêng bước sóng dài, tăng dần theo khoảng cách (Fattahi & Amelung 2014).
  - Bản thân tham chiếu cũng có thể chuyển dịch. Với các sản phẩm GeoEyes tham chiếu vào *trung bình cảnh*, tốc độ
    bị lệch một lượng bằng âm của chuyển dịch trung bình toàn cảnh.
- **Hệ thống định vị vệ tinh toàn cầu (GNSS)** cho vị trí 3-D hằng ngày tại một điểm, trong hệ quy chiếu toàn cầu (ở
  đây là IGS20 / ITRF2020). Nhiễu ngày của GNSS gồm nhiễu trắng cộng nhiễu nhấp nháy (flicker), nên sigma vận tốc
  tính theo giả thiết nhiễu trắng là quá nhỏ (Mao et al. 1999; Williams et al. 2004). Tín hiệu năm làm lệch vận tốc
  ước tính trên khoảng thời gian ngắn (Blewitt & Lavallée 2002).
- **Phép chiếu.** Chuyển dịch ENU được chiếu lên LOS bằng vectơ đơn vị hướng từ mặt đất lên vệ tinh (Wright et al.
  2004).
- **Các cách kết hợp.** Các phương pháp kết hợp GNSS–InSAR đã công bố trải từ gắn tham chiếu đơn giản đến tích hợp
  hoàn toàn:
  - "GPS Imaging" nội suy tốc độ đứng GNSS thành bản đồ, chỉ dùng GNSS (Hammond et al. 2016; toàn cầu: Hammond et
    al. 2021). Hammond et al. (2018) kết hợp cách này với InSAR: GNSS làm khung quy chiếu, InSAR bổ sung chi tiết.
  - Tong et al. (2013) dùng GPS để loại bỏ / lọc / khôi phục (Remove / Filter / Restore) thành phần bước sóng dài;
    sau tích hợp, InSAR khớp với GPS trong phạm vi 1,5 mm/năm (độ lệch tuyệt đối trung bình).
  - Neely et al. (2020) hiệu chỉnh từng lần chụp bằng cGPS (GInSAR). Xu et al. (2021) lấy thành phần bước sóng dài
    từ GNSS và thành phần bước sóng ngắn từ InSAR.
  - Shen & Liu (2020) ước lượng đồng thời mặt nghiêng và độ lệch của InSAR.
  - Weiss et al. (2020) gắn trường vận tốc Sentinel-1 trên vùng Anatolia vào GNSS.
  - Với giao thoa điểm tán xạ bền vững (PSI) và sụt lún: Farolfi et al. (2019); tổng quan các nghiên cứu ở châu Âu:
    Del Soldato et al. (2021).
- **Vấn đề mốc trạm.** Ăng-ten GNSS và các điểm tán xạ bền vững (PS) quanh nó không phải cùng một vật thể: ăng-ten có
  thể đặt trên mái nhà, còn PS nằm trên công trình khác hoặc trên mặt đất (Dheenathayalan et al. 2016, 2018).
  - Đặt gương phản xạ góc (corner reflector) hoặc bộ phát đáp (transponder) ngay cạnh ăng-ten GNSS sẽ giải quyết
    được vấn đề này (Parker et al. 2017; Mahapatra et al. 2018).
  - Khi không có các thiết bị đó, phép so sánh dùng trung vị của các PS trong một bán kính và báo cáo kèm độ phân
    tán.
- **Mexico City.**
  - Thành phố lún với tốc độ tới khoảng 40 cm/năm: Cabral-Cano et al. (2008); Chaussard et al. (2014); Cigna &
    Tapete (2021); Solano-Rojas et al. (2020).
  - Thành phố có mạng cGNSS dày đặc (TLALOCNet, Cabral-Cano et al. 2018), nên là nơi thử nghiệm phù hợp nhất.
- **Hà Nội.** Dang et al. (2014) đã lập bản đồ sụt lún Hà Nội bằng ảnh ALOS.

## 3. Dữ liệu: NGL

Nevada Geodetic Laboratory (NGL, University of Nevada, Reno) xử lý số liệu các trạm GNSS trên toàn thế giới bằng
GipsyX. Từ tháng 8/2025, lời giải của NGL dùng hệ **IGS20**; các sản phẩm IGS14 không còn được cập nhật. NGL đề nghị
người dùng trích dẫn:

- Blewitt, Hammond & Kreemer (2018);
- DOI dữ liệu của từng trạm (ghi trên trang của trạm);
- Blewitt et al. (2016) nếu dùng vận tốc MIDAS.

| Dữ liệu | URL (chỉ dùng https; http thường bị chuyển hướng tới một máy chủ hỏng) |
|---|---|
| Danh sách trạm | `https://geodesy.unr.edu/NGLStationPages/DataHoldings.txt` (trạm, vĩ độ, kinh độ 0–360°, độ cao, XYZ, ngày đầu / ngày cuối, các lời giải) |
| Bước nhảy do thay thiết bị và do động đất | `https://geodesy.unr.edu/NGLStationPages/steps.txt` |
| Vị trí hằng ngày | `https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/IGS20/<SITE>.tenv3` |
| Vận tốc MIDAS | `https://geodesy.unr.edu/gps_timeseries/IGS20/midas/midas.IGS.txt` (cột 9–11: vận tốc E, N, U tính bằng m/năm; cột 12–14: sigma tương ứng) |

**tenv3** gồm 23 cột, mô tả trong `gps_timeseries/readmes/README_tenv3.txt`: trạm, ngày, năm thập phân, MJD, tuần và
ngày GPS, kinh tuyến tham chiếu, tiếp đến là các toạ độ đông, bắc và lên.

- Mỗi toạ độ gồm phần nguyên và phần lẻ (m) trong một hệ cục bộ; phần nguyên chỉ được đặt lại khi có bước nhảy lớn
  hơn 10 m.
- Sau đó là chiều cao ăng-ten, các sigma, các hệ số tương quan, rồi vĩ độ, kinh độ và độ cao danh định. Kinh độ nhỏ
  hơn −180 được quy đổi về khoảng chuẩn (−254,16 = 105,84° E).

**Các trạm trong khu vực các dự án thử nghiệm** (theo `DataHoldings.txt`, ngày 2026-10-25):

| Khu vực | Trạm | Dữ liệu | Trùng thời gian với sản phẩm |
|---|---|---|---|
| Hà Nội | **HUMG** (21.072 N, 105.774 E) | 2024-01 → 2026-09 | Hanoi S1 2025-10 → 2026-10 |
| Hà Nội | **JNAV** (21.005 N, 105.844 E) | 2014-01 → 2026-09, có gián đoạn; dời vị trí tháng 10/2025 | Hanoi S1; Hanoi CSK chỉ trong năm 2014 (2 lần chụp) |
| Hà Nội | HNOI, HN_0, SIVN, VN3P, TEC0 | kết thúc 2016–2021 | không |
| Mexico City | **MMX1** (19.432 N, 99.068 W) | 2008-04 → 2026-10 | Mexico S1 2024-05 → 2024-10 |
| Mexico City | ICMX, MXTX | đến 2026-01 / 2025-02 | ngoài phạm vi sản phẩm S1 |
| Mexico City | khoảng 15 trạm khác (UNIP, TNGF, UTUL, MXTM, …) | kết thúc trước 2024 | không |

## 4. Phương pháp (v1, đã triển khai)

### 4.1 Chọn trạm và làm sạch số liệu

Chọn các trạm trong `DataHoldings.txt` nằm trong phạm vi sản phẩm và có số liệu trong giai đoạn của sản phẩm. Vị trí
hằng ngày của từng trạm trong giai đoạn này (±30 ngày) được làm sạch như sau:

1. **Giá trị ngoại lai.** Với từng thành phần, loại các ngày lệch quá 5 sigma bền vững (MAD) so với trung vị trượt
   15 ngày.
2. **Phân đoạn.** Chuỗi được cắt tại:
   - các lần thay thiết bị do NGL ghi nhận (`steps.txt`, loại 1);
   - các bước nhảy giữa hai ngày liên tiếp vượt max(15 mm theo phương ngang / 30 mm theo phương đứng, 5 σ).
   Loại bỏ các đoạn ngắn hơn 30 ngày.
3. **Nối lại.** Các đoạn được nối lại bằng một xu thế tuyến tính chung và một độ lệch riêng cho mỗi đoạn.
   - Nhờ vậy giữ được tốc độ của trạm đã dời vị trí nhưng vẫn mang tên cũ. Tháng 10/2025, JNAV dời đi khoảng 250 m
     và thay đổi 11 m về độ cao, với các bước nhảy ngày 2025-10-12 và 2025-10-27.
   - Cách này giả định hai mốc trạm chuyển dịch như nhau; kết quả có ghi rõ giả định này.

### 4.2 Ghép cặp InSAR và GNSS

- **InSAR.** Lấy chuỗi trung vị của các điểm nằm trong bán kính `radius_m` (100 m) quanh ăng-ten, cần ít nhất
  `min_points` (5) điểm. Độ phân tán giữa các điểm được lưu lại.
- **GNSS.** Lấy trung bình các vị trí đã làm sạch trong khoảng ±`window_days` (3) ngày quanh mỗi ngày chụp InSAR.
- **Phép chiếu.** Chiếu GNSS lên vectơ đơn vị LOS trung vị **l** (mặt đất → vệ tinh) của các điểm đó, theo hai
  cách:
  - **full (toàn phần):** d = e·l_e + n·l_n + u·l_u, tức toàn bộ chuyển dịch trong IGS20. Đại lượng này gồm cả
    chuyển động mảng kiến tạo, ở Hà Nội khoảng 31 mm/năm về phía đông (mảng Sunda), vốn không có trong sản phẩm InSAR
    tương đối.
  - **vertical (thẳng đứng)** (mặc định): d = u·l_u. Trong phạm vi một cảnh, chuyển dịch ngang được coi là chuyển
    động của mảng; chuyển động này đồng nhất nên đã nằm trong tham chiếu InSAR. Đại lượng được so sánh và dùng để gắn
    là chuyển dịch thẳng đứng cục bộ, cũng chính là đại lượng cần cho bài toán sụt lún.
  - *Lưu ý (2026-11-05):* giả định này không đúng ở Mexico City. Trong thời kỳ S1, MMX1 dịch +14,4 E / −3,3 N
    mm/năm, so với −6,6 / +5,0 theo MIDAS: dị thường hướng đông khoảng 21 mm/năm, tức ≈ −14 mm/năm theo LOS
    (l_e −0,69), lớn hơn mục tiêu 10 mm/năm. Chuyển động mảng dù đồng nhất cũng không phải hằng số theo LOS, vì **l**
    thay đổi trên bề rộng dải quét. Xem §8.3.
- **Mốc 0 chung.** Đưa cả hai chuỗi về cùng một mốc 0 (trung bình của từng chuỗi trên các ngày chung).

**Thống kê** (chỉ tính trên các ngày chung):

- tốc độ InSAR và GNSS (OLS) cùng hiệu của chúng, v_GNSS − v_InSAR;
- RMSE của hiệu;
- RMSE sau khi loại xu thế tuyến tính của hiệu (mức khớp về hình dạng);
- hệ số tương quan;
- tốc độ MIDAS (tính trên toàn bộ chuỗi, bền vững) chiếu theo cùng cách, và hiệu của nó so với InSAR.

### 4.3 Hiệu chỉnh và kiểm tra hiệu chỉnh

Số hiệu chỉnh cộng vào chuỗi LOS của InSAR có ba dạng:

- **offset:** Δv = trung bình của (v_GNSS − v_InSAR) trên các trạm, cộng vào mọi điểm dưới dạng Δv·t. Dạng này hiệu
  chỉnh tốc độ của tham chiếu.
- **plane:** Δv = a + b·x + c·y, khớp theo các trạm (cần ít nhất 3 trạm). Dạng này hiệu chỉnh thêm cả mặt nghiêng.
- **epoch:** c(t) = trung vị hiệu giữa hai chuỗi trên các trạm. Đây là hiệu chỉnh sai số chung theo từng ngày, như
  trong GInSAR (Neely et al. 2020), nhưng sẽ đưa nhiễu ngày của GNSS vào mọi điểm.

Tốc độ GNSS (`gnss_rate`) lấy từ một trong hai nguồn:

- `window`: tốc độ trong giai đoạn InSAR. Cách này bám theo các thay đổi, chẳng hạn sụt lún đang tăng tốc.
- `midas`: tốc độ dài hạn, bền vững của NGL. Trên các giai đoạn ngắn, tốc độ này ít bị tín hiệu mùa làm lệch hơn,
  nhưng sẽ sai ở nơi chuyển dịch đã thay đổi.

**Kiểm tra chéo bỏ-một (leave-one-out).** Khi có từ hai trạm trở lên, mỗi trạm được dự đoán bằng phép hiệu chỉnh lập
từ các trạm còn lại. RMS của GNSS − InSAR tại các trạm bị bỏ ra, trước và sau hiệu chỉnh, là thước đo khách quan cho
hiệu quả của hiệu chỉnh *ở nơi không có trạm*. Nếu chỉ có một trạm thì không kiểm tra được phép gắn, và kết quả ghi
rõ điều này.

**Nguy cơ.** Với `[postprocess.hazard] gnss_tie = true`, số hiệu chỉnh được cộng vào chuỗi của các ô trước khi chiếu
và xếp lớp. Khi đó tham chiếu của lần chạy phân tích nguy cơ là "GNSS (stations)".

## 5. Tham số

Đặt trong mục `[validation.gnss]` của `project.toml`, qua `geoeyes gnss --set key=value`, hoặc trên biểu mẫu của ứng
dụng web.

| Khoá | Mặc định | Lý do |
|---|---|---|
| `radius_m` | 100 | Vài PS quanh ăng-ten với mật độ điểm của Sentinel-1 / CSK; đủ nhỏ để vẫn nằm trong cùng một khối nhà |
| `min_points` | 5 | Đủ cho một trung vị bền vững |
| `window_days` | 3 | Số ngày GNSS lấy trung bình quanh một ngày chụp SAR; một tuần đủ giảm nhiễu ngày mà không làm trơn tín hiệu mùa |
| `min_epochs` | 6 | Số ngày chung tối thiểu để tính tốc độ |
| `los_mode` | vertical | §4.2: chuyển động mảng đồng nhất nên triệt tiêu cùng tham chiếu InSAR |
| `calibration` | offset | Ổn định khi chỉ có 1–2 trạm; `plane` cần ít nhất 3 trạm |
| `gnss_rate` | window | Bám theo chuyển dịch trong giai đoạn InSAR (Mexico City đang tăng tốc) |
| `stations`, `exclude` | all, none | Chọn hoặc loại trạm, ví dụ ăng-ten đã dời vị trí hoặc mốc trạm đặt trên mái nhà |

## 6. Kết quả trên các dự án GeoEyes

Mọi lần chạy: ngày 2026-10-25, tham số mặc định, phép chiếu thẳng đứng.

### 6.1 Mexico City: Sentinel-1 asc 078, 2024-05 → 2024-10, trạm MMX1

| | Giá trị |
|---|---|
| Số điểm trong bán kính 100 m · số ngày chung | 66 (khoảng cách trung vị 64 m) · 14 |
| GNSS trong giai đoạn (E / N / U) | +14.4 / −3.3 / **−364.3 mm/năm** |
| MIDAS 2008–2026 (E / N / U) | −6.6 / +5.0 / −265.0 mm/năm |
| Tốc độ InSAR (LOS) | −128.1 ± 10.8 mm/năm |
| GNSS thẳng đứng chiếu lên LOS | −258.2 ± 3.2 mm/năm |
| **GNSS − InSAR** | **−130.1 mm/năm** |
| RMSE · RMSE sau khi loại xu thế · hệ số tương quan | 18.0 mm · **5.3 mm** · **0.96** |

**Diễn giải.**

- **Hình dạng.** Sau khi loại chênh lệch tốc độ, hai chuỗi khớp nhau rất tốt: phần dư 5 mm, hệ số tương quan 0,96.
  InSAR bám sát chuyển dịch GNSS trong suốt sáu tháng.
- **Tốc độ.** Tốc độ theo LOS lệch −130 mm/năm. Sản phẩm tham chiếu vào trung bình cảnh, mà phần lớn cảnh đang lún,
  nên bản thân tham chiếu cũng lún theo. Đây đúng là độ lệch đã dự báo trong ghi chú mưa – InSAR (§7 của ghi chú
  đó).
- **Tốc độ dài hạn.** MIDAS cho −265 mm/năm tính trên 18 năm, nhưng riêng năm 2024 trạm lún −364 mm/năm. Dùng tốc độ
  dài hạn ở đây sẽ sai, vì vậy `window` được chọn làm mặc định.

**Phân tích nguy cơ khi có và không gắn vào GNSS (ô 100 m).**

| | Tham chiếu của sản phẩm (trung bình cảnh) | Gắn vào GNSS (MMX1, offset) |
|---|---|---|
| Số ô chuyển dịch *lên* (gắn cờ, không xếp lớp) | 19 087 | 531 |
| Tốc độ lún trung vị · P90 · P99 | n/a (tương đối) | **159 · 319 · 378 mm/năm** |
| Sụt lún: cao / rất cao | 113.9 / 10.7 km² | 394.7 / 28.5 km² |
| Sụt lún: rất thấp | 289.1 km² | 9.6 km² |

Khi gắn vào GNSS, tốc độ nằm trong khoảng đã công bố cho Mexico City (tới khoảng 40 cm/năm; Cigna & Tapete 2021;
Chaussard et al. 2014). Góc biến dạng không phụ thuộc vào tham chiếu nên giữ nguyên.

Phép gắn chỉ dựa trên một trạm và chưa được kiểm tra độc lập. ICMX và MXTX cũng có số liệu năm 2024 nhưng nằm ngoài
phạm vi sản phẩm này; một sản phẩm phủ cả hai trạm đó sẽ cho phép kiểm tra bỏ-một.

*Đã lỗi thời (2026-11-05):* phép kiểm tra đó (G3.1, §9.1) cho độ lệch từng trạm là −79 / −145 / −23 mm/năm và sai số
bỏ-một tại MMX1 là −94 mm/năm. Phép gắn một trạm, và diện tích nguy cơ ở bảng trên, không đáng tin.

### 6.2 Hà Nội: Sentinel-1 desc 091, 2025-10 → 2026-10, các trạm HUMG và JNAV

| Trạm | Số điểm · số ngày | InSAR (LOS) | GNSS thẳng đứng (LOS), trong giai đoạn | GNSS − InSAR | RMSE sau loại xu thế · tương quan | MIDAS thẳng đứng (LOS) |
|---|---|---|---|---|---|---|
| HUMG | 145 · 16 | +3.1 ± 2.0 | +9.1 ± 6.2 | +6.0 | 6.6 mm · 0.27 | −1.7 (2.7 năm) |
| JNAV (2 đoạn) | 159 · 21 | −3.3 ± 1.9 | +12.5 ± 4.6 | +15.8 | 7.0 mm · −0.33 | +0.1 (12.7 năm, hai mốc trạm) |

| Hiệu chỉnh | Độ lệch | RMS bỏ-một trước → sau |
|---|---|---|
| offset, tốc độ GNSS trong giai đoạn | +11.0 mm/năm | 12.0 → 9.8 mm/năm |
| offset, tốc độ MIDAS | −0.7 mm/năm | 4.1 → **8.1** mm/năm (kém hơn) |

**Diễn giải.**

- Chuyển dịch quanh cả hai trạm đều nhỏ (vài mm/năm). Ở mức đó, một năm số liệu GNSS thành phần đứng quá nhiễu và
  chịu ảnh hưởng mùa quá mạnh để so sánh:
  - sigma tốc độ 5–6 mm/năm dựa trên giả thiết nhiễu trắng nên quá lạc quan;
  - gió mùa tạo ra tín hiệu năm lớn theo phương đứng, một phần do tải trọng thuỷ văn;
  - tốc độ tính trên một năm phụ thuộc vào pha của tín hiệu đó (Blewitt & Lavallée 2002).
- Hệ số tương quan thấp (0,27 và −0,33): không có tín hiệu chung nào để khớp. Phần dư ở cả hai trạm là 6–7 mm.
- So với tốc độ MIDAS dài hạn, InSAR chưa hiệu chỉnh đã khớp trong khoảng 4 mm/năm (RMS). Gắn vào một trạm rồi dự
  đoán trạm kia lại làm sai số tăng gấp đôi.
- **Ở Hà Nội hiện nay, GNSS chưa cải thiện được InSAR, và không nên gắn sản phẩm vào GNSS.** Cần có một trong hai
  điều kiện:
  - từ hai năm số liệu GNSS và InSAR trở lên, để khớp tốc độ kèm các số hạng năm; hoặc
  - thêm trạm.

**Hanoi CSK (2011–2014).** Không so sánh được: JNAV chỉ có số liệu từ năm 2014 và chỉ trùng 2 ngày với chồng ảnh.

## 7. Trả lời: GNSS có hiệu chỉnh được chuỗi InSAR không?

Có, đối với tham chiếu và tốc độ của tham chiếu, với ba điều kiện:

1. **Sai số tham chiếu của InSAR lớn hơn độ bất định của tốc độ GNSS.**
   - Mexico City: độ lệch tham chiếu 130 mm/năm, trong khi tốc độ GNSS chính xác tới vài mm/năm. Phép gắn có tác
     dụng quyết định, và mức khớp về hình dạng (5 mm, r = 0,96) cho thấy phần sai còn lại chủ yếu là độ lệch tham
     chiếu.
     *Đã lỗi thời (2026-11-05):* với 3 trạm (G3.1, §9.1) độ lệch không phải hằng số (−79 / −145 / −23 mm/năm; sai số
     bỏ-một tại MMX1 −94 mm/năm), nên phép gắn MMX1 không có tác dụng quyết định. Diện tích nguy cơ ở §6.1 và lớp Đã
     hiệu chỉnh (§7.3) đều dựa trên phép gắn này.
   - Hà Nội, một năm số liệu: độ lệch chỉ vài mm/năm, còn độ bất định GNSS là 5–6 mm/năm. Phép gắn chỉ thêm nhiễu.
2. **GNSS được chiếu nhất quán với đại lượng mà InSAR đo.**
   - Phép chiếu thẳng đứng loại bỏ chuyển động mảng mà InSAR tương đối không nhìn thấy. Ở Hà Nội, phép chiếu 3-D toàn
     phần cộng thêm 16–19 mm/năm chuyển động mảng Sunda vào LOS (GNSS − InSAR: +24,9 thay vì +6,0 tại HUMG, +32,1
     thay vì +15,8 tại JNAV).
   - Trạm đã dời vị trí cần được xử lý theo từng đoạn.
3. **Hiệu chỉnh được kiểm tra ở nơi không có trạm.** Kiểm tra bỏ-một cần ít nhất hai trạm; hiệu chỉnh mặt nghiêng cần
   ít nhất ba. Với một trạm, phép gắn hợp lý nhưng chưa được kiểm chứng.

**Hiệu chỉnh theo từng lần chụp** (sai số chung) đã được triển khai. Khi có ít hơn khoảng 3–5 trạm phân bố đều, cách
này đưa nhiễu ngày của GNSS vào mọi điểm, nên không được chọn làm mặc định.

### 7.1 Có dùng được phương trình hiệu chỉnh lập ở Mexico City cho Việt Nam không? (2026-10-30)

**Vì sao cần hỏi.** Phần lớn trạm NGL ở Việt Nam đã ngừng hoạt động trong khoảng 2019–2021. Không trạm nào phủ sản
phẩm TP.HCM hiện tại (2025–2026). Nếu phương trình hiệu chỉnh chuyển giao được, có thể gắn các sản phẩm ở Việt Nam
mà không cần trạm tại chỗ.

**Thí nghiệm.** Năm cặp trạm–sản phẩm, phép chiếu thẳng đứng, `gnss_rate = window`:

- MMX1 trên sản phẩm S1 asc 078 của Mexico City;
- HUMG và JNAV trên mỗi sản phẩm S1 Hà Nội, quỹ đạo lên asc 128 và quỹ đạo xuống desc 091.

Hai dạng quan hệ được lập ở nguồn rồi áp dụng sang đích:

- **M1, chỉ có độ lệch:** g(t) = i(t) + Δv·t. Đây là phương trình hiện đang dùng.
- **M2, độ lệch kèm hệ số tỉ lệ:** g(t) = k·i(t) + Δv·t + c. Hệ số k (độ khuếch đại của quá trình xử lý) là số hạng
  duy nhất không phụ thuộc cảnh ảnh.

Mã nguồn thí nghiệm: [code/gnss_transfer.py](../../en/research/code/gnss_transfer.py).

| Nguồn → đích | Dạng | Sai lệch tốc độ tại các trạm đích (mm/năm) | RMSE chuỗi (mm) |
|---|---|---|---|
| không hiệu chỉnh → HN quỹ đạo lên | – | 7,6 | 7,1 |
| **Mexico → HN quỹ đạo lên** | M1 | **134,0** | 39,6 |
| Mexico → HN quỹ đạo lên | M2 | 265,3 | 77,4 |
| HN quỹ đạo xuống → HN quỹ đạo lên | M1 | 3,4 | 6,8 |
| không hiệu chỉnh → HN quỹ đạo xuống | – | 10,9 | 7,7 |
| **Mexico → HN quỹ đạo xuống** | M1 | **137,4** | 41,2 |
| Mexico → HN quỹ đạo xuống | M2 | 270,2 | 80,0 |
| HN quỹ đạo lên → HN quỹ đạo xuống | M1 | 4,9 | 7,0 |

**Đọc kết quả.**

1. **Phương trình của Mexico không chuyển giao được.** Áp sang Hà Nội, sai số lớn gấp khoảng 15 lần so với không
   hiệu chỉnh.
   - Hệ số duy nhất của phương trình, Δv = −126 mm/năm, chính là chuyển động của điểm tham chiếu trong sản phẩm
     Mexico. Điểm tham chiếu đó là trung bình toàn cảnh; tốc độ trung bình của sản phẩm là +0,1 mm/năm, đúng như
     vậy.
   - Do đó Δv đo mức lún chung của cả cảnh Mexico City. Đó là đặc trưng của cảnh ảnh, không phải của cảm biến hay
     của quá trình xử lý, nên không mang thông tin gì về một thành phố khác.
2. **Không học được hệ số khuếch đại của quá trình xử lý từ Mexico.** Dạng M2 cần tín hiệu không phải đường thẳng.
   - Tại MMX1, lún gần như tuyến tính trong sáu tháng, nên i(t) và t gần như cộng tuyến (số điều kiện khoảng 500).
   - Hệ số k = −0,01 ± 0,09 không có ý nghĩa: phép khớp chỉ thay chuỗi InSAR bằng một đường thẳng.
   - Muốn xác định được hệ số tỉ lệ thì cần nhiều trạm có tốc độ khác nhau, hoặc chuyển dịch phi tuyến.
3. **Chuyển giao được trong cùng một thành phố.** Hiệu chỉnh của sản phẩm Hà Nội quỹ đạo lên áp sang sản phẩm quỹ
   đạo xuống, và ngược lại, đều giảm sai lệch tốc độ (10,9 → 4,9 và 7,6 → 3,4 mm/năm).
   - Hai sản phẩm cùng thành phố, cùng thời kỳ và cùng kiểu tham chiếu (trung bình cảnh), nên vùng tham chiếu của
     chúng chuyển động giống nhau.
   - Mức cải thiện cỡ sigma tốc độ GNSS (3,5–6 mm/năm), nên mới là gợi ý, chưa phải kết luận chắc chắn.
4. **Mức sai số chuyển giao được.** Phần dư sau khi bỏ xu hướng là 5–8 mm ở mọi cặp, cả Mexico lẫn Hà Nội. Đây là
   nhiễu của trung vị PS Sentinel-1 so với GNSS theo ngày, dùng được làm độ bất định tiên nghiệm cho các sản phẩm
   không có trạm.

**Trả lời.** Không: phương trình hiệu chỉnh không chuyển giao được giữa các địa điểm. Hệ số của nó là chuyển động của
điểm tham chiếu trong sản phẩm, vốn thuộc riêng một cảnh ảnh. Những gì chuyển giao được:

- **phương pháp**: phép chiếu thẳng đứng, xử lý trạm dời vị trí, tốc độ theo cửa sổ thời gian, kiểm tra bỏ-một;
- **mô hình sai số**: 5–8 mm mỗi lần chụp;
- **trong cùng một thành phố**, hiệu chỉnh giữa các sản phẩm cùng thời kỳ và cùng kiểu tham chiếu.

**Với Việt Nam khi không có trạm đang hoạt động, có ba hướng:**

1. **Hiệu chỉnh tại chỗ bằng dữ liệu lịch sử (G7).** Xử lý Sentinel-1 TP.HCM giai đoạn 2017–2019, khi các trạm HCMC,
   XC03, GOCO, LTHA, BTRE và VUNT còn hoạt động, rồi hiệu chỉnh và kiểm tra bỏ-một với 3–6 trạm.
   - Sau đó thử chuyển giao theo thời gian sang 2025–2026, dùng những vùng tham chiếu không đổi giữa hai giai đoạn,
     chẳng hạn cùng các công trình ổn định.
   - Chuyển giao trong cùng một thành phố thì có cơ sở; giữa hai thành phố thì không.
2. **Tham chiếu ổn định thay cho trung bình cảnh.** Chọn `reference_bbox` trên nền đất đã biết là ổn định, như thềm
   Pleistocen hoặc công trình móng cọc. Khi đó sản phẩm gần như không cần gắn GNSS, vì Δv tự gần bằng 0.
3. **Trạm mới hoặc gương phản xạ góc.** Gương đặt cạnh ăng-ten GNSS (G4), hoặc một trạm liên tục ở mỗi thành phố.

### 7.2 Hiệu chỉnh lịch sử cho TP.HCM và việc dùng nó cho 2025–2026 (G7, 2026-10-31)

**Dữ liệu.** Sentinel-1 quỹ đạo xuống 018 trên TP.HCM, 11/2017 → 09/2019: 46 ảnh, 2,3 triệu điểm, tham chiếu là
trung bình cả cảnh (dự án `hcm_hist_des`). Ba trạm NGL có số liệu trong giai đoạn này và có điểm InSAR trong bán kính
100 m: HCMC, LTHA và XC03 (GOCO, BTRE và VUNT không có phần chồng dùng được). Script:
[code/gnss_g7.py](../../en/research/code/gnss_g7.py).

| Trạm | InSAR (thẳng đứng, mm/năm) | GNSS (mm/năm) | Chênh lệch | Số kỳ |
|---|---|---|---|---|
| HCMC | +0,5 | +6,9 ± 2,7 | +6,4 | 31 |
| LTHA | +2,2 | −0,7 ± 6,3 | −2,9 | 12 |
| XC03 | +0,1 | +5,5 ± 2,9 | +5,4 | 11 |

**Kiểm định bỏ-một-trạm** (sai lệch tốc độ tại trạm bị bỏ ra, RMS trên cả ba trạm):

| Mô hình | HCMC | LTHA | XC03 | RMS (mm/năm) |
|---|---|---|---|---|
| không hiệu chỉnh | +6,4 | −2,9 | +5,4 | 5,1 |
| M1, độ lệch | +5,2 | −8,8 | +3,6 | **6,3** |
| M2, độ lệch và tỉ lệ | +4,5 | −6,9 | −0,7 | 4,8 |

**Dùng cho 2025–2026** (dự án `hcm_test_des`, cùng vệt quỹ đạo, phạm vi nhỏ hơn ở nội thành). Hai sản phẩm được nối
qua độ lệch của 2017–2019 (+2,97 mm/năm) và chênh lệch giữa trung bình cả cảnh của hai phạm vi (+0,55 mm/năm).
Trên 243.894 ô 20 m chung của hai sản phẩm:

- thay đổi tốc độ 2025 − 2017 có trung vị −1,3 mm/năm (IQR 6,4);
- trên các ô ổn định trong 2017–2019 (|v| < 2 mm/năm), thay đổi là **+3,4** mm/năm;
- bản đồ 2025–2026 sau khi nối có trung vị **+3,9** mm/năm, tức là nội thành TP.HCM đang trồi lên.

**Nhận xét.**

1. **Ba trạm không đủ để xác định một độ lệch.** Chênh lệch giữa chúng (−2,9 đến +6,4 mm/năm) còn lớn hơn chính độ
   lệch. Độ phân tán này bằng cỡ sai số tốc độ GNSS (2,7–6,3 mm/năm, vì chuỗi 2017–2019 ngắn). Độ lệch khớp trên cả
   ba trạm, +3,0 mm/năm, có sai số chuẩn khoảng 2,9 mm/năm: không khác 0.
2. **Độ lệch làm trạm bị bỏ ra kém đi.** M1 tăng RMS bỏ-một-trạm từ 5,1 lên 6,3 mm/năm. M2 giảm được một chút,
   nhưng chỉ vì thay InSAR bằng một đường thẳng: hệ số k là +0,05, −0,33 và −0,42, không có ý nghĩa, giống §7.1.
3. **Dùng theo thời gian cho ra bản đồ vô lý.** Nội thành trồi lên trái với mọi công bố về lún ở TP.HCM. Các ô ổn
   định trong 2017–2019 lại thành trồi 3 mm/năm. Phép nối cộng độ lệch 2017–2019 (vốn không có ý nghĩa thống kê) vào
   một tham chiếu (trung bình cả cảnh) mà chuyển động của nó thay đổi theo thời gian và theo phạm vi.

**Trả lời.** Các trạm 2017–2019 không ủng hộ phép hiệu chỉnh nào, và cũng không có phép hiệu chỉnh nào dùng được cho
2025–2026. Các sản phẩm TP.HCM giữ tham chiếu là trung bình cả cảnh, kèm ghi rõ độ bất định của tham chiếu: khoảng
±3 mm/năm, bằng độ phân tán của ba trạm. Muốn nối với GNSS thì vẫn là các phương án 2 và 3 ở trên: một vùng tham chiếu
ổn định (thềm Pleistocene hoặc công trình móng cọc), hoặc gương phản xạ góc và một trạm liên tục mới.

### 7.3 Hai cảm biến trên Mexico City: nối Capella vào Sentinel-1 (2026-11-01)

**Câu hỏi.** Mexico City có hai sản phẩm cho cùng một bức tranh lún nhưng vận tốc khác nhau:

- sản phẩm Capella (`mexico_capella` v4): quỹ đạo lên, nhìn trái, 18 ảnh từ 26/6 đến 15/8/2024, 241.165 điểm trên
  6 × 6 km ở Iztapalapa;
- sản phẩm Sentinel-1 (`mexico_s1` v7): quỹ đạo lên 078, nhìn phải, 16 ảnh từ 3/5 đến 30/10/2024.

Trong vùng sản phẩm Capella không có trạm NGL nào. Vì sao hai sản phẩm khác nhau, và có hiệu chỉnh được Capella
không?

**So sánh** trên 1.734 ô 100 m chung (trung vị mỗi ô):

| Cách so | Capella theo S1 | Tương quan |
|---|---|---|
| LOS, mỗi sản phẩm trong thời kỳ của nó | 1,29 × S1 + 36 mm/năm | 0,89 |
| Tốc độ S1 chỉ trong thời kỳ Capella (20/6 → 19/8) | 1,15 × S1 − 26 mm/năm | 0,89 |
| Như trên, cả hai đổi sang thẳng đứng (v / los_u) | **1,07** × S1 | 0,89 |

**Diễn giải.** Hai sản phẩm khớp nhau về không gian (tương quan 0,89). Chúng khác nhau ở ba điểm, đều đã biết rõ:

1. **Thời kỳ.** Capella chỉ có 50 ngày giữa mùa mưa. Trên vùng chung, tốc độ S1 trong đúng những ngày đó cao hơn tốc
   độ 6 tháng khoảng 54 mm/năm. Trạm MMX1 cũng cho thấy điều này: lún −364 mm/năm trong thời kỳ S1, so với
   −265 mm/năm theo MIDAS 18 năm. Lún ở Mexico City nhanh hơn vào mùa mưa.
2. **Hướng nhìn.** LOS của S1 (đông/bắc/đứng) là (−0,69, −0,15, 0,71), của Capella là (+0,47, −0,46, 0,76). Độ nhạy
   theo phương đứng chênh 7%, còn chuyển động theo hướng đông bị chiếu với dấu ngược nhau. Khi đổi sang thẳng đứng
   trong cùng thời kỳ, hệ số chỉ còn 1,07.
3. **Tham chiếu.** Mỗi sản phẩm lấy trung bình cảnh của chính nó làm mốc 0: S1 là cả lòng chảo, Capella là 6 × 6 km.
   Đây cũng là lý do S1 lệch xa MMX1. Hình dạng chuỗi khớp (tương quan 0,96, 5,2 mm sau khi bỏ xu hướng), nhưng tốc
   độ chênh −126 mm/năm, vì chính "trung bình cảnh" mà InSAR coi là đứng yên cũng đang lún.

**Phép nối.** Sản phẩm không có trạm có thể lấy hiệu chỉnh từ một sản phẩm khác cùng vùng
(`geoeyes.validation.tie`):

- tốc độ của sản phẩm tham chiếu chỉ được tính trong các ngày của sản phẩm đích;
- cả hai đổi sang tốc độ thẳng đứng;
- trung vị trên các ô chung của (tham chiếu − đích) là độ hiệu chỉnh, rồi chiếu ngược lại về LOS của sản phẩm đích.

Nếu sản phẩm tham chiếu có hiệu chỉnh GNSS riêng thì hiệu chỉnh đó được áp trước. Nhờ vậy sản phẩm đích được nối với
GNSS thông qua nó. Hệ số khuếch đại giữa hai sản phẩm chỉ được báo, không hiệu chỉnh: nó đến từ khác biệt thời kỳ và
hình học, không phải lỗi của sản phẩm nào, nên ép nó theo một trạm sẽ làm sai cả bản đồ.

| Nối Capella vào S1 v7 | Giá trị |
|---|---|
| Ô 100 m chung | 1.731 |
| Tương quan, hệ số (thẳng đứng) | 0,888, 1,07 |
| Hiệu chỉnh | **−109,0 mm/năm theo LOS** (−144,3 thẳng đứng), thông qua GNSS MMX1 |
| Độ phân tán giữa các ô (1,48 × MAD) | ±49,6 mm/năm |
| Không dùng hiệu chỉnh GNSS của S1 | +26,5 mm/năm (chỉ nối với trung bình cảnh của S1) |

**Trả lời.** Sự khác biệt giải thích được mà không cần coi sản phẩm nào là sai. Cả hai đều đưa được về hệ GNSS bằng
một tốc độ hiệu chỉnh mỗi sản phẩm: S1 qua MMX1 (−126,4 mm/năm), Capella qua phép nối (−109,0 mm/năm).

Chưa sản phẩm nào được kiểm chứng độc lập, vì trong vùng S1 chỉ MMX1 có dữ liệu năm 2024 (MXTM, UFXN và UTUL đã ngừng
ghi năm 2019–2020). Hai trạm ICMX (3 km về phía tây) và MXTX (5 km về phía bắc) có ghi năm 2024. Một sản phẩm S1 mở
rộng để phủ cả hai trạm này sẽ cho phép kiểm tra bỏ-một (G3).

*Đã lỗi thời (2026-11-05):* G3.1 (§9.1) đã làm phép kiểm tra này, và độ lệch của MMX1 không đúng cho ICMX và MXTX
(−79 / −145 / −23 mm/năm; sai số bỏ-một tại MMX1 −94). Các phép gắn −126,4 và −109,0 mm/năm, cùng lớp Đã hiệu chỉnh
và diện tích nguy cơ ở §6.1 dựa trên chúng, chưa đưa được sản phẩm nào về hệ GNSS.

Hiệu chỉnh được áp dụng mà không sửa tệp sản phẩm:

- **Trên bản đồ:** công tắc **Đã hiệu chỉnh** của lớp hiển thị vận tốc và chuỗi thời gian đã hiệu chỉnh, và chú giải
  ghi rõ điều đó.
- **Trong mục Kiểm định:** khung hiệu chỉnh ghi ra `<sản phẩm>_calibrated.gpkg` / `.csv`, có cột `vel_los_cal_mm_yr`
  bên cạnh `vel_los_mm_yr`.

## 8. Hạn chế

1. **Mốc trạm và PS.** Trung vị các PS trong bán kính 100 m có thể không chuyển dịch giống mốc trạm của ăng-ten (trên
   mái hay trên mặt đất). Gương phản xạ đặt cùng vị trí với ăng-ten GNSS sẽ khắc phục được điều này (§9, G4).
2. **Mô hình nhiễu GNSS.** Sigma tốc độ dựa trên giả thiết nhiễu trắng nên lạc quan (Williams et al. 2004). v1 chưa
   mô hình hoá nhiễu nhấp nháy và các số hạng năm.
3. **Gắn theo phương đứng và chuyển dịch ngang.** Cách gắn theo phương đứng giả định chuyển dịch ngang cục bộ không
   đáng kể. Gần mép các phễu lún, chuyển dịch ngang làm giả định này không còn đúng. Dùng sản phẩm quỹ đạo lên + quỹ
   đạo xuống sẽ cho phép so sánh 3-D.
   - *(2026-11-05)* Tại MMX1, dị thường ngang cục bộ khoảng 21 mm/năm về phía đông (≈ −14 mm/năm theo LOS), vượt mục
     tiêu 10 mm/năm; chuyển động mảng chiếu lên **l** thay đổi theo dải quét thành một mặt nghiêng. **TODO:** thêm chế
     độ `full − plate`: trừ chuyển động mảng (ITRF2020-PMM) hoặc một vận tốc tham chiếu khu vực khỏi ENU toàn phần
     trước khi chiếu, để giữ lại chuyển dịch ngang cục bộ.
4. **Nối lại các đoạn.** Việc nối đoạn giả định hai mốc trạm của một trạm đã dời vị trí có cùng tốc độ.
5. **Ít trạm.** Với một hoặc hai trạm, hiệu chỉnh chỉ gắn được tham chiếu (offset). Hiệu chỉnh mặt nghiêng cần từ ba
   trạm trở lên phân bố quanh cảnh.

## 9. Trình tự nghiên cứu

| Bước | Câu hỏi | Phương pháp | Tiêu chí |
|---|---|---|---|
| G1 (đã xong) | InSAR và GNSS có khớp nhau không? | §4 cho từng trạm, cả hai phép chiếu | RMSE hình dạng ≲ nhiễu InSAR; tương quan > 0.8 ở nơi chuyển dịch lớn hơn nhiễu. *(Đã sửa trong code (2026-11-05): `corr` trong `compare.py` nay là tương quan của hai chuỗi sau khi loại xu thế tuyến tính riêng của từng chuỗi; giá trị cũ (chỉ trừ trung bình) giữ ở `corr_with_trend`. Các bảng trước dùng định nghĩa cũ, cần tính lại)* |
| G2 (một phần) | Gắn vào GNSS có cải thiện InSAR ở xa trạm không? | Kiểm tra bỏ-một | RMS sau < RMS trước, với ≥ 3 trạm. *(2026-11-05: §6.2 chỉ dùng 2 trạm; với 3 trạm ở G7 thì không đạt, 5,1 → 6,3 mm/năm, §7.2)* |
| G3 | Kiểm tra trên chuỗi dài hơn, mạng trạm dày hơn | Sản phẩm S1 Mexico City phủ ICMX, MXTX và MMX1 (ba trạm NGL duy nhất có ghi năm 2024, §7.3); Hà Nội ≥ 2 năm | Bỏ-một với 3 trạm; có số hạng mùa trong cả hai tốc độ. Kế hoạch chi tiết: §9.1 |
| G4 | Ảnh hưởng của mốc trạm | Gương phản xạ góc cạnh HUMG / JNAV (đã có module gương phản xạ góc); chọn PS theo độ cao | Gương phản xạ − GNSS < 2 mm/năm |
| G5 | Tốc độ GNSS chính xác hơn | Nhiễu nhấp nháy cộng nhiễu trắng (Williams et al. 2004), số hạng năm, lọc sai số chung (Wdowinski et al. 1997; Dong et al. 2006) | Sigma sát thực tế |
| G6 | Tích hợp hoàn toàn | Mặt nghiêng theo từng lần chụp (GInSAR, Neely et al. 2020), 3-D với asc + desc (Shen & Liu 2020) | Bỏ-một theo từng lần chụp |
| G7 | Chuyển giao hiệu chỉnh (§7.1): giữa hai địa điểm thì thất bại; theo thời gian trong cùng thành phố thì sao? | S1 TP.HCM 2017–2019 với các trạm HCMC, XC03, GOCO, LTHA, BTRE và VUNT; hiệu chỉnh rồi áp sang 2025–2026 với cùng các vùng tham chiếu | Bỏ-một với 3–6 trạm cho 2017–2019; tốc độ 2025–2026 hợp lý so với các công bố về lún ở TP.HCM. **Đã làm (§7.2): không; 3 trạm không xác định được độ lệch, và khi nối sang 2025–2026 thì nội thành lại trồi lên** |

### 9.1 Kế hoạch G3: một chuẩn tham chiếu GNSS cho GeoEyes (lập 2026-11-04)

**Mục tiêu.** Có một phép kiểm chứng độc lập thật sự, tức là kiểm tra bỏ-một với ít nhất 3 trạm, rồi giữ nó làm *chuẩn
tham chiếu cố định*: mỗi lần sửa engine thì chạy lại và so với chuẩn. Mexico City là nơi duy nhất có đủ điều kiện,
vì tín hiệu lún (tới ~360 mm/năm) lớn hơn nhiều so với nhiễu GNSS. Ở Hà Nội thì ngược lại (§6.2).

Mỗi bước kết thúc bằng một điểm duyệt: ghi kết quả vào mục này, chờ duyệt rồi mới sang bước sau.

| Bước | Việc | Tiêu chí đạt | Trạng thái |
|---|---|---|---|
| G3.0 | Khả thi: trạm, phạm vi burst, dung lượng | Đủ 3 trạm có số liệu trong cùng giai đoạn và nằm trong cùng một subswath | **Đã xong** (dưới đây) |
| G3.1 | Thử nghiệm: cùng giai đoạn 05–10/2024, mở rộng khung để phủ cả 3 trạm | Xem bên dưới | **Không đạt** (2026-11-04), chờ duyệt |
| G3.1b | Chẩn đoán: APS, SCLA, unwrap tại 3 trạm, tính trên `state.h5` của G3.1 | Tìm ra nguyên nhân | **Xong** (2026-11-04) |
| G3.1c | Chạy lại với (b) APS chỉ khớp trên vùng ổn định, (c) ERA5 cho mọi interferogram | Hệ số so với GNSS tiến về 1 | **Xong** (2026-11-04): (c) tốt nhất, vẫn chưa đạt; chờ duyệt |
| G3.2 | Chuỗi dài 07/2023 → 01/2025 và số hạng mùa | Bỏ-một vẫn đạt khi có số hạng năm; tốc độ khác G3.1 không quá sai số | Chờ |
| G3.3 | Đóng băng thành chuẩn tham chiếu (benchmark) | Lệnh chạy lại cho ra đúng số liệu, báo lỗi khi chỉ số xấu đi | Chờ |
| G3.4 | Hà Nội ≥ 2 năm (S1 desc 091, HUMG + JNAV) | Tương quan hình dạng > 0,5 khi đã loại số hạng năm; hoặc kết luận chưa dùng được | Chờ |

**G3.0, khả thi (2026-11-04).**

- Trạm NGL trong khoảng [−99,40, 19,10, −98,70, 19,70] có số liệu từ 2023:

  | Trạm | Kinh độ, vĩ độ | Số liệu | Ghi chú |
  |---|---|---|---|
  | MMX1 | −99,068, 19,432 | 2008-04 → 2026-10 | đã dùng (§6.1) |
  | ICMX | −99,171, 19,406 | 2017-07 → 2026-01 | nằm phía tây khung `mexico_s1` hiện tại |
  | MXTX | −98,876, 19,540 | 2019-08 → **2025-02** | nằm phía đông bắc khung hiện tại |
  | MXAJ | −98,759, 19,136 | 2017-07 → 2023-12 | ngừng trước 2024, không dùng |

- Cả ba trạm đều nằm trong IW3 của track 78 (burst 165499–165500), là các burst đã tải về cho `mexico_s1`. Không
  cần tải thêm cho G3.1. MXTX chỉ cách mép đông của burst 165500 khoảng 700 m, nên G3.1 phải kiểm tra trạm này còn
  nằm trong cửa sổ mẫu hợp lệ hay không.
- Dung lượng: lần chạy `mexico_s1` (16 ảnh, khung 0,2° × 0,2°) chiếm khoảng 2 GB stack và 2 GB ps_runs. Khung G3.1 lớn
  hơn khoảng 2× nên cần ~10 GB; ổ D còn 30 GB. G3.2 (~48 ảnh) cần ~35–45 GB kể cả burst, **vượt dung lượng hiện có**.
  Tới G3.2 phải chọn: giải phóng chỗ hoặc dùng ổ khác, hoặc giảm còn 1–2 ảnh mỗi tháng (`max_per_month`).

**G3.1, thử nghiệm ba trạm.**

- Dự án mới `mexico_g3`: giữ mọi tham số của `mexico_s1` v7, chỉ đổi khung thành [−99,20, 19,33, −98,85, 19,57].
  Tham chiếu vẫn là trung bình cảnh, để độ lệch tham chiếu lộ ra rõ.
- Kiểm tra trước khi tin kết quả:
  - mỗi trạm có ≥ 20 PS trong bán kính 100 m;
  - MXTX nằm trong vùng mẫu hợp lệ của burst;
  - trên vùng chung với `mexico_s1` v7, vận tốc tương quan > 0,98 (mở rộng khung không được làm đổi kết quả cũ, ngoài
    độ lệch tham chiếu).
- Chạy `geoeyes gnss mexico_g3` với `calibration = offset` và `plane` (3 trạm vừa đủ cho mặt phẳng).
- Tiêu chí đạt:
  - từng trạm: tương quan hình dạng > 0,8 và RMSE sau khi loại xu thế ≤ 8 mm (*đã sửa trong code 2026-11-05:* `corr`
    nay đã loại xu thế, xem G1 ở §9; các giá trị tương quan của G3.1 bên dưới là `corr_with_trend` cũ, cần tính lại);
  - RMS bỏ-một sau hiệu chỉnh < trước hiệu chỉnh;
  - RMS bỏ-một sau hiệu chỉnh ≤ 10 mm/năm (khoảng 3% tín hiệu lún tối đa). Con số này được báo cáo dù đạt hay không.
- Kết quả có thể là "không đạt"; khi đó ghi lại nguyên nhân (mốc trạm, chuyển dịch ngang, ít PS) thay vì chỉnh tham
  số cho đạt.

**Kết quả G3.1 (2026-11-04): không đạt.** Sản phẩm `mexico_g3_sentinel1-asc-078_20240503_20241030_v1`, 3 632 594 PS,
PS chạy 55 phút. Script kiểm tra: [code/gnss_g3.py](../../en/research/code/gnss_g3.py).

- Kiểm tra đầu vào: **đạt.**
  - Số PS trong bán kính 100 m: ICMX 174, MMX1 59, MXTX 33. MXTX có PS gần nhất cách 18 m, nên nằm trong vùng mẫu hợp
    lệ.
  - So với v7 trên 35 708 ô 100 m chung: tương quan 0,982, g3 = 0,887 × v7 − 8,0 mm/năm, chênh trung vị −10 mm/năm.
    Hệ số góc 0,887 cho thấy khi khung rộng hơn, dải vận tốc bị *nén* khoảng 11%, không chỉ lệch hằng số (xem giả
    thuyết 2).
- So với GNSS (chiếu thẳng đứng, tốc độ GNSS lấy trên cùng cửa sổ 6 tháng):

  | Trạm | InSAR LOS | GNSS LOS | Chênh | Chênh so với MIDAS | Tương quan (còn xu thế) | RMSE loại xu thế |
  |---|---|---|---|---|---|---|
  | ICMX | +27,4 | −52,1 | −79,4 | −45,8 | **−0,46** | 7,7 mm |
  | MMX1 | −113,2 | −258,2 | −145,1 | −74,5 | 0,92 | 6,8 mm |
  | MXTX | −9,5 | −32,3 | −22,7 | +0,1 | **0,17** | **13,7 mm** |

  (mm/năm). Chỉ MMX1 đạt tiêu chí từng trạm.
- Bỏ-một với offset: RMS trước 96,4 → sau **75,0 mm/năm**. Sau hiệu chỉnh tốt hơn trước, nhưng còn xa ngưỡng 10
  mm/năm. Sai số bỏ-một từng trạm: ICMX +4,5, MMX1 −94,0, MXTX +89,5. Mặt phẳng với 3 trạm khớp đúng tuyệt đối nên
  không có kiểm tra độc lập; bỏ-một với mặt phẳng (còn 2 trạm) quay về offset và cho cùng các số trên.
- Như vậy chênh lệch **không phải một hằng số**. Hiệu vận tốc MMX1 − ICMX theo InSAR là −140 mm/năm, theo GNSS là −206:
  InSAR chỉ giữ được khoảng 68% độ tương phản giữa hai trạm.

**Giả thuyết nguyên nhân** (chưa kiểm tra; không chỉnh tham số để làm đạt):

1. *Tốc độ GNSS trên cửa sổ 6 tháng bị mùa chi phối.* Tốc độ đứng theo cửa sổ ở MMX1 là −364 mm/năm, theo MIDAS
   (18 năm) là −265; ở ICMX là −73 so với −26 (tính từ LOS −52,1 / −18,4 và l_u ≈ 0,71; sửa ngày 2026-11-05, trước
   ghi −64). Khi so với MIDAS thì chênh co lại còn −46 / −75 / 0. 6 tháng (mùa mưa)
   không đủ để có tốc độ tham chiếu; đây chính là lý do của G3.2.
2. *APS tuyến tính theo độ cao ăn mất tín hiệu lún.* Mỗi interferogram được bỏ một số hạng pha tỉ lệ với độ cao, và
   14/15 interferogram dùng cách này. Ở Mexico City, vùng lún mạnh là lòng hồ cũ thấp, còn vùng ổn định là đồi cao, nên
   lún tương quan với độ cao và một phần bị coi là khí quyển. Giả thuyết này giải thích được cả hệ số 0,68 giữa các trạm
   lẫn hệ số 0,887 khi đổi khung, vì khung rộng hơn chứa nhiều núi hơn nên hệ số pha–độ cao thay đổi. Cách kiểm: chạy
   lại bước APS với `weather` hoặc tắt APS độ cao, rồi so lại hệ số góc.
3. *ICMX và MXTX có thể nằm trên nền khác với PS xung quanh.* ICMX ở rìa đồi phía tây: InSAR cho +27 trong khi GNSS
   cho −52. Cần xem bản đồ PS trong bán kính 100 m.

**Đề xuất cho điểm duyệt:** trước G3.2, làm thêm G3.1b là chẩn đoán giả thuyết 2 trên chính dữ liệu G3.1 (chạy lại từ
bước APS, không tốn dung lượng tải). Nếu hệ số góc so với GNSS tiến về 1 thì đây là lỗi của engine, phải sửa trước khi
đóng băng chuẩn tham chiếu. Sau đó G3.2 vẫn cần quyết định về dung lượng ổ D (hiện còn ~10 GB).

**G3.1b, chẩn đoán (2026-11-04).** Không chạy lại engine: G3.1 đã xoá checkpoint bước 1–5 và ổ D không đủ chỗ cho một
lần chạy đầy đủ. Vận tốc tuyến tính theo pha, nên phần vận tốc mà mỗi số hạng (APS, SCLA) lấy đi bằng độ dốc theo thời
gian của chính số hạng đó trong `state.h5`. Script: [code/gnss_g3_aps.py](../../en/research/code/gnss_g3_aps.py).
Phép tách tái tạo `v_linear` của engine với sai lệch 1,5 mm/năm. Lưu ý: cách này bỏ qua việc pass 2 unwrap lại.

- **APS tuyến tính theo độ cao ăn một phần tín hiệu lún: đúng một phần.** Vận tốc mà APS tuyến tính mang đi là
  −41 mm/năm trên 100 m độ cao và tương quan −0,81 với độ cao, trên dải cao độ PS chỉ ~200 m. Tại trạm, APS làm vận
  tốc thay đổi +20 (ICMX), +22 (MMX1) và −5 mm/năm (MXTX); dấu dương nghĩa là APS *làm tăng* vận tốc (sửa cách diễn
  đạt ngày 2026-11-05, trước ghi "lấy đi"). Hai giá trị gần bằng nhau +20 / +22 ở ICMX / MMX1 vốn đã cho thấy APS không
  giải thích được hệ số 0,68. Bỏ APS thì kết quả tốt lên (trung vị PS tính từ `state.h5`, không phải từ sản phẩm):

  | Biến thể InSAR | so với GNSS cửa sổ: hệ số, RMS bỏ-một | so với MIDAS: hệ số, RMS bỏ-một |
  |---|---|---|
  | như sản phẩm | 0,58, 70,7 mm/năm (sản phẩm: 75,0) | 0,73, 42,1 mm/năm (sản phẩm: 46,1) |
  | bỏ APS | 0,65, 55,5 | 0,81, 25,2 |
  | bỏ APS và SCLA | 0,67, 51,4 | 0,83, 23,4 |

- **SCLA lẫn vận tốc.** Trung bình cảnh của B⊥ tương quan −0,47 với thời gian, nên trong chuỗi 6 tháng sai số góc
  nhìn và vận tốc khó tách. Số hạng SCLA mang 14 mm/năm (độ lệch chuẩn trên cảnh), tại MXTX là −23 mm/năm.
- **Không thấy unwrap sai theo chu kỳ.** Hiệu InSAR − GNSS tại MMX1 tăng đều theo thời gian (−22 → +47 mm), không có
  bước nhảy ~28 mm. Chuỗi ở MXTX nhiễu ±20–40 mm giữa các ngày liền nhau, dù các PS trong 100 m rất đồng nhất (spread
  2–3 mm). Đó là nhiễu chung của cả vùng, giống khí quyển, chứ không phải nhiễu của từng điểm.
- **Ngưỡng 10 mm/năm của G3.1 vốn không thể đạt với 6 tháng.** Sai số chuẩn của tốc độ InSAR tại trạm là 13,6 / 13,2
  / 26,7 mm/năm, nên RMS bỏ-một kỳ vọng ngay cả khi engine đúng hoàn toàn đã khoảng 20–30 mm/năm. Con số 23–25 mm/năm
  khi bỏ APS nằm đúng mức nhiễu này. Đây là lỗi khi đặt tiêu chí G3.1, không phải lỗi engine.

**Kết luận G3.1b.**

1. APS tuyến tính ước lượng riêng từng interferogram, trên mọi PS, là **một lỗi thật của engine** ở vùng lún tương
   quan với độ cao. Nó làm nén dải vận tốc và phụ thuộc khung (hệ số 0,887 khi đổi khung). Cách sửa phải được duyệt vì
   ảnh hưởng mọi dự án đang dùng mặc định. Các lựa chọn:
   - (a) ước lượng hệ số pha–độ cao cùng với mô hình biến dạng theo thời gian, thay vì riêng từng interferogram;
   - (b) chỉ khớp trên vùng ổn định (`aps_non_defo`), là cách StaMPS làm;
   - (c) dùng ERA5 cho mọi interferogram (`select = "all"`).
2. Dữ liệu 6 tháng không đủ để làm chuẩn tham chiếu. G3.2 (18 tháng) giảm sai số tốc độ khoảng 5 lần và làm B⊥ bớt
   tương quan với thời gian. Tiêu chí 10 mm/năm giữ cho G3.2. Với G3.1, ngưỡng hợp lý là ≤ 2× sai số chuẩn kỳ vọng,
   tức ~40 mm/năm: bản sản phẩm đạt so với MIDAS (42 → biên), bản bỏ APS đạt rõ (25).
   *(2026-11-05)* "khoảng 5 lần" là cận trên lạc quan: nó giả định nhiễu trắng và 46 ảnh, trong khi kế hoạch là 2 ảnh
   mỗi tháng (~36 ảnh, ≈ 4,5 lần); số hạng năm trên 1,5 chu kỳ làm sai số chuẩn tăng lên, và APS tương quan còn làm
   mức giảm nhỏ hơn nữa. Sai số chuẩn kỳ vọng phải tính với số hạng năm trong ma trận thiết kế. Tính từ sản phẩm
   (`compare.py`), RMS bỏ-một của bản sản phẩm so với MIDAS là 46,1, tức không đạt ngưỡng 40.

*Sửa lại sau G3.1c:* APS tuyến tính có ăn tín hiệu, nhưng **không phải** nguyên nhân chính làm InSAR chỉ giữ ~70%
chênh lệch giữa các trạm (xem dưới).

**G3.1c, chạy lại với APS khác (2026-11-04).** Cùng dữ liệu và tham số với G3.1, chỉ đổi cách khử khí quyển.
Checkpoint để chế độ `lean` vì ổ đĩa đầy (đã dọn 37 GB trong `trash` của workspace, có sự đồng ý của chủ dự án).

| | v1: APS tuyến tính trên mọi PS, ERA5 khi tốt hơn (1/15) | v2 (b): APS chỉ khớp trên đồi Sierra de Guadalupe | v3 (c): ERA5 cho mọi interferogram |
|---|---|---|---|
| Hệ số pha–độ cao của APS | −41 mm/năm/100 m | −7 | (ERA5) |
| Thay đổi vận tốc do APS tại ICMX / MMX1 / MXTX (+ = tăng) | +20 / +22 / −5 | −42 / −44 / −57 | +21 / +10 / −14 |
| InSAR ICMX / MMX1 / MXTX (mm/năm) | +27 / −113 / −10 | +19 / −104 / −3 | +26 / −143 / −19 |
| Hệ số so với GNSS cửa sổ / MIDAS | 0,58 / 0,73 | 0,57 / 0,72 | **0,67 / 0,84** |
| RMS bỏ-một so với GNSS cửa sổ (sau) | 75,0 | 77,9 | **63,4** |
| RMS bỏ-một so với MIDAS (sau) | 46,1 (42,1 tính từ `state.h5`) | 36,2 | 37,8 |
| Tương quan (còn xu thế) ICMX / MMX1 / MXTX | −0,46 / 0,92 / 0,17 | −0,31 / 0,95 / 0,09 | −0,34 / **0,97** / 0,27 |
| So với `mexico_s1` v7: tương quan, hệ số | 0,982, 0,887 | — | 0,904, 0,931 |

Đọc kết quả:

- **(b) gần như không đổi gì.** Khớp trên đồi làm APS lấy đi gần như cùng một lượng ở cả ba trạm, tức là thành một
  hằng số mà hiệu chỉnh offset đã xử lý. Mức nén giữa các trạm vẫn y như cũ.
- **(c) tốt nhất trong ba phương án.** Hệ số tăng 0,58 → 0,67 so với GNSS cửa sổ và 0,73 → 0,84 so với MIDAS. RMS
  bỏ-một giảm 75 → 63 mm/năm. Tương quan hình dạng ở MMX1 lên 0,97, RMSE loại xu thế 4,9 mm.
  - ERA5 cũng lấy đi tới 20 mm/năm ở ICMX. Đó là xu thế khí quyển thật từ mùa khô sang mùa mưa (05 → 10). Trong
    6 tháng, xu thế này không tách được khỏi vận tốc nếu chỉ dựa vào dữ liệu InSAR.
- **Vẫn chưa đạt, và nguyên nhân chính chưa được xác định.** MMX1 vẫn chậm hơn GNSS khoảng 70 mm/năm sau offset. ICMX
  và MXTX có tương quan hình dạng thấp: tín hiệu ở đó nhỏ (−52 và −32 mm/năm LOS) so với nhiễu 6 tháng. Các nguyên
  nhân còn lại:
  - tốc độ GNSS 6 tháng lệch theo mùa so với tốc độ dài hạn (§ giả thuyết 1);
  - SCLA lẫn vận tốc (B⊥ tương quan −0,47 với thời gian);
  - nhiễu khí quyển chung của từng vùng (MXTX).

  Cả ba đều giảm mạnh khi chuỗi dài hơn.

**Đề xuất cho điểm duyệt:**

1. Dùng (c) (`select = "all"`) cho G3.2. Chưa đổi mặc định của engine cho mọi dự án; quyết định đó chờ G3.2 xác nhận
   trên chuỗi dài.
2. Sang G3.2 (07/2023 → 01/2025). Ổ D còn ~27 GB, ổ C ~12 GB; G3.2 cần ~35–45 GB. Có thể làm vừa nếu
   `checkpoints = "lean"`, giới hạn 2 ảnh mỗi tháng (~36 ảnh) và xoá stack/ps_runs của G3.1 khi bắt đầu.

**G3.1d, vì sao ICMX và MXTX không bám GNSS (2026-11-04).** Phân tích offline trên v3 (`state.h5`), script
[code/gnss_g3_ramp.py](../../en/research/code/gnss_g3_ramp.py).

- **Hình dạng: đã tìm ra nguyên nhân là một mặt dốc (ramp) trên toàn cảnh, khác nhau ở từng ngày chụp.** PS trong
  100 m quanh mỗi trạm khớp nhau tới 2–5 mm, nhưng ICMX (phía tây) và MXTX (phía đông, cách ~34 km, trong đó 31 km theo hướng đông–tây) lệch ngược chiều
  nhau trong cùng một ngày (27/05/2024: −26 / +69 mm). Khớp một mặt phẳng cho phần phi tuyến của dịch chuyển ở từng
  ngày (đã bỏ đường thẳng riêng của mỗi PS) thì độ dốc lên tới ±16 mm mỗi 10 km theo hướng đông–tây, lớn nhất vào
  tháng 5 và cuối tháng 10. Mặt phẳng này giải thích 62% phương sai phi tuyến trên cả cảnh. Nó gần như không đổi trước
  và sau hiệu chỉnh ERA5, nên không phải phần tầng đối lưu mà ERA5 nhìn thấy được. Nhiều khả năng là tầng điện ly
  (2024 là năm cực đại Mặt Trời, lượt bay lên chụp vào buổi tối, và Mexico City nằm dưới dị thường xích đạo) hoặc
  sai số quỹ đạo.

  | Trạm | Phần dư InSAR − GNSS đã loại xu thế (độ lệch chuẩn, mm) | Tương quan với mặt phẳng | Sau khi bỏ mặt phẳng |
  |---|---|---|---|
  | ICMX | 10,0 | **0,92** | **3,8** |
  | MMX1 | 4,8 | 0,66 | 3,6 |
  | MXTX | 14,6 | 0,69 | 12,8 |

  MXTX chỉ được giải thích một phần vì trạm cách mép burst 700 m. Ở đó, mặt phẳng khớp trên cả cảnh chỉ là phép ngoại
  suy.
- **Quy trình có sai không?** Ngoài APS tuyến tính ước lượng riêng từng interferogram (G3.1b, đã khắc phục bằng (c)),
  chưa thấy bước nào đã cài đặt bị sai. Chỗ hổng là **một bước còn thiếu**: engine, cũng như StaMPS mặc định, không có
  hiệu chỉnh tầng điện ly hay ramp (`scla_deramp = "n"`). *Sửa lại ở G3.1e:* bước 8 có khử được ramp này, kết quả
  nằm trong `disp_scn_mm`; bước kiểm định lại đọc `disp_mm`.
- **Tốc độ: chưa giải quyết xong.**
  - Trường PS quanh MMX1 đồng nhất tới 2 km (−128 đến −143 mm/năm), nên trạm không nằm trên một điểm cục bộ.
  - So với MIDAS, ICMX và MMX1 có cùng offset (GNSS − InSAR −44 mm/năm), tức chênh lệch ICMX–MMX1 được giữ đủ 100%. So với tốc độ
    GNSS 6 tháng thì còn 82%.
  - MXTX là điểm lệch: thấp hơn khoảng 55–65 mm/năm so với ICMX. Tuy vậy sai số chuẩn tốc độ InSAR ở đây là 28,6
    mm/năm, nên độ lệch chỉ khoảng 2σ.
  - Nếu ramp tăng tuyến tính theo thời gian, nó sẽ làm lệch tốc độ theo đúng kiểu này. Chỉ với dữ liệu InSAR 6 tháng
    thì không tách được ramp đó khỏi phễu lún.

**Đề xuất:**
1. Thêm tuỳ chọn ước lượng ramp theo từng ngày chụp, chỉ trên phần phi tuyến (không động vào tốc độ), để khử nhiễu
   hình dạng.
2. Lên kế hoạch hiệu chỉnh tầng điện ly bằng tách phổ (split-spectrum) cho S1, cần cho dữ liệu 2024–2025.
3. Kiểm tra cả hai trong G3.2 trên chuỗi 18 tháng, khi ramp tuyến tính theo thời gian và phễu lún tách nhau tốt hơn.

**G3.1e, kế hoạch cho đề xuất (1), đã sửa trước khi viết code (2026-11-04).** Khi xem lại engine, mình thấy bước 8
đã khử được ramp này. SCN là pha được lọc thông cao theo thời gian (khớp tuyến tính cục bộ, nên chuỗi 6 tháng vẫn giữ
xu thế), rồi lọc thông thấp theo không gian bằng Gaussian 100 m. Bộ lọc này giữ lại mọi bước sóng dài hơn 100 m, kể cả
ramp trên toàn cảnh. Sản phẩm lưu kết quả ở cột `disp_scn_mm`. Trên v3, chuỗi ở các trạm lấy từ `disp_scn_mm` cho:

| Trạm | RMSE loại xu thế `disp_mm` → `disp_scn_mm` (mm) | Tương quan, `disp_scn_mm` (đã trừ trung bình, còn xu thế) |
|---|---|---|
| ICMX | 10,0 → **2,6** | (tương quan chuỗi gốc là −0,86 vì xu thế sai dấu, xem phần tốc độ) |
| MMX1 | 4,8 → **1,5** | 1,00 |
| MXTX | 14,7 → **3,8** | 0,47 |

Tốc độ gần như không đổi, vì SCN được thiết kế để giữ xu thế: hệ số 0,62 / 0,79, RMS bỏ-một 66 / 38 mm/năm so với
GNSS cửa sổ / MIDAS. Như vậy chỗ hổng không nằm ở engine mà ở bước kiểm định, vốn chỉ đọc `disp_mm`. Kế hoạch sửa lại
như sau, thay cho việc thêm một bước deramp mới:

1. Thêm `[validation.gnss] series = "scn" | "raw"`, mặc định `"scn"`. Sản phẩm không có `disp_scn_mm` thì quay về
   `"raw"` kèm cảnh báo. Chuỗi đã dùng được ghi vào `comparison.json` và `series.npz`.
2. Unit test: kiểm tra giá trị tham số, việc đọc cột SCN, và cảnh báo khi phải quay về `"raw"`.
3. Chạy lại `geoeyes gnss mexico_g3` trên v3 và ghi số liệu vào đây.
4. Không đổi: engine, sản phẩm, và hiệu chỉnh mà web app áp lên `disp_mm` (offset / plane là hiệu chỉnh tốc độ, áp
   được cho cả hai chuỗi).

Câu hỏi còn mở là tốc độ (độ tương phản giữa các trạm và việc xu thế ở ICMX sai dấu). G3.2 sẽ giải quyết phần này.

*Đã làm (2026-11-04):* mục 1–3. `geoeyes gnss mexico_g3` trên v3 nay đọc `disp_scn_mm`. RMSE loại xu thế: ICMX 2,6,
MMX1 1,5, MXTX 3,8 mm (trước là 10,0 / 4,8 / 14,7). RMS bỏ-một với offset: 86,7 → 66,0 mm/năm (ICMX −5, MMX1 −78, MXTX
+83). Unit test: 23 đạt.

*Lưu ý (2026-11-05):* với chồng ảnh 6 tháng, chuỗi SCN gần như chỉ còn xu thế tuyến tính cộng nhiễu dưới 100 m: phần
lọc thông cao theo thời gian của phép khớp tuyến tính cục bộ 365 ngày là toàn bộ phần ngoài đường thẳng, và qua
Gaussian 100 m, SCN bỏ phần phi tuyến đó ở mọi bước sóng trên 100 m. Vì vậy mức giảm 4,8 → 1,5 mm tại MMX1 chủ yếu
phản ánh bộ lọc chứ không phải mức khớp InSAR–GNSS, và con số "1,00" ở trên là của xu thế. Kiểm định nên dùng `raw`;
SCN chỉ dùng để chẩn đoán. *Đã sửa trong code (2026-11-05):* mặc định nay là `series = "raw"`
(`validation/gnss/compare.py`, schema đầu ra `geoeyes.gnss/2`); `"scn"` vẫn dùng được khi chỉ định rõ, để chẩn đoán.
Các con số ở trên tính với `"scn"` và định nghĩa tương quan cũ, cần tính lại.

*Bước deramp interferogram của quy trình cũ* (`[ps] scla_deramp`, theo StaMPS):
- Engine **có** bước này: bỏ một mặt phẳng khỏi mỗi interferogram (hoặc mặt bậc hai nếu khớp rõ tốt hơn) trước khi
  ước lượng SCLA, unwrap lần 2 và tính vận tốc.
- Bước này bật trong preset ICEYE và COSMO-SkyMed (`hanoi_csk`) nhưng tắt với Sentinel-1 (`mexico_s1`, `mexico_g3`).
- Nó bỏ cả mặt phẳng, kể cả phần tăng tuyến tính theo thời gian. Khi phễu lún trải hết khung ảnh, nó bỏ luôn độ nghiêng
  của phễu và làm thay đổi tốc độ. Ngược lại, SCN chỉ bỏ phần không tuyến tính theo thời gian.
- Cách kiểm tra sạch là thử `scla_deramp = "y"` trên chuỗi 18 tháng của G3.2. Khi đó sẽ biết ramp tuyến tính theo
  thời gian có phải là nguyên nhân làm nén độ tương phản giữa các trạm hay không.

**Rà soát 2026-11-05** (định hướng từ G3.2 trở đi):

- 3 trạm chuẩn cũng chính là tập dùng để tinh chỉnh: phương án (c) được chọn bằng bỏ-một trên chính chúng, và khoảng
  cách so với v1 (63 so với 75 mm/năm) nhỏ hơn mức nhiễu kỳ vọng ~23 mm/năm; so với MIDAS thì phương án (b) tốt nhất
  (36,2 so với 37,8). Việc chọn (c) chưa có dữ liệu độc lập ủng hộ.
- Với n = 3, cần báo khoảng tin cậy (bootstrap hoặc giải tích) cho hệ số và RMS bỏ-một.
- "Sau < trước" là tiêu chí yếu với sản phẩm tham chiếu vào trung bình cảnh: nên so với một mốc cơ sở tham chiếu vùng
  ổn định (`reference_bbox`).
- Ngưỡng đạt đã đổi từ 10 sang ~40 mm/năm sau khi thấy kết quả. Cần đăng ký trước ngưỡng của G3.2 từ sai số chuẩn kỳ
  vọng (có số hạng năm) trước khi chạy.
- Việc quy cho tầng điện ly ở G3.1d mới là suy đoán: mặt phẳng khớp theo từng ngày chụp trên chính các PS đó có thể
  hấp thụ chuyển dịch của phễu lún. Cần kiểm bằng hiệu chỉnh tách phổ (split-spectrum) hoặc một vệt quỹ đạo xuống.

**G3.2–G3.4** sẽ được viết chi tiết sau khi G3.1 được duyệt.

## 10. Triển khai

| Thành phần | Vị trí |
|---|---|
| Danh sách trạm NGL, bước nhảy, tenv3, MIDAS (có lưu đệm, qua https), làm sạch và phân đoạn | `src/geoeyes/validation/gnss/ngl.py` |
| Ghép cặp, phép chiếu, thống kê, hiệu chỉnh, bỏ-một, áp dụng số hiệu chỉnh | `src/geoeyes/validation/gnss/compare.py` |
| CLI `geoeyes gnss <project> [--product ID] [--set key=value]` | `src/geoeyes/cli/main.py` |
| API `/api/projects/{p}/products/{id}/gnss[...]` | `src/geoeyes/api/gnss.py` (chạy nền: `api/jobs.py`) |
| Ứng dụng web: dự án → Validation → GNSS (bảng, hiệu chỉnh, biểu đồ cho từng trạm); Hazard → "GNSS tie" và các trạm trên bản đồ | `webapp/src/components/Gnss.tsx`, `webapp/src/pages/Hazard.tsx` |
| Gắn GNSS cho phân tích nguy cơ | `[postprocess.hazard] gnss_tie`, `src/geoeyes/hazard/assess.py` |
| Nối với sản phẩm khác (§7.3), hiệu chỉnh đang áp dụng (GNSS, nếu không có thì phép nối) | `src/geoeyes/validation/tie.py`; CLI `geoeyes tie <project> --reference P/ID`; API `/api/projects/{p}/products/{id}/tie` và `/export-calibrated` |
| Lớp bản đồ và export đã hiệu chỉnh | `cal=1` trên các route của lớp điểm (`api/points.py`: cache `<product_id>@cal`); `export/vector.py` (`calibration=`); ứng dụng web: công tắc Đã hiệu chỉnh của lớp, `webapp/src/components/Calibration.tsx` |
| Test (đọc tenv3, ăng-ten dời vị trí, tìm lại độ lệch tham chiếu tổng hợp bằng mặt phẳng từ 3 trạm, bỏ-một, gắn GNSS cho phân tích nguy cơ; phép nối tìm lại độ lệch đã biết dù khác hình học và thời kỳ, lớp và export đã hiệu chỉnh) | `tests/unit/validation/test_gnss.py`, `tests/unit/validation/test_tie.py`, `tests/unit/hazard/test_hazard.py` |

Kết quả được ghi vào `<project>/analyses/gnss/<product_id>/`: `comparison.json`, `series.npz` và `manifest.json`;
phép nối ghi vào `<project>/analyses/tie/<product_id>/tie.json`.
Tệp NGL được lưu đệm trong `<workspace>/cache/gnss/ngl/`: số liệu vị trí lưu một ngày, các danh sách lưu một tuần.

## 11. Tài liệu tham khảo

Tất cả DOI dưới đây đã được kiểm tra trên Crossref ngày 2026-10-25.

**NGL**

- Blewitt G, Hammond WC, Kreemer C (2018) Harnessing the GPS data explosion for interdisciplinary science. *Eos* 99. https://doi.org/10.1029/2018EO104623
- Blewitt G, Kreemer C, Hammond WC, Gazeaux J (2016) MIDAS robust trend estimator for accurate GPS station velocities without step detection. *J. Geophys. Res. Solid Earth* 121(3):2054–2068. https://doi.org/10.1002/2015JB012552

**GNSS và InSAR**

- Del Soldato M, Confuorto P, Bianchini S, Sbarra P, Casagli N (2021) Review of works combining GNSS and InSAR in Europe. *Remote Sensing* 13:1684. https://doi.org/10.3390/rs13091684
- Farolfi G, Del Soldato M, Bianchini S, Casagli N (2019) A procedure to use GNSS data to calibrate satellite PSI data for the study of subsidence: an example from the north-western Adriatic coast (Italy). *European Journal of Remote Sensing* 52:54–63. https://doi.org/10.1080/22797254.2019.1663710
- Fattahi H, Amelung F (2014) InSAR uncertainty due to orbital errors. *Geophysical Journal International* 199(1):549–560. https://doi.org/10.1093/gji/ggu276
- Hammond WC, Blewitt G, Kreemer C (2016) GPS Imaging of vertical land motion in California and Nevada: Implications for Sierra Nevada uplift. *J. Geophys. Res. Solid Earth* 121(10):7681–7703. https://doi.org/10.1002/2016JB013458
- Hammond WC, Burgette RJ, Johnson KM, Blewitt G (2018) Uplift of the Western Transverse Ranges and Ventura area of Southern California: a four-technique geodetic study combining GPS, InSAR, leveling, and tide gauges. *J. Geophys. Res. Solid Earth* 123(1):836–858. https://doi.org/10.1002/2017JB014499
- Hammond WC, Blewitt G, Kreemer C, Nerem RS (2021) GPS Imaging of global vertical land motion for studies of sea level rise. *J. Geophys. Res. Solid Earth* 126(7):e2021JB022355. https://doi.org/10.1029/2021JB022355
- Neely WR, Borsa AA, Silverii F (2020) GInSAR: a cGPS correction for enhanced InSAR time series. *IEEE Trans. Geoscience and Remote Sensing* 58(1):136–146. https://doi.org/10.1109/TGRS.2019.2934118
- Shen ZK, Liu Z (2020) Integration of GPS and InSAR data for resolving 3-dimensional crustal deformation. *Earth and Space Science* 7(4):e2019EA001036. https://doi.org/10.1029/2019EA001036
- Tong X, Sandwell DT, Smith-Konter B (2013) High-resolution interseismic velocity data along the San Andreas fault from GPS and InSAR. *J. Geophys. Res. Solid Earth* 118:369–389. https://doi.org/10.1029/2012JB009442
- Weiss JR, Walters RJ, Morishita Y, Wright TJ, Lazecky M, Wang H, Hussain E, Hooper AJ, Elliott JR, Rollins C, et al. (2020) High-resolution surface velocities and strain for Anatolia from Sentinel-1 InSAR and GNSS data. *Geophysical Research Letters* 47(17):e2020GL087376. https://doi.org/10.1029/2020GL087376
- Wright TJ, Parsons BE, Lu Z (2004) Toward mapping surface deformation in three dimensions using InSAR. *Geophysical Research Letters* 31(1). https://doi.org/10.1029/2003GL018827
- Xu X, Sandwell DT, Klein E, Bock Y (2021) Integrated Sentinel-1 InSAR and GNSS time-series along the San Andreas fault system. *J. Geophys. Res. Solid Earth* 126:e2021JB022579. https://doi.org/10.1029/2021JB022579

**Mốc trạm và điểm tán xạ**

- Dheenathayalan P, Small D, Schubert A, Hanssen RF (2016) High-precision positioning of radar scatterers. *Journal of Geodesy* 90:403–422. https://doi.org/10.1007/s00190-015-0883-4
- Dheenathayalan P, Small D, Hanssen RF (2018) 3-D positioning and target association for medium-resolution SAR sensors. *IEEE Trans. Geoscience and Remote Sensing* 56:6841–6853. https://doi.org/10.1109/TGRS.2018.2844108
- Mahapatra P, van der Marel H, van Leijen F, Samiei-Esfahany S, Klees R, Hanssen R (2018) InSAR datum connection using GNSS-augmented radar transponders. *Journal of Geodesy* 92(1):21–32. https://doi.org/10.1007/s00190-017-1041-y
- Parker AL, Featherstone WE, Penna NT, Filmer MS, Garthwaite MC (2017) Practical considerations before installing ground-based geodetic infrastructure for integrated InSAR and cGNSS monitoring of vertical land motion. *Sensors* 17(8):1753. https://doi.org/10.3390/s17081753

**Nhiễu và tốc độ GNSS**

- Blewitt G, Lavallée D (2002) Effect of annual signals on geodetic velocity. *J. Geophys. Res.* 107(B7). https://doi.org/10.1029/2001JB000570
- Dong D, Fang P, Bock Y, Webb F, Prawirodirdjo L, Kedar S, Jamason P (2006) Spatiotemporal filtering using principal component analysis and Karhunen-Loeve expansion approaches for regional GPS network analysis. *J. Geophys. Res.* 111:B03405. https://doi.org/10.1029/2005JB003806
- Mao A, Harrison CGA, Dixon TH (1999) Noise in GPS coordinate time series. *J. Geophys. Res.* 104(B2):2797–2816. https://doi.org/10.1029/1998JB900033
- Wdowinski S, Bock Y, Zhang J, Fang P, Genrich J (1997) Southern California permanent GPS geodetic array: spatial filtering of daily positions for estimating coseismic and postseismic displacements induced by the 1992 Landers earthquake. *J. Geophys. Res.* 102(B8):18057–18070. https://doi.org/10.1029/97JB01378
- Williams SDP, Bock Y, Fang P, Jamason P, Nikolaidis RM, Prawirodirdjo L, Miller M, Johnson DJ (2004) Error analysis of continuous GPS position time series. *J. Geophys. Res.* 109:B03412. https://doi.org/10.1029/2003JB002741

**Mexico City và Hà Nội**

- Cabral-Cano E, Dixon TH, Miralles-Wilhelm F, Díaz-Molina O, Sánchez-Zamora O, Carande RE (2008) Space geodetic imaging of rapid ground subsidence in Mexico City. *GSA Bulletin* 120(11–12):1556–1566. https://doi.org/10.1130/B26001.1
- Cabral-Cano E, Pérez-Campos X, Márquez-Azúa B, Sergeeva MA, Salazar-Tlaczani L, DeMets C, Adams D, Galetzka J, Hodgkinson K, Feaux K, et al. (2018) TLALOCNet: a continuous GPS-Met backbone in Mexico for seismotectonic and atmospheric research. *Seismological Research Letters* 89(2A):373–381. https://doi.org/10.1785/0220170190
- Chaussard E, Wdowinski S, Cabral-Cano E, Amelung F (2014) Land subsidence in central Mexico detected by ALOS InSAR time-series. *Remote Sensing of Environment* 140:94–106. https://doi.org/10.1016/j.rse.2013.08.038
- Cigna F, Tapete D (2021) Present-day land subsidence rates, surface faulting hazard and risk in Mexico City with 2014–2020 Sentinel-1 IW InSAR. *Remote Sensing of Environment* 253:112161. https://doi.org/10.1016/j.rse.2020.112161
- Dang VK, Doubre C, Weber C, Gourmelen N, Masson F (2014) Recent land subsidence caused by the rapid urban development in the Hanoi region (Vietnam) using ALOS InSAR data. *Natural Hazards and Earth System Sciences* 14(3):657–674. https://doi.org/10.5194/nhess-14-657-2014
- Solano-Rojas D, Wdowinski S, Cabral-Cano E, Osmanoğlu B (2020) Detecting differential ground displacements of civil structures in fast-subsiding metropolises with interferometric SAR and band-pass filtering. *Scientific Reports* 10:15460. https://doi.org/10.1038/s41598-020-72293-z

