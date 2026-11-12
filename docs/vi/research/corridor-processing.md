# Xử lý theo một hành lang vẽ trên bản đồ

Trạng thái (2026-11-12): đã viết kế hoạch, chủ dự án đồng ý làm.
- **K0 xong** (mục 6), phạm vi đã được duyệt.
- **K1 xong:**
  - cấu hình `[aoi] corridor` và lệnh `geoeyes corridor`;
  - chọn burst theo đa giác khi tải, khi dựng stack và trong phần xem trước ASF;
  - test.
- **K2 đã làm, chờ chủ dự án dùng thử:**
  - cọ trong "Dự án mới" và tab "Vùng xử lý" của dự án;
  - đã có test cho API, nhưng chưa thử cọ trên trình duyệt.

Yêu cầu của chủ dự án:
- "Chỉ chạy qua một tuyến được vẽ sẵn: burst tải về rồi clip theo tuyến, sau đó tạo stack như thường."
- Vẽ trực tiếp trên bản đồ: đặt bề rộng trước, nhấn giữ chuột và kéo dọc tuyến. Vùng đệm tự lớn ra và nối liền
  theo con trỏ.

Bản tiếng Anh: [../../en/research/corridor-processing.md](../../en/research/corridor-processing.md).

## 1. Câu hỏi

Đường bộ, đường sắt, kênh và đê đều dài và hẹp, trong khi lõi hiện xử lý một hình chữ nhật (bbox, rồi khung chữ nhật
tương ứng trên lưới radar). QL6 từ Sơn La đến Hòa Lạc dài khoảng 230 km, nên hình chữ nhật bao quanh rộng khoảng
1,2 độ²:
- khoảng 136 GB dữ liệu burst gốc;
- khoảng 400 GB stack;
- 97 % trong đó là núi không cần xử lý.

Nếu cắt tuyến thành nhiều hình chữ nhật thì mỗi đoạn có một điểm tham chiếu riêng. Khi đó phải nối các đoạn bằng
`geoeyes tie`, và sai lệch cộng dồn dọc chuỗi.

Câu hỏi: **có thể làm một stack, một điểm tham chiếu và một sản phẩm đi theo hành lang, với chi phí xấp xỉ diện tích
hành lang không?**

## 2. Hiện trạng

| Phần | Hiện nay | Sẵn sàng cho hành lang? |
|---|---|---|
| Tải dữ liệu (S1) | theo burst: chỉ các burst chạm bbox | cần dùng đa giác, không dùng bbox |
| Stack | khung chữ nhật quanh AOI, ghi mọi ô 512 × 512 | chưa: dày đặc |
| Hình học (lat, lon, hgt…) | mảng dày đặc trên khung cắt | chưa |
| Phase linking | theo ô, trên cả khung | bỏ qua ô được |
| Chọn điểm PS / DS | mọi pixel của khung | cần mặt nạ |
| Giải pha (lưới IRLS) | điểm thưa trên lưới | được |
| Khí quyển, xuất kết quả, web | theo điểm | được |

## 3. Thiết kế

### 3.1 Hành lang

- Cấu hình `[aoi] corridor = "corridor.geojson"`: một đa giác WGS84 trong thư mục dự án. bbox suy ra từ đa giác này.
- Đa giác là hợp của các nét vẽ đã tạo vùng đệm. Phép tính chạy trên server bằng shapely, theo múi UTM tại chỗ, nên
  bề rộng luôn tính bằng mét.

### 3.2 Công cụ "cọ" trên bản đồ (Dự án mới và "Sửa vùng" của dự án)

- **Bề rộng:** đặt trước, từ 100 m đến 5 km. Mặc định 1000 m, tức 500 m mỗi bên.
- **Cọ:**
  - Nhấn giữ chuột trái và kéo dọc tuyến.
  - Khi cọ đang bật, bản đồ không kéo được; giữ phím Space để kéo bản đồ.
  - Điểm được lấy cách nhau khoảng ¼ bề rộng, nên kéo nhanh cũng không bị hở.
- **Xem trước:**
  - Nét đang vẽ hiện bằng PathLayer, bề rộng tính bằng **mét**, đầu và góc bo tròn. Vẽ như vậy thì hình thấy được
    chính là vùng đệm của đường, nên thấy gì thì xử lý đúng như thế.
  - Các nét chạm hoặc chồng lên nhau tự nối thành một hành lang.
- **Tẩy:** giữ Alt và kéo để xóa một phần.
- **Hoàn tác / làm lại:** Ctrl+Z / Ctrl+Y.
- **Xóa hết:** xóa mọi nét.
- **Nhập tệp:** tuyến hoặc vùng (gpkg, kml/kmz, geojson, shp), ví dụ tuyến QL6 của chủ dự án; vùng đệm theo bề rộng
  đã đặt.
