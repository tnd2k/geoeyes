> Bản dịch tiếng Việt của [`docs/en/research/landslide-susceptibility.md`](../../en/research/landslide-susceptibility.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-11-01.

# Tính nhạy cảm trượt lở kết hợp mưa và InSAR (Việt Nam)

> Ghi chú nghiên cứu kiêm kế hoạch triển khai. Đây là nghiên cứu tách riêng khỏi
> [`rainfall-insar-hazard.md`](rainfall-insar-hazard.md) (phân vùng chuyển dịch *chậm* của mặt đất). Nghiên cứu này
> bàn về trượt lở *nhanh* do mưa kích hoạt, với nhãn lấy từ các danh mục trượt lở. Hai nghiên cứu dùng chung dữ liệu
> (DEM, mưa, sản phẩm InSAR, các lớp chuyên đề) và mã nguồn (`geoeyes.ml.layers.Grid`, kiểm định chéo theo khối không
> gian).
> Trạng thái (2026-11-05): **L0–L5 đã chạy trên vùng thí điểm** (đã chốt các điểm duyệt L0–L3b; L3c đã xong C1, C3,
> C5; L4 và L5 báo cáo ngày 2026-11-03 / 2026-11-04: H2 và H3 không được ủng hộ); L6 đã có mã nhưng chưa báo cáo;
> L5b, L7, L8, L9 chưa bắt đầu (L7 và L9 nay được thay bằng
> [`landslide-forecast-system.md`](landslide-forecast-system.md)). Kế hoạch viết lần đầu ngày 2026-11-01. Mỗi bước
> (§5) kết thúc bằng một lần chủ dự án xem xét kết quả, trước khi bước sau bắt đầu.
>
> **Rà soát 2026-11-05: định hướng.** (1) Phép thử 2025 không còn độc lập (đã dùng để bỏ Hansen và chọn mô hình
> chính): giữ riêng 156 đối tượng đã định ngày mưa (L3b.7), chỉ dùng một lần. (2) Hansen / Landsat không độc lập với
> chiếu sáng (đồng bộ mặt trời ~10:00; các vết nền nghiêng về đông nam), nên B1 không loại trừ hẳn sai lệch chiếu
> sáng. (3) Mẫu âm chỉ lấy trong vùng phủ `near`: hiệu chuẩn và các cấp không có giá trị ngoài miền đã lấy mẫu; ghi
> rõ, hoặc thêm mẫu âm ở ngoài. (4) Ngưỡng L6 không ổn định (116 sự kiện ≤ 5 km, sai số tới 25 km, hai vùng, bỏ ra
> từng năm): báo cáo số sự kiện theo vùng, bootstrap, cân nhắc gộp vùng. (5) H5 / L5b: đếm các vụ trượt về sau
> (kiểm tra độ mạnh) trước khi tốn ổ đĩa.

## Mục lục

1. [Câu hỏi và phạm vi](#1-câu-hỏi-và-phạm-vi)
2. [Tổng quan tài liệu](#2-tổng-quan-tài-liệu)
3. [Dữ liệu](#3-dữ-liệu)
4. [Giả thuyết](#4-giả-thuyết)
5. [Phương pháp: các bước L0–L9](#5-phương-pháp-các-bước-l0l9) (L0–L7, rồi L9, rồi L8; các bước chèn thêm L2a, L2b, L3b, L3c, L5b)
6. [Triển khai trong GeoEyes](#6-triển-khai-trong-geoeyes)
7. [Tham số và căn cứ chọn giá trị mặc định](#7-tham-số-và-căn-cứ-chọn-giá-trị-mặc-định)
8. [Rủi ro và hạn chế](#8-rủi-ro-và-hạn-chế)
9. [Tài liệu tham khảo](#9-tài-liệu-tham-khảo)

---

## 1. Câu hỏi và phạm vi

Bốn câu hỏi, mỗi câu có nhãn riêng:

| | Câu hỏi | Nhãn | Kết quả |
|---|---|---|---|
| **Q1 ở đâu** | Sườn nào bị trượt khi bão đổ bộ? | polygon khối trượt đã khoanh vẽ (Das 2024) | bản đồ tính nhạy cảm, 30 m |
| **Q2 khi nào** | Mưa bao nhiêu thì kích hoạt trượt lở, theo từng vùng? | các sự kiện trượt lở có ngày (`vietnam.csv`) | ngưỡng mưa |
| **Q3 InSAR** | Chuyển dịch của sườn *trước* sự kiện (InSAR) có bổ sung gì cho Q1 không? | cùng bộ polygon | mức tăng độ chính xác, mức độ quan trọng |
| **Q4 sau bão** | Khối trượt đã khoanh vẽ nào còn chuyển động sau bão, và chúng có trượt lại không? (thêm ngày 2026-11-02, theo Sui et al. 2026) | các polygon Molave; các báo cáo sau đó | các nhóm mức hoạt động, có kiểm chứng (L5b) |

Bước cuối ghép Q1 và Q2 thành một chỉ số nguy cơ (ở đâu × khi nào), theo cách của NASA LHASA, và kiểm tra ngược
(hindcast) chỉ số này trên các sự kiện đã được báo cáo.

**Ngoài phạm vi.** Quãng đường trượt và vùng bồi lấp, mức độ phơi nhiễm và rủi ro, và bản thân việc khoanh vẽ khối
trượt (một việc riêng cho bão Yagi, §5 L8). Dịch vụ dự báo vận hành, lúc đầu nằm ngoài phạm vi, nay là mục tiêu (chủ
dự án, 2026-11-03): thiết kế và kế hoạch ở [`landslide-forecast-system.md`](landslide-forecast-system.md) (F0–F9);
ghi chú này cung cấp đầu vào cho nó.

**Thuật ngữ** (Fell et al. 2008): *tính nhạy cảm* = ở đâu (xác suất không gian, không có yếu tố thời gian); *nguy cơ*
= ở đâu + bao lâu một lần hoặc khi nào; *rủi ro* = nguy cơ × mức độ phơi nhiễm × tính dễ tổn thương.

## 2. Tổng quan tài liệu

- **Mô hình thống kê tính nhạy cảm.** Tổng quan của Reichenbach et al. (2018) bao quát hơn 500 công trình. Các
  khuyến nghị của họ được áp dụng ở đây:
  - kiểm định độc lập về không gian;
  - báo cáo rõ danh mục trượt lở và đơn vị bản đồ;
  - dùng ít biến dự báo dễ diễn giải thay vì nhiều biến;
  - nói rõ việc không có khối trượt mang ý nghĩa gì.
- **Kiểm định chéo theo không gian.** Brenning (2005) chỉ ra rằng kiểm định chéo ngẫu nhiên đánh giá quá cao khả năng
  của mô hình tính nhạy cảm, do tự tương quan không gian. Kiểm định chéo theo khối là chuẩn tham chiếu;
  `ml.susceptibility` đã báo cáo cả hai cách.
- **Sai số của danh mục trượt lở.**
  - Cách lấy mẫu: Hussin et al. (2016) cho thấy vị trí lấy mẫu bên trong polygon có ảnh hưởng. Lấy mẫu ở vùng vách
    trượt (vùng khởi trượt) cho một mô hình khác và có ý nghĩa hơn so với lấy tâm hoặc cả polygon, vốn bao gồm cả
    phần vật liệu trượt xuống. (Sửa ngày 2026-11-05: trước đây ghi nhầm là Steger et al. 2016.)
  - Sai số vị trí: Steger et al. (2016) cho thấy sai số vị trí của các polygon đã khoanh vẽ lan truyền vào mô hình
    như thế nào; vì thế có vùng đệm mẫu âm ở L1.
  - Thiếu sót có hệ thống: Steger et al. (2017) cho thấy khi khối trượt được khoanh vẽ thiên về gần đường hoặc ở
    vùng không có rừng, mô hình sẽ học thành "đường gây ra trượt lở".
  - Độ đầy đủ của danh mục kiểm tra được bằng phân bố diện tích – tần suất (Malamud et al. 2004; Guzzetti et al.
    2012).
- **Đơn vị bản đồ.**
  - Ô lưới đơn giản và khớp với DEM.
  - Đơn vị sườn dốc (slope unit; Alvioli et al. 2016, `r.slopeunits`) bám theo cấu trúc thủy văn của sườn và giảm tự
    tương quan. Ở đây chúng là đơn vị thứ yếu.
- **Ngưỡng mưa.**
  - Ngưỡng cường độ – thời đoạn và ngưỡng lượng mưa tích lũy của trận mưa – thời đoạn (E–D): Guzzetti et al.
    (2008), Brunetti et al. (2010; phương pháp tần suất, ngưỡng tại một xác suất không vượt), tái dựng tự động các
    trận mưa CTRL-T (Melillo et al. 2018). Tổng quan: Segoni et al. (2018).
  - LHASA (Kirschbaum & Stanley 2018): một cây quyết định toàn cầu, trong đó cấp tính nhạy cảm (Stanley & Kirschbaum
    2017) được ghép với percentile lượng mưa tích lũy 7 ngày trước đó (IMERG). Đây là mô hình mẫu cho bước ghép ở
    L7.
- **InSAR và trượt lở.** Ma trận hoạt động / cường độ PSI (Cigna et al. 2013), việc tinh chỉnh tính nhạy cảm bằng
  vận tốc PSI (Ciampalini et al. 2016), trượt lở chậm và mưa (Handwerger et al. 2013; Lacroix et al. 2020) đã được
  tổng quan trong [`rainfall-insar-hazard.md`](rainfall-insar-hazard.md) §2.1, §2.3.
  - Ở đây câu hỏi hẹp hơn: chuyển dịch chậm *trước* cơn bão có giúp dự báo nơi xảy ra trượt nhanh *trong* cơn bão
    không?
  - Câu trả lời còn bỏ ngỏ. Nhiều khối trượt nông không có dấu hiệu báo trước, trong khi các biến dạng sườn lớn
    thường có.
  - Tán rừng ở miền Trung khiến việc đo ở băng C rất khó.
  - Hoạt động sau sự kiện của các khối trượt đã khoanh vẽ: Sui et al. (2026) kết hợp khoanh vẽ bằng U-Net trên ảnh
    GF-6 với SBAS-InSAR (27 ảnh Sentinel-1) và mưa trạm cho khoảng 4.200 khối trượt của trận mưa Zixing tháng 7/2024,
    rồi xếp chúng vào các nhóm ổn định / tiềm năng / hoạt động / nhanh. Các tác giả nêu rằng chiếu sáng và bóng địa
    hình ảnh hưởng tới việc khoanh vẽ trên ảnh quang học (xem L2a). Câu hỏi họ để ngỏ, liệu gia tốc InSAR kết hợp
    với mưa tích lũy có tách được khối trượt đang hoạt động với khối trượt có khả năng tái hoạt động hay không,
    được đưa vào nghiên cứu này thành Q4 (L5b), trên các polygon Molave và có câu trả lời cho từng hạn chế của nghiên
    cứu đó. Q4 dùng chung phương pháp với nghiên cứu chuyển dịch chậm
    ([`rainfall-insar-hazard.md`](rainfall-insar-hazard.md)).
- **Việt Nam.**
  - Danh mục của Das (2024) được khoanh vẽ từ ảnh RapidEye và PlanetScope (NC State; AGU 2022).
  - Đề án điều tra toàn quốc của Viện KHĐC&KS đã lập bản đồ điểm trượt tỷ lệ 1:50.000 từ năm 2012, nhưng dữ liệu
    không công khai (xem `inventories/landslide/SOURCES.md`).
  - Chưa tìm thấy công trình đã công bố nào kết hợp danh mục polygon, InSAR và ngưỡng mưa ở Việt Nam.

## 3. Dữ liệu

### 3.1 Danh mục trượt lở (`<workspace>/inventories/landslide/`)

| File | Nội dung | Dùng cho |
|---|---|---|
| `central_vn_das2024.gpkg` | 21.234 polygon và điểm: Ketsana 2009 (8.744), Podul 2013 (915), Molave 2020 (11.575); 107,50–108,44° Đ, 14,31–15,38° B; CC-BY-4.0 | nhãn cho Q1, Q3 |
| `vietnam.csv` / `.geojson` | 235 sự kiện được báo cáo 2007–2026 (NASA GLC 127, tổng hợp 108), 116 sự kiện định vị ≤ 5 km; mỗi sự kiện một ngày | nhãn cho Q2, kiểm tra ngược ở L7 |
| `SOURCES.md` | các bộ dữ liệu mở đã kiểm tra, các lớp GeoServer của Viện KHĐC&KS, những gì không dùng được | — |

Vùng phủ của từng sự kiện, lấy từ bao lõm (concave hull, ratio 0,3) của các khối trượt trong sự kiện đó. Đây
**không phải** vùng đã khoanh vẽ, vốn không được công bố.

| | Ketsana | Podul | Molave |
|---|---|---|---|
| Bao lõm | 5.409 km² | 427 km² | 2.431 km² |
| Phần chồng với Molave | 878 km² (bên trong có 561 khối Ketsana / 6.252 khối Molave) | 88 km² | — |
| Diện tích polygon, trung vị / p95 | 2.198 / 21.579 m² | 925 / 5.175 m² | 1.072 / 11.199 m² |

Bộ Molave nhiều khả năng bao gồm cả chuỗi bão tháng 10/2020:
- Các cơn bão: Linfa, Nangka, Saudel và Molave, từ ngày 6 đến 29/10.
- Rào Trăng 3 sạt ngày 12–13/10, Trà Leng ngày 29/10.
- Bộ này được coi là **tập sự kiện tháng 10/2020**, vì ngày chụp của ảnh dùng để khoanh vẽ không được công bố.

### 3.2 Biến dự báo

Mọi biến dự báo được lấy mẫu trên lưới 30 m `Grid(cell_m=30)` của `geoeyes.ml.layers`. Cột thời điểm cho biết lớp đó
có mô tả trạng thái *trước* mỗi sự kiện hay không (điều kiện để tránh rò rỉ dữ liệu).

| Nhóm | Lớp | Nguồn | Thời điểm | Ghi chú |
|---|---|---|---|---|
| Địa hình | độ cao, độ dốc, hướng sườn (sin, cos), độ cong ngang / dọc, TPI (150 / 500 m), độ chênh cao (300 m), TWI, tích lũy dòng chảy, khoảng cách tới suối | Copernicus GLO-30 (cache `dem/copernicus-30`) | DEM 2011–2015: sau Ketsana, trước Molave; thời gian chụp trùm lên Podul (11/2013) | DEM có thể chứa vết trượt cũ (Ketsana, có thể cả Podul): một sai lệch nhỏ, đã biết |
| Thạch học | lớp thạch học, khoảng cách tới đứt gãy | GLiM (Hartmann & Moosdorf 2012, ~1:3,75 triệu); bản đồ địa chất Việt Nam 1:200.000 nếu có (L0) | không đổi | GLiM thô: ít lớp trên vùng phủ |
| Đất | sét, cát, độ sâu tới đá gốc | SoilGrids 2.0 (250 m); lớp độ sâu tới đá gốc toàn cầu (250 m) | không đổi | thô |
| Lớp phủ | độ che phủ rừng năm 2000, diện tích mất rừng trước năm xảy ra sự kiện | Hansen et al. (2013) Global Forest Change, 30 m | theo sự kiện | WorldCover 2020 (v100) và 2021 (v200) đều không có trước các sự kiện (bản 2020 lấy ảnh cả năm, gồm cả Molave): không dùng |
| Tiếp cận | khoảng cách tới đường | OSM (hiện tại) | hiện tại | đường làm sau sự kiện gây sai lệch cho mô hình; chạy cả có và không có lớp này |
| Mưa (sự kiện) | lượng mưa 3, 7 và 30 ngày trước khi sự kiện kết thúc, theo từng pixel (L4 đã chạy như vậy; điểm duyệt L0 chọn 5, 10 và 30 ngày cho L6) | CHIRPS v3 ngày (0,05°); GPM IMERG Final (0,1°) để đối chiếu | theo sự kiện | khoảng 80 pixel CHIRPS (mỗi pixel ~30 km²) trong bao lõm Molave, khoảng 22 trong vùng thí điểm: kiểm tra như một đại lượng thay thế cho vị trí (L4) |
| InSAR (trước sự kiện) | vận tốc theo hướng dốc, mức ý nghĩa, độ kết hợp theo thời gian (temporal coherence), mật độ điểm, gia tốc theo mùa | Sentinel-1, §3.3 | trước sự kiện | chỉ Molave |

### 3.3 Sentinel-1 trên vùng phủ Molave

Tìm trên ASF, IW SLC, điểm 108,0° Đ 15,0° B, 2016-01-01 → 2020-10-27:

| Track | Hướng bay | 2016 | 2017 | 2018 | 2019 | 2020 | Tổng |
|---|---|---|---|---|---|---|---|
| 55 | quỹ đạo lên | 15 | 23 | 29 | 31 | 25 | 123 |
| 120 | quỹ đạo xuống | 26 | 30 | 31 | 31 | 26 | 144 |

- Có cả hai hình học chụp, chu kỳ lặp 12 ngày từ năm 2017.
- Ketsana (2009) và Podul (2013) xảy ra trước khi có Sentinel-1, nên câu hỏi về InSAR (Q3) chỉ kiểm chứng được trên
  Molave.
- ALOS PALSAR (băng L, 2006–2011) có thể phủ Ketsana; đó là lựa chọn cho sau này, không nằm trong kế hoạch này.

### 3.4 Vùng thí điểm (quyết định tại điểm duyệt L0, 2026-11-01)

Toàn bộ chuỗi L1–L7 chạy trước trên một **vùng thí điểm**, sau đó mới mở rộng. Vùng thí điểm giữ dung lượng tải InSAR
vừa ổ đĩa (mỗi track một burst thay vì 6–8) và vẫn kiểm tra được phương pháp trên cả hai sự kiện.

- **Vùng:** phần giao của hai burst Sentinel-1 `120_256591_IW3` (quỹ đạo xuống) và `055_116074_IW1` (quỹ đạo lên),
  cắt theo vùng phủ `near` của Ketsana và Molave.
  - Phạm vi: 107,60–108,20° Đ, 15,00–15,21° B, 666 km².
  - File: `studies/landslide_central_vn/l0/pilot.gpkg`.
- **Nội dung:**

  | Sự kiện | Vùng phủ trong vùng thí điểm | Khối trượt |
  |---|---|---|
  | Ketsana | 523 km² | 1.111 |
  | Molave | 273 km² | 880 |
  | Phần chồng của hai sự kiện | 130 km² | 207 Ketsana, 444 Molave |

  Podul nằm ngoài vùng thí điểm.
- **InSAR (L5, L5b):** hai năm trước và hai năm sau các cơn bão (quyết định của chủ dự án, 2026-11-02):
  - mỗi track một burst, chu kỳ lặp 12 ngày;
  - L5: 2018-10-01 → 2020-09-30;
  - L5b: 2020-11-01 → 2022-10-31;
  - khoảng 60 ngày chụp cho mỗi giai đoạn và mỗi track, tức khoảng 8,5 GB burst thô mỗi giai đoạn cho track 120 và
    ít hơn một chút cho track 55; số chính xác sẽ đếm bằng ASF ở L5;
  - *số đo thực tế (2026-11-05):* mỗi burst khoảng 0,14 GB, nhưng kho track 120 lưu ba burst IW3 mỗi ngày chụp cho
    vùng thí điểm (khoảng 0,4 GB mỗi ngày; 20 ngày chụp năm 2021 chiếm 8,1 GB), tức khoảng 25 GB burst thô mỗi giai
    đoạn. Phần xử lý tính thêm: dự án L5 24 ngày chụp `quangnam_l5_d120` chiếm 35 GB (chồng ảnh đã đồng đăng ký 21 GB,
    các lần chạy PS / DS 12 GB);
  - làm track 120 trước.
- **Hạn chế của vùng thí điểm:**
  - Với 880 khối Molave, số khối không gian ít: khoảng 70 khối 2 km và 11 khối 5 km. Độ bất định của AUC được báo
    cáo, và H1 không được chấp nhận hay bác bỏ chỉ dựa trên vùng thí điểm.
  - Thạch học ít thay đổi trong 666 km².

## 4. Giả thuyết

- **H1 – địa hình giải thích được "ở đâu".** Một mô hình gồm địa hình, thạch học, đất và lớp phủ tách được vùng khởi
  trượt Molave khỏi các sườn ổn định trong vùng phủ, với AUC kiểm định theo khối không gian ≥ 0,80. Mô hình chuyển
  giao được giữa các sự kiện:
  - huấn luyện trên Ketsana và kiểm tra trên Molave trong phần chồng nhau, AUC giảm dưới 0,05 so với kiểm định chéo
    theo khối của Molave;
  - và chiều ngược lại.
- **H2 – mưa của sự kiện bổ sung cho địa hình.** Lượng mưa tháng 10/2020 theo từng pixel CHIRPS cải thiện AUC trên
  dữ liệu kiểm tra nhiều hơn một trường ngẫu nhiên trơn có cùng tự tương quan không gian. Nếu không, trên một vùng
  nhỏ như thế này mưa chỉ đóng vai trò thay thế cho vị trí (giống `rain_annual_mm` trong `ml.susceptibility`).
- **H3 – InSAR trước sự kiện bổ sung cho địa hình.** Trên các sườn có điểm InSAR, vận tốc theo hướng dốc và độ kết
  hợp trước sự kiện cải thiện AUC trên dữ liệu kiểm tra (bootstrap theo khối có ghép cặp, khoảng tin cậy 95 % không
  chứa 0). Kết quả âm tính vẫn là một kết quả: nó cho biết băng C làm được gì và không làm được gì trên sườn có rừng.
- **H4 – ngưỡng mưa.** Với từng vùng (miền núi phía Bắc và miền Trung), lượng mưa tích lũy trước đó (A10, A30, tính
  bằng percentile so với khí hậu của chính vị trí đó; cửa sổ 5, 10, 30 ngày theo điểm duyệt L0) và cặp E–D tách được các ngày có trượt lở khỏi những ngày mùa
  mưa khác:
  - TSS ≥ 0,4 khi kiểm định bỏ ra từng năm (leave-one-year-out);
  - ngưỡng của hai vùng khác nhau.
- **H5 – mức hoạt động sau sự kiện.** Trong các khối trượt Molave có điểm InSAR, một cách phân nhóm mức hoạt động có
  dùng gia tốc và phản ứng có độ trễ với mưa tích lũy (từ hai năm InSAR sau bão) tách được các khối trượt (hoặc vùng
  xung quanh chúng) trượt lại sau cửa sổ đó (2022-11 → 2026) với các khối còn lại, tốt hơn so với chỉ dùng vận tốc
  trung bình, và tốt hơn so với ngưỡng vận tốc
  cố định như của Sui et al. (2026).

## 5. Phương pháp: các bước L0–L9

Mỗi bước nêu đầu vào, các thao tác, đầu ra, các phép kiểm tra và **điểm duyệt**. Tại điểm duyệt, kết quả được báo
cáo cho chủ dự án, người quyết định có bắt đầu bước tiếp theo hay không.

### L0 — Kiểm tra dữ liệu và vùng phủ

- **Đầu vào:** `central_vn_das2024.gpkg`, `vietnam.csv`, bản ghi Zenodo và tóm tắt AGU.
- **Thao tác:**
  1. **Dùng bộ dữ liệu như đã công bố** (CC-BY-4.0): mọi đầu ra, báo cáo và hình vẽ có dùng bộ này đều trích dẫn
     Das (2024), https://doi.org/10.5281/zenodo.15596033. Vùng đã khoanh vẽ và ngày chụp ảnh không được công bố,
     nên "không có khối trượt" bên ngoài vùng đó là chưa biết. Vì vậy vùng phủ được ước lượng (2) và ảnh hưởng của
     nó được kiểm tra (L3, §8).
  2. Ước lượng vùng phủ:
     - lấy bao lõm của các khối trượt trong từng sự kiện, nới rộng 1 km;
     - chỉ giữ phần đất có độ dốc > 5°;
     - đối chiếu bằng mắt với ảnh PlanetScope / Sentinel-2 của sự kiện (mây, khoảng trống).
  3. Phân bố diện tích – tần suất của từng sự kiện: diện tích tại điểm uốn (rollover) và đuôi luật lũy thừa (Malamud
     et al. 2004). Nó cho biết mỗi danh mục đầy đủ tới diện tích nào, và ba sự kiện có so sánh được với nhau không.
  4. Phần chồng nhau:
     - polygon Molave giao với polygon Ketsana là trượt tái hoạt động; đếm và đánh dấu chúng;
     - các polygon trùng nhau trong cùng một sự kiện là những polygon chạm nhau; kiểm tra xem chúng chung một cạnh
       (bị tách khi khoanh vẽ) hay là các khối riêng.
  5. Kiểm tra khả năng truy cập:
     - CHIRPS v3 ngày (đường dẫn và giai đoạn);
     - IMERG Final ngày (tài khoản Earthdata, đã có trong `sensors/sentinel1/earthdata.py`);
     - các mảnh Hansen GFC (20N_100E);
     - GLiM, đứt gãy, lớp độ sâu tới đá gốc;
     - bản đồ địa chất Việt Nam 1:200.000.
  6. Đếm các burst Sentinel-1 phủ vùng Molave theo từng track và từng ngày, rồi ước tính dung lượng tải (dự kiến vài
     chục GB mỗi track nếu tải theo burst, so với vài TB nếu tải nguyên cảnh SLC).
- **Đầu ra:** `footprints.gpkg` (mỗi sự kiện một polygon, ghi rõ cách tạo), `l0_audit.md` (số lượng, biểu đồ diện
  tích – tần suất, phần chồng nhau, khả năng truy cập dữ liệu, số burst và dung lượng).
- **Điểm duyệt:** vùng phủ được chấp nhận; danh sách các biến dự báo thực sự đọc được.
- **Kết quả điểm duyệt (2026-11-01).** Báo cáo: `studies/landslide_central_vn/l0/l0_audit.md`. Các quyết định sau
  thay thế nội dung của các bước sau ở những chỗ khác nhau:
  1. **Vùng phủ.** Bao lõm của Ketsana chứa những vùng lớn chưa khoanh vẽ, với mép thẳng giống ranh giới cảnh ảnh.
     - Vùng phủ chính: `near` (trong bán kính 1 km quanh khối trượt đã khoanh vẽ, lấp khe hở < 3 km, bỏ vùng phẳng
       > 1 km²).
     - Phương án thử độ nhạy: bao lõm + 1 km, thay cho "bao lõm thu nhỏ 1 km".
  2. **Độ đầy đủ.** Ketsana (RapidEye 5 m) có ít khối trượt dưới khoảng 1.000 m² hơn Molave (PlanetScope 3 m). Phép
     thử chuyển giao ở L3 được chạy thêm chỉ với các khối trượt ≥ 1.000 m².
  3. **Mưa.** CHIRPS v3 theo ngày là tổng 5 ngày được chia theo tỷ lệ mưa ngày của ERA5 hoặc IMERG (ngày UTC), không
     phải sản phẩm ngày độc lập.
     - L6 dựng các trận mưa từ IMERG Final ngày.
     - CHIRPS cho lượng mưa và khí hậu.
     - Cửa sổ mưa tích lũy là 5, 10 và 30 ngày.
  4. **Biến dự báo.**
     - Thạch học lấy từ GLiM độ phân giải đầy đủ (1:3,75 triệu; không tìm thấy bản đồ số mở nào của Việt Nam).
     - Bỏ "khoảng cách tới đứt gãy": GEM chỉ có 4 đoạn gần vùng nghiên cứu.
     - Thêm độ dày đất và regolith sườn đồi của Pelletier et al. (2016) (1 km).
  5. **Ổ đĩa.** InSAR cho toàn bộ vùng phủ Molave cần 70 GB (track 120) và 88 GB (track 55), trong khi chỉ còn 21 GB
     trống. Chuỗi phân tích chạy trước trên vùng thí điểm ở §3.4.

### L1 — Nhãn và mẫu

- **Mẫu dương (vùng khởi trượt).** Với mỗi polygon, trên lưới 30 m:
  - (a) **mặc định**: ô lưới cao nhất bên trong polygon (điểm vách trượt; các cách lấy mẫu được Hussin et al. 2016
    so sánh);
  - (b) các ô thuộc một phần ba trên cùng của khoảng độ cao trong polygon;
  - (c) tâm polygon (chỉ để so sánh: nó trộn vùng nguồn với phần vật liệu trượt xuống).
  - Polygon nhỏ hơn một ô (< 900 m²) chỉ dùng phương án (a).
  - Ba phương án được so sánh ở L3 (AUC và phân bố độ dốc của các mẫu dương).
- **Mẫu âm.** Các ô lưới bên trong vùng phủ của sự kiện, cách mọi polygon của sự kiện đó hơn 60 m (2 ô).
  - Mặc định không lọc theo độ dốc: ô bằng phẳng là mẫu âm dễ. Báo cáo cả khi có và khi bỏ các ô dốc < 5°, vì mẫu âm
    dễ làm AUC tăng giả tạo.
  - Cân bằng 1:1 với mẫu dương, rút 10 lần với các seed khác nhau. Báo cáo trung bình ± độ lệch chuẩn.
  - Toàn bộ vùng phủ cũng được dự báo, để hiệu chuẩn: hiệu chỉnh hệ số chặn của mô hình logistic về tỷ lệ thực
    (prior correction).
- **Trượt tái hoạt động.** Mẫu dương Molave nằm trên polygon Ketsana vẫn được giữ, nhưng đánh dấu (`reactivated`).
  Một phương án bỏ chúng đi cho biết mô hình có chỉ học các vết trượt cũ hay không.
- **Đầu ra:** `labels_<event>.parquet` (ô, x, y, nhãn, phương án, seed, reactivated).
- **Điểm duyệt:** số mẫu dương theo sự kiện và phương án; bản đồ một vài khu vực mẫu kèm polygon, điểm vách trượt và
  mẫu âm.

### L2 — Biến dự báo

- Dựng các lớp ở §3.2 trên `Grid(cell_m=30)` phủ hợp của các vùng phủ, mỗi sự kiện một bảng: lớp phủ và mưa phụ thuộc
  vào sự kiện.
- **Các đại lượng địa hình** từ GLO-30:
  - DEM được lấy mẫu lại một lần sang lưới mét 30 m.
  - Độ cong và TPI được tính trên lưới đó (Zevenbergen–Thorne).
  - TWI là ln(a / tan β), với a lấy từ tích lũy dòng chảy D8.
  - Suối là các ô có tích lũy dòng chảy ≥ 0,5 km² (thử độ nhạy với 0,1 và 1 km²).
- **Đa cộng tuyến:** Spearman |ρ| > 0,8 → giữ biến dễ diễn giải hơn; VIF < 5 cho mô hình logistic.
- **Thạch học:** one-hot, gộp các lớp hiếm (< 1 % vùng phủ).
- **Đầu ra:** `predictors_<event>.parquet`, `predictors.md` (nguồn, phiên bản, tỷ lệ thiếu dữ liệu của từng lớp, bản
  đồ).
- **Điểm duyệt:** bản đồ và histogram của từng lớp; các lớp bị loại và lý do.
- **Kết quả điểm duyệt (2026-11-02).** Báo cáo: `studies/landslide_central_vn/predictors/predictors.md`.
  - 24 lớp trên 1,19 triệu ô.
  - Bị loại khi sàng lọc: `flow_acc_km2` (ρ 0,86–0,90 với TWI), `tree_cover_2000` (với `tree_cover_event`), và
    `tpi_150` đối với mô hình logistic (VIF 5,4–5,8).
  - **Chủ dự án đã chấp nhận (2026-11-02):** `regolith_thick_m` không đưa vào các mô hình L3. Các ô 1 km của lớp
    này nhảy qua lại giữa 0 và mức trần 50 m, và AUC đơn biến chỉ 0,52–0,54. `soil_thick_m` vẫn được giữ.
  - GLiM không mang thông tin ở đây: đá xâm nhập bazơ phủ 84 % vùng thí điểm, và mọi lớp đều có AUC khoảng 0,5.
  - Sét đất (250 m) tách tốt Molave (0,69) nhưng không tách được Ketsana (0,55): có thể chỉ thay thế cho vị trí,
    điều mà các khối không gian ở L3 sẽ kiểm tra.
  - **Hướng sườn** tách Ketsana (AUC theo thành phần bắc–nam 0,33: khối trượt quay về hướng nam) mạnh hơn nhiều so
    với Molave (0,45) trên cùng địa hình. Chủ dự án yêu cầu một nghiên cứu riêng trước L3: **L2a**.

### L2a — Hướng sườn của các khối trượt (thêm tại điểm duyệt L2, 2026-11-02)

**Vì sao.** Hướng sườn là biến dự báo thường dùng cho tính nhạy cảm. Nhưng trong một danh mục khoanh vẽ trên ảnh
quang học, nó có thể mô tả cách khoanh vẽ chứ không phải các khối trượt:
- Sườn quay lưng về phía mặt trời thì tối hơn hoặc nằm trong bóng, nên khối trượt ở đó dễ bị bỏ sót. Liu et al.
  (2018) thấy bóng phủ 34 % vùng nghiên cứu Formosat-2 của họ và khuyến nghị loại vùng bóng khỏi việc lấy mẫu. Sui
  et al. (2026) nêu chiếu sáng và bóng là một hạn chế của việc khoanh vẽ bằng U-Net.
- Nếu sai lệch đó đi vào L3 mà không được xem xét, mô hình sẽ học nơi ảnh sáng, và bản đồ tính nhạy cảm sẽ thừa
  hưởng sai lệch ấy.

**Các dữ kiện làm khung cho nghiên cứu.**
- **Vị trí mặt trời** tại vùng thí điểm (15,1° B), tính cho mùa khô (tháng 10 – tháng 2), khi dễ có ảnh không mây:
  - lúc khoảng 11:00 giờ mặt trời địa phương (RapidEye): phương vị 146–159° (đông nam – nam đông nam), độ cao
    49–62°;
  - lúc khoảng 10:00 (PlanetScope): phương vị 126–142°, độ cao 42–52°.
  - Một sườn chỉ tự che bóng khi quay lưng về phía mặt trời (hướng tây bắc) và dốc hơn độ cao mặt trời, tức 42–62°.
    Ở đây điều đó hiếm (95 % số ô dốc dưới khoảng 40°).
  - Vì vậy nếu chiếu sáng có ảnh hưởng, nó tác động qua ánh sáng yếu hơn và bóng đổ từ dãy núi bên cạnh, chứ không
    phải bóng tự che.
- **Ngày chụp ảnh dùng để khoanh vẽ không được công bố.**
- **Ảnh hưởng mạnh hơn khi mặt trời cao hơn.** Ketsana, khoanh vẽ trên RapidEye (5 m, khoảng 11:00, mặt trời cao
  hơn), lệch mạnh hơn; Molave, khoanh vẽ trên PlanetScope (3 m, khoảng 10:00, mặt trời thấp hơn), lệch yếu hơn. Nếu
  cùng ngày và cùng độ phân giải, chỉ riêng chiếu sáng sẽ cho kết quả ngược lại. Vậy hoặc mùa chụp hay độ phân giải
  của ảnh khác nhau đủ nhiều, hoặc nguyên nhân không phải chiếu sáng. Đây là điều đầu tiên phải giải thích.

**Giả thuyết** (không loại trừ nhau):

| | Giả thuyết | Cùng địa hình, hai sự kiện | Khi xét độ dốc | Điều quyết định |
|---|---|---|---|---|
| A0 | **Nhiễu**: hướng sườn thay thế cho độ dốc, độ chênh cao, độ cong hay vị trí | — | biến mất khi kiểm soát các yếu tố đó | mô hình có điều kiện (2) |
| A1 | **Chiếu sáng lúc khoanh vẽ**: tìm thấy ít khối trượt hơn ở nơi ánh sáng yếu hoặc có bóng đổ | khác nhau (ngày, cảm biến khác) | mạnh nhất trên sườn dốc quay lưng về mặt trời | một số hạng chiếu sáng khớp tốt bằng các hài của hướng sườn, với vị trí mặt trời hợp lý (3) |
| A2 | **Lệch đăng ký tọa độ**: danh mục bị dịch so với GLO-30 (nắn ảnh trên địa hình dốc), nên ô vách trượt rơi sang phía bên kia sống núi | khác nhau (ảnh khác) | — | độ dịch tối ưu khác 0 và làm thay đổi tín hiệu hướng sườn (4) |
| A3 | **Hướng đón bão**: sườn quay về phía gió thổi tới trong lúc mưa lớn nhất nhận nhiều mưa hơn (mưa địa hình) | khác nhau theo gió của từng cơn bão | — | chỉ số đón gió tính từ quỹ đạo bão khớp (5) |
| A4 | **Vật lý của địa hình hay thảm thực vật**: bức xạ, độ ẩm đất, rừng, cấu trúc đá | giống nhau | vẫn còn khi kiểm soát độ dốc | cùng một tín hiệu ở cả hai sự kiện trong phần chồng nhau (6) |

**Dữ liệu.**
- Nhãn của L1 (mẫu dương vách trượt; mẫu âm của vùng phủ chính, 10 lần rút) và các biến dự báo của L2.
- Vị trí mặt trời từ các phương trình vị trí mặt trời của NOAA, cho tháng 9 – tháng 4 × 09:30–11:30 giờ mặt trời
  địa phương.
- Bóng đổ: góc chân trời của từng ô theo phương vị mặt trời, tính từ GLO-30 trên lưới mở rộng.
- Quỹ đạo bão: IBTrACS v04r01, Tây Thái Bình Dương (Knapp et al. 2010), cho Ketsana 2009, Molave và các cơn bão
  khác của tháng 10/2020.
  - Hướng gió tại vùng thí điểm theo từng giờ được tính từ quỹ đạo bằng một mô hình xoáy tham số (Holland 1980):
    gió tiếp tuyến cộng góc thổi vào khoảng 20°.
  - Các ngày mưa lớn nhất lấy từ IMERG ngày, như ở L6.

**Phương pháp.**
1. **Mô tả.** Với mỗi sự kiện:
   - tỷ số tần suất (mẫu dương / mẫu âm) trong 16 cung hướng sườn, qua 10 lần rút, với khoảng tin cậy bootstrap
     theo khối (khối 2 km);
   - biểu đồ hoa hồng theo cấp độ dốc (< 20°, 20–30°, 30–40°, ≥ 40°) và cho cả hai vùng phủ (`near`, `hull`);
   - làm lại chỉ trong phần chồng Ketsana – Molave.
2. **Mô hình có điều kiện.** Mô hình logistic theo độ dốc (spline), độ chênh cao, độ cong và TWI, cộng các hài của
   hướng sườn (sin θ, cos θ, sin 2θ, cos 2θ).
   - Kiểm định tỷ số hợp lý cho các hài.
   - Biên độ và pha của hài bậc một, kèm bootstrap theo khối.
   - Làm lại bằng mô hình logistic có điều kiện với các khối 2 km làm tầng, để loại bỏ ảnh hưởng của vị trí.
3. **Chiếu sáng.** Tính cos i = cos z cos s + sin z sin s cos(φ_mặt_trời − θ) trên một lưới vị trí mặt trời (phương
   vị 90–200°, độ cao 30–70°, bước 5°).
   - Thay các hài bằng cos i, có và không có số hạng cos i × độ dốc, rồi so sánh độ lệch (deviance) và AIC.
   - Báo cáo vị trí mặt trời khớp nhất và xem nó có nằm trong khoảng hợp lý ở trên không.
   - Với vị trí đó, so sánh tỷ lệ mẫu dương và mẫu âm nằm trong bóng đổ.
4. **Dịch chuyển.** Dịch danh mục một đoạn (dx, dy) trong [−90, 90] m, bước 15 m.
   - Tiêu chí: độ dốc trung vị của các ô vách trượt và AUC của độ dốc, vẽ thành mặt theo độ dịch.
   - Làm lại bước 1–2 với độ dịch tốt nhất.
5. **Hướng đón bão.** Chỉ số đón gió w = cos(θ − φ_từ), trong đó φ_từ là hướng gió thổi tới, có trọng số theo
   lượng mưa từng ngày của sự kiện. Chỉ số này thay các hài trong mô hình ở bước 2.
6. **Cùng địa hình.** Mô hình của bước 2 trên phần chồng nhau, có số hạng tương tác sự kiện × hướng sườn. Theo A4
   thì tương tác bằng 0; theo A1–A3 thì khác 0.

**Đầu ra:** thư mục `aspect/` gồm `aspect.json`, `aspect.md`, các biểu đồ hoa hồng, mặt chiếu sáng (độ lệch theo vị
trí mặt trời), mặt dịch chuyển và phép thử đón gió. Code: `landslide/aspect.py`, lệnh `geoeyes landslide aspect`.

**Điểm duyệt (quyết định cho L3):**
- A1 hoặc A2 được ủng hộ:
  - hướng sườn bị đưa ra khỏi các mô hình L3, hoặc đi vào ở dạng đã hiệu chỉnh;
  - mẫu âm được rút ngoài các ô thiếu sáng, như Liu et al. (2018) khuyến nghị cho vùng bóng;
  - với A2, danh mục được dịch lại.
- A3 được ủng hộ: một chỉ số đón gió riêng cho từng sự kiện thay cho hướng sườn và đi cùng lượng mưa của L4.
- A4 được ủng hộ: hướng sườn được giữ như một biến địa hình.
- Không kết luận được: L3 chạy cả có và không có hướng sườn và báo cáo cả hai bản đồ.

**Hạn chế.**
- Ngày chụp ảnh không rõ, nên phép thử chiếu sáng phải ước lượng vị trí mặt trời thay vì biết trước.
- Mô hình chiếu sáng bỏ qua ánh sáng tán xạ và khí quyển.
- Gió từ mô hình xoáy bỏ qua địa hình.
- Với 864 mẫu dương Molave trong vùng thí điểm, biểu đồ hoa hồng 16 cung sẽ nhiễu. Có thể làm lại nghiên cứu trên
  toàn bộ vùng phủ của Das khi L1 và L2 chạy ở đó.

**Kết quả điểm duyệt (2026-11-02).** Báo cáo: `studies/landslide_central_vn/aspect/aspect.md`.

Tín hiệu, sau khi đã tính đến độ dốc, độ chênh cao, độ cong và TWI:
- Ketsana: khối trượt thiên về sườn hướng nam (176,7°, khoảng tin cậy 95 % là 164–188°; odds cao gấp khoảng 6,5 lần
  sườn hướng bắc).
- Molave: yếu, hướng 213°.

| | Kết quả | Căn cứ |
|---|---|---|
| A0 | bác bỏ với Ketsana; tín hiệu Molave phần lớn là do vị trí | Ketsana vẫn có LR 143 khi cố định theo khối 2 km; Molave giảm từ LR 31 xuống 14 và hướng nhảy từ 213° sang 128° |
| A1 | bác bỏ với Molave; Ketsana chỉ khớp một phần | xem bên dưới |
| A2 | bác bỏ | dịch Ketsana 30 m về phía nam làm AUC độ dốc tăng từ 0,70 lên 0,73 nhưng tín hiệu hướng sườn không đổi; Molave không cần dịch |
| A3 | bác bỏ ở dạng mô hình xoáy | chỉ số đón gió khớp kém hơn hẳn các hài, và mang dấu ngược: Ketsana thiên về sườn khuất gió |
| A4 | bác bỏ | trên cùng 130 km², hai sự kiện khác nhau (LR tương tác sự kiện × hài là 28, p = 1,2·10⁻⁵): 146° và biên độ 1,30 so với 203° và 0,62 |

Chi tiết về A1:
- Molave: biên độ giảm khi sườn dốc hơn (0,70 → 0,29), ngược với dự đoán của chiếu sáng.
- Ketsana: biên độ tăng theo độ dốc nhưng ít hơn dự đoán (gấp 1,64 lần so với 2,37 lần). Phương vị mặt trời khớp
  nhất là 175°, nằm ngoài khoảng hợp lý 126–159°.
- Bóng đổ chiếm dưới 2,5 % số ô ở mọi vị trí mặt trời hợp lý.
- Ngay cả trên sườn 2–20°, Ketsana vẫn có biên độ 0,64 (odds gấp khoảng 3,6 lần), trong khi chênh lệch chiếu sáng
  giữa sườn hướng nam và hướng bắc ở độ dốc này chỉ khoảng 1,3 lần.

Khác biệt so với kế hoạch:
- bước dịch là 30 m (theo lưới), không phải 15 m;
- mưa ngày lấy từ CHIRPS v3 bản `sat` (theo nhịp mưa ngày của IMERG) thay cho IMERG ngày;
- thêm hai phép thử: biên độ theo cấp độ dốc, và bóng đổ tại bốn vị trí mặt trời hợp lý.

Giả thuyết mới **A5, thực vật mọc lại trước khi khoanh vẽ**: nếu ảnh Ketsana được chụp nhiều tháng sau bão, vết trượt
trên sườn hướng bắc (râm và ẩm hơn) có thể đã phủ xanh trước và bị bỏ sót.

Quyết định:
- **Mô hình chính ở L3 không dùng hướng sườn**: tín hiệu này gắn với từng sự kiện hoặc từng danh mục và không chuyển
  giao được giữa các cơn bão. Một phương án có hướng sườn chạy song song.
- **L2b** kiểm tra các danh mục bằng nguồn độc lập với việc khoanh vẽ trên ảnh quang học, trước L3.
- **Q4 / L5b** (hoạt động sau sự kiện, theo Sui et al. 2026) được thêm sau L5.

### L2b — Kiểm chứng độc lập các danh mục (thêm tại điểm duyệt L2a, 2026-11-02)

**Vì sao.** L2a chỉ dùng một danh mục cho mỗi sự kiện, nên không phân biệt được "sườn hướng bắc ít trượt hơn" với
"sườn hướng bắc được khoanh vẽ ít hơn". Đây chính là hạn chế số 5 trong bản nhận xét về Sui et al. (2026): một cách
phân loại cần được kiểm chứng độc lập. Các nguồn độc lập với một lần khoanh vẽ trên ảnh quang học:
- Landsat, qua Hansen GFC: mỗi ảnh tổng hợp năm gồm nhiều ngày chụp. *Lưu ý (2026-11-05):* Landsat bay trên quỹ đạo
  đồng bộ mặt trời (khoảng 10:00), nên điều kiện chiếu sáng chỉ đổi theo mùa; đây là một góc nhìn quang học thứ hai,
  không phải một nguồn không phụ thuộc chiếu sáng;
- SAR Sentinel-1: không phụ thuộc ánh sáng mặt trời, và ít bị ảnh hưởng bởi cây mọc lại trong vài tuần đầu.

**Các phép thử.**
1. **Hansen GFC, cho cả hai sự kiện** (B1). Mất rừng trong năm xảy ra sự kiện và năm kế tiếp đánh dấu đất trống mới:
   `lossyear` 9–10 cho Ketsana, 20–21 cho Molave.
   - Bên trong các polygon của Das: tỷ lệ polygon có mất rừng trong năm sự kiện (Landsat thấy vết trượt), theo cung
     hướng sườn.
   - Bên ngoài polygon, trong vùng phủ: mất rừng trong năm sự kiện trên sườn ≥ 15°, theo mảng ≤ 5 ha (vết trượt, không
     phải phát rừng), theo cung hướng sườn. Đây là các vết trượt có thể bị danh mục bỏ sót.
   - Nền so sánh: làm tương tự cho mất rừng trong các năm không có bão lớn (Ketsana: GFC không có 2005–2008 nên dùng
     2011–2012; Molave: 2017–2018).
   - Lấy kiểu phân bố theo hướng sườn của các năm sự kiện trừ đi kiểu của nền (sai khác kép) để tách vết trượt do bão
     khỏi việc phát rừng.
   - Cách đọc kết quả:
     - Vết trượt theo Hansen trải đều mọi hướng trong khi Das thiên về hướng nam: sai lệch của danh mục (A1 hoặc A5).
     - Hansen cũng thiên về hướng nam: nguyên nhân là cơn bão.
2. **Biến đổi Sentinel-1, cho Molave** (B2). Mỗi track một burst (120, 55): ba ngày trước và ba ngày sau chuỗi bão
   tháng 10/2020, ví dụ track 120 vào các ngày 2020-09-11, 09-23, 10-05 và 11-10, 11-22, 12-04 (khoảng 1,7 GB cho cả
   hai track).
   - Biến đổi gồm tỷ số log của σ⁰ trung bình sau so với trước (đã lọc nhiễu đốm, đưa lên lưới 30 m qua lat / lon
     của sản phẩm) và mức sụt giảm độ kết hợp của các cặp vắt qua sự kiện so với các cặp trước sự kiện.
   - Các ô bị chồng lấn (layover) hoặc nằm trong bóng radar của từng track được che đi. Dùng cả hai track sẽ loại bỏ
     sai lệch theo hướng nhìn của SAR.
   - Đo theo cung hướng sườn: tỷ lệ phát hiện các polygon của Das, và các ô biến đổi bên ngoài polygon. Cách đọc như
     ở phép thử 1.
3. **Kích thước** (B3, A5). Biên độ hướng sườn của L2a theo diện tích polygon (< 900, 900–3.000, ≥ 3.000 m²) cho
   từng sự kiện. Nếu do thực vật mọc lại thì tín hiệu phải mạnh hơn ở khối trượt nhỏ; nếu là đặc tính của sườn thì
   không có khác biệt.
4. **ALOS PALSAR cho Ketsana** (B4, tùy chọn). Chỉ kiểm tra có ảnh hay không: ảnh băng L trong khoảng 46 ngày trước và
   sau 2009-09-29 phủ vùng thí điểm (ASF). Nếu có, làm lại phép thử 2 với các ảnh đó.

**Đầu ra:** thư mục `verify/` gồm `verify.json`, `verify.md`, bản đồ các vết trượt từ nguồn độc lập, biểu đồ hoa
hồng. Code: `landslide/verify.py`, lệnh `geoeyes landslide verify`. Các burst Sentinel-1 được lưu vào kho của
workspace như thường lệ (`processing/acquire/s1_bursts.py`).

**Điểm duyệt:**
- Các nguồn độc lập trải đều trong khi Das thiên về hướng nam:
  - hướng sườn tiếp tục nằm ngoài L3;
  - báo cáo L3 ghi rõ danh mục của sự kiện nào bị sai lệch;
  - phép thử chuyển giao Ketsana → Molave được diễn giải có tính đến sai lệch đó;
  - các vết trượt từ nguồn độc lập có thể được thêm làm mẫu dương trong một phương án.
- Các nguồn độc lập cũng thiên về hướng nam: tín hiệu là của cơn bão. Khi đó hướng sườn đi vào L4 như một số hạng
  riêng của từng sự kiện, cùng với lượng mưa.

**Hạn chế.**
- Hansen ghi nhận mất tán rừng trên pixel 30 m: vết trượt nhỏ (dưới một pixel) và vết trượt trên đất không có rừng
  bị bỏ sót, và việc khai thác gỗ vẫn còn lẫn trong các năm sự kiện dù đã có nền so sánh.
- σ⁰ băng C thay đổi ít giữa rừng ướt và đất ướt (khoảng 1–3 dB).
- Mặt nạ SAR loại các sườn dốc quay về phía hoặc quay lưng với từng track, nên mỗi track mất một tập ô khác nhau;
  hai track vẫn cùng phủ phần lớn các sườn dốc vừa. (Sửa ngày 2026-11-05: độ phủ 20 % của track 55 trong kết quả dưới
  đây là do phạm vi chồng ảnh của nó, AOI 15,11–15,21° B và chỉ IW1, không phải do mặt nạ.)

**Kết quả điểm duyệt (2026-11-02).** Báo cáo: `studies/landslide_central_vn/verify/verify.md` (lần chạy bằng cửa sổ
hộp được giữ ở `verify_boxcar.md`).

- **B1 Hansen (bằng chứng chính).** Trong các vết trượt mà Landsat thấy trong các năm sự kiện, Das bắt được:
  - Ketsana: khoảng 40 % ở sườn hướng nam so với khoảng 15 % ở sườn hướng bắc (708 trong 2.454 mảng; LR hướng sườn
    154, p ≈ 10⁻³², hướng 195°).
  - Molave: 20 % so với 11 % (LR 22, p ≈ 10⁻⁴).
  - Bản thân các vết của Landsat có kiểu phân bố theo hướng sườn trong các năm sự kiện giống hệt các năm nền
    (Ketsana: hướng 140° so với 129°, biên độ 0,30 so với 0,30). Vậy cơn bão không ưu tiên sườn hướng nam.
- **B2 Sentinel-1 (không kết luận được).**
  - Hai chồng ảnh (track 120: 9 ngày chụp; track 55: 7 ngày chụp; tháng 8–12/2020), phase linking (adaptive, SHP
    Anderson-Darling).
  - Trên họ SHP, độ kết hợp 36 ngày *trước* bão đã chỉ khoảng 0,10–0,12 (con số 0,30–0,32 của cửa sổ hộp là sai lệch
    dương khi độ kết hợp thấp). Không còn độ kết hợp để mất thêm, và mức sụt bằng 0,00 cả trong lẫn ngoài polygon.
  - σ⁰ chỉ thay đổi khoảng 0,1 dB.
  - Các ô "thay đổi" đi theo hình học SAR: thiên về sườn hướng đông, phía vệ tinh của track quỹ đạo xuống. Track 55
    chỉ phủ khoảng 20 % số ô nên không bù được.
- **B3 kích thước.** Tín hiệu hướng sườn của Ketsana như nhau ở mọi kích thước, nên giả thuyết thực vật mọc lại (A5)
  không được ủng hộ. Của Molave chỉ còn ở khối dưới 900 m².
- **B4 ALOS PALSAR: bỏ.** ASF có hai cảnh PALSAR FBD (2009-08-22, 2009-10-07), nhưng GeoEyes chưa có trình đọc PALSAR
  (ADR-013, thế hệ ALOS còn để ngỏ).

Quyết định (chủ dự án đã chấp nhận):
1. **Tín hiệu hướng sườn là sai lệch của danh mục.** Nó mạnh ở Ketsana và yếu ở Molave; cơ chế chưa xác định được
   (không phải thực vật mọc lại; chiếu sáng chỉ khớp một phần).
   - L3 không dùng hướng sườn trong mô hình chính.
   - Phép chuyển giao Ketsana ↔ Molave được diễn giải với lưu ý rằng Ketsana thiếu vết trượt ở sườn hướng bắc.
2. **Không bổ sung vết Landsat làm mẫu dương.** Các năm nền có khoảng 1.100 mảng mất rừng (phát rừng), gần bằng một
   nửa số mảng của các năm sự kiện.
3. **SAR băng C 36 ngày không kiểm chứng được vết trượt dưới rừng ở vùng này.** Đây cũng là cảnh báo cho L5 / L5b:
   - độ kết hợp DS gần mức nhiễu;
   - độ phủ điểm InSAR trên sườn có rừng sẽ thấp;
   - điểm duyệt độ phủ của L5 (10 % số ô sườn dốc) nhiều khả năng sẽ bị chạm.

### L3 — Mô hình tính nhạy cảm (Q1, H1)

- **Mô hình**, giống `ml.susceptibility`:
  - hồi quy logistic (biến dự báo chuẩn hóa, odds ratio theo mỗi độ lệch chuẩn);
  - random forest và gradient boosting (scikit-learn, trọng số lớp cân bằng).
  - GBM còn được chạy với ràng buộc đơn điệu trên độ dốc và TWI, để kiểm tra tính hợp lý vật lý.
- **Kiểm định:**
  - kiểm định chéo theo khối không gian với khối 2 km và 5 km;
  - kích thước khối được đối chiếu với tầm (range) của semivariogram phần dư (Roberts et al. 2017; như blockCV,
    Valavi et al. 2019); bản thân kiểm định chéo không gian theo Brenning (2005);
  - kiểm định chéo ngẫu nhiên được báo cáo bên cạnh;
  - chỉ số: ROC AUC, average precision, điểm Brier, đường hiệu chuẩn.
- **Chuyển giao giữa các sự kiện:**
  - huấn luyện trên toàn bộ vùng phủ Ketsana, kiểm tra trên Molave trong phần chồng Ketsana – Molave (878 km², 6.252
    khối Molave);
  - sau đó Molave → Ketsana;
  - Podul chỉ là phép kiểm tra thêm (nhỏ).
- **Diễn giải:** mức độ quan trọng theo hoán vị (permutation importance) trên các khối kiểm tra, odds ratio của mô
  hình logistic, phụ thuộc riêng phần (partial dependence) theo độ dốc, độ chênh cao, TWI và thạch học.
- **Các phương án:**
  - các phương án nhãn (a / b / c);
  - có và không có khoảng cách tới đường;
  - có và không có trượt tái hoạt động;
  - có hoặc bỏ mẫu âm dốc < 5°.
- **Đầu ra:** `models/<event>/` (metrics.json, mức độ quan trọng, hiệu chuẩn, raster tính nhạy cảm 30 m chia 5 cấp
  0,2 / 0,4 / 0,6 / 0,8 như `ml.susceptibility`), `l3_report.md`.
- **Điểm duyệt:** H1 có được chấp nhận hay không; lựa chọn mô hình, phương án và kích thước khối dùng cho L4–L7.

**Kết quả (2026-11-02):**
- AUC không gian, khối 2 km: Ketsana 0,74–0,77, Molave 0,73–0,77.
- Khối 5 km: Ketsana 0,71–0,73, Molave 0,64–0,70.
- Kiểm định chéo ngẫu nhiên: 0,76–0,86.
- Tầm tự tương quan của phần dư: Ketsana 2,9 km, Molave 5,4 km. Khối 2 km nhỏ hơn tầm này, nên điểm ở khối 2 km là
  lạc quan.
- Random forest của Molave dựa vào `soil_clay` (SoilGrids, 250 m) và độ cao. AUC của nó rơi từ 0,77 xuống 0,66 khi
  khối tăng từ 2 km lên 5 km, và bản đồ hiện rõ các ô 250 m của SoilGrids. Đây là các biến thay thế cho vị trí.
- Chuyển giao trên phần chồng nhau: Ketsana → Molave 0,705 (logistic), so với 0,761 trong cùng sự kiện. Molave →
  Ketsana 0,627, so với 0,780.
- H1 chưa đạt trên vùng thí điểm.
- Chủ nhiệm yêu cầu làm sâu hơn để có mô hình chính xác hơn, theo hướng của Sui et al. (2026): dùng các khối trượt
  của một đợt mưa về sau làm phép thử. Từ đó có L3b.

### L3b — Hướng tới mô hình chính xác và chuyển giao được (thêm tại điểm duyệt L3, 2026-11-02)

Mục tiêu: mô hình tốt hơn theo thước đo *trung thực*. Thước đo đó là AUC không gian với khối không nhỏ hơn tầm tự
tương quan của phần dư, cộng với phép thử trên các khối trượt mà chưa mô hình nào thấy: một đợt mưa về sau, được
khoanh vẽ độc lập. AUC kiểm định ngẫu nhiên cao hơn không phải là mục tiêu.

**L3b.1 — Các sửa đổi từ điểm duyệt L3**
- **Thước đo chính:** khối 5 km (`[models] blocks_m = [5000, 2000]`). Mô hình tốt nhất và bản đồ được chọn theo
  thước đo này.
- **Bỏ khoảng cách tới đường khỏi mô hình chính:**
  - mức tăng của nó ≤ 0,01;
  - nó dùng đường OSM của hiện tại;
  - nó không chuyển giao được.
  - Biến này vẫn giữ làm một phương án (`with_roads`).
- **Phương án mới:**
  - `no_soil`: bỏ `soil_clay`, `soil_sand`, `soil_thick_m`;
  - `no_height`;
  - `terrain_forest`: chỉ địa hình và rừng.
  - Nếu AUC khối 5 km của một phương án không thấp hơn (trong phạm vi một độ lệch chuẩn), hoặc chuyển giao tốt hơn,
    thì các lớp tương ứng rời khỏi mô hình chính.
- **Chuyển giao:** tính thêm AUC trong cùng sự kiện trên cùng các ô cho mẫu dương ≥ 1.000 m².

**L3b.2 — Địa hình ở tỷ lệ sườn dốc.** Địa hình của L2 ở tỷ lệ ô (30 m). Sự khởi phát trượt phụ thuộc vào cả sườn và
lưu vực phía trên nó, nên các lớp sau được thêm vào `landslide.terrain`:
- `slope_s90`, `profile_curv_s150`, `plan_curv_s150`: độ dốc và độ cong của DEM được làm trơn trên 90 m và 150 m
  (lọc hộp);
- `hand_m`: độ cao so với mạng tiêu thoát gần nhất, theo đường D8 tới ô có diện tích tập trung nước ≥ 0,5 km² (Rennó
  et al. 2008);
- `upslope_slope_deg`: độ dốc trung bình của vùng tập trung nước phía trên (D8, trọng số theo ô);
- `spi`: chỉ số năng lượng dòng chảy ln(a · tan β);
- `tpi_1000`, `relief_1000`: vị trí và độ chênh cao ở tỷ lệ 1 km.

Các lớp này đi qua cùng bước sàng lọc (Spearman |ρ| > 0,8 theo thứ tự ưu tiên; VIF < 5 cho mô hình logistic). L2
được chạy lại; nhãn L1 không đổi.

**L3b.3 — Mô hình gộp.** Huấn luyện một mô hình trên mẫu của cả Ketsana và Molave:
- mỗi hàng giữ trạng thái rừng trước sự kiện của chính nó;
- các fold không gian gom cùng khối cho cả hai sự kiện, để không khối nào nằm trong tập huấn luyện của sự kiện này mà
  lại ở tập kiểm tra của sự kiện kia.
- Kết quả báo cáo theo từng sự kiện và trên phép thử độc lập (L3b.5).
- Câu hỏi: gộp hai sự kiện có cho mô hình chuyển giao tốt hơn từng mô hình một sự kiện không?

**L3b.4 — Sự kiện thứ ba khoanh từ Sentinel-2 (hướng của Sui et al. 2026).** Module mới `landslide/scars.py` khoanh
các vết đất trống mới xuất hiện giữa hai ảnh tổng hợp không mây:
- **Ảnh tổng hợp:** Sentinel-2 L2A từ Earth Search (dữ liệu mở AWS), mảnh 48PYB và 48PZB.
  - Trung vị theo từng điểm ảnh của các quan sát quang đãng (lớp SCL 4 và 5) trong một cửa sổ mùa khô.
  - Kênh đỏ và NIR ở 10 m, SWIR ở 20 m.
- **Ứng viên:**
  - NDVI giảm ≥ `dndvi`, NDVI sau ≤ `ndvi_post`, NDVI trước ≥ `ndvi_pre` (trước đó có thực phủ);
  - độ dốc ≥ 15°;
  - đối tượng liên thông có ≥ `min_px` điểm ảnh.
  - Hình dạng đối tượng: độ kéo dài theo hướng dốc, và vị trí trên sườn (đỉnh cao hơn chân).
- **Hiệu chỉnh trên Molave:**
  - ảnh tổng hợp 2020-01-01 → 2020-10-05 (trước) và 2020-11-15 → 2021-04-30 (sau);
  - ngưỡng được chọn để F1 của các đối tượng so với polygon Molave của Das (2024) trong vùng thí điểm là lớn nhất;
  - báo cáo độ chính xác theo đối tượng, độ đầy đủ theo cấp diện tích, và mức nhầm với phát quang (mất rừng Hansen năm
    2021–2022 tại cùng vị trí).
- **Áp dụng cho 2025:**
  - ảnh tổng hợp 2025-01-01 → 2025-10-20 và 2025-11-20 → 2026-04-30, cùng các ngưỡng;
  - đợt này gồm mưa kỷ lục cuối tháng 10 – tháng 11/2025, bão Kalmaegi, và các vụ sạt được báo chí đưa tin ở Trà
    Leng, Trà Linh, đèo Lò Xo, Phước Thành.
  - Đầu ra: `scars/scars_2025.gpkg` (polygon và vùng đã khoanh vẽ: quang đãng ở cả hai ảnh).
  - Mỗi đối tượng mang độ chính xác kỳ vọng lấy từ bước hiệu chỉnh trên Molave.
- **Sự kiện được báo chí đưa tin:** các tin về sạt lở giai đoạn 2015–2026 trong và quanh vùng thí điểm
  (`inventories/landslide/`, kèm ngày và độ chính xác vị trí) được đối chiếu với các đối tượng của 2025. Chúng cũng
  được giữ lại cho L6.
- Hạn chế:
  - ảnh tổng hợp mùa khô không xác định được ngày của vết trượt trong mùa mưa;
  - phát quang trồng rừng cũng làm mất thực phủ, vì thế cần hiệu chỉnh và ước lượng độ chính xác;
  - bỏ sót các vết dưới 300 m².

**L3b.5 — Phép thử độc lập.**
- Mọi mô hình của L3, L3b.1–L3b.3 được huấn luyện trên Ketsana, Molave hoặc cả hai, rồi dự báo các đối tượng năm 2025:
  - ô vách trượt (ô cao nhất của mỗi đối tượng), đối với mẫu âm rút trong vùng đã khoanh vẽ, cách mọi đối tượng > 60 m;
  - trạng thái rừng trước 2025 (Hansen đến 2024).
- Các điểm từ báo chí được chấm bằng giá trị nhạy cảm cao nhất trong phạm vi độ chính xác vị trí của chúng, so với các
  điểm ngẫu nhiên. Đây chỉ là kiểm tra thô.
- Đây là phép thử quyết định mô hình nào được dùng tiếp cho L4–L7. Một mô hình tốt hơn ở kiểm định chéo nhưng không
  tốt hơn trên 2025 thì không được ưu tiên.

**L3b.6 — Độ tin cậy của danh mục và miền địa hình (chủ nhiệm, 2026-11-02).** Mất thực vật không có nghĩa là trượt
lở, và bản thân Das (2024) là một kết quả giải đoán có độ tin cậy chưa cao. Vì vậy cả hai danh mục được làm sạch theo
cùng các quy tắc địa hình, và mô hình được huấn luyện và chấm điểm chỉ trên các sườn dốc.
- **Đo được trong vùng thí điểm:**
  - polygon Das có ô dốc nhất < 15° trên cả hai DEM: Ketsana 3–4 %, Molave 10–11 %;
  - dưới 20°: Ketsana 8–9 %, Molave 21 %;
  - 20–23 % mẫu âm nằm trên sườn dưới 15°: các mẫu âm "dễ" làm thổi phồng AUC.
- **Cờ độ tin cậy cho mỗi polygon** (Das cũng như Sentinel-2), chỉ dựa vào địa hình:
  - *không hợp lý*: ô dốc nhất < 15° trên cả GLO-30 và AW3D30, hoặc nằm trọn ở đáy thung lũng (mọi ô có HAND <
    5 m) cách dòng chảy có lưu vực ≥ 1 km² trong vòng 30 m (xói bờ; dòng lũ bùn đá khởi phát trên cao rồi chảy
    xuống tới suối thì không bị gắn cờ);
  - *đáng ngờ*: ô dốc nhất 15–20°, hoặc chênh cao trên polygon < 10 m (lấy mẫu DEM 10 m), hoặc có mất rừng Hansen
    vào một năm không có sự kiện tại cùng vị trí (phát quang);
  - *tin cậy*: phần còn lại.
  - Các quy tắc dùng ngưỡng hợp lý về mặt vật lý, không dùng các lớp liên tục của mô hình. Tỷ lệ và bản đồ của từng
    lớp được báo cáo cho mỗi sự kiện.
- **Miền địa hình:** cả mẫu dương *và* mẫu âm chỉ lấy ở các ô có độ dốc ≥ 15° (miền của cảnh báo). Khi đó AUC đo đúng
  điều cần đo — sườn nào sẽ trượt — chứ không phải sườn dốc so với đất phẳng. AUC trên toàn miền vẫn được báo cáo bên
  cạnh.
- **Các phương án:**
  - mô hình chính trên các mẫu dương tin cậy trong miền;
  - mọi mẫu dương trong miền;
  - mọi mẫu dương trên toàn miền (cách làm của L3 / L3b);
  - `no_forest` và `terrain_only`: bỏ các lớp Hansen (câu hỏi của chủ nhiệm, 2026-11-02). Các lớp rừng có trọng số
    nhỏ, và chiều tác động ngược với vật lý (Molave: rừng càng dày, càng nhiều vết trượt được khoanh). Điều này giống
    thiên lệch phát hiện: vết trượt trong rừng dễ thấy, trên đất đã phát quang thì bị bỏ sót. Hansen còn trễ một năm.
    Nếu phép thử 2025 không giảm khi bỏ chúng, các lớp này rời khỏi mô hình chính và chuỗi vận hành chỉ cần địa hình.
  - **Kết quả (chủ nhiệm, 2026-11-02): các lớp Hansen rời khỏi mô hình chính.** Khi bỏ chúng, AUC kiểm định chéo khối
    5 km hầu như không đổi (Ketsana 0,744 → 0,741, gộp 0,753 → 0,728), trong khi phép thử 2025 tăng ở mọi nguồn huấn
    luyện (logistic gộp 0,41 → 0,59 trên toàn bộ đối tượng, 0,69 → 0,83 trên tập strict; miền sườn dốc, vẫn còn lớp
    đất).
  - Phép thử 2025 được chấm theo cùng cách.
- **Hướng sườn, xét lại:** danh mục Sentinel-2 năm 2025 không dùng chung cách khoanh vẽ với Das. Nếu các vết trượt tin
  cậy của nó cũng thiên về cùng hướng sườn như Das-Ketsana, hướng sườn là yếu tố vật lý và được đưa vào mô hình. Nếu
  không, nó vẫn đứng ngoài (L2b).
- **Bộ phát hiện Sentinel-2** được thêm cùng các quy tắc hợp lý về địa hình bên cạnh NDVI, để một vết trượt cũng phải
  trông giống trượt lở về mặt địa hình.

**L3b.7 — Xác định thời điểm của các đối tượng và đối chiếu với InSAR (chủ nhiệm, 2026-11-02).** Một cặp ảnh tổng
hợp mùa khô không cho biết thực vật mất *khi nào*, mà thời điểm lại là thứ phân biệt các quá trình tốt nhất: phát
nương rẫy và khai thác rừng trồng diễn ra vào mùa khô (khoảng tháng 1–4), còn trượt lở xảy ra trong các đợt mưa (tháng
10–11). Thay đổi quang học một mình không phân biệt được vết trượt với vết phát quang; chuyển dịch mặt đất thì có
thể. Các phát hiện dẫn tới bước này (lần chạy L3b.6):
- trong miền sườn dốc, mọi mô hình chấm các đối tượng Sentinel-2 năm 2025 với AUC 0,42–0,55 (toàn bộ đối tượng, lần
  chạy L3b.6 đầu tiên khi còn các lớp Hansen; khi bỏ chúng, logistic gộp đạt 0,59 trên toàn bộ đối tượng và 0,83 trên
  tập strict, xem kết quả L3b.6 ở trên);
- các đối tượng Molave không trùng polygon Das nào được mô hình Ketsana chấm 0,56–0,58, so với 0,72 cho các đối
  tượng trùng. Phần lớn đối tượng không trùng không phải trượt lở.
1. **Ngày mất thực vật của từng đối tượng (chuỗi thời gian Sentinel-2, chi phí thấp).**
   - Với mỗi đối tượng, lấy NDVI của từng cảnh quang đãng (không lấy trung vị) trong hai cửa sổ.
   - Ngày mất thực vật nằm giữa lần quan sát cuối còn thực phủ và lần đầu tiên thấy đất trống.
   - Phân lớp: *trong một đợt mưa* (khoảng thời gian chứa một ngày mưa vượt bách phân vị 95 của mưa ngày IMERG và
     không chứa tháng mùa khô nào), *mùa khô* (nhiều khả năng là phát quang), *không xác định* (khoảng quá rộng).
   - Làm tương tự cho các polygon Das của Molave: đó là một phép kiểm tra độc lập về thời điểm cho Das.
2. **Đối chiếu với InSAR (Sentinel-1, chi phí cao; dùng chung stack với L5 / L5b).**
   - Xử lý (chủ nhiệm, 2026-11-02; vùng nhiều tán xạ phân tán). Chủ nhiệm đề nghị SBAS kết hợp phase linking.
     Khi đó GeoEyes chưa có bộ nghịch đảo SBAS: `method = "sbas"` và `[network.sbas]` là các trường cấu hình chuyển
     từ hệ thống cũ, không đoạn mã xử lý nào dùng tới. *Đã lỗi thời (2026-11-03):* nay đã có engine SBAS
     (`processing/sbas/runner.py`, engine `"sbas"` trong `controller/pipeline.py`) và nó được dùng trong kết quả bước 2
     ở dưới; chuỗi PS / DS chạy song song. Chuỗi xử lý theo kế hoạch ban đầu:
     - phase linking `[phase_linking]` adaptive / `ad`. Nó ước lượng từ mọi cặp giao thoa (toàn bộ ma trận độ kết
       hợp), nhiều hơn mạng đường đáy ngắn của SBAS;
     - `[selection] da_threshold = 0.6` (nới hơn mặc định 0,42);
     - `ds_coherence_min = 0.5`, để các tán xạ phân tán đã liên kết cũng cho ra điểm.
     - Một bộ nghịch đảo SBAS đúng nghĩa (mạng cặp ngắn đã đa nhìn, giải SVD) sẽ là một hạng mục phát triển riêng.
   - Cửa sổ và dung lượng:
     - quỹ đạo 120, IW3, toàn vùng thí điểm (15,00–15,21 N), 2020-11-01 → 2021-10-31 (một năm sau Molave);
     - tối đa hai cảnh mỗi tháng, khoảng 24 ngày ảnh và khoảng 15 GB. *Số đo thực tế (2026-11-05):* khoảng 10 GB
       burst thô (ba burst IW3 mỗi ngày chụp, ≈ 0,4 GB), cộng dung lượng xử lý (dự án L5 24 ngày chụp chiếm 35 GB:
       chồng ảnh 21 GB, các lần chạy PS / DS 12 GB);
     - năm thứ hai của L5b và năm sau 2025 sẽ làm tiếp khi đã đọc kết quả năm đầu.
   - Cho mỗi polygon: số điểm tán xạ bền vững và tán xạ phân tán, vận tốc theo hướng dốc nhất, biến đổi độ kết hợp và
     biên độ tại ngày mất thực vật.
   - *Đang hoạt động* (chuyển dịch vượt ngưỡng ổn định của `hazard.assess`) củng cố giả thuyết trượt lở.
   - *Ổn định nhưng có điểm* là trung tính: nhiều vết trượt nông trượt một lần rồi dừng.
   - *Không có điểm* không nói lên điều gì.
   - Bằng chứng này chỉ nâng độ tin cậy, không bao giờ hạ nó.
3. **Độ tin cậy tổng hợp:**
   - địa hình (L3b.6) + thời điểm (1) + chuyển dịch (2);
   - Das và Sentinel-2 dùng chung một sơ đồ; tỷ lệ mỗi lớp được báo cáo cho từng sự kiện;
   - phép thử 2025 và vòng cập nhật theo mùa của L9 dùng các đối tượng đạt yêu cầu.
- **Kết quả bước 1 (2026-11-02, `landslide/dating.py`, `geoeyes landslide dating`; 164–167 cảnh mỗi cửa sổ):**

  | Đối tượng | mùa mưa | mùa khô | không xác định |
  |---|---|---|---|
  | Sentinel-2, năm Molave, trùng Das | 74 % | 6 % | 20 % |
  | Sentinel-2, năm Molave, không trùng Das | 34 % | 39 % | 27 % |
  | Polygon Das, Molave | 57 % | 5 % | 38 % |
  | Sentinel-2, 2025 | 9 % (156) | 56 % | 35 % |

  - Cách xác định thời điểm hoạt động đúng: các đối tượng trùng Das rơi vào mùa mưa.
  - Das-Molave có ít vùng phát quang (5 % mùa khô).
  - Khoảng một phần ba số đối tượng Molave không trùng Das mất thực vật trong mùa mưa, nhiều khả năng là vết trượt mà
    Das bỏ sót.
  - Phần lớn đối tượng Sentinel-2 năm 2025 là phát quang. Tập thử sạch là 156 đối tượng mùa mưa (tập con
    `rain_dated` của L3b.5).
- **Kết quả bước 2 (2026-11-03, dự án `quangnam_l5b_d120`, T120 IW3, 24 ngày ảnh 2020-11-04 → 2021-10-24):**
  - SBAS (engine mới, looks 4 × 16, IRLS refined, nối đảo): 23.275 điểm, gần như không có điểm trên sườn rừng (560
    điểm trong vòng 100 m quanh polygon Das). Độ kết hợp băng C trên ô 60 m không giữ được qua một năm ở rừng nhiệt đới.
  - PS + DS (phase linking adaptive / `ad`): `da_threshold = 0.6` bị hết bộ nhớ. Nhiễu đốm thuần có D_A ≈ 0,52 nên 0,6
    nhận 23,5 triệu trên khoảng 52 triệu pixel; lần chạy dùng 0,42 cùng DS (độ kết hợp thời gian PL ≥ 0,5). Kết quả:
    2,93 triệu điểm (0,78 triệu DS), khoảng một điểm mỗi ô 30 m kể cả dưới rừng (trung vị độ kết hợp thời gian 0,80 ở
    đất trống, 0,65 ở rừng > 70 %).
  - Độ trải vận tốc (p2–p98 ±16 mm/năm) như nhau ở mọi lớp phủ và độ dốc, trơn trên vài km (lệch 2 mm/năm so với 8
    điểm gần nhất) và không theo độ cao (r = 0,00). Đây là nền khí quyển hỗn loạn / sai số giải chập, không phải chuyển
    động sườn; một năm 24 ảnh chưa đủ để trung bình hoá.
  - Thử trên các polygon Das-Molave: dị thường cục bộ (v trừ trung vị trong ±1,5 km), điểm có độ kết hợp ≥ 0,7, chiếu
    theo hướng xuống dốc. 94 polygon trên sườn ≥ 15° có ≥ 3 điểm; so với chính các polygon đó dịch 1–3 km (1.775 mẫu
    giả): AUC 0,53 (p = 0,18), chỉ polygon tin cậy 0,54 (p = 0,14).
  - **Kết luận:** một năm PS / DS băng C không tách được vết sạt Das khỏi vùng xung quanh. InSAR vẫn là đặc trưng tuỳ
    chọn (không vào mô hình chính). Nếu thử tiếp: năm thứ hai (chuỗi dài hơn), quỹ đạo ascending (hướng nhìn khác),
    hoặc băng L (NISAR / ALOS-2).
- Dung lượng: stack 2 năm cho một burst mỗi quỹ đạo cần khoảng 20–30 GB. Trước bước 2, cần xoá các stack của L2b
  hoặc chuyển stack sang một ổ khác. *Sửa (2026-11-05):* hai năm (~60 ngày chụp) của một quỹ đạo là khoảng 25 GB burst
  thô (ba burst mỗi ngày) và, theo mức của L5 (35 GB cho 24 ngày), cỡ 85 GB dung lượng xử lý nếu chạy một lần; vì
  thế chia đoạn, xoá burst thô và stack của đoạn đã xong.

**Đầu ra:** `scars/` (ảnh tổng hợp, đối tượng, `scars.md`), `models/` (chạy lại với L3b), `l3b_report.md`.

**Kết quả điểm duyệt (chủ nhiệm, 2026-11-02): đã chốt.**
- **Mô hình chính (champion của O4):** random forest trên mẫu gộp Ketsana + Molave (chủ nhiệm chọn RF thay cho
  logistic ngay trong ngày: số hạng độ cao tuyến tính của logistic kéo các khối núi cao về gần 0 trên bản đồ). Chỉ
  polygon tin cậy, miền độ dốc ≥ 15°, GLO-30, **chỉ các lớp địa hình**: bỏ rừng Hansen và SoilGrids, bỏ đường và hướng
  sườn. Hồi quy logistic là challenger.
- Kết quả với polygon tin cậy trong miền, đã bỏ rừng (vẫn còn lớp đất), khối 5 km:
  - Kiểm định chéo: Ketsana 0,740 (RF) / 0,723 (logistic), Molave 0,704, gộp 0,726 / 0,709; tầm phần dư 2,4 / 2,6 km.
    (Các mốc RF trích ở các phần sau, Ketsana / Molave / gộp, khác nhau theo lần chạy: 0,738 / 0,691 / 0,725 ở L3c là
    mô hình chính chỉ địa hình của `models/l3_report.md`, đã bỏ lớp đất; 0,736 / 0,710 / 0,725 ở C1 là khung
    `improve` với 10 lượt rút. Ghi chú 2026-11-05.)
  - Chuyển giao, logistic: Ketsana → Molave **0,728**, so với 0,712 trong cùng sự kiện trên cùng các ô (đạt tiêu chí
    của H1 theo chiều này). Molave → Ketsana 0,661 so với 0,734, giảm 0,073 > 0,05: không đạt (ở L3 là 0,627 so với
    0,780). *Sửa ngày 2026-11-05:* H1 đòi hỏi cả hai chiều, nên chuyển giao chỉ đạt một chiều.
  - Phép thử 2025, logistic gộp: 0,59 trên toàn bộ đối tượng, 0,83 trên tập strict; bỏ lớp đất: 0,60 / 0,84.
- **AW3D30:** giữ làm phương án độ nhạy. Nó tăng kiểm định chéo của Ketsana (0,793) nhưng giảm ở Molave và ở phép thử
  2025.
- **H1 chưa đạt:** chuyển giao chỉ đạt một chiều (Ketsana → Molave; Molave → Ketsana giảm 0,073); AUC không gian
  (0,71–0,74) vẫn dưới 0,80. (Trước ghi "đạt một nửa: đạt về chuyển giao"; sửa ngày 2026-11-05.) Phép thử 2025 chưa quyết định được
  khi các đối tượng Sentinel-2 còn lẫn vết trượt và vùng phát quang (L3b.7 và kiểm tra trực quan).
- Tiếp theo: O1 (kho lớp biến tĩnh trên toàn vùng); InSAR của L3b.7 khi ASF cung cấp burst trở lại (với bộ xử lý SBAS
  mới).

**Điểm duyệt:**
- mô hình chính và tập lớp biến;
- danh mục Sentinel-2 có đủ tốt để làm phép thử hay không (độ chính xác theo đối tượng trên Molave ≥ 0,6);
- H1 có đạt trên phép thử 2025 hay không (AUC ≥ 0,80).

### L3c — Cải thiện random forest của lớp tính nhạy cảm (chủ dự án, 2026-11-03)

**Lý do.** Chủ dự án tạm gác phần mưa (L6) để cải thiện mô hình chính trước: RF gộp đạt 0,725 (khối 5 km; Ketsana
0,738, Molave 0,691), dưới mức 0,80 của H1. Nghiên cứu trước của chủ dự án (Truong et al. 2023, Văn Yên, Yên Bái, RF;
tài liệu tham khảo cần bổ sung) dùng khoảng cách tới sông, đứt gãy và đường, mà mô hình chính chưa có.

**Quy trình cố định (mọi bước đều chấm theo cùng một cách, so với cùng một mốc).**
- Dữ liệu: của mô hình chính (gộp, polygon tin cậy, sườn ≥ 15°, chỉ địa hình), 10 lượt rút mẫu âm.
- Điểm: AUC ngoài fold trên khối 5 km (gộp và từng sự kiện); chuyển giao Ketsana → Molave và Molave → Ketsana; phép
  thử 2025 trên tập strict và tập đã định ngày mưa (L3b.5).
- Một thay đổi được giữ khi AUC gộp ở khối 5 km tăng ≥ 0,01, khoảng tin cậy 95 % của bootstrap theo cặp trên các khối
  5 km (1.000 lần) nằm trên 0, và không chiều chuyển giao nào giảm quá 0,01. Mức tăng nhỏ hơn được báo cáo, không áp
  dụng.

**Các bước (mỗi bước kết thúc bằng một báo cáo ngắn; chủ dự án quyết định trước bước sau).**
1. **C1 — Khung so sánh và tinh chỉnh.** Phép so sánh theo cặp trong mã (`landslide/improve.py`), rồi tinh chỉnh tham số
   RF bằng CV không gian lồng nhau (fold bên trong theo khối): `max_features` (sqrt, 0,2–0,6), `min_samples_leaf`
   (1–50), `max_depth`, `max_samples` (0,3–1,0), 500–1.000 cây. Tham số mặc định (300 cây, lá 5, sqrt) chưa từng được
   tinh chỉnh.
2. **C2 — Chọn biến theo không gian.** Chọn tiến chấm bằng CV không gian (Meyer et al. 2018, 2019): các lớp chỉ giúp
   với fold ngẫu nhiên là lớp mô tả vị trí (độ cao, địa hình 1 km) và làm giảm chuyển giao. Bộ biến được chọn được so
   với bộ đầy đủ trên chuyển giao và phép thử 2025.
3. **C3 — Thêm địa hình.** Các lớp phổ biến trong tài liệu mà ở đây chưa có: độ gồ ghề (TRI) và VRM; geomorphons (lớp
   dạng địa hình, Jasiewicz & Stepinski 2013) ở 150 / 500 m; chỉ số hội tụ; khoảng cách tới đỉnh và tới đường phân
   thuỷ; chiều dài sườn / hệ số LS; độ dốc và độ cong ở nhiều tỷ lệ hơn (60, 90, 150, 300 m). Mỗi nhóm vào như một khối
   và được chấm theo quy trình.
4. **C4 — Khoảng cách tới sông, đứt gãy và đường (bộ biến của chủ dự án).**
   - Sông: giữ bắt buộc `dist_stream_*` (bước sàng lọc đã loại nó ở Molave), cộng sông số hoá nếu chủ dự án có.
   - Đứt gãy: khoảng cách và mật độ (1 km) từ bản đồ địa chất 1:200.000 / 1:50.000 của chủ dự án nếu có; dự phòng là
     lineament từ DEM cộng GEM Global Active Faults, ghi rõ là biến xấp xỉ.
   - Đường: chỉ các đường đã có trước mỗi sự kiện (lịch sử OSM, hoặc đường vẽ trên ảnh Landsat năm trước). Đường hiện
     tại vẫn không dùng (điểm duyệt L3).
5. **C5 — Nhãn và cách lấy mẫu.**
   - Mẫu dương: scarp (hiện tại) so với nhiều ô trong polygon (một phần ba phía trên, trọng số 1/n mỗi polygon) và
     tâm polygon. Chỉ so trên các phép thử chung, vì AUC CV của các bộ mẫu dương khác nhau không so trực tiếp được.
   - Mẫu âm: tỷ lệ 1 : 1 → 1 : 3 / 1 : 5 với trọng số lớp; mẫu âm tránh các vết sạt chưa được lập bản đồ (đối tượng S2
     của L3b.4 không có trong Das).
6. **C6 — Mô hình chính mới.** Gộp các thay đổi được giữ, chạy lại toàn bộ L3 (`geoeyes landslide fit`), bản đồ, hiệu
   chỉnh xác suất (isotonic trên xác suất ngoài fold, cho 5 cấp của O4), báo cáo.

**Đầu ra:** `models/improve/` (mỗi bước một JSON + markdown, các phép so sánh theo cặp), mô hình chính mới trong
`models/`.

**Điểm duyệt:** bộ biến và tham số của mô hình chính mới; H1 (AUC ≥ 0,80) có đạt được chỉ với địa hình hay không.

**Kết quả C1 (2026-11-03, `geoeyes landslide improve`; `models/improve/c1.md`).** Mốc 0,725 (Ketsana 0,736, Molave
0,710; chuyển giao K → M 0,721, M → K 0,663). Tốt nhất trong 30 cấu hình (lá 20, `max_features` 0,5, `max_samples`
0,5, 500 cây) 0,731: Δ +0,0056 (95 % +0,004 – +0,008), chuyển giao −0,003 / −0,006; ước lượng lồng nhau 0,730. Lá to
và lấy mẫu con luôn hơn lá 1 (0,718). **Không áp dụng** (dưới ngưỡng 0,01): tham số không phải là giới hạn.

**Kết quả C3 (2026-11-03, `--step c3`; `models/improve/c3.md`; RF mặc định).**

| thêm vào 18 lớp của mô hình chính | gộp | Δ (95 %) | K → M | M → K |
|---|---|---|---|---|
| độ gồ ghề (TRI, VRM 150 / 450 m) | 0,730 | +0,0047 (+0,003 – +0,006) | 0,723 | 0,668 |
| dạng địa hình (geomorphons 150 / 500 m, chỉ số hội tụ) | 0,725 | −0,0006 (−0,002 – +0,001) | 0,720 | 0,672 |
| vị trí (vị trí tương đối 500 m / 1 km, chiều dài dòng chảy) | 0,727 | +0,0012 (0,000 – +0,002) | 0,721 | 0,672 |
| xói mòn (hệ số LS) | 0,725 | −0,0001 | 0,721 | 0,668 |
| đa tỷ lệ (độ dốc 150 / 300 m, độ cong 300 m) | 0,726 | +0,0010 (−0,000 – +0,002) | 0,719 | 0,668 |
| cả 18 lớp mới | 0,733 | +0,0072 (+0,005 – +0,009) | 0,722 | 0,673 |

- Không nhóm nào qua ngưỡng 0,01; gộp cả 18 lớp tăng +0,007, chuyển giao M → K +0,010.
- **Nhận định:** địa hình từ DEM 30 m đã bão hoà quanh 0,73. Giới hạn nằm ở chỗ khác: những gì các lớp địa hình không
  thấy (địa chất, đứt gãy, sử dụng đất, đường — C4) và chính nhãn (một ô scarp mỗi polygon, nhiễu khi lập bản đồ — C5).

**Kết quả C5 (2026-11-03, `--step c5`; `models/improve/c5.md`).** Mỗi biến thể được huấn luyện trên các dòng của riêng
nó, rồi chấm điểm trên các dòng của mô hình chính (ô scarp và các ô âm của chúng), trên cùng các block 5 km. Vì vậy
phép so sánh là so sánh cặp.

| dòng huấn luyện | + / − | gộp | Δ (95 %) | K → M | M → K |
|---|---|---|---|---|---|
| mô hình chính (scarp, 1 : 1) | 1.487 / 1.559 | 0,725 | — | 0,721 | 0,663 |
| một phần ba phía trên, trọng số 1/n | 2.756 / 1.559 | 0,704 | −0,022 (−0,027 – −0,018) | 0,701 | 0,641 |
| tâm polygon | 1.469 / 1.559 | 0,558 | −0,167 | 0,568 | 0,488 |
| cả polygon, trọng số 1/n | 8.404 / 1.559 | 0,568 | −0,158 | 0,607 | 0,485 |
| ô âm 1 : 3 | 1.487 / 4.663 | 0,727 | +0,002 (0,000 – +0,004) | 0,727 | 0,668 |
| ô âm 1 : 5 | 1.487 / 7.750 | 0,727 | +0,002 (−0,001 – +0,003) | 0,728 | 0,667 |
| ô âm tránh vết Sentinel-2 chưa lập bản đồ | 1.487 / 1.526 | 0,726 | +0,001 (−0,001 – +0,002) | 0,721 | 0,659 |

- Không giữ biến thể nào. Ô scarp là nhãn dương đúng:
  - mô hình học trên tâm hoặc cả polygon học vùng trượt xuống và vùng tích tụ, nên xếp hạng ô khởi phát gần như ngẫu
    nhiên (đúng như phép so sánh cách lấy mẫu của Hussin et al. 2016 gợi ý);
  - tập chấm điểm là ô scarp, nên theo cách thiết kế đã có lợi cho cách huấn luyện bằng scarp. Tuy vậy mức giảm
    (−0,16) lớn hơn nhiều so với hiệu ứng đó.
- Thêm ô âm hay làm sạch ô âm đều không thay đổi gì, nên cách lấy mẫu không phải là giới hạn. Chỉ có 36 ô âm kiểm tra
  của Molave nằm trên vết sạt chưa lập bản đồ.
- **L3c đến nay:** tham số (C1), địa hình (C3) và nhãn (C5) đều đã hết dư địa quanh 0,73. Đòn bẩy còn lại là thông
  tin mà các lớp đang thiếu: địa chất và đứt gãy (C4).

### L4 — Mưa của sự kiện làm biến dự báo (H2)

- **Bản đồ mưa** theo từng pixel CHIRPS cho tháng 10/2020: tổng lượng mưa 3, 7 và 30 ngày trước 2020-10-29, và lượng
  mưa ngày lớn nhất. (Đã chạy như vậy, 2026-11-03; các cửa sổ 5 / 10 / 30 ngày theo pentad của điểm duyệt L0 áp dụng
  cho L6.)
  - Làm tương tự với IMERG, để kiểm tra kết quả không phụ thuộc vào sản phẩm mưa.
  - Làm tương tự cho Ketsana (quanh 2009-09-29) và Podul (quanh 2013-11-15), phục vụ chuyển giao.
- Đưa bản đồ mưa vào mô hình L3. Khó khăn nằm ở khía cạnh không gian: chỉ có khoảng 80 pixel trên bao lõm
  Molave, khoảng 22 trên vùng thí điểm (sửa ngày 2026-11-05; trước ghi "khoảng 120").
- **Phép thử đối chứng:**
  - thay mưa bằng 100 trường Gauss ngẫu nhiên có cùng variogram;
  - H2 chỉ đúng nếu mức tăng nhờ mưa thật vượt percentile 95 của các mức tăng nhờ trường ngẫu nhiên.
  - Dùng khối 10 km để mỗi khối chứa trọn các pixel mưa.
- **Đầu ra:** `l4_report.md` (Δ AUC, phân bố đối chứng, phụ thuộc riêng phần theo mưa).
- **Điểm duyệt:** giữ mưa trong mô hình không gian, hay chỉ dùng mưa theo thời gian (L6–L7).

**Kết quả (2026-11-03, `landslide/rain.py`, `geoeyes landslide rain`; báo cáo `rain/l4_report.md`).**
- CHIRPS v3 ngày `sat`, 10 × 17 pixel trên lưới (có đệm); riêng vùng pilot khoảng 22 pixel (666 km², mỗi pixel
  ~30 km²; khoảng 50 trong khung bao), không phải 120 (sửa ngày 2026-11-05; trước ghi "khoảng 65"). Mưa
  tương đối so với trung bình của sự kiện (`rain_*_rel`) trên dữ liệu của mô hình chính (gộp, polygon tin cậy, sườn
  ≥ 15°; 3.035 mẫu mỗi lượt, 5 lượt). Cả hai sự kiện có cùng một gradient trơn, mưa tăng về phía đông bắc (Molave 30
  ngày 438–1.729 mm).
- AUC ngoài fold, random forest, khối 10 km / 5 km: địa hình 0,720 / 0,726; + mưa tương đối 0,757 / 0,777; + mưa mm
  0,770 / 0,783; chỉ mưa 0,646. Logistic: 0,696 → 0,713.
- Phép thử loại trừ (100 trường ngẫu nhiên hoá pha, cùng variogram): mức tăng của mưa thật +0,037, trung bình của
  trường giả +0,021, phân vị 95 % +0,058, p = 0,23. **H2 không đạt**: bất kỳ trường trơn nào cỡ này cũng tăng gần bằng,
  vì nó đóng vai trò toạ độ (khối CV nhỏ hơn gradient mưa).
- **Đề xuất cho điểm duyệt:** mưa không vào mô hình không gian; mưa dùng theo thời gian (L6–L7: ngưỡng trên chuỗi mưa
  ngày để dự báo). Chưa chạy IMERG (môi trường chưa có `icechunk`; 0,1° chỉ khoảng 21 pixel trên bao lõm Molave, ~6 pixel trên
  vùng thí điểm, còn ít thông tin hơn).

### L5 — InSAR trước sự kiện (Q3, H3)

- **Chồng ảnh:**
  - Sentinel-1 track 120 (quỹ đạo xuống) trước, sau đó track 55 (quỹ đạo lên).
  - Giai đoạn 2018-10-01 → 2020-09-30: hai năm (Barra et al. 2017 yêu cầu ≥ 1,5 năm). Giai đoạn này kết thúc trước
    các cơn bão tháng 10: **không ảnh nào sau 2020-10-05 được đưa vào biến dự báo**.
  - Chỉ các burst phủ vùng Molave (`processing/acquire/s1_bursts.py`).
- **Xử lý:** điểm tán xạ phân bố với phase linking (shp_test `ad`, estimator `adaptive`, mặc định của dự án). Tạo
  sản phẩm như thường lệ, rồi chạy phân tích nguy cơ để có vận tốc theo hướng dốc (`hazard/assess.py`: chiếu theo
  hướng dốc nhất, ngưỡng ổn định, gia tốc theo mùa).
  - Khi có đủ hai track: tách thành phần 2-D theo
    [`two-geometries-and-soft-soil.md`](two-geometries-and-soft-soil.md).
- **Kiểm tra độ phủ trước:**
  - lập bản đồ các ô (100 m, như phân tích nguy cơ) có ≥ 3 điểm, chia theo cấp độ dốc và độ che phủ rừng;
  - **nếu ít hơn 10 % số ô sườn dốc trong vùng phủ có điểm, H3 chỉ được kiểm chứng trên tập con đó và kết quả được
    ghi rõ như vậy.**
- **Đặc trưng cho mỗi ô 30 m**, lấy từ ô 100 m chứa nó:
  - vận tốc theo hướng dốc;
  - `moving` (|v| ≥ 2σ, Barra et al. 2017);
  - độ kết hợp theo thời gian và mật độ điểm;
  - gia tốc theo mùa (hệ số k ghép với mưa của `hazard.coupling`);
  - `insar_covered` (0 / 1).
- **Kiểm chứng H3:**
  - mô hình L3 trên các ô có điểm InSAR, có và không có các đặc trưng InSAR;
  - Δ AUC bằng bootstrap theo khối có ghép cặp (1.000 lần lấy mẫu lại);
  - mức độ quan trọng theo hoán vị;
  - tỷ lệ điểm khởi trượt Molave nằm trên ô "moving", so với tỷ lệ đó ở mẫu âm.
- **Kiểm tra chất lượng, không phải biến dự báo:** mức sụt giảm độ kết hợp sau sự kiện (một cặp ảnh vắt qua
  2020-10-29) trên các polygon đã khoanh vẽ, cho biết danh mục và InSAR có cùng thấy các sườn đó không.
- **Đầu ra:** các dự án InSAR, `insar_features.parquet`, `l5_report.md`. Tên thực tế (2026-11-05):
  `projects/quangnam_l5_d120` (trước sự kiện, track 120; mặc định của `geoeyes landslide l5 --insar`),
  `quangnam_l5b_d120` (sau sự kiện, L3b.7 / L5b), `quangnam_l2b_a55` (track 55, chỉ cho phép thử biến đổi của L2b);
  chưa có dự án L5 cho track 55.
- **Điểm duyệt:** độ phủ và H3, quyết định trước khi bất kỳ đặc trưng InSAR nào được đưa vào mô hình ghép.
- **Kết quả (2026-11-04, mới có track 120; lệnh `geoeyes landslide l5`, `insar/l5_report.md`):**
  - Chồng ảnh: 2019-10-11 → 2020-09-23, 24 ảnh (hai ảnh mỗi tháng), 2,90 triệu điểm (0,75 triệu tán xạ phân tán).
    Chuỗi chỉ dài 11,4 tháng thay vì hai năm như kế hoạch, do hạn chế ổ đĩa. Vì vậy không ước lượng được tương
    quan với mưa (cần ≥ 12 tháng) và gia tốc (cần ≥ 18 tháng). Các đặc trưng dùng được là vận tốc, `moving`, độ
    kết hợp và mật độ điểm.
  - Độ phủ trên các ô dốc của vùng Molave: **15,4 %** (rừng 14,9 %, đất trống 23,9 %), đạt ngưỡng 10 %. Có 74 trong
    544 ô sạt lở (14 %) nằm trong vùng có số liệu.
  - Trên ô đang dịch chuyển: 6,8 % số ô sạt lở, so với 4,8 % số ô không sạt lở (chênh +0,019, khoảng 95 % từ −0,039
    đến +0,083). Không có bằng chứng rằng các khối trượt Molave bắt đầu trên những sườn đã dịch chuyển trong năm
    trước đó.
  - H3 trên các dòng có số liệu (khoảng 180 dòng mỗi lượt rút mẫu, 10 lượt): AUC 0,725 với các lớp của mô hình tốt
    nhất, 0,720 khi thêm InSAR, Δ −0,005 (khoảng 95 % từ −0,012 đến +0,002). **H3 không được ủng hộ** trên các sườn
    có số liệu. Kiểm định có độ nhạy thấp (74 ô sạt lở), và không nói được gì về sườn rừng, nơi băng C không thấy
    mặt đất.
  - Quyết định: không đưa đặc trưng InSAR nào vào mô hình tính nhạy. Trong hệ thống dự báo, InSAR được giữ làm lớp
    hoạt động của [`landslide-forecast-system.md` §8.2–8.3](landslide-forecast-system.md#82-chính-sách-cập-nhật-và-xử-lý-lại-theo-từng-lớp)
    (buộc cập nhật, đánh dấu sườn đang dịch chuyển), không làm biến dự báo. Track 55 và năm thứ
    hai chỉ tăng độ nhạy của kiểm định, không tăng độ phủ dưới tán rừng; chỉ chạy nếu anh yêu cầu.

### L5b — Mức hoạt động sau sự kiện của các khối trượt đã khoanh vẽ (Q4, H5; thêm ngày 2026-11-02)

**Điểm xuất phát.** Sui et al. (2026) dùng SBAS-InSAR xếp khoảng 4.200 khối trượt của trận mưa Zixing tháng 7/2024
vào các nhóm ổn định / tiềm năng / hoạt động / nhanh. Bản nhận xét chủ dự án gửi nêu năm hạn chế, và L5b trả lời
từng hạn chế:

| Hạn chế của Sui et al. (2026) | Cách L5b trả lời |
|---|---|
| 1. Không có mô hình về thời điểm hay xác suất trượt | các nhóm mức hoạt động được kiểm tra với các vụ trượt xảy ra sau đó (tỷ lệ phát hiện đúng, báo động giả, rủi ro tương đối) |
| 2. Chuỗi ngắn và thưa (27 ảnh trong khoảng một năm) | chuỗi 12 ngày một ảnh trong hai năm sau bão (2020-11 → 2022-10), khoảng 60 ngày chụp mỗi track, và hai track; thêm hai năm trước bão (L5) làm mốc so sánh |
| 3. Chỉ một hình học chụp: LOS trộn chuyển động ngang và đứng | hai track (55, 120): tách thành phần 2-D và chiếu theo hướng dốc như trong `hazard` |
| 4. Mưa và biến dạng tương quan nhưng chưa phải cơ chế | mô hình độ trễ phân bố của tốc độ theo hướng dốc với mưa tích lũy (độ trễ 0–60 ngày, hệ số k của `hazard.coupling`), sau khi đã loại chu kỳ mùa |
| 5. Ngưỡng cố định, không kiểm chứng độc lập | ngưỡng thích nghi cho từng khối (2σ nhiễu của một vành ổn định quanh khối), đối chiếu với các báo cáo trong `vietnam.csv` sau 2020 và các vết trượt mới từ Sentinel-2 / Sentinel-1 |

**Dữ liệu.**
- Các polygon Molave trong vùng thí điểm.
- Các chồng ảnh của L5, kéo dài thêm hai năm sau bão: mỗi track một chồng ảnh 2018-10 → 2022-10, xử lý thành hai
  đoạn (trước và sau các cơn bão).
- Mưa: CHIRPS và IMERG, như ở L6.
- Các vụ trượt xảy ra sau đó:
  - các dòng của `vietnam.csv` trong vùng thí điểm hoặc cách vùng dưới 5 km, giai đoạn 2021–2026; các cơn bão tháng
    10–11/2025 ở Quảng Nam là phép thử chính;
  - các vết trượt mới từ Sentinel-2 (NDVI trước / sau mỗi mùa mưa) và biến đổi Sentinel-1, như ở L2b.

**Các bước.**
1. **Điểm đo của từng khối trượt:**
   - các điểm nằm trong polygon nới rộng 30 m (một ô);
   - khối trượt có dưới 3 điểm được ghi là "không có điểm", được báo cáo chứ không bị bỏ qua;
   - các khối trượt cách nhau dưới 100 m cũng được gộp thành cụm, vì phần lớn polygon chỉ cỡ một ô và nhiều polygon
     không có điểm nào.
2. **Chỉ số của từng khối trượt hoặc cụm:**
   - vận tốc theo hướng dốc trước và sau bão;
   - gia tốc (thay đổi vận tốc giữa hai nửa mỗi năm, và xu thế từng đoạn có điểm gãy tại mỗi cơn bão lớn);
   - chuyển dịch tích lũy;
   - độ bất định tính từ nhiễu của vành xung quanh.
3. **Phản ứng với mưa:**
   - mô hình độ trễ phân bố của tốc độ theo hướng dốc (đã loại xu thế và chu kỳ mùa) với mưa ngày (độ trễ 0–60 ngày,
     trọng số trơn theo độ trễ);
   - đầu ra: hệ số khuếch đại, độ trễ tại đỉnh và tỷ lệ phương sai được giải thích, so với mô hình chỉ có chu kỳ mùa;
   - dùng mô hình cộng tính kiểu GAM (spline) trước, như bản nhận xét gợi ý, rồi mới thử các mô hình phức tạp hơn.
4. **Các nhóm:**
   - ổn định: vận tốc nằm trong 2σ của vành xung quanh;
   - hoạt động: chuyển động đều;
   - tăng tốc: có gia tốc đáng kể sau một cơn bão;
   - phản ứng với mưa: hệ số khuếch đại có độ trễ đáng kể.
   - Các ngưỡng cố định của Sui et al. (2026) được tính song song làm mốc so sánh.
5. **Kiểm chứng (H5):** với mỗi nhóm, tỷ lệ khối trượt (hoặc vùng 100 m xung quanh) trượt lại **sau cửa sổ quan
   sát**, giai đoạn 2022-11 → 2026. Các nhóm được xác định trước khi xảy ra những vụ trượt dùng để kiểm chứng, nên
   không có thông tin tương lai nào lọt vào. Các vụ trượt trong cửa sổ (2020-11 → 2022-10) được báo cáo riêng.
   - Chỉ số: rủi ro tương đối so với nhóm "ổn định", tỷ lệ phát hiện đúng, tỷ lệ báo động giả, mỗi chỉ số kèm khoảng
     tin cậy bootstrap.
   - Làm tương tự cho riêng vận tốc trung bình và cho các ngưỡng cố định.

**Đầu ra:** thư mục `activity/` gồm `activity.parquet` (mỗi khối trượt hoặc cụm một dòng), `activity.json`,
`activity.md`, biểu đồ chuỗi của các khối trượt đại diện, bản đồ các nhóm. Code: `landslide/activity.py`, lệnh
`geoeyes landslide activity`.

**Điểm duyệt:** H5 trên vùng thí điểm. Nếu H5 đúng, việc hiển thị gì trên ứng dụng web (một lớp các nhóm mức hoạt
động trên trang `Hazard`) được quyết định cùng L7.

**Hạn chế.**
- Độ phủ băng C dưới tán rừng kém: phần lớn khối trượt Molave có thể không có điểm nào, và những khối có điểm thì
  thiên về sườn đất trống và đất canh tác. Tỷ lệ khối có điểm là con số đầu tiên được báo cáo.
- Các vụ trượt xảy ra sau đó ít và được báo cáo không đều (§8).
- Hai năm sau bão chỉ gồm hai mùa mưa, nên phản ứng có độ trễ với mưa được ước lượng trên ít sự kiện và khoảng tin
  cậy sẽ rộng. Có thể kéo dài cửa sổ sau này nếu ổ đĩa cho phép.
- Ổ đĩa: 2018-10 → 2022-10 cỡ 120 ngày chụp × 0,14 GB ≈ 17 GB burst thô cho track 120. Chồng ảnh được xử lý thành
  hai đoạn, xóa burst thô của đoạn đã xong, trừ khi có thêm ổ đĩa. *Sửa (2026-11-05):* với ba burst mỗi ngày chụp,
  con số là khoảng 120 × 0,4 GB ≈ 50 GB burst thô, cộng phần xử lý (35 GB cho 24 ngày ở L5). Trước hết, đếm các vụ
  trượt về sau trong và quanh vùng thí điểm (kiểm tra độ mạnh cho H5, rà soát 2026-11-05).

### L6 — Ngưỡng mưa (Q2, H4)

*Ghi chú (2026-11-05):* các ngưỡng này cần được đối chiếu và thống nhất với mô hình kích hoạt ở bước F5 của
[`landslide-forecast-system.md`](landslide-forecast-system.md) (khớp trên sản phẩm mưa vận hành của F2, theo
đơn vị–ngày, bỏ ra từng mùa). Xem thêm phần rà soát 2026-11-05 ở đầu ghi chú (số sự kiện theo vùng, bootstrap, gộp
vùng).

- **Sự kiện:** các dòng của `vietnam.csv` có ngày chính xác.
  - Sai số vị trí tới 25 km chấp nhận được ở đây: một pixel CHIRPS là 5,5 km, một pixel IMERG là 11 km.
  - Thêm ba ngày của bộ Das.
  - Các vùng:
    - Bắc: vùng núi phía bắc vĩ độ 19,5° B;
    - Trung: 11–19,5° B, dãy Trường Sơn và Tây Nguyên;
    - đồng bằng (sạt lở bờ sông) bị loại.
- **Mưa ngày** tại pixel của mỗi sự kiện: CHIRPS v3 ngày từ 1981 (khí hậu) và IMERG Final (đối chiếu).
- **Trận mưa** (CTRL-T giản lược, Melillo et al. 2018):
  - các ngày liên tiếp có mưa ≥ 1 mm, ngăn cách bởi ≥ 2 ngày khô;
  - E = tổng lượng mưa của trận, D = thời đoạn;
  - lấy trận mưa kết thúc vào ngày trượt lở, hoặc ngày trước đó (do ngày trong các bản tin không chắc chắn).
- **Mưa tích lũy trước đó:** A5, A10, A30 (trọn pentad, theo điểm duyệt L0) tính bằng percentile so với khí hậu của
  cùng pixel, trong cùng cửa sổ thời gian trong năm (LHASA dùng percentile 7 ngày). Đã sửa trong mã
  (2026-11-05: `landslide/thresholds.py` và các cửa sổ L4 của `landslide/rain.py`); kết quả L4 được tính với 3/7/30.
- **Mẫu không có trượt lở:**
  - mọi trận mưa trong mùa mưa (Bắc tháng 5–10, Trung tháng 9–12) tại cùng các pixel, 2007–2026;
  - loại những trận nằm trong khoảng ±3 ngày so với bất kỳ trượt lở nào được báo cáo trong bán kính 25 km.
- **Ngưỡng:**
  - E = α D^β tại xác suất không vượt 5 % của các sự kiện trượt lở (phương pháp tần suất, Brunetti et al. 2010), kèm
    độ bất định của α và β bằng bootstrap;
  - percentile A10 tối ưu theo ROC (TSS lớn nhất; trong mã hiện vẫn là A7);
  - tính riêng cho từng vùng.
- **Kiểm định:** bỏ ra từng năm; TSS, tỷ lệ phát hiện đúng, tỷ lệ báo động giả.
- **Các sai lệch, ghi rõ trong báo cáo:**
  - tin báo chí thiên về đường giao thông, làng bản và các sự kiện có thương vong;
  - ngày trong GLC có thể là ngày đưa tin;
  - các ngày "không có trượt lở" vẫn chứa những vụ trượt không được báo cáo, nên tỷ lệ báo động giả là giới hạn trên.
- **CHIRPS ngày** cần một hàm đọc mới bên cạnh hàm đọc theo tháng trong `ancillary/rainfall.py` (cùng cơ chế cache,
  cùng cách xử lý khi máy chủ giới hạn truy cập).
- **Đầu ra:** `thresholds.json` (theo vùng: α, β, A7, khoảng tin cậy, TSS), `l6_report.md` (biểu đồ E–D và ROC).
- **Điểm duyệt:** H4; hai vùng có thực sự khác nhau không; ngưỡng nào được đưa vào L7.

### L7 — Ghép và kiểm tra ngược

*Đã được thay thế (2026-11-05)* bằng các bước F5–F7 của [`landslide-forecast-system.md`](landslide-forecast-system.md):
phần ghép là một mô hình kích hoạt theo đơn vị–ngày, mưa dự báo lấy từ ECMWF ENS (51 thành phần), và InSAR đứng ngoài
mô hình kích hoạt cho tới khi L5 cho thấy có ích (L5 chưa cho thấy điều đó). Phần dưới giữ lại như kế hoạch ban đầu.

- **Chỉ số nguy cơ** cho mỗi ô 30 m theo từng ngày:
  - cấp tính nhạy cảm từ L3 (và L4 / L5 nếu được chấp nhận) × cấp mưa từ L6 (dưới ngưỡng, trên ngưỡng, trên
    percentile 95);
  - ghép bằng một ma trận tường minh (cây quyết định) như LHASA, không nhân như xác suất: hai mô hình không được hiệu
    chuẩn trên cùng một tập.
- **Kiểm tra ngược:**
  - **Tháng 10–11/2020 trên vùng phủ của Das:** bản đồ theo ngày; tỷ lệ điểm khởi trượt Molave nằm trong ô "cao" vào
    những ngày trước ngày (gần đúng) xảy ra trượt. Mô hình chính gộp đã được huấn luyện trên chính các điểm này, nên
    tính nhạy cảm ở đây phải là dự báo ngoài fold (khối 5 km) hoặc từ mô hình chỉ học trên Ketsana; điểm số trong mẫu
    không phải là kiểm tra ngược (2026-11-05).
  - **Các sự kiện 2017–2026 của `vietnam.csv` ở miền Trung, ngoài vùng phủ:** đây là phép chuyển giao về không gian.
    Ô của mỗi sự kiện có ở mức "cao" vào đúng ngày đó không, và các ô ở mức "cao" thường xuyên đến đâu vào những
    ngày không có báo cáo?
- **Đầu ra:** `hindcast/` (raster theo ngày, điểm số), `l7_report.md`.
- **Điểm duyệt:** chỉ số có đủ hữu ích để đưa lên ứng dụng web (trang `Hazard`) hay chỉ dừng ở kết quả nghiên cứu.

### L9 — Chuỗi dự báo vận hành (yêu cầu của chủ nhiệm, 2026-11-02)

*Đã được thay thế (2026-11-05)* bằng F8 (chuỗi vận hành) và F9 (một mùa chạy song song, tháng 9–12/2027, trước khi
dùng chính thức) của [`landslide-forecast-system.md`](landslide-forecast-system.md). Khác biệt: mưa dự báo từ ECMWF ENS
(51 thành phần) chứ không phải IFS / GFS; InSAR không là đầu vào của mô hình kích hoạt cho tới khi L5 cho thấy có ích.
Các yêu cầu và lớp nền O1–O4 dưới đây vẫn giữ nguyên.

Mục tiêu không phải một bản đồ nhạy cảm, mà là một dự báo được chạy đi chạy lại: lặp lại được, và đủ nhanh cho cảnh
báo. Yêu cầu này định hình mọi bước trước đó.

**Yêu cầu**
- **R1 Lặp lại được.** Mọi sản phẩm đi từ đầu vào có phiên bản và một bản lưu mô hình cố định. Cùng đầu vào cho cùng
  đầu ra (mô hình có seed, manifest ghi hash của đầu vào và phiên bản mã).
- **R2 Nhanh.** Công việc chia làm hai:
  - *ngoại tuyến*: huấn luyện, các lớp biến tĩnh, kiểm định — vài giờ, ít khi chạy;
  - *trực tuyến*: dự báo — vài phút, chạy mỗi ngày (mỗi 3 giờ khi có sự kiện).
  - Mục tiêu sau khi có số liệu mưa: vùng thí điểm ≤ 1 phút, một tỉnh ≤ 5 phút.
- **R3 Được cập nhật và kiểm tra.**
  - Sau mỗi mùa mưa, các vết trượt Sentinel-2 của `scars.py` cho một danh mục mới, và mọi dự báo đã lưu được chấm
    điểm theo danh mục đó và theo tin báo (tỷ lệ trúng, báo động nhầm, TSS).
  - Một mô hình mới chỉ thay mô hình đang chạy nếu nó tốt hơn trên mùa đó ("champion / challenger").

**Chuỗi xử lý**
1. **Kho lớp biến tĩnh** cho mỗi vùng: *mọi* ô lưới, không chỉ các vùng phủ của danh mục như L2.
   - Dựng lại khi một đầu vào thay đổi: DEM, rừng hằng năm (Hansen, hoặc ảnh tổng hợp NDVI Sentinel-2 không bị trễ
     một năm), thạch học.
2. **Bản lưu mô hình** `models/<version>/`:
   - mô hình đã huấn luyện, danh sách lớp biến và thẻ mô hình (dữ liệu huấn luyện, điểm số L3b, hiệu chuẩn, seed,
     phiên bản mã);
   - khi suy luận chỉ cần nạp nó.
3. **Raster tính nhạy cảm** tính sẵn mỗi năm một lần (trạng thái rừng) và cho mỗi phiên bản mô hình.
4. **Mưa, trực tuyến, trên lưới mưa** (~0,1°: vài trăm ô cho một tỉnh, nên tính rất nhanh):
   - quan trắc: GSMaP NRT (theo giờ, trễ ~4 giờ) hoặc IMERG Early (~4 giờ);
   - dự báo: dữ liệu mở ECMWF (IFS 0,25°, tới 10 ngày), GFS làm dự phòng;
   - chỉ số: lượng mưa trận E và thời lượng D của L6, mưa tiền kỳ A7, lượng mưa dự báo cộng dồn 24 / 72 giờ.
5. **Kết hợp** (ma trận của L7):
   - cấp mưa của mỗi ô mưa được tra cho từng ô 30 m — một phép toán vector hoá, khoảng một giây cho một triệu ô;
   - hoạt động InSAR của L5 / L5b (cập nhật mỗi 12 ngày) nâng cấp của các sườn đang chuyển động.
6. **Đầu ra:**
   - GeoTIFF tối ưu cho đám mây (COG) hằng ngày;
   - bảng tổng hợp theo xã (cấp cao nhất, tỷ lệ diện tích ở các cấp cao) cho bản tin cảnh báo;
   - trang `Hazard` của ứng dụng web;
   - nhật ký của mỗi lần chạy, phục vụ R3.

**Hệ quả cho các bước trước**
- **Lớp biến phải có ở mọi nơi và cập nhật được.**
  - Đường hiện tại đã bị loại (đã làm ở L3).
  - Không lớp nào được phụ thuộc vào vùng phủ của một danh mục.
  - Rừng phải có một nguồn vận hành được (ảnh tổng hợp Sentinel-2) bên cạnh Hansen.
- **Xác suất đã hiệu chuẩn.** Mô hình đưa vào một ma trận quyết định, nên xác suất phải được hiệu chuẩn (logistic,
  hoặc GBM / RF hiệu chuẩn isotonic). L3 có báo cáo điểm Brier nhưng chưa kiểm tra hiệu chuẩn ở đầu thấp; việc đó
  thuộc bước isotonic của C6 (L3c, đã lên kế hoạch). (Viết lại cho đúng mức, 2026-11-05.)
- **Ngưỡng trên sản phẩm mưa vận hành.** CHIRPS bản chính thức có muộn vài tuần. L6 hiệu chỉnh ngưỡng trên sản
  phẩm dùng trực tuyến (GSMaP NRT / IMERG Early), hoặc trên chuỗi dài của nó có kiểm tra sai lệch với trạm. Nếu
  không, ngưỡng và dự báo ở hai thang đo khác nhau. CHIRPS vẫn dùng cho khí hậu.
- **Mã nguồn:**
  - tách `run_fit` thành `fit` (ghi bản lưu mô hình), `map` (áp dụng nó) và `forecast` (mưa × tính nhạy cảm);
  - L2 trên toàn vùng;
  - priority-flood biên dịch (numba) cho DEM cấp tỉnh.

**Thứ tự (chủ nhiệm, 2026-11-02): lớp nền ngoại tuyến trước; InSAR và mưa trực tuyến làm sau cùng.** Lớp nền được
dựng ngay sau điểm duyệt L3b, qua bốn bước. Mỗi bước là một lệnh, ghi manifest, và chỉ dựng lại khi đầu vào thay đổi.
- **O1 Kho lớp biến tĩnh** `<study>/base/static/`:
  - mỗi lớp một GeoTIFF tối ưu cho đám mây (COG) trên *mọi* ô của vùng (lưới 30 m của L1);
  - địa hình trên GLO-30 và trên AW3D30;
  - các lớp thạch học, SoilGrids;
  - rừng dạng khối dữ liệu: độ che phủ năm 2000 và tỷ lệ diện tích mất trong từng năm 2001–2024 (Hansen), để trạng
    thái trước một ngày bất kỳ chỉ là một phép cộng, không phải tải lại;
  - ảnh tổng hợp NDVI mùa khô Sentinel-2 hằng năm từ 2017 (rừng không bị trễ như Hansen, và làm nền cho việc khoanh
    vết trượt).
  - Mã nguồn: priority-flood biên dịch (numba), để một tỉnh chỉ mất vài phút thay vì vài giờ.
- **O2 Danh mục sự kiện** `<study>/base/events/`:
  - mọi danh mục sạt trượt theo cùng một lược đồ: Das 2024, các vết trượt Sentinel-2 của từng mùa (`scars.py`, có cờ
    `strict`), các điểm từ báo chí (ngày, độ chính xác vị trí);
  - mỗi danh mục kèm vùng đã khoanh vẽ, để luôn rút được mẫu âm.
- **O3 Kho dữ liệu mưa** `<study>/base/rain/`:
  - mưa ngày (và theo giờ trong các đợt mưa) trên vùng, từ chính các sản phẩm dùng khi vận hành (GSMaP NRT / IMERG
    Early, từ 2015);
  - IMERG Final và CHIRPS đặt bên cạnh để kiểm tra sai lệch và làm khí hậu.
- **O4 Bản lưu mô hình và raster tính nhạy cảm** `<study>/base/models/<version>/`:
  - mô hình được chọn tại điểm duyệt L3b, huấn luyện trên mọi sự kiện của danh mục, cố định cùng thẻ mô hình;
  - raster tính nhạy cảm cho từng năm (trạng thái rừng), dạng COG.
- Sau đó, theo thứ tự: L4 và L6 trên O3 (mưa làm biến dự báo, ngưỡng), L7 (ma trận và chạy lại); cuối cùng L5 / L5b
  (InSAR) và dự báo trực tuyến. Trên thực tế L5 đã chạy ngày 2026-11-04, trước L6 (chưa báo cáo; ghi chú 2026-11-05).

**Đầu ra:** `geoeyes landslide forecast --date … [--lead 72h]`, `forecast/<date>/` (raster, bảng theo xã, manifest
của lần chạy), `l9_report.md` (thời gian chạy, chạy thử lại cho mùa 2025).

**Điểm duyệt:**
- thời gian chạy đạt R2;
- chạy lại toàn bộ cho cùng một raster (R1);
- lần chạy thử cho mùa 2025 đạt điểm ít nhất bằng lần chạy lại của L7.

### L8 — Miền Bắc Việt Nam (đang bị chặn)

Mô hình của L3 không được chuyển nguyên sang miền Bắc: thạch học khác (đá biến chất và granit của Hoàng Liên Sơn, đá
vôi), chế độ mưa khác. Cần một danh mục polygon cho miền Bắc:

1. **Bão Yagi (tháng 9/2024):** khoanh vẽ khối trượt từ biến đổi trên Sentinel-2 (NDVI trước / sau, chỉ số đất trống,
   mặt nạ độ dốc) và biến đổi biên độ Sentinel-1, như một việc riêng. Việc này nối với ý tưởng ở
   [`paper-ideas.md`](paper-ideas.md) §4.
2. **Viện KHĐC&KS:** lớp điểm `<TỈNH>:...diemtruot84` trên `canhbaotruotlo.vn:8081`, xin cấp.
3. **Than Uyên** (Lai Châu, Zenodo 19562697): các điểm của một mô hình đã công bố, dùng làm phép thử đầu tiên.

## 6. Triển khai trong GeoEyes

**Gói `geoeyes.landslide`** (mới). Gói này dùng lại `geoeyes.ml.layers.Grid`, kiểm định chéo theo khối và mã mô hình
của `geoeyes.ml.susceptibility`, `geoeyes.ancillary.rainfall` và các sản phẩm InSAR.

| Module | Nội dung | Bước |
|---|---|---|
| `inventory.py` | đọc GeoPackage và CSV, vùng phủ, diện tích – tần suất | L0 |
| `labels.py` | điểm vách trượt / một phần ba trên / tâm, mẫu âm, seed | L1 |
| `terrain.py` | các đại lượng địa hình từ DEM trên một `Grid` (độ dốc, độ cong, TPI, TWI, suối) | L2 |
| `predictors.py` | các lớp theo thời điểm của từng sự kiện (Hansen GFC, GLiM, SoilGrids, đường, bản đồ mưa) | L2, L4 |
| `aspect.py` | biểu đồ hoa hồng hướng sườn, mô hình có điều kiện và mô hình chiếu sáng, dịch chuyển danh mục, chỉ số đón gió | L2a |
| `verify.py` | kiểm chứng độc lập các danh mục: mất rừng năm sự kiện của Hansen, biến đổi Sentinel-1, kích thước | L2b |
| `scars.py` | vết trượt mới giữa hai ảnh tổng hợp Sentinel-2, hiệu chỉnh trên một sự kiện có danh mục | L3b |
| `reliability.py` | cờ độ tin cậy theo địa hình của các polygon (Das và Sentinel-2) | L3b.6 |
| `dating.py` | ngày mất thực vật của từng đối tượng từ chuỗi Sentinel-2; độ bền (persistence) | L3b.7 |
| `screening.py` | sàng lọc các đối tượng Sentinel-2: có phải trượt lở hay không | L3b.7 |
| `improve.py` | khung L3c: so sánh theo cặp bằng bootstrap khối, các bước C1, C3, C5 | L3c |
| `rain.py` | bản đồ mưa sự kiện từ CHIRPS v3 ngày, phép thử đối chứng bằng trường ngẫu nhiên hoá pha | L4 |
| `insar.py` | đặc trưng InSAR trước sự kiện trên các ô nghiên cứu, độ phủ, kiểm định H3 | L5 |
| `model.py` | huấn luyện, kiểm định không gian và chuyển giao, phép thử 2025, bootstrap | L3–L3b |
| `thresholds.py` | chuỗi mưa ngày, trận mưa, ngưỡng E–D và ngưỡng percentile | L6 |
| `catalogue.py` | danh mục sự kiện trượt lở có ngày (bước F1 của hệ thống dự báo) | F1 |
| `satrain.py` | kho mưa vệ tinh và kiểm tra sản phẩm, GSMaP / IMERG (bước F2 của hệ thống dự báo) | F2 |
| `study.py` | file nghiên cứu `study.toml` | mọi bước |
| `activity.py` (*dự kiến*) | mức hoạt động sau sự kiện của từng khối trượt: chỉ số, phản ứng với mưa, phân nhóm, kiểm chứng | L5b |
| `hindcast.py` (*dự kiến*) | ma trận, bản đồ theo ngày, điểm số | L7 |
| `forecast.py` (*dự kiến*) | kho lớp biến tĩnh, bản lưu mô hình, mưa trực tuyến, dự báo hằng ngày, nhật ký chạy | L9 / F8 |

(Bảng được cập nhật theo `src/geoeyes/landslide/` ngày 2026-11-05.)

- **CLI:**
  - `geoeyes landslide <action> --study <name>` (mặc định `landslide_central_vn`); các action có trong mã
    (2026-11-05): `inventory`, `audit`, `labels`, `layers`, `aspect`, `verify`, `scars`, `dating`, `persistence`,
    `reliability`, `fit`, `test`, `improve --step c1|c3|c5`, `rain`, `thresholds`, `l5 [--insar <project>]`,
    `catalogue`, `rainarchive`, `raincheck`, `rainproducts`. Dự kiến: `activity`, `hindcast`, `forecast`;
  - cấu hình nằm trong file nghiên cứu `studies/<name>/study.toml`: danh mục, sự kiện, vùng phủ, lưới, tham số mô
    hình và ngưỡng.
- **Bố cục workspace:** `<workspace>/studies/landslide_central_vn/` (đầu vào được tham chiếu, mỗi đầu ra có một
  `Manifest`, như `io.manifest`). Các chồng ảnh InSAR vẫn là dự án bình thường (`projects/quangnam_l5_d120`,
  `quangnam_l5b_d120`, `quangnam_l2b_a55`).
- **Kiểm thử:** `tests/unit/landslide/`: polygon tổng hợp trên DEM tổng hợp (điểm vách trượt, mẫu âm ở khoảng cách
  đúng), ngưỡng trên chuỗi mưa tổng hợp, kiểm định chéo theo khối không rò rỉ.
- **Bản ghi quyết định:** ADR-030 (Proposed, 2026-11-01), viết cùng L1.
- Hai script dựng danh mục (`inventories/landslide/build_*.py`) đã được chuyển vào `landslide.inventory` ở L1
  (`geoeyes landslide inventory`); các file dựng lại giống hệt các file trước đó.

## 7. Tham số và căn cứ chọn giá trị mặc định

| Tham số | Mặc định | Lý do |
|---|---|---|
| Kích thước ô | 30 m | độ phân giải của GLO-30 và Hansen GFC; polygon trung vị ≈ 1.000–2.200 m² ≈ 1–2 ô |
| Mẫu dương | ô cao nhất của polygon | Hussin et al. (2016): vùng khởi trượt, không phải phần vật liệu trượt xuống; C5 (L3c) xác nhận |
| Vùng đệm mẫu âm | 60 m (2 ô) | giữ mẫu âm tránh xa mép polygon đã khoanh vẽ, vốn có sai số vị trí vài ô |
| Dương : âm | 1 : 1, rút 10 lần | huấn luyện cân bằng; các lần rút cho biết độ phân tán do lấy mẫu; tỷ lệ thực được khôi phục bằng prior correction |
| Khối | 5 km là chính, 2 km bên cạnh (10 km cho mưa) | Brenning (2005); đối chiếu với semivariogram phần dư (Roberts et al. 2017; Valavi et al. 2019) |
| Vùng phủ | `near`: trong 1 km quanh khối trượt đã khoanh vẽ, lấp khe hở < 3 km, bỏ vùng phẳng > 1 km² (điểm duyệt L0) | vùng đã khoanh vẽ không được công bố; thử độ nhạy: bao lõm (ratio 0,3) + 1 km |
| Ngưỡng suối | 0,5 km² | diện tích khởi nguồn lòng suối thường gặp ở lưu vực núi nhỏ; thử độ nhạy 0,1 / 1 km² |
| Giai đoạn InSAR | 2018-10-01 → 2020-09-30 (L5); 2020-11-01 → 2022-10-31 (L5b) | mỗi giai đoạn hai năm (quyết định của chủ dự án; Barra et al. 2017 yêu cầu ≥ 1,5 năm); L5 kết thúc trước các cơn bão tháng 10/2020 |
| InSAR "moving" | \|v\| ≥ 2σ, ≥ 3 điểm mỗi ô | Barra et al. (2017); Tomás et al. (2019); giống `hazard` |
| Điểm duyệt độ phủ InSAR | 10 % ô sườn dốc | dưới mức này, H3 chỉ được trả lời cho tập con có điểm |
| Khoảng ngăn giữa hai trận mưa | 2 ngày khô (< 1 mm) | CTRL-T giản lược (Melillo et al. 2018) |
| Cửa sổ mưa tích lũy | 5, 10, 30 ngày | trọn pentad của CHIRPS (điểm duyệt L0) |
| Ngưỡng | không vượt 5 % (E–D); TSS lớn nhất (A10) | Brunetti et al. (2010); Kirschbaum & Stanley (2018) |
| Cửa sổ loại trừ | ±3 ngày, 25 km | độ bất định về ngày và độ chính xác vị trí của các bản tin |
| Các cấp | 0,2 / 0,4 / 0,6 / 0,8 | như `ml.susceptibility` |

## 8. Rủi ro và hạn chế

- **Chưa biết vùng đã khoanh vẽ** (rủi ro chính). Mẫu âm rút ở nơi không ai khảo sát sẽ dạy mô hình rằng các sườn
  chưa khoanh vẽ là ổn định. Giảm thiểu: dùng vùng phủ thận trọng `near` (điểm duyệt L0), phép thử độ nhạy với bao
  lõm + 1 km (L3), và đối chiếu bằng mắt với ảnh của từng sự kiện. Mẫu âm chỉ lấy trong vùng phủ `near`, nên hiệu
  chuẩn và các cấp chỉ có giá trị trong miền đã lấy mẫu (rà soát 2026-11-05).
- **Ngày của Molave.** Bộ này nhiều khả năng trộn nhiều cơn bão tháng 10/2020, nên mưa của sự kiện là tổng 30 ngày,
  không phải của một cơn bão.
- **Thời điểm của các biến dự báo.**
  - DEM (2011–2015) có trước Molave nhưng sau Ketsana, và trùm lên Podul (2013): vết trượt Ketsana và Podul có thể
    nằm trong DEM.
  - Đường OSM là của hiện tại.
  - Cả hai được kiểm tra bằng các phương án, không bị bỏ qua.
- **Địa chất thô.** GLiM chỉ cho vài lớp trên vùng phủ, nên thạch học có thể tỏ ra không quan trọng chỉ vì được lập
  bản đồ sơ sài. Bản đồ 1:200.000 của Viện KHĐC&KS sẽ thay đổi điều này.
- **Mưa như một đại lượng thay thế cho vị trí.** Khoảng 80 pixel CHIRPS trên bao lõm Molave (khoảng 22 trên vùng
  thí điểm) là quá ít để tách mưa khỏi vị
  trí; vì thế mới có phép thử đối chứng (L4).
- **InSAR trên sườn có rừng.**
  - Băng C mất độ kết hợp dưới tán rừng, nên các sườn có điểm sẽ thiên về đất trống và đất nông nghiệp.
  - Vì vậy H3 chỉ được trả lời cho các sườn có điểm, không cho vùng rừng.
  - Băng L (ALOS-2, NISAR) mới kiểm tra được vùng rừng; điều này không nằm trong kế hoạch.
- **Sai lệch do cách đưa tin trong `vietnam.csv`.** Sự kiện gần đường và có thương vong chiếm tỷ lệ quá cao; miền Bắc
  và miền Trung không được lấy mẫu như nhau. Ngưỡng thu được là ngưỡng của trượt lở *được báo cáo*.
- **Chuyển giao.** Mô hình từ ba cơn bão ở Quảng Nam – Kon Tum mô tả các sườn đó và các cơn bão đó; nó không phải bản
  đồ toàn quốc.

## 9. Tài liệu tham khảo

Tất cả DOI dưới đây đã được kiểm tra trên Crossref hoặc DataCite ngày 2026-11-01; các tài liệu thêm ngày 2026-11-05
(Hussin, Jasiewicz, Meyer, Pelletier, Roberts, Valavi) được kiểm tra trên Crossref cùng ngày đó.

- Alvioli, M., Marchesini, I., Reichenbach, P., Rossi, M., Ardizzone, F., Fiorucci, F., Guzzetti, F. (2016).
  Automatic delineation of geomorphological slope units with r.slopeunits v1.0 and their optimization for landslide
  susceptibility modeling. *Geoscientific Model Development* 9, 3975–3991. https://doi.org/10.5194/gmd-9-3975-2016
- Brenning, A. (2005). Spatial prediction models for landslide hazards: review, comparison and evaluation. *Natural
  Hazards and Earth System Sciences* 5, 853–862. https://doi.org/10.5194/nhess-5-853-2005
- Brunetti, M. T., Peruccacci, S., Rossi, M., Luciani, S., Valigi, D., Guzzetti, F. (2010). Rainfall thresholds for
  the possible occurrence of landslides in Italy. *Natural Hazards and Earth System Sciences* 10, 447–458.
  https://doi.org/10.5194/nhess-10-447-2010
- Das, R. (2024). Mapped landslides for Typhoon Ketsana, Molave and Tropical Storm Podul in central Vietnam
  [dataset]. Zenodo. https://doi.org/10.5281/zenodo.15596033
- Fell, R., Corominas, J., Bonnard, C., Cascini, L., Leroi, E., Savage, W. Z. (2008). Guidelines for landslide
  susceptibility, hazard and risk zoning for land use planning. *Engineering Geology* 102, 85–98.
  https://doi.org/10.1016/j.enggeo.2008.03.022
- Funk, C., et al. (2015). The climate hazards infrared precipitation with stations — a new environmental record for
  monitoring extremes. *Scientific Data* 2, 150066. https://doi.org/10.1038/sdata.2015.66
- Guzzetti, F., Peruccacci, S., Rossi, M., Stark, C. P. (2008). The rainfall intensity–duration control of shallow
  landslides and debris flows: an update. *Landslides* 5, 3–17. https://doi.org/10.1007/s10346-007-0112-1
- Guzzetti, F., Mondini, A. C., Cardinali, M., Fiorucci, F., Santangelo, M., Chang, K.-T. (2012). Landslide
  inventory maps: new tools for an old problem. *Earth-Science Reviews* 112, 42–66.
  https://doi.org/10.1016/j.earscirev.2012.02.001
- Hansen, M. C., et al. (2013). High-resolution global maps of 21st-century forest cover change. *Science* 342,
  850–853. https://doi.org/10.1126/science.1244693
- Hartmann, J., Moosdorf, N. (2012). The new global lithological map database GLiM: a representation of rock
  properties at the Earth surface. *Geochemistry, Geophysics, Geosystems* 13, Q12004.
  https://doi.org/10.1029/2012GC004370
- Holland, G. J. (1980). An analytic model of the wind and pressure profiles in hurricanes. *Monthly Weather Review*
  108, 1212–1218. https://doi.org/10.1175/1520-0493(1980)108<1212:AAMOTW>2.0.CO;2
- Hussin, H. Y., Zumpano, V., Reichenbach, P., Sterlacchini, S., Micu, M., van Westen, C., Bălteanu, D. (2016).
  Different landslide sampling strategies in a grid-based bi-variate statistical susceptibility model.
  *Geomorphology* 253, 508–523. https://doi.org/10.1016/j.geomorph.2015.10.030
- Jasiewicz, J., Stepinski, T. F. (2013). Geomorphons — a pattern recognition approach to classification and
  mapping of landforms. *Geomorphology* 182, 147–156. https://doi.org/10.1016/j.geomorph.2012.11.005
- Kirschbaum, D., Stanley, T. (2018). Satellite-based assessment of rainfall-triggered landslide hazard for
  situational awareness. *Earth's Future* 6, 505–523. https://doi.org/10.1002/2017EF000715
- Knapp, K. R., Kruk, M. C., Levinson, D. H., Diamond, H. J., Neumann, C. J. (2010). The International Best Track
  Archive for Climate Stewardship (IBTrACS). *Bulletin of the American Meteorological Society* 91, 363–376.
  https://doi.org/10.1175/2009BAMS2755.1
- Liu, C., Luo, W., Chung, H., Yin, H., Yan, K. (2018). Influences of the shadow inventory on a landslide
  susceptibility model. *ISPRS International Journal of Geo-Information* 7, 374. https://doi.org/10.3390/ijgi7090374
- Malamud, B. D., Turcotte, D. L., Guzzetti, F., Reichenbach, P. (2004). Landslide inventories and their statistical
  properties. *Earth Surface Processes and Landforms* 29, 687–711. https://doi.org/10.1002/esp.1064
- Melillo, M., Brunetti, M. T., Peruccacci, S., Gariano, S. L., Roccati, A., Guzzetti, F. (2018). A tool for the
  automatic calculation of rainfall thresholds for landslide occurrence. *Environmental Modelling & Software* 105,
  230–243. https://doi.org/10.1016/j.envsoft.2018.03.024
- Meyer, H., Reudenbach, C., Hengl, T., Katurji, M., Nauss, T. (2018). Improving performance of spatio-temporal
  machine learning models using forward feature selection and target-oriented validation. *Environmental Modelling &
  Software* 101, 1–9. https://doi.org/10.1016/j.envsoft.2017.12.001
- Meyer, H., Reudenbach, C., Wöllauer, S., Nauss, T. (2019). Importance of spatial predictor variable selection in
  machine learning applications — moving from data reproduction to spatial prediction. *Ecological Modelling* 411,
  108815. https://doi.org/10.1016/j.ecolmodel.2019.108815
- Pelletier, J. D., Broxton, P. D., Hazenberg, P., Zeng, X., Troch, P. A., Niu, G.-Y., Williams, Z., Brunke, M. A.,
  Gochis, D. (2016). A gridded global data set of soil, intact regolith, and sedimentary deposit thicknesses for
  regional and global land surface modeling. *Journal of Advances in Modeling Earth Systems* 8, 41–65.
  https://doi.org/10.1002/2015MS000526
- Reichenbach, P., Rossi, M., Malamud, B. D., Mihir, M., Guzzetti, F. (2018). A review of statistically-based
  landslide susceptibility models. *Earth-Science Reviews* 180, 60–91. https://doi.org/10.1016/j.earscirev.2018.03.001
- Rennó, C. D., Nobre, A. D., Cuartas, L. A., Soares, J. V., Hodnett, M. G., Tomasella, J., Waterloo, M. J. (2008).
  HAND, a new terrain descriptor using SRTM-DEM: mapping terra-firme rainforest environments in Amazonia. *Remote
  Sensing of Environment* 112, 3469–3481. https://doi.org/10.1016/j.rse.2008.03.018
- Roberts, D. R., Bahn, V., Ciuti, S., Boyce, M. S., Elith, J., Guillera-Arroita, G., Hauenstein, S., Lahoz-Monfort,
  J. J., Schröder, B., Thuiller, W., Warton, D. I., Wintle, B. A., Hartig, F., Dormann, C. F. (2017).
  Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*
  40, 913–929. https://doi.org/10.1111/ecog.02881
- Segoni, S., Piciullo, L., Gariano, S. L. (2018). A review of the recent literature on rainfall thresholds for
  landslide occurrence. *Landslides* 15, 1483–1501. https://doi.org/10.1007/s10346-018-0966-4
- Stanley, T., Kirschbaum, D. B. (2017). A heuristic approach to global landslide susceptibility mapping. *Natural
  Hazards* 87, 145–164. https://doi.org/10.1007/s11069-017-2757-y
- Steger, S., Brenning, A., Bell, R., Glade, T. (2016). The propagation of inventory-based positional errors into
  statistical landslide susceptibility models. *Natural Hazards and Earth System Sciences* 16, 2729–2745.
  https://doi.org/10.5194/nhess-16-2729-2016
- Steger, S., Brenning, A., Bell, R., Glade, T. (2017). The influence of systematically incomplete shallow landslide
  inventories on statistical susceptibility models and suggestions for improvements. *Landslides* 14, 1767–1781.
  https://doi.org/10.1007/s10346-017-0820-0
- Sui, B., Fang, Y., Li, D., Zhang, Z., Chen, L., Du, D., Wang, T. (2026). Quantitative stability assessment of
  landslides following the 2024 Zixing rainstorm using time-series InSAR. *Remote Sensing* 18, 929.
  https://doi.org/10.3390/rs18060929
- Truong et al. (2023), mô hình tính nhạy cảm random forest, Văn Yên (Yên Bái): tài liệu tham khảo cần bổ sung.
- Valavi, R., Elith, J., Lahoz-Monfort, J. J., Guillera-Arroita, G. (2019). blockCV: an R package for generating
  spatially or environmentally separated folds for k-fold cross-validation of species distribution models. *Methods
  in Ecology and Evolution* 10, 225–232. https://doi.org/10.1111/2041-210X.13107
- Zevenbergen, L. W., Thorne, C. R. (1987). Quantitative analysis of land surface topography. *Earth Surface
  Processes and Landforms* 12, 47–56. https://doi.org/10.1002/esp.3290120107
- InSAR và trượt lở chậm (Barra et al. 2017; Cigna et al. 2013; Ciampalini et al. 2016; Handwerger et al. 2013;
  Lacroix et al. 2020; Tomás et al. 2019): xem [`rainfall-insar-hazard.md`](rainfall-insar-hazard.md) §10.
