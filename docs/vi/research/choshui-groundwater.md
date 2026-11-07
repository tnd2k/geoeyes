> Bản dịch tiếng Việt của [`docs/en/research/choshui-groundwater.md`](../../en/research/choshui-groundwater.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-11-05.

# Nước ngầm và InSAR trên quạt bồi tích sông Choshui

> Kế hoạch nghiên cứu (2026-11-05). Trạng thái: **đã duyệt C0; xong C1, chờ duyệt**. Mỗi bước kết thúc bằng một điểm
> duyệt; bước sau chỉ bắt đầu khi chủ dự án đã xem kết quả.
> Ghi chú liên quan: [groundwater-insar.md](groundwater-insar.md) (liên hệ với trữ lượng mô hình, GLDAS/GRACE),
> [two-geometries-and-soft-soil.md](two-geometries-and-soft-soil.md) (phân tách quỹ đạo lên + xuống),
> [ramp-selection.md](ramp-selection.md) (bỏ xu hướng mà không bỏ phễu lún),
> [gnss-insar-calibration.md](gnss-insar-calibration.md) (kiểm tra bằng GNSS).

## Mục lục

1. [Vì sao làm nghiên cứu này](#1-vì-sao-làm-nghiên-cứu-này)
2. [Dữ liệu đã nhận](#2-dữ-liệu-đã-nhận)
3. [Câu hỏi và giả thuyết](#3-câu-hỏi-và-giả-thuyết)
4. [Nguyên tắc](#4-nguyên-tắc)
5. [Các bước C0–C8](#5-các-bước-c0c8)
6. [Rủi ro và yếu tố gây nhiễu](#6-rủi-ro-và-yếu-tố-gây-nhiễu)
7. [Tài nguyên](#7-tài-nguyên)
8. [Một phát hiện sẽ trông như thế nào](#8-một-phát-hiện-sẽ-trông-như-thế-nào)
9. [Tài liệu tham khảo](#9-tài-liệu-tham-khảo)

## 1. Vì sao làm nghiên cứu này

Các phép thử ở Hà Nội và đồng bằng sông Cửu Long trong [groundwater-insar.md](groundwater-insar.md) không trả lời
được câu hỏi chuyển dịch có đi theo mực nước hay không: không có mực nước đo, chỉ có trữ lượng mô hình (GLDAS) hoặc
lượng mưa làm đại lượng thay thế, và cửa sổ trễ (0–6 tháng) chỉ thăm dò được đáp ứng đàn hồi. Quạt bồi tích sông
Choshui (濁水溪沖積扇, Chương Hóa và Vân Lâm, Đài Loan) là trường hợp ngược lại:

- một mạng quan trắc dày, dài và **nhiều tầng**: 315 giếng ở 104 trạm, phần lớn trạm có 2–5 giếng đặt ống lọc ở
  các tầng chứa nước khác nhau, mực nước hằng ngày 2001–2024;
- một trong những vùng lún do khai thác nước ngầm được ghi nhận kỹ nhất thế giới (tốc độ vài cm/năm ở nội địa Vân
  Lâm trong thập niên 2010; đường sắt cao tốc chạy qua phễu lún), nên tín hiệu lớn;
- 11 năm Sentinel-1 ở hai hướng quỹ đạo.

Vì vậy đây là nơi có thể kiểm tra chuỗi xử lý GeoEyes với một *tác nhân vật lý độc lập*, không phải với một sản
phẩm InSAR khác, và là nơi có thể đẩy các phương pháp trong các ghi chú về nguy cơ (liên hệ, phân tách, kiểu chuyển
dịch, tuyến) tới các tham số vật lý (hệ số trữ khung cốt, độ trễ, tầng nào bị nén).

## 2. Dữ liệu đã nhận

Rà soát ngày 2026-11-05 (chỉ đọc metadata và thống kê tóm tắt).

### 2.1 Nước ngầm (`20240828_GWL_CRFP_model.h5`, 46 MB)

- HDF5 ghi ngày 2024-08-28 từ các file Excel của mạng quan trắc ("Transform GWL data from Excel to HDF5").
- Dataset gốc `date`: hằng ngày, 2001-01-01 → 2024-12-31 (8.766 ngày). Số liệu kết thúc ngày 2024-08-20.
- Mỗi trạm một nhóm (104): `X`, `Y` theo TWD97 / TM2 (EPSG:3826), địa chỉ, lưu vực, số giếng. Ba trạm không có
  metadata (`GANYUAN`, `XIABANTIAN`, `ZHONGLIAO`), một trạm sai tọa độ (vĩ độ 0).
- Mỗi giếng một nhóm con (315): `Well_Depth(m)`, `Well_Elev(m)`, `Well_Screen(m)` (thiếu ở phần lớn giếng làm lại
  sau 2011), `FIRST_OBS`, `LAST_OBS`, `Status`; các dataset `measure/daily_value` (mực nước, m; giá trị khoảng −45
  đến +10 m, nên là cao độ mực nước so với mực nước biển trung bình — cần xác nhận) và `measure/model` (mực nước
  mô hình hoặc đã lấp chỗ trống; ở ANHE(1) tương quan 0,94 với số đo, lệch RMS 0,9 m — **cần hỏi bên cung cấp dữ
  liệu**).
- Nhiều giếng được làm lại khoảng 2011–2012: mã cũ (`…11`, tới 2010-12) và mã mới (`…12`, từ 2012-01) là cùng một
  số giếng ở cùng trạm, cách nhau một năm, có thể khác độ sâu hoặc mốc cao độ.
- Độ sâu: < 50 m 58 giếng, 50–100 m 68, 100–150 m 74, 150–200 m 35, 200–300 m 68, > 300 m 5. 233 giếng có
  ≥ 1.500 ngày đo hợp lệ trong 2015–2024. 99 trong 101 trạm có tọa độ nằm trong khung InSAR.
- Số thứ tự giếng ở một trạm (1), (2), (3), (4) tăng theo độ sâu (ANHE: 40–52, 72–90, 144–156, 260–278 m): có lẽ
  đó là chỉ số tầng chứa nước của hệ nhiều tầng của quạt bồi tích. Kiểm tra ở C0.

### 2.2 InSAR (MintPy trên HyP3, chỉ để đối chiếu)

| | Quỹ đạo lên | Quỹ đạo xuống |
|---|---|---|
| Track | 69 | 105 |
| Số ngày chụp | 433 (2015-01-14 → 2026-06-09) | 441 (2015-01-16 → 2026-06-11) |
| Lưới | 2728 × 2053, 40 m, UTM 50N (EPSG:32650) | 2817 × 2053, 40 m |
| File | `timeseries_SET_ERA5_ramp_demErr-001.h5` (9,9 GB) | `…-002.h5` (10,6 GB) |
| Tầng đối lưu | `height_correlation` | `pyaps` (ERA5) |
| Tham chiếu | `auto` (hàng 1749, cột 1436) | 23,7612 N, 120,6809 E |

Cả hai: thủy triều đất rắn, **bỏ ramp tuyến tính**, hiệu chỉnh sai số DEM, trọng số `var`, sửa lỗi giải cuộn pha
bằng bridging + phase closure, 2 × 10 look. Có kèm `geometryGeo.h5` (góc tới, góc phương vị, độ cao, mặt nạ nước)
và file cấu hình MintPy.

Nhận xét:
- Hai track không được xử lý giống nhau (tầng đối lưu, tham chiếu), dù tên file đều ghi "ERA5".
- Bỏ ramp tuyến tính trên khung 80 × 110 km sẽ lấy mất một phần phễu lún cùng kích thước
  ([ramp-selection.md](ramp-selection.md) §2): phần lún bước sóng dài của sản phẩm này không đáng tin.
- Chuỗi nước ngầm kết thúc 2024-08; phần chồng với InSAR là 2015-01 → 2024-08 (9,6 năm).

Nơi để dữ liệu: bản gốc giữ nguyên trong `Downloads`; bản làm việc chép sang
`geoeyes_workspace/studies/choshui_gw/data/` ở bước C0.

## 3. Câu hỏi và giả thuyết

- **Q1. Tầng nào bị nén?** Ở một trạm có giếng ở các tầng 1–4, chuyển dịch đứng được giải thích tốt nhất bởi mực
  nước của tầng nào, với độ trễ bao nhiêu?
  - *H1*: ở phần giữa và phần xa của quạt, các tầng chứa nước có áp sâu hơn (2–3) giải thích phần lún dài hạn nhiều
    hơn tầng 1; ở phần đỉnh quạt (không áp, hạt thô) liên hệ yếu.
- **Q2. Trữ đàn hồi và không đàn hồi.** Tỷ số biên độ theo mùa (chuyển dịch đứng / mực nước) có cho được hệ số trữ
  khung cốt đàn hồi S_ke·b, và chuyển dịch dài hạn khi mực nước xuống dưới mức thấp nhất trước đó có cho được hệ số
  không đàn hồi S_kv·b không (Hoffmann et al. 2001; Chen et al. 2016; Smith et al. 2017)?
  - *H2*: S_ke·b cỡ 10⁻⁴–10⁻³ và S_kv/S_ke ≫ 1 nơi lớp cách nước dày; tỷ lệ nén vĩnh viễn được lập bản đồ chứ không
    giả định.
- **Q3. Độ trễ.** Thời gian trễ giữa mực nước và độ nén đo thời gian thoát nước của lớp cách nước τ ∝ b²/c_v.
  - *H3*: τ tăng từ đỉnh quạt ra bờ biển (sét dày hơn); τ vài tháng là đáp ứng đàn hồi của tầng chứa nước, τ nhiều
    năm là thoát nước của lớp cách nước (theo mùa hay bị trễ; xem [two-geometries-and-soft-soil.md](two-geometries-and-soft-soil.md) §4.3).
- **Q4. Dự báo.** Mực nước có dự báo được lún ở những trạm và những năm được giữ lại không?
  - *H4*: mô hình theo mực nước tốt hơn xu hướng tuyến tính trên các năm giữ lại (2023–2024) và các trạm giữ lại.
- **Q2b. Hạn hán 2021** (thêm sau C0). 140 giếng xuống dưới mức thấp nhất trước 2015 vào năm 2021.
  - *H5*: ở những giếng đó, InSAR cho thấy lún thêm trong 2021 và không hồi lại trong 2022; ở những giếng không
    xuống dưới mức cũ, chỗ trũng của 2021 hồi lại. Đây là phép thử trực tiếp cho nén không đàn hồi.
- **Q5. Chuyển dịch ngang.** Có chuyển dịch đông–tây hướng về tâm các phễu hạ thấp mực nước không (nén ba chiều)?
- **Q6. Phương pháp của mình.** Những lựa chọn xử lý nào của GeoEyes (APS, ramp `auto`, SCN, tham chiếu, engine)
  giữ được tín hiệu mà mực nước dự báo, và lựa chọn nào làm mất hoặc méo nó? Mực nước là trọng tài, không phải sản
  phẩm MintPy.

## 4. Nguyên tắc

- **Nước ngầm là biến độc lập.** Không sản phẩm InSAR nào (của mình hay MintPy) là chuẩn; cả hai được đánh giá theo
  mức khớp với mực nước *và* với nhau, và với GNSS khi có.
- **Đăng ký trước.** Tiêu chí của mỗi bước được viết ra trước khi chạy bước đó (như kế hoạch sạt lở).
- **Giữ lại.** Giai đoạn 2023-01 → 2024-08 và một khối trạm theo không gian được giữ lại tới C6.
- **Cùng một quy ước dấu.** Dấu GeoEyes: lún là âm. Mực nước tính bằng m (lên là dương).
- **Mỗi lần một bước**, có duyệt của chủ dự án giữa các bước.

## 5. Các bước C0–C8

### C0. Rà soát dữ liệu và lập danh mục (điểm duyệt)

- Chép dữ liệu sang `geoeyes_workspace/studies/choshui_gw/data/` (không động vào bản gốc).
- Danh mục giếng (`wells.parquet`): trạm, giếng, lon/lat (EPSG:3826 → 4326 và → 32650), cao độ mặt đất và miệng
  giếng, độ sâu, ống lọc, ngày đo đầu/cuối, trạng thái, số ngày hợp lệ trong giai đoạn chồng.
- Nối mã cũ và mã mới của cùng một số giếng (làm lại 2011–2012): kiểm tra mốc cao độ và độ sâu, đánh dấu bước nhảy.
- Chỉ số tầng: kiểm tra "số giếng = tầng chứa nước" theo độ sâu và ống lọc; tìm ranh giới các lớp địa chất thủy văn
  ở từng trạm (báo cáo của Cục Địa chất Trung ương / Cục Tài nguyên Nước, cần xin) — tới lúc đó dùng số giếng và
  ghi rõ giả định.
- Kiểm tra chất lượng từng chuỗi: gai, đoạn phẳng, nhảy mốc; lấy mẫu lại theo tháng và theo 12 ngày (trung vị) về
  các ngày chụp InSAR.
- Chuỗi `model`: hỏi bên cung cấp dữ liệu đó là gì; chỉ dùng `daily_value` cho tới khi có câu trả lời.
- Bản đồ tóm tắt mực nước: xu hướng dài hạn từng tầng 2015–2024, biên độ và pha theo mùa, mức thấp nhất lịch sử
  (đại diện cho áp lực tiền cố kết) từ 2001.
- **Điểm duyệt:** danh mục, báo cáo chất lượng, bản đồ mực nước; các câu hỏi gửi bên cung cấp dữ liệu (ý nghĩa của
  `model`, mốc cao độ, ranh giới tầng, có giếng đo nén nhiều tầng hoặc số liệu thủy chuẩn không).

**Kết quả C0 (2026-11-05, đã duyệt và chấp nhận cùng ngày: gán tầng theo ống lọc hoặc độ sâu, dùng số giếng khi
thiếu; chỉ dùng mã mới cho 2015–2024; thêm H5 vào §3).** Script `code/choshui_c0.py` (trong `docs/en/research/`); kết quả và báo cáo
đầy đủ ở `geoeyes_workspace/studies/choshui_gw/c0/` (`c0_audit.md`).
- Có 233 giếng ở 94 trạm dùng được trong giai đoạn chồng (≥ 1.500 ngày hợp lệ, có tọa độ): giếng số 1 có 92,
  số 2 có 79, số 3 có 39, số 4 có 21. Năm trạm không có tọa độ. 13 giếng thiếu độ sâu, trong đó có ba giếng TUKU
  ở tâm phễu lún.
- `model` là mực nước đã lấp chỗ trống: nó lấp năm 2006 và kéo dài quá ngày đo cuối. Chỉ dùng `daily_value`.
- Độ sâu theo số giếng (trung vị 62, 129, 201, 261 m) cho thấy bốn tầng, và độ sâu tăng theo số giếng ở 86 % số
  trạm. Đề xuất: gán tầng theo ống lọc hoặc độ sâu, dùng số giếng khi thiếu.
- Làm lại giếng 2011–2012: 37 trên 62 cặp đổi độ sâu hơn 5 m, nên không nối mã cũ và mã mới cho 2015–2024. Cao độ
  miệng giếng giảm trung vị 0,19 m giữa hai lần đo (cùng độ sâu); đó có thể là lún đo được trong thập niên 2000
  (cần xác nhận).
- Kiểm tra chất lượng: các bước nhảy đột ngột phần lớn là hạ mực nước do bơm (dao động theo mùa 10–20 m ở Vân
  Lâm), nên được giữ lại. Gai và đoạn phẳng được loại bỏ.
- **Thời điểm:** mực nước thấp nhất rơi vào tháng 4–5 và đến muộn hơn theo độ sâu. So với giếng số 1, số 3 muộn
  hơn 1,1 tháng (KTC 95 % 0,6–1,4) và số 4 muộn hơn 1,4 tháng (0,6–2,0). C4 phải tìm thấy pha phụ thuộc độ sâu
  này trong chuyển dịch.
- **Hạn hán 2021:** 187 trên 233 giếng có mức thấp nhất 2015–2024 vào năm 2021, thấp hơn trung vị 2,4 m so với
  mức thấp của 2015–2020. 140 giếng xuống dưới mức thấp nhất trước 2015, trung vị 2,3 m. Đây là phép thử tự nhiên
  cho nén không đàn hồi, đề xuất thành H5:
  - *H5:* nơi mực nước 2021 xuống dưới mức thấp nhất trước đó, InSAR cho thấy lún thêm trong 2021 và không hồi
    lại trong 2022.
  - Nơi mực nước không xuống dưới mức đó, chỗ trũng của 2021 hồi lại.

### C1. Sản phẩm MintPy như một sản phẩm bên ngoài (điểm duyệt)

- Bộ đọc nhỏ cho `timeseries` + `geometryGeo` của MintPy (chỉ đọc theo cửa sổ: mỗi file 10 GB), xuất ra cấu trúc
  sản phẩm của GeoEyes (điểm hoặc lưới, vận tốc, chuỗi, véc-tơ đơn vị LOS) để các module phân tích chạy được trên nó.
- Vận tốc và chuỗi tại các trạm giếng (trung vị trong một bán kính, bắt đầu với 200 m).
- Không dùng làm chuẩn; nó là một trong các ứng viên được đánh giá ở C4 và C7.
- **Điểm duyệt:** bộ đọc có unit test, bản đồ vận tốc LOS hai track, xem sơ bộ mực nước và chuyển dịch ở 5 trạm
  (chưa tính thống kê).

**Kết quả C1 (2026-11-05, chờ duyệt).** Bộ đọc `geoeyes.products.foreign.import_mintpy` (3 unit test); script
`code/choshui_c1.py`; báo cáo `studies/choshui_gw/c1/c1_report.md`.
- **Sản phẩm.** Hai sản phẩm trong `projects/choshui_mintpy/products/`, gồm các khối 200 m: 88.737 điểm (lên) và
  87.110 điểm (xuống). Véc-tơ LOS lấy từ các góc của MintPy (l_e −0,56 / +0,56). Cả hai được đánh dấu là sản phẩm
  bên ngoài, và `geoeyes decompose` tìm thấy chúng.
- **Phễu lún.** Một phễu lún chiếm ưu thế ở nội địa Vân Lâm (Tuku–Yuanchang). Nó tới −89 mm/năm LOS ở quỹ đạo lên
  và −68 ở quỹ đạo xuống; LUNZI lún khoảng −69 mm/năm theo phương đứng, khoảng 0,7 m trong 11 năm.
- **Chuỗi tại trạm.** Cả 94 trạm giếng đều có chuỗi ở hai track, lấy từ các pixel gốc trong bán kính 200 m.
  - Hai track khớp nhau về phân bố (r = 0,97), nhưng lên − xuống = −7,7 mm/năm theo phép chiếu đứng.
  - Chênh lệch này không do tham chiếu, vì hai pixel tham chiếu chỉ cách nhau 250 m. Nó là chuyển dịch về phía
    tây của đồng bằng hoặc là khác biệt trong xử lý (tầng đối lưu: tương quan theo độ cao so với ERA5; bỏ ramp
    tuyến tính ở từng track). Việc này chuyển sang C3, với GNSS.
- **Khoảng trống của quỹ đạo xuống.** Quỹ đạo xuống có **khoảng trống 168 ngày** (2022-02-08 → 2022-07-26, sau khi
  mất Sentinel-1B). Sau 2022 chuỗi của nó phẳng hơn quỹ đạo lên, nên chưa dùng được cho H5 hay cho phép phân tách
  sau 2022-02. C2 phải nối khoảng trống bằng các cặp dài, hoặc xử lý hai đoạn riêng.
- **Lấy mẫu không đều.** Lấy mẫu 6 ngày trong 2018–2021 và 12 ngày ở các giai đoạn khác, nên các phân tích dùng
  các khối 12 ngày của C0.
- **Thiếu file.** Bản giao không có mặt nạ độ kết hợp: cần xin `temporalCoherence.h5` và `velocity.h5`.

### C2. GeoEyes xử lý vùng lõi (điểm duyệt)

- Vùng: phễu lún nội địa Vân Lâm cộng một vùng tham chiếu ổn định ở đồi núi phía đông, kích thước theo ngân sách ổ
  đĩa (§7). Không xử lý toàn khung.
- Cả hai track (lên 69, xuống 105), 2015-01 → 2026-06, lấy mẫu tối đa 12 ngày (24 ngày nếu ổ đĩa không đủ).
- Engine: SBAS (tán xạ phân bố chiếm ưu thế ở vùng nông nghiệp) và `ps_lite` trên cùng chồng ảnh để so sánh.
- Ramp: `scla_deramp = "auto"` **có vùng ổn định** (`deramp_non_defo` trên vùng đồi phía đông) — theo quy tắc ngày
  2026-11-05, xu hướng phẳng không bị bỏ nếu không có vùng này. Giữ thêm một lần chạy không bỏ ramp cho C7.
- Tham chiếu: vùng ổn định; kiểm tra bằng `geoeyes gnss` với các trạm NGL trong vùng.
- **Điểm duyệt:** sản phẩm hai track, so sánh GNSS (chuỗi raw), độ phủ tại các giếng, dung lượng ổ đĩa đã dùng.

**Thiết kế C2 (2026-11-05, trước khi tải dữ liệu).**
- **Engine.** `ps_lite` là quy trình cho Capella, nên với Sentinel-1 hai engine là **SBAS** (`method = "sbas"`)
  và **PSI** (`method = "psi"`), chạy trên cùng một chồng ảnh.
- **Vùng.** AOI `[120.31, 23.58, 120.65, 23.78]`: 60 giếng dùng được ở 28 trạm, trong đó có LUNZI, TUKU, và
  thềm Douliu ở phía đông làm vùng ổn định. Burst đã tra trên ASF:
  - quỹ đạo lên 69: burst IW1 146196 và 146197, tức 2 burst mỗi ngày, ASF có 440 ngày chụp;
  - quỹ đạo xuống 105: burst IW2 224319–224321, tức 3 burst mỗi ngày với `subswaths = ["IW2"]`, ASF có 453 ngày
    chụp. Bỏ góc IW3 ở tây bắc.
- **Lấy mẫu.** `max_per_month = 1`, cho khoảng 138 ngày (lên) và 132 ngày (xuống) trong 2015-01 → 2026-06. Mỗi
  tháng một ngày là đủ cho mực nước thấp nhất tháng 4–5 và cho hạn hán 2021.
- **Ổ đĩa.** Khoảng 0,148 GB mỗi file burst (chỉ VV), đo trên archive; ước tính đầu 0,12 GB là thấp.
  - Burst thô: quỹ đạo lên khoảng 41 GB (276 burst), quỹ đạo xuống khoảng 59 GB (396 burst). Chồng ảnh được cắt theo AOI, khoảng 4–6 GB
    mỗi track.
  - Hai track chạy **lần lượt**. Khi chồng ảnh của một track đã dựng xong và đã kiểm tra, các burst thô của nó
    (chỉ những burst tải cho nghiên cứu này) sẽ bị xóa. Lúc cao nhất dùng khoảng 65–70 GB (quỹ đạo xuống), trong
    khi còn trống 81 GB.
- **Bắt đầu 2026-11-05:** tải và dựng chồng ảnh quỹ đạo lên 69 (`geoeyes run choshui_s1 --track
  sentinel1-asc-069 --to build_stack`).

**Tiến độ C2 (2026-11-06): xong quỹ đạo lên; quỹ đạo xuống đã xử lý, phễu lún bị nông (chưa giải quyết).**
- **Dữ liệu.**
  - Burst thô: 276 burst, 34 GB. Chồng ảnh: 127 ngày (2015-12 → 2026-06), 22 GB.
  - 11 ngày năm 2015 bị bỏ: cảnh của các ngày đó thiếu một trong hai burst.
  - Sửa: chú giải IPF đầu 2015 ghi FM rate dạng `c0, c1, c2`. Trình đọc nay nhận cả dạng này
    (`sensors/sentinel1/burst.py`, có test).
- **SBAS, ba lần chạy** trên cùng chồng ảnh:

  | Lần | Thiết lập | Số điểm | Trạm ≤ 300 m | So với MintPy tại trạm |
  |---|---|---|---|---|
  | v1 | 2 × 8 look, ngưỡng 0,7 / 0,3 | 33.984 | 9 / 28 | r = 0,81, hệ số góc 0,42 |
  | v2 | 4 × 16 look, 0,5 / 0,2 | 62.452 | 26 / 28 | r = 0,93, hệ số góc 0,61 |
  | v3 | như v2, bỏ hiệu chỉnh pha–độ cao theo từng cặp | 61.999 | 26 / 28 | r = 0,96, hệ số góc 0,75 |

  - Mỗi tháng một ngày nên cặp ngắn nhất là 24–60 ngày. Ruộng lúa mất độ kết hợp trong khoảng đó, nên với 2 × 8
    look gần như không giữ được vùng nông nghiệp.
  - Hiệu chỉnh tầng đối lưu phân tầng theo từng cặp lấy mất một phần phễu lún, vì phễu thấp hơn thềm tham chiếu.
    Đây là phát hiện C7 đầu tiên về một mặc định của GeoEyes.
- **GNSS** (NGL, phương đứng, 3 trạm trong AOI: DNAN, GUKN, S103).
  - v3 lệch −5,8 mm/năm: bản thân vùng tham chiếu Douliu đang lún. Sau khi trừ độ lệch, RMS 1,9 mm/năm. Tại DNAN:
    GNSS −11,9, GeoEyes −14,4, MintPy −22,3 mm/năm.
  - Sản phẩm MintPy quỹ đạo lên so với 31 trạm NGL: trung vị +3,3, RMS khoảng 21 mm/năm sau khi trừ độ lệch
    (HUWE +31).
  - Vậy hệ số góc 0,75 so với MintPy chủ yếu là do MintPy quỹ đạo lên ước lượng quá mức, khớp với chênh lệch
    lên − xuống −7,7 mm/năm ở C1.
  - Chỉ có 3 trạm: đây là dấu hiệu, chưa phải kiểm định.
- **v3 là sản phẩm quỹ đạo lên dùng tiếp**: `choshui_s1_sentinel1-asc-069_20151204_20260609_v3`, độ lệch GNSS
  −5,8 mm/năm.
- **Dữ liệu quỹ đạo xuống.** Thô 579 file, khoảng 56 GB (đã xóa sau khi dựng chồng ảnh). Chồng ảnh 131 ngày
  (2015-01 → 2026-06), khoảng 27 GB. Trong quá trình đó tìm và sửa hai lỗi của engine:
  - Ở 53 ngày, ba burst của AOI nằm trong hai slice liên tiếp của cùng một datatake. Bộ dựng chồng ảnh chỉ giữ một
    thư mục mỗi ngày nên bỏ các ngày đó vì cho là thiếu burst. Nay nó đọc cả các slice khác của datatake
    (`processing/stack/native/s1_stack.py: datatake_slices`, `aoi_burst_ids`; có test). Chỉ 2017-11-01 thực sự
    thiếu (ASF chỉ có hai trong ba burst).
  - Ba ngày nằm ngoài ống quỹ đạo: 2015-04-22 (B⊥ −248 m), 2024-04-10 (−435 m), 2025-05-05 (−397 m). Trong ngưỡng
    150 m, chúng chỉ nối được với các ngày khác bằng cặp 786–1260 ngày, vốn mất kết hợp, nên mọi pixel mất các ngày
    này và hai lần chạy đầu ra 0 điểm. SBAS nay bỏ các ngày thuộc một nhánh mạng mà cặp dài tối đa một năm không
    với tới, nếu nhánh đó nhỏ (ít hơn max(3, 10 %) số ngày) (`processing/sbas/runner.py: baseline_outliers`; có
    test). Mạng quỹ đạo lên không bị ảnh hưởng.
- **Độ kết hợp quỹ đạo xuống thấp.** Trung vị coherence mỗi cặp 0,13–0,23 ở 4 × 16 look, cả trên thềm tham chiếu;
  nguyên nhân hợp lý là sương ở lượt bay 05:50 giờ địa phương (quỹ đạo lên: khoảng 18:00). Ở 223 trên 378 cặp,
  vùng tham chiếu 3 × 3 có ít hơn 3 pixel hợp lệ và cả cặp thành NaN. SBAS nay lùi về cửa sổ 11 × 11 (khoảng
  600 m) quanh cùng điểm; cả 378 cặp đều được tham chiếu.
- **SBAS quỹ đạo xuống v1** (thiết lập v3 của quỹ đạo lên, 128 ngày, 378 cặp, cặp dài nhất 396 ngày):
  76.077 điểm, temporal coherence p50 0,77 / p90 0,91; tỷ lệ cặp có giá trị thấp (p50 0,19, p90 0,84), nên các
  điểm là khoảng một phần năm diện tích có độ kết hợp tốt.
  - Tại các trạm so với MintPy quỹ đạo xuống: 25 / 28, r = 0,905, hệ số góc 0,50.
  - **Phễu lún ở quỹ đạo xuống bị nông.** Tốc độ quy về phương đứng (LOS / cos θ) tại các trạm, GeoEyes xuống so
    với GeoEyes lên v3: hệ số góc 0,61 (r = 0,94). MintPy xuống so với MintPy lên: 0,88. Ở tâm phễu GeoEyes xuống
    cho khoảng −24 mm/năm, quỹ đạo lên khoảng −35 (XIUTAN −19 so với −36).
  - GNSS: ERLN (trong phễu, −32,9 mm/năm phương đứng) chỉ được +1,3 ở quỹ đạo xuống; DNAN −6,3 so với −10,5; JSAN
    +6,2 so với +0,7. Độ lệch hiệu chỉnh (−14,6 mm/năm) bị ERLN chi phối nên không dùng.
  - Giả thuyết chính: trong phễu, độ kết hợp thấp để lại ít cặp cho mỗi pixel và mặt nạ closure (che 9,6 triệu giá
    trị) giữ chủ yếu các cặp ngắn; lỗi unwrap hoặc thiên lệch về các pixel có độ kết hợp tốt (lún ít hơn) trong
    mỗi khối làm dẹt tốc độ. Kiểm tra tiếp, rẻ trước: số cặp và tỷ lệ closure sai của từng pixel trong phễu; chạy
    8 × 32 look; `min_pair_coherence` 0,15.
  - **Sản phẩm quỹ đạo xuống chưa dùng được cho C3.**
  - **Chẩn đoán (cùng ngày).**
    - Hạng của mạng từng pixel: bác bỏ. Mỗi điểm nay ghi `n_pairs` và `rank_deficit` (số khoảng mà các cặp hợp lệ
      của nó không nối; lời giải chuẩn nhỏ nhất kéo vận tốc ở đó về 0). 63 % số điểm thiếu hạng, nhưng trong phễu
      các điểm đủ hạng cũng nông như các điểm khác (HONGLUN −22,3 so với −19,1, TUKU −20,6 so với −21,0).
    - Thiên lệch pha của cặp ngắn ("fading signal"): đúng một phần. Theo giai đoạn, tỷ lệ xuống / lên là 0,53 năm
      2018–2020 (có S1B, cặp 12 ngày) và 0,88 năm 2021–2022 (không còn S1B; kỳ vọng 0,91 với lún thuần đứng). Với
      `[network.sbas] min_temporal_days = 48` (tùy chọn mới; 375 cặp, trung vị 96 ngày; desc v3, 52.111 điểm,
      temporal coherence p50 0,62), hệ số góc đứng xuống / lên tăng từ 0,61 lên 0,70 (r = 0,96), XIUTAN từ −19 lên
      −31 mm/năm.
    - Vẫn là 0,70 chứ chưa gần 1: thiên lệch chỉ giải thích một phần. Quỹ đạo lên còn giữ cặp 24 ngày và có thể
      mang cùng thiên lệch; kiểm tra tiếp là chạy quỹ đạo lên với cùng ngưỡng 48 ngày, rồi so tỷ lệ xuống / lên của
      hai lần chạy đã bỏ cặp ngắn.
    - **Asc v4 (cùng ngưỡng 48 ngày, 06/11/2026).** 368 cặp, 38.241 điểm (v3: 61.999); số trạm có ≥ 3 điểm trong
      300 m: 29 (v3: 37; mất XIUTAN). Tốc độ tại các trạm gần như không đổi: hệ số góc asc v4 / asc v3 qua gốc =
      1,02 (r = 0,98; HONGLUN −35,2 → −34,7, TUKU −39,4 → −39,3 mm/năm). **Quỹ đạo lên không mang thiên lệch cặp
      ngắn trong tốc độ**; bỏ cặp 24 ngày chỉ làm mất điểm.
    - Desc v3 / asc v4, quy về phương đứng tại 22 trạm: hệ số góc OLS 0,83, qua gốc 0,80, r = 0,95 (desc v3 / asc v3
      cùng cách tính: 0,76 / 0,85). Theo giai đoạn, qua gốc: 0,75 (2016–17), 0,73 (2018–20), 0,92 (2021–22), 0,84
      (2023–26). Giá trị trạm là trung vị các điểm trong 300 m (khác script cho con số 0,70 ở trên).
    - Như vậy còn khoảng 0,8, và vẫn thấp nhất trong những năm có S1B. Còn hai cách hiểu: thiên lệch còn lại của quỹ
      đạo xuống (chu kỳ 12 ngày vẫn đi vào qua các cặp 48–96 ngày của lượt bay rạng sáng có độ kết hợp thấp), hoặc
      chuyển động ngang thật hướng vào phễu, làm tăng giá trị quy về phương đứng của một quỹ đạo và giảm của quỹ đạo
      kia. Phân tách asc + desc ở C3 sẽ tách được: thiên lệch cho trường đông–tây không có dạng hướng tâm của phễu.
    - Tốc độ tại trạm của cả bốn lần chạy: `studies/choshui_gw/c2_station_rates_v4.csv`.
    - ERLN (GNSS −32,9 mm/năm) lệch xa mọi sản phẩm InSAR (GeoEyes desc v3 khoảng +3, MintPy asc −18,8): nhiều khả
      năng là hiệu ứng cục bộ của mốc; chưa dùng làm trọng tài cho tới khi kiểm tra.
- **Khoảng trống 2022** (168 ngày) được nối bằng các cặp thường dài tối đa 396 ngày; closure không bỏ cặp nào.
- **Tham chiếu và ramp.**
  - SBAS: `reference` đặt trên thềm Douliu, kiểm tra với các trạm có mực nước phẳng.
  - PSI: `scla_deramp = "auto"` với `deramp_non_defo` trên cùng vùng đó.

### C3. Thành phần đứng và đông–tây (điểm duyệt)

- `geoeyes decompose` cho mỗi cặp sản phẩm (của mình, của MintPy), trên lưới chung và ngày chung (gom 12 ngày).
- Thành phần bắc–nam không giải được; phần rò của nó được chặn bằng thành phần ngang của GNSS.
- **Điểm duyệt:** bản đồ và chuỗi thành phần đứng, đông–tây tại các giếng; độ bất định của chúng.

### C4. Liên hệ tại các trạm giếng (điểm duyệt)

Đăng ký trước khi chạy. Ở mỗi trạm có chuỗi chuyển dịch đứng và mực nước:
1. **Phần theo mùa (đàn hồi):** lọc dải (0,5–2 chu kỳ/năm) cả hai chuỗi; tỷ số biên độ và độ lệch pha theo từng
   tầng; S_ke·b = Δb / Δh kèm khoảng bootstrap. Tiêu chí: độ lệch pha nhất quán giữa hai track và với pha của mực
   nước (nếu không, chuyển dịch theo mùa là do tầng đối lưu, §6).
2. **Phần dài hạn (không đàn hồi):** tốc độ nén so với thời gian mực nước nằm dưới mức thấp nhất lịch sử; S_kv·b ở
   nơi mực nước xuống mức thấp mới.
3. **Tầng nào:** hồi quy chuyển dịch đứng theo mực nước các tầng 1–4 (có trễ, hệ số không âm), so sánh bằng kỹ năng
   kiểm chéo theo năm; báo cáo tỷ lệ phương sai của từng tầng.
4. **Đối chứng:** các trạm có mực nước gần như không đổi (phải có ít chuyển dịch), và các điểm nằm giữa các trạm.
- Thống kê: chia khối theo năm (không chia ngẫu nhiên), khoảng tin cậy bằng block bootstrap, ghi số trạm đứng sau
  mỗi con số.
- **Điểm duyệt:** bảng theo trạm và tầng; bản đồ S_ke·b, S_kv·b, độ trễ; H1–H3 được trả lời hay chưa.

### C5. Phân bố không gian (điểm duyệt)

- Nội suy các tham số của C4 (kèm độ bất định) trên toàn quạt; so với vị trí từ đỉnh quạt ra bờ biển và với bề dày
  sét nơi có nhật ký lỗ khoan.
- Hạ tầng: `geoeyes lines` dọc đường sắt cao tốc và các đê chính, với tiêu chí biến dạng mới (thay đổi độ dốc,
  [lines-and-consolidation.md](lines-and-consolidation.md)).
- Chuyển dịch đông–tây so với tâm các phễu hạ thấp mực nước (Q5).
- **Điểm duyệt:** các bản đồ, và danh sách những mẫu hình đúng ở cả hai sản phẩm và cả hai track.

### C6. Dự báo và kịch bản (điểm duyệt)

- Mô hình chuyển dịch đứng theo mực nước cho từng trạm: đàn hồi + không đàn hồi (trễ theo mức thấp nhất lịch sử),
  có thể thêm khuếch tán 1-D trong lớp cách nước với τ từ C4.
- Kiểm định: các năm giữ lại 2023–2024 và các trạm giữ lại (khối không gian), so với mốc là xu hướng tuyến tính.
- Kịch bản: mực nước giữ ở mức 2024, hồi phục 1 m/năm, tiếp tục hạ theo tốc độ 2015–2024.
- **Điểm duyệt:** bảng kỹ năng kèm khoảng tin cậy (H4), bản đồ kịch bản kèm độ bất định.

### C7. Xử lý của mình làm gì với tín hiệu (điểm duyệt)

- Với mỗi phương án (MintPy như được giao; GeoEyes có và không có APS, ramp `auto` và bỏ ramp tuyến tính toàn phần,
  SBAS và `ps_lite`, chuỗi raw và SCN), đo mức khớp với chuyển dịch mà mực nước dự báo ở C6 tại các trạm: pha và
  biên độ theo mùa, tốc độ dài hạn, đông–tây.
- Dự đoán: bỏ ramp tuyến tính toàn phần làm phễu lún nhỏ lại; SCN trên cửa sổ ngắn bỏ mất chuyển dịch theo mùa
  ([gnss-insar-calibration.md](gnss-insar-calibration.md) G3.1e); hiệu chỉnh tầng đối lưu theo độ cao có thể bỏ
  mất một phần phễu lún nếu phễu tương quan với địa hình.
- **Điểm duyệt:** xếp hạng các phương án theo mức khớp với mực nước; các mặc định cần sửa trong GeoEyes, nếu có.

### C8. Viết kết quả

- Ghi chú kết quả (EN/VI) và, nếu các phát hiện đứng vững, dàn ý một bài báo (xem
  [paper-ideas.md](paper-ideas.md)).

## 6. Rủi ro và yếu tố gây nhiễu

- **Tầng đối lưu theo mùa và mực nước theo mùa.** Mùa mưa ở Đài Loan (tháng 5–9) tạo ra trễ tầng đối lưu theo mùa,
  có thể giống hoặc triệt tiêu chuyển dịch đàn hồi theo mùa. Kiểm tra: pha nhất quán giữa quỹ đạo lên và xuống
  (tầng đối lưu khác nhau giữa lượt bay 6 giờ và 18 giờ), các trạm có mực nước phẳng làm đối chứng, biên độ so với
  địa hình.
- **Mốc cao độ và việc làm lại giếng (2011–2012):** bước nhảy mực nước sẽ trông như sự kiện nén không đàn hồi giả.
- **Gán tầng:** thiếu ống lọc sau khi làm lại giếng; ranh giới các lớp thay đổi trên quạt.
- **Lấy mẫu điểm:** giếng là một điểm, InSAR là trung bình 40 m (hoặc thô hơn); thử bán kính (100–500 m) là một phần
  của C4.
- **Thiếu số liệu đo nén:** không có giếng đo nén nhiều tầng thì "tầng nào bị nén" là suy ra từ mực nước, không phải
  đo được.
- **Ổ đĩa:** D: còn trống 81 GB (2026-11-05); chồng ảnh SLC của toàn khung không vừa (§7).
- **Giấy phép dữ liệu:** dữ liệu được chia sẻ để nghiên cứu; cần hỏi trước khi công bố hình theo từng trạm.

## 7. Tài nguyên

- Ổ đĩa: khoảng 0,14 GB mỗi burst mỗi ngày chụp (đo trên chồng ảnh Quảng Nam). Một vùng lõi 3 burst mỗi track lấy
  mẫu 12 ngày (khoảng 270 ngày chụp tới 2026-06) cần khoảng 110 GB burst thô mỗi track: quá nhiều. Các phương án ở
  C2: 2 burst mỗi track lấy mẫu 24 ngày (khoảng 135 ngày chụp, khoảng 75 GB cho cả hai track, vẫn sát dung lượng
  trống), chồng ảnh từng giai đoạn rồi xóa burst thô sau khi đã chồng, hoặc giải phóng dung lượng trên D:. Quyết
  định ở điểm duyệt C2.
- Tính toán: các engine SBAS và `ps_lite` hiện có; không có gì mới ngoài bộ đọc MintPy (C1) và phân tích liên hệ
  (C4), dùng lại `hazard.coupling`.
- Từ bên cung cấp dữ liệu: ý nghĩa của `model`, mốc cao độ mực nước, ranh giới tầng ở từng trạm, số liệu giếng đo
  nén hoặc thủy chuẩn nếu có, quyền công bố.

## 8. Một phát hiện sẽ trông như thế nào

- "Ở phần giữa quạt, lún dài hạn đi theo mực nước tầng 2–3 với độ trễ N tháng; S_kv/S_ke ≈ K; X % độ nén 2015–2024
  là vĩnh viễn" — kèm khoảng tin cậy và số trạm.
- "Chỉ riêng mực nước đã dự báo được lún 2023–2024 ở các trạm giữ lại trong phạm vi Y mm/năm, tốt hơn xu hướng."
- "Bỏ ramp tuyến tính toàn phần làm mất Z % phễu lún; ramp `auto` có vùng ổn định giữ được nó" — một nhận định về
  phương pháp của mình, do mực nước phân xử.

## 9. Tài liệu tham khảo

Chi tiết cần kiểm trên Crossref trước khi dùng trong bài báo. Danh sách đầy đủ ở bản tiếng Anh
([../../en/research/choshui-groundwater.md](../../en/research/choshui-groundwater.md) §9): Chen et al. 2016;
Galloway & Burbey 2011; Hoffmann et al. 2001; Hung et al. 2010; Smith et al. 2017.