- **Số liệu tức thời** sau mỗi nét:
  - diện tích và chiều dài hành lang;
  - các track và burst Sentinel-1 mà hành lang chạm;
  - ước tính dung lượng dữ liệu gốc và stack;
  - tỷ lệ so với bbox.
- **Bám theo đường OSM (sau, K2b):** nét vẽ gần một con đường sẽ tự bám theo đường đó.

### 3.3 Stack thưa

- **Mặt nạ:** tính trên lưới radar từ lat/lon của ảnh tham chiếu, nới rộng thêm theo nhân nội suy và cửa sổ phase
  linking.
- **Ô nào được xử lý:**
  - Chỉ những ô chạm mặt nạ mới được nắn khớp và ghi.
  - Zarr không tạo tệp cho ô chưa ghi; đọc ô đó sẽ nhận giá trị rỗng.
- **Cỡ ô:** ô nhỏ hơn (ví dụ 256 × 128) bám tuyến sát hơn. Cỡ ô sẽ chọn theo số đo ở K0.
- **Hình học:** các mảng hình học cũng chỉ ghi theo ô.
- **ESD:** dùng phần chồng giữa các burst nằm trong mặt nạ. Nếu hành lang không chạm phần chồng nào thì dùng cả phần
  chồng.

### 3.4 Các bước sau

- Phase linking và việc chọn điểm chỉ chạy trong mặt nạ.
- Ảnh QC được cắt theo mặt nạ.
- Sản phẩm mang theo đa giác hành lang để vẽ viền trên bản đồ và trong báo cáo.

### 3.5 Dữ liệu gốc (tùy chọn)

`[acquire] keep_raw = false`: dựng xong stack cho ngày nào thì xóa burst gốc của ngày đó. Đổi lại, muốn thêm ngày
hay dựng lại stack thì phải tải lại.

## 4. Các bước và điểm duyệt

| Bước | Việc | Điểm duyệt |
|---|---|---|
| K0 | Đo trên `ql6_km124_141` (tuyến QL6, rộng 1 km): tỷ lệ ô theo các cỡ ô 512² / 256 × 128 / 128²; liệt kê mọi chỗ đang giả định khung dày đặc | **chủ dự án duyệt** |
| K1 | `[aoi] corridor`: cấu hình, kiểm tra, chọn burst theo đa giác, lệnh `geoeyes corridor` | unit test |
| K2 | Công cụ cọ trên web: bề rộng, kéo, tẩy, hoàn tác, nhập tệp, số liệu tức thời | **chủ dự án dùng thử** |
| K3 | Stack thưa: mặt nạ, danh sách ô, nắn khớp và hình học theo ô, ESD | unit test + đối chiếu |
| K4 | Mặt nạ cho các bước sau: PL, chọn điểm, QC, viền sản phẩm | unit test |
| K5 | `keep_raw = false` | unit test |
| K6 | Kiểm chứng: chạy lại `ql6_km124_141` theo hành lang và so với v7. Điểm trong hành lang phải trùng vị trí, NMAD chênh vận tốc < 0,3 mm/năm; so cả dung lượng và thời gian. Sau đó lập kế hoạch cho cả tuyến QL6 | **chủ dự án duyệt** |

Quy tắc đối chiếu ở K3: nếu hành lang trùng đúng bbox thì stack phải giống hệt stack dày đặc.

## 5. Rủi ro

- **Đảo rời:** hành lang hẹp đi qua rừng hoặc mặt nước có thể mất độ kết hợp cả một đoạn. Khi đó lưới giải pha bị tách
  thành nhiều mảnh không nối được.
  - K0 sẽ đo các khoảng trống này.
  - Công cụ cảnh báo chỗ điểm thưa, để nới rộng cọ ở đó.
- **Ramp và khí quyển trên dải dài, hẹp:**
  - Mặt phẳng khớp trên dải 2 km × 230 km xác định kém theo chiều ngang của dải.
  - Phải kiểm tra lại `scla_deramp "auto"` và việc chọn ERA5 ở bước K6.
- **Điểm tham chiếu:** chỉ một điểm cho 230 km, nên khí quyển ở xa điểm tham chiếu là sai số lớn nhất. Báo cáo sẽ có
  phần kiểm tra theo từng đoạn.
- **Hiệu năng cọ:** nét dài có hàng nghìn điểm.
  - Trình duyệt làm thưa điểm trước (Douglas–Peucker, khoảng 10 % bề rộng).
  - Server chờ người dùng dừng tay rồi mới tính hợp.

## 6. Kết quả K0

Script `k0_corridor.py` và `k0_whole.py` nằm trong `analyses/` của dự án `ql6_km124_141`.

