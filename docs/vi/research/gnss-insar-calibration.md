> Bản dịch tiếng Việt của [`docs/en/research/gnss-insar-calibration.md`](../../en/research/gnss-insar-calibration.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.

# Dùng GNSS (Nevada Geodetic Laboratory) để kiểm định và hiệu chỉnh chuỗi thời gian InSAR

> Ghi chú nghiên cứu, đồng thời mô tả phương pháp của `geoeyes gnss` (gói `geoeyes.validation.gnss`; trên ứng dụng
> web: trang dự án → Validation → GNSS, và mục "GNSS tie" trên trang Hazard).
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
  - Hammond et al. (2016, 2018) dùng GNSS làm khung quy chiếu, còn InSAR bổ sung chi tiết ("GPS Imaging").
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

## 8. Hạn chế

1. **Mốc trạm và PS.** Trung vị các PS trong bán kính 100 m có thể không chuyển dịch giống mốc trạm của ăng-ten (trên
   mái hay trên mặt đất). Gương phản xạ đặt cùng vị trí với ăng-ten GNSS sẽ khắc phục được điều này (§9, G4).
2. **Mô hình nhiễu GNSS.** Sigma tốc độ dựa trên giả thiết nhiễu trắng nên lạc quan (Williams et al. 2004). v1 chưa
   mô hình hoá nhiễu nhấp nháy và các số hạng năm.
3. **Gắn theo phương đứng và chuyển dịch ngang.** Cách gắn theo phương đứng giả định chuyển dịch ngang cục bộ không
   đáng kể. Gần mép các phễu lún, chuyển dịch ngang làm giả định này không còn đúng. Dùng sản phẩm quỹ đạo lên + quỹ
   đạo xuống sẽ cho phép so sánh 3-D.
4. **Nối lại các đoạn.** Việc nối đoạn giả định hai mốc trạm của một trạm đã dời vị trí có cùng tốc độ.
5. **Ít trạm.** Với một hoặc hai trạm, hiệu chỉnh chỉ gắn được tham chiếu (offset). Hiệu chỉnh mặt nghiêng cần từ ba
   trạm trở lên phân bố quanh cảnh.

## 9. Trình tự nghiên cứu

| Bước | Câu hỏi | Phương pháp | Tiêu chí |
|---|---|---|---|
| G1 (đã xong) | InSAR và GNSS có khớp nhau không? | §4 cho từng trạm, cả hai phép chiếu | RMSE hình dạng ≲ nhiễu InSAR; tương quan > 0.8 ở nơi chuyển dịch lớn hơn nhiễu |
| G2 (đã xong) | Gắn vào GNSS có cải thiện InSAR ở xa trạm không? | Kiểm tra bỏ-một | RMS sau < RMS trước, với ≥ 3 trạm |
| G3 | Kiểm tra trên chuỗi dài hơn, mạng trạm dày hơn | Sản phẩm S1 Mexico City phủ ICMX, MXTX và MMX1; Hà Nội ≥ 2 năm | Bỏ-một với 3 trạm; có số hạng mùa trong cả hai tốc độ |
| G4 | Ảnh hưởng của mốc trạm | Gương phản xạ góc cạnh HUMG / JNAV (đã có module gương phản xạ góc); chọn PS theo độ cao | Gương phản xạ − GNSS < 2 mm/năm |
| G5 | Tốc độ GNSS chính xác hơn | Nhiễu nhấp nháy cộng nhiễu trắng (Williams et al. 2004), số hạng năm, lọc sai số chung (Wdowinski et al. 1997; Dong et al. 2006) | Sigma sát thực tế |
| G6 | Tích hợp hoàn toàn | Mặt nghiêng theo từng lần chụp (GInSAR, Neely et al. 2020), 3-D với asc + desc (Shen & Liu 2020) | Bỏ-một theo từng lần chụp |

## 10. Triển khai

| Thành phần | Vị trí |
|---|---|
| Danh sách trạm NGL, bước nhảy, tenv3, MIDAS (có lưu đệm, qua https), làm sạch và phân đoạn | `src/geoeyes/validation/gnss/ngl.py` |
| Ghép cặp, phép chiếu, thống kê, hiệu chỉnh, bỏ-một, áp dụng số hiệu chỉnh | `src/geoeyes/validation/gnss/compare.py` |
| CLI `geoeyes gnss <project> [--product ID] [--set key=value]` | `src/geoeyes/cli/main.py` |
| API `/api/projects/{p}/products/{id}/gnss[...]` | `src/geoeyes/api/gnss.py` (chạy nền: `api/jobs.py`) |
| Ứng dụng web: dự án → Validation → GNSS (bảng, hiệu chỉnh, biểu đồ cho từng trạm); Hazard → "GNSS tie" và các trạm trên bản đồ | `webapp/src/components/Gnss.tsx`, `webapp/src/pages/Hazard.tsx` |
| Gắn GNSS cho phân tích nguy cơ | `[postprocess.hazard] gnss_tie`, `src/geoeyes/hazard/assess.py` |
| Test (đọc tenv3, ăng-ten dời vị trí, tìm lại độ lệch tham chiếu tổng hợp bằng mặt phẳng từ 3 trạm, bỏ-một, gắn GNSS cho phân tích nguy cơ) | `tests/unit/validation/test_gnss.py`, `tests/unit/hazard/test_hazard.py` |

Kết quả được ghi vào `<project>/analyses/gnss/<product_id>/`: `comparison.json`, `series.npz` và `manifest.json`.
Tệp NGL được lưu đệm trong `<workspace>/cache/gnss/ngl/`: số liệu vị trí lưu một ngày, các danh sách lưu một tuần.

## 11. Tài liệu tham khảo

Tất cả DOI dưới đây đã được kiểm tra trên Crossref ngày 2026-10-25.

**NGL**

- Blewitt G, Hammond WC, Kreemer C (2018) Harnessing the GPS data explosion for interdisciplinary science. *Eos* 99. https://doi.org/10.1029/2018EO104623
- Blewitt G, Kreemer C, Hammond WC, Gazeaux J (2016) MIDAS robust trend estimator for accurate GPS station velocities without step detection. *J. Geophys. Res. Solid Earth* 121(3):2054–2068. https://doi.org/10.1002/2015JB012552
- Blewitt G (2024) An improved equation of latitude and a global system of graticule distance coordinates. *Journal of Geodesy* 98:6. https://doi.org/10.1007/s00190-023-01815-0

**GNSS và InSAR**

- Del Soldato M, Confuorto P, Bianchini S, Sbarra P, Casagli N (2021) Review of works combining GNSS and InSAR in Europe. *Remote Sensing* 13:1684. https://doi.org/10.3390/rs13091684
- Farolfi G, Del Soldato M, Bianchini S, Casagli N (2019) A procedure to use GNSS data to calibrate satellite PSI data for the study of subsidence: an example from the north-western Adriatic coast (Italy). *European Journal of Remote Sensing* 52:54–63. https://doi.org/10.1080/22797254.2019.1663710
- Fattahi H, Amelung F (2014) InSAR uncertainty due to orbital errors. *Geophysical Journal International* 199(1):549–560. https://doi.org/10.1093/gji/ggu276
- Hammond WC, Blewitt G, Kreemer C (2016) GPS Imaging of vertical land motion in California and Nevada. *J. Geophys. Res. Solid Earth* 121(10):7681–7703. https://doi.org/10.1002/2016JB013458
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

