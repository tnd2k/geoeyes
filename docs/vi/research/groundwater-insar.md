> Bản dịch tiếng Việt của [`docs/en/research/groundwater-insar.md`](../../en/research/groundwater-insar.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-10-26.

# Trữ lượng nước ngầm và InSAR

Trạng thái: đã triển khai v1 (kiểm định liên hệ với nước ngầm GLDAS trong phân vùng nguy cơ, đặc trưng nước ngầm
trong mô hình dự báo).
Mã nguồn: `geoeyes.ancillary.groundwater`, `geoeyes.hazard.assess._groundwater`, `geoeyes.hazard.coupling.storage`,
`geoeyes.ml.forecast._gws_features`. Ghi chú liên quan: [rainfall-insar-hazard.md](rainfall-insar-hazard.md)
(phép kiểm định liên hệ dùng lại ở đây), [ai-forecasting.md](ai-forecasting.md).

## Mục lục

1. [Câu hỏi](#1-câu-hỏi)
2. [Tổng quan](#2-tổng-quan)
3. [Dữ liệu nước ngầm nào của NASA dùng được](#3-dữ-liệu-nước-ngầm-nào-của-nasa-dùng-được)
4. [Phương pháp (v1)](#4-phương-pháp-v1)
5. [Kết quả đầu tiên](#5-kết-quả-đầu-tiên)
6. [Hạn chế](#6-hạn-chế)
7. [Trình tự nghiên cứu](#7-trình-tự-nghiên-cứu)
8. [Tài liệu tham khảo](#8-tài-liệu-tham-khảo)

## 1. Câu hỏi

Khai thác nước ngầm là tác nhân chính gây sụt lún ở các vùng châu thổ và bồn trũng mà GeoEyes đang theo dõi (Hà
Nội, đồng bằng sông Cửu Long, Thành phố Mexico). Trong phép kiểm định liên hệ với mưa (ghi chú về mưa, §4.3), nước
ngầm chỉ là mắt xích ngầm định: mưa bổ cập cho tầng chứa nước, và mực nước biến đổi theo độ lệch mưa tích luỹ. Trang
nước ngầm của NASA Earthdata liệt kê các sản phẩm mở ước tính trực tiếp trữ lượng nước ngầm. Các câu hỏi đặt ra:

- **Q1.** Có đọc được các sản phẩm này một cách tự động cho bất kỳ vùng dự án nào không?
- **Q2.** Sau khi loại xu thế ổn định, chuyển dịch InSAR có biến đổi theo trữ lượng nước ngầm không, với độ trễ và dấu
  như thế nào?
- **Q3.** Các đặc trưng nước ngầm có cải thiện dự báo biến dạng không?
- **Q4.** Nước ngầm có dùng được làm một lớp *không gian* cho mô hình tính nhạy cảm không?

## 2. Tổng quan

- **Nén chặt hệ tầng chứa nước.** Khi mực nước hạ, ứng suất hữu hiệu lên các lớp sét tăng và chúng bị nén. Một phần
  nén chặt là đàn hồi (hồi lại khi mực nước phục hồi), một phần không đàn hồi (vĩnh viễn khi mực nước xuống thấp hơn
  mức thấp nhất trước đó) (Galloway & Burbey 2011). InSAR thấy được cả hai:
  - lún và nâng theo mùa, đi theo nhịp khai thác và bổ cập (Hoffmann et al. 2001; Chaussard et al. 2014);
  - xu thế dài hạn do nén chặt không đàn hồi (Minderhoud et al. 2017 cho đồng bằng sông Cửu Long; Bui et al. 2021
    cho Hà Nội).
- **Trọng lực vệ tinh.** GRACE (2002–2017) và GRACE-FO (từ 2018) đo biến đổi tổng lượng nước trên lục địa. Các lời
  giải mascon có độ phân giải hiệu dụng khoảng 3°, lưới 0,5° (Watkins et al. 2015). Cần một mô hình bề mặt đất để
  tách phần nước ngầm khỏi độ ẩm đất, tuyết và nước mặt.
- **GLDAS đồng hoá dữ liệu GRACE.** GLDAS (Rodell et al. 2004) dùng mô hình bề mặt đất Catchment có đồng hoá GRACE
  (Li et al. 2019). Sản phẩm cho trữ lượng nước ngầm hằng ngày ở độ phân giải 0,25°; thông tin ở quy mô GRACE được
  chi tiết hoá nhờ các quá trình vật lý của mô hình.
- **Kết hợp GRACE và InSAR.** Các nghiên cứu ở miền Trung Mexico (Castellazzi et al. 2016) và Thung lũng Trung tâm
  California (Ojha et al. 2018) ghép lượng nước mất ở quy mô vùng từ GRACE với sụt lún cục bộ từ InSAR. GRACE cho biết
  khối lượng và thời điểm; InSAR cho biết mặt đất phản ứng ở đâu.

## 3. Dữ liệu nước ngầm nào của NASA dùng được

Rà soát các sản phẩm và công cụ trên trang nước ngầm của Earthdata, thử ngày 2026-10-25:

| Sản phẩm / công cụ | Độ phân giải | Giai đoạn | Phạm vi | Kết quả thử truy cập | Dùng trong GeoEyes |
|---|---|---|---|---|---|
| **GLDAS CLSM025 DA1 D v2.2**, `GWS_tavg` | 0,25°, hằng ngày | từ 2003 (trễ vài tháng) | đất liền toàn cầu | cắt dữ liệu qua Harmony với token Earthdata: chạy được | **được chọn** |
| GRACE / GRACE-FO JPL mascon RL06.3 | lưới 0,5°, hiệu dụng ~3° | từ 2002, theo tháng, khuyết 2017–2018 | toàn cầu | PO.DAAC (token) | sau này (R-G2): kiểm tra độc lập |
| GES DISC Data Rods (chuỗi thời gian tại một điểm) | như mô hình | như mô hình | toàn cầu | chuyển hướng sang trang đăng nhập: không dùng được với token | không |
| NLDAS / NCA-LDAS | 0,125° | từ 1979 | chỉ Hoa Kỳ | – | không (ngoài vùng nghiên cứu) |
| USGS / số liệu giếng quốc gia | giếng | tuỳ nơi | quốc gia | chưa công khai cho Việt Nam | khi người dùng có số liệu |

**Trả lời Q1.** Có. GeoEyes đọc `GWS_tavg` của GLDAS qua NASA Harmony (API OGC coverages): mỗi năm một tác vụ bất
đồng bộ với khung toạ độ và khoảng thời gian, trả về mỗi ngày một tệp netCDF4. GeoEyes lấy trung bình các ngày thành
giá trị tháng cho từng pixel 0,25° và lưu đệm trong `<workspace>/cache/groundwater`. Một tháng chỉ được tính khi
thiếu không quá hai ngày. Lần chạy đầu cho một vùng mất vài phút (Harmony chạy song song các tác vụ theo năm); những
lần sau đọc từ bộ đệm. Cần `EARTHDATA_TOKEN`, cùng token dùng để tải DEM và quỹ đạo.

## 4. Phương pháp (v1)

### 4.1 Liên hệ với chuỗi InSAR (phân vùng nguy cơ)

Với mỗi ô phân tích, trên chuỗi theo hướng chuyển dịch dự kiến (dấu của GeoEyes: âm là lún ở nền phẳng, xuống dốc ở
sườn dốc) và trữ lượng S của pixel 0,25° chứa ô đó:

    d(t) = a + b·t + g·S(t − τ) + ε

- Trữ lượng nước ngầm là đại lượng trạng thái, không phải dòng chảy, nên S đóng vai trò mà độ lệch mưa tích luỹ đóng
  trong mô hình mưa (`coupling.storage`). S lấy tại giữa tháng và nội suy tuyến tính giữa các tháng.
- Độ trễ τ chạy từ 0 đến `max_lag_months` và được chọn theo hệ số tương quan riêng phần lớn nhất sau khi đã loại
  [1, t].
- Ý nghĩa thống kê: như với mưa, việc dò độ trễ được lặp lại trên các chuỗi thay thế xáo pha ngẫu nhiên (Ebisuzaki
  1997) của biến đổi trữ lượng theo tháng, rồi áp tỉ lệ phát hiện sai Benjamini–Hochberg trên toàn bản đồ.
- Dấu kỳ vọng: ở chế độ sụt lún, **g > 0** nghĩa là mặt đất nâng lên và hạ xuống theo trữ lượng, lún nhiều hơn khi
  trữ lượng giảm (phản ứng đàn hồi của tầng chứa nước). Phần tóm tắt báo tỉ lệ ô có ý nghĩa mang g > 0.
- GLDAS được công bố trễ vài tháng. Phép kiểm định chỉ dùng những ngày chụp InSAR mà dữ liệu trữ lượng đã phủ, và
  chỉ khi chúng vẫn đủ `min_span_months` và `min_epochs`; một cảnh báo ghi ngày cuối cùng được dùng.
- **Liên hệ này không làm thay đổi mức nguy cơ.** Trữ lượng mang tính vùng, nên nó giải thích *khi nào* mặt đất
  chuyển dịch, không chỉ ra *nơi nào* nguy hiểm hơn. Đây là một lớp chẩn đoán: lớp "Liên hệ với nước ngầm" trên trang
  Phân tích chuyên đề, có khung riêng trong bảng thông tin ô và đường mô hình đã khớp trong biểu đồ của ô.
- Tham số: `[postprocess.hazard] groundwater = "auto" | "gldas" | "off"`.
  - `auto` (mặc định): dùng khi đã đặt token; nếu lỗi chỉ thêm một cảnh báo.
  - `gldas`: bắt buộc; nếu lỗi thì dừng lần chạy.
- Đầu ra:
  - các cột `gw_*` trong `cells.parquet`;
  - `groundwater.npz` (trữ lượng theo tháng cho từng pixel);
  - mục `groundwater` trong `hazard.json` (số ô đã kiểm định và có ý nghĩa, độ trễ trung vị, tỉ lệ g > 0, xu thế
    trữ lượng của từng pixel).

### 4.2 Đặc trưng cho mô hình dự báo

Khi phân tích nguy cơ có `groundwater.npz`, mô hình gradient boosting toàn cục của phần dự báo nhận thêm ba đặc trưng,
đều lấy từ trữ lượng trung bình trên vùng quan tâm của tháng cuối cùng đã công bố trước thời điểm dự báo:

- `gws_anom`: độ lệch của tháng đó so với trung bình;
- `gws_d3`: biến đổi trong 3 tháng gần nhất;
- `gws_d12`: biến đổi trong 12 tháng gần nhất.

Quy tắc "tháng cuối cùng đã công bố" áp dụng như nhau khi huấn luyện và tại thời điểm dự báo, nên độ trễ công bố
không làm lộ giá trị tương lai cũng không tạo khoảng trống. Như mọi đặc trưng khác, chúng chỉ có tác dụng nếu mô hình
thắng các mô hình đơn giản khi kiểm tra ngược trên dữ liệu quá khứ (ai-forecasting.md).

### 4.3 Không phải biến giải thích không gian (Q4)

Một vùng đô thị chỉ gồm vài pixel 0,25° (Hà Nội: 2 × 2), nên nếu làm lớp tính nhạy cảm thì trữ lượng chỉ đóng vai
một mã vị trí thô, không phải nguyên nhân. Điều này cũng đúng với lượng mưa khí hậu, vốn mặc định bị loại vì cùng lý
do. Vì vậy nước ngầm không được dùng làm lớp tính nhạy cảm. Muốn có một lớp không gian thực sự cần số liệu khai thác
(giếng, giấy phép khai thác) hoặc mực nước quan trắc (R-G3).

## 5. Kết quả đầu tiên

Phân vùng nguy cơ với `groundwater = "auto"`, ngày 2026-10-26 (tham số mặc định: ô 100 m, độ trễ 0–6 tháng, FDR
0,05):

| Sản phẩm | Giai đoạn InSAR | Số pixel GLDAS | Trữ lượng | Số ô đã kiểm định | Có ý nghĩa (FDR) |
|---|---|---|---|---|---|
| Hà Nội CSK v3 | 2011-07 → 2014-12 (18 cảnh) | 2 | đầy đủ; xu thế +27 đến +42 mm/năm | 6.362 | 0 |
| Hà Nội S1 v4 | 2025-10 → 2026-10 (26 cảnh) | 4 | công bố đến 2026-08; xu thế −16 đến −4 mm/năm | 0 (chưa đánh giá) | – |

- **Truy cập chạy được (Q1).** Cả hai vùng đều đọc được qua Harmony; Hà Nội CSK cần bốn tác vụ theo năm, Hà Nội S1
  cần hai.
- **Hà Nội CSK: không có liên hệ.** Sau khi loại xu thế, không ô nào trong 6.362 ô biến đổi theo trữ lượng. Điều này
  khớp với các phân tích khác của vùng này (trung tâm Hà Nội): tốc độ chỉ nằm trong khoảng ±3 mm/năm (P5–P95) so với
  trung bình toàn cảnh, và cũng không ô nào liên hệ với mưa. Trữ lượng tăng trong giai đoạn 2011–2014 trong khi vùng
  này vẫn ổn định, nên ở đây hai xu thế không nói lên gì về nhau.
- **Hà Nội S1: chưa đánh giá.** GLDAS mới công bố đến tháng 8/2026, nên trữ lượng chỉ phủ khoảng 11 tháng của chuỗi,
  dưới mức 12 tháng mà một phép kiểm định theo mùa cần. Bản thân trữ lượng có chu kỳ mùa rõ, biên độ khoảng 300 mm:
  cao nhất vào tháng 10/2025 (khoảng 1.880 mm), thấp nhất vào tháng 4–6/2026 (khoảng 1.610 mm). Phép kiểm định sẽ chạy
  khi các tháng còn lại được công bố, không cần đổi phương pháp.
- **Tiếp theo:** Q2 sẽ được trả lời ở những vùng lún nhanh (Hoàng Mai, Thanh Trì, Hà Đông; Thành phố Mexico) và với
  các chuỗi dài hơn.

## 6. Hạn chế

- **Quy mô.** Trữ lượng có độ phân giải 0,25°, còn thông tin GRACE bên trong ở quy mô khoảng 300 km. Các phễu hạ thấp
  mực nước cục bộ trong thành phố không thấy được; phép kiểm định chỉ tìm ra những ô có chuyển dịch cùng *nhịp thời
  gian* với trữ lượng của cả vùng.
- **Mô hình, không phải quan trắc.** Trữ lượng GLDAS là trạng thái của một mô hình được ràng buộc bởi GRACE, không
  phải mực nước đo được. Ở nơi tầng chứa nước trong mô hình không sát thực tế (khai thác có điều tiết, tầng chứa nước
  có áp), tính mùa của nó có thể sai.
- **Độ trễ công bố.** Với sản phẩm gần đây, phép kiểm định chỉ dùng được các ngày chụp cũ hơn.
- **Đồng tuyến với xu thế.** Một chuỗi không đủ để tách xu thế trữ lượng khỏi xu thế sụt lún: [1, t] được loại trước,
  nên chỉ phần phi tuyến, chủ yếu là phần theo mùa, được kiểm định. Hai xu thế được báo cạnh nhau để tham khảo khi
  diễn giải, không phải như một quan hệ nhân quả.
- **Yếu tố gây nhiễu do nhiệt và mưa.** Trữ lượng theo mùa, lượng mưa và nhiệt độ biến đổi cùng nhau. Bước R-G1 sẽ
  tách chúng ra.

## 7. Trình tự nghiên cứu

- **R-G0 — Truy cập và kiểm tra dữ liệu** *(đã xong)*: truy cập Harmony, bộ đệm theo tháng, độ trễ công bố, số pixel
  phủ mỗi vùng quan tâm.
- **R-G1 — Xác định nguyên nhân** *(tiếp theo)*: mô hình chung d = a + b·t + k·CRD(t − τ₁) + g·S(t − τ₂) + c·T(t)
  trên cùng các ô. Tiêu chí: g vẫn có ý nghĩa khi đã đưa mưa và nhiệt độ vào mô hình (gắn với bước R2 của ghi chú về
  mưa).
- **R-G2 — Trữ lượng độc lập**: lặp lại với mascon GRACE/GRACE-FO của JPL. Tiêu chí: cùng dấu và cùng độ trễ ở các
  vùng có liên hệ.
- **R-G3 — Mực nước và khai thác**: số liệu quan trắc mực nước (Hà Nội: mạng quan trắc quốc gia, Bui et al. 2021) và
  số liệu khai thác. Ước tính hệ số nhả nước đàn hồi của khung đất (skeletal storage coefficient) từ InSAR và mực
  nước (Chaussard et al. 2014; Smith & Knight 2019); một bản đồ khai thác sẽ là lớp không gian thực sự cho mô hình
  tính nhạy cảm.
- **R-G4 — Giá trị cho dự báo**: so sánh kết quả kiểm tra ngược có và không có đặc trưng nước ngầm trên các chuỗi dài
  (CSK 2011–2014, Sentinel-1 từ 2016). Tiêu chí: MAE thấp hơn ở tầm dự báo 3–6 tháng.

## 8. Tài liệu tham khảo

- Bui, L. K., Le, P. V. V., Dao, P. D., Long, N. Q., Pham, H. V., Tran, H. H., Xie, L. (2021). Recent land
  deformation detected by Sentinel-1A InSAR data (2016–2020) over Hanoi, Vietnam, and the relationship with
  groundwater level change. *GIScience & Remote Sensing* 58(2), 161–179.
- Castellazzi, P., Arroyo-Domínguez, N., Martel, R., Calderhead, A. I., Normand, J. C. L., Gárfias, J., Rivera, A.
  (2016). Land subsidence in major cities of Central Mexico: interpreting InSAR-derived land subsidence mapping
  with hydrogeological data. *International Journal of Applied Earth Observation and Geoinformation* 47, 102–111.
- Castellazzi, P., Martel, R., Rivera, A., Huang, J., Pavlic, G., Calderhead, A. I., Chaussard, E., Garfias, J.,
  Salas, J. (2016). Groundwater depletion in Central Mexico: use of GRACE and InSAR to support water resources
  management. *Water Resources Research* 52, 5985–6003.
- Chaussard, E., Bürgmann, R., Shirzaei, M., Fielding, E. J., Baker, B. (2014). Predictability of hydraulic head
  changes and characterization of aquifer-system and fault properties from InSAR-derived ground deformation.
  *Journal of Geophysical Research: Solid Earth* 119, 6572–6590.
- Ebisuzaki, W. (1997). A method to estimate the statistical significance of a correlation when the data are
  serially correlated. *Journal of Climate* 10, 2147–2153.
- Galloway, D. L., Burbey, T. J. (2011). Review: Regional land subsidence accompanying groundwater extraction.
  *Hydrogeology Journal* 19, 1459–1486.
- Hoffmann, J., Zebker, H. A., Galloway, D. L., Amelung, F. (2001). Seasonal subsidence and rebound in Las Vegas
  Valley, Nevada, observed by synthetic aperture radar interferometry. *Water Resources Research* 37(6),
  1551–1566.
- Li, B., Rodell, M., Kumar, S., Beaudoing, H. K., Getirana, A., Zaitchik, B. F., et al. (2019). Global GRACE data
  assimilation for groundwater and drought monitoring: advances and challenges. *Water Resources Research* 55,
  7564–7586.
- Minderhoud, P. S. J., Erkens, G., Pham, V. H., Bui, V. T., Erban, L., Kooi, H., Stouthamer, E. (2017). Impacts
  of 25 years of groundwater extraction on subsidence in the Mekong delta, Vietnam. *Environmental Research
  Letters* 12, 064006.
- Ojha, C., Shirzaei, M., Werth, S., Argus, D. F., Farr, T. G. (2018). Sustained groundwater loss in California's
  Central Valley exacerbated by intense drought periods. *Water Resources Research* 54, 4449–4460.
- Rodell, M., Houser, P. R., Jambor, U., Gottschalck, J., Mitchell, K., Meng, C.-J., et al. (2004). The Global
  Land Data Assimilation System. *Bulletin of the American Meteorological Society* 85(3), 381–394.
- Smith, R., Knight, R. (2019). Modeling land subsidence using InSAR and airborne electromagnetic data. *Water
  Resources Research* 55, 2801–2819.
- Watkins, M. M., Wiese, D. N., Yuan, D.-N., Boening, C., Landerer, F. W. (2015). Improved methods for observing
  Earth's time variable mass distribution with GRACE using spherical cap mascons. *Journal of Geophysical
  Research: Solid Earth* 120, 2648–2671.
- Dữ liệu: Li, B., Beaudoing, H., Rodell, M. (2020). GLDAS Catchment Land Surface Model L4 daily 0.25 × 0.25 degree
  GRACE-DA1 V2.2. Goddard Earth Sciences Data and Information Services Center (GES DISC),
  doi:10.5067/TXBMLX370XX8.