### 6.1 Tỷ lệ stack mà hành lang cần

**Đoạn `ql6_km124_141`** (16,8 km đường; lưới radar 928 × 4225; mặt nạ nới thêm nửa cửa sổ PL và nhân nội suy):

| Nửa bề rộng | Pixel | Ô 512² (hiện nay) | 256 × 128 | 128 × 128 |
|---|---|---|---|---|
| 250 m | 5,3 % | 44 % | 21 % | 13 % |
| 500 m | 9,0 % | 44 % | 24 % | 16 % |
| 1000 m | 16,5 % | 44 % | 32 % | 24 % |

**Cả QL6 trong phạm vi 104,05–105,82°E** (267 km đường; bbox 178 × 66 km, tức 11.691 km²):

| Nửa bề rộng | Diện tích hành lang | Ô 512² | 256 × 128 | 128 × 128 |
|---|---|---|---|---|
| 500 m | 261 km² (2,2 % bbox) | 10,2 % | 5,4 % | 3,6 % |
| 1000 m | 512 km² (4,4 %) | 11,4 % | 6,8 % | 5,1 % |

Kết luận:
- Ô 512² quá to để bám theo một tuyến hẹp. Stack theo hành lang nên dùng ô **128 × 128**.
- Với cả tuyến QL6, stack giảm từ khoảng 400 GB xuống khoảng 20 GB.
- Bbox nhỏ và đã ôm sát tuyến như `ql6_km124_141` chỉ lợi khoảng 3 lần.

### 6.2 Nguy cơ đứt đoạn

Trên v7, trong hành lang 1 km quanh Km124+300–141+200:
- có 100.344 điểm, trong đó 62.862 điểm có độ kết hợp ≥ 0,6;
- trung vị khoảng 1.000 điểm trên mỗi 200 m đường;
- không có đoạn nào trống. Ô 200 m trống duy nhất ở Km131.7 là do tuyến OSM có một đoạn thẳng 350 m; điểm đo vẫn chỉ cách
  đường 6–12 m.

Như vậy nguy cơ đứt đoạn trên đoạn này thấp. Vẫn phải kiểm tra lại ở các đoạn rừng của cả tuyến.

### 6.3 Mã đang giả định khung chữ nhật dày đặc

Đây là kết quả rà soát mã; số dòng sẽ kiểm lại khi sửa. Có khoảng 40 chỗ, chia ba nhóm:

- **Chỉ dùng bbox:**
  - tìm burst;
  - dấu vân tay (fingerprint) của stack;
  - nạp DEM.

  Trường đa giác `AoiSection.file` đã có trong cấu hình nhưng chưa nơi nào dùng.
- **Đọc nguyên cả mảng, phải chuyển sang đọc theo ô:**
  - dựng stack: hình học, ghi burst, sửa mối nối và tầng điện ly, tái sử dụng ngày cũ;
  - QC stack;
  - phase linking: `pl_pair_coherence` và bộ lọc Gauss sau PL;
  - chọn điểm PS: `_candidates`, độ phân tán biên độ, `pair_coherence`, cập nhật PS;
  - `ps_lite` và `sbas`;
  - xuất raster;
  - một số chỗ đọc góc tới.
- **Coi ô rỗng là dữ liệu thật:**
  - QC: khoảng cách pixel lấy ở hàng giữa, ô cắt ở giữa, kéo giãn biên độ;
  - `edge_margin`;
  - các nút hình học của `ps_lite`;
  - phân vị độ kết hợp trong SBAS.
- **Đã chạy được với dữ liệu thưa:**
  - các bước PS 2–8;
  - ERA5, CERRA và GACOS tại điểm;
  - phép thử SHP (đã loại pixel bằng 0);
  - mặt nạ độ kết hợp trong QC;
  - ESD và `bperp`.

### 6.4 Phạm vi đề xuất (để duyệt)

1. **Làm K1–K2 trước:** cấu hình hành lang và công cụ cọ trên web. Chọn burst theo đa giác đã giảm được lượng tải, ngay cả
   khi stack vẫn dày đặc như hiện nay.
2. **K3–K4 chỉ làm cho chuỗi xử lý anh/chị đang dùng:** stack TOPS Sentinel-1, phase linking, chọn điểm PS/PSDS và xuất
   kết quả.
   - `io/stack.py` có thêm `valid_mask` và `iter_chunks()`, ô 128 × 128.
   - `ps_lite` và `sbas` sẽ báo lỗi rõ ràng khi gặp stack thưa, cho đến khi được chuyển đổi.
3. **Quy tắc đối chiếu giữ nguyên:** nếu hành lang trùng bbox thì stack phải giống hệt từng bit như hiện nay.
