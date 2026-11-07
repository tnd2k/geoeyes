# Skill: từ chồng ảnh băng X mở (ICEYE, Capella, Umbra) đến dự án

> Bản dịch của [docs/en/skills/opendata-stacks.md](../../en/skills/opendata-stacks.md). Dịch ngày 2026-11-01.

> Tìm các chồng ảnh chụp lặp trong danh mục STAC mở của ICEYE, Capella và Umbra, tải phần ảnh trên một vùng và tạo
> dự án GeoEyes từ đó. Trạng thái: vận hành. Kiểm tra gần nhất 2026-11-01. CLI: `geoeyes opendata sync | sources |
> scenes | stacks | show | fetch | project`. Web app: Projects → Open data.

## 1. Khi nào dùng

- Bạn muốn làm InSAR băng X độ phân giải cao mà không phải mua ảnh, hoặc cần một chồng ảnh thử cho chuỗi stripmap /
  spotlight.
- Câu hỏi đặt ra là "ở nơi này có chồng ảnh chụp lặp nào mở không, bao nhiêu ngày, bao lâu một lần?", rồi "xử lý nó".
- Không dùng cho: Sentinel-1 (burst lấy từ ASF qua `[acquire] date_range`, xem
  [insar-processing.md](insar-processing.md)); chồng ảnh đánh dấu *search only* (GeoEyes chưa có bộ đọc định dạng
  đó); các lớp ngập lụt và phơi nhiễm của Source Cooperative (`geoeyes coop`, xem skill exposure-and-flood-layers).

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Truy cập Internet tới AWS S3 (us-west-2) | có | bucket công khai, không cần tài khoản hay khoá | — | ICEYE `iceye-open-data-catalog`, Capella `capella-open-data`, Umbra `umbra-open-data-catalog` (đều CC-BY 4.0) |
| Không gian làm việc | có | như mọi dự án | `GEOEYES_WORKSPACE` | chỉ mục lưu ở `<workspace>/cache/opendata/` |
| Chỉ mục dữ liệu mở cục bộ | có | `geoeyes opendata sync` (hoặc trang web tự làm) | `<workspace>/cache/opendata/<source>.json`, `places.json` | web app tự làm mới khi chỉ mục cũ hơn 24 giờ |
| AOI | có (fetch, project) | khung nằm trong vùng phủ chung của chồng ảnh | `--bbox=W,S,E,N` → `[aoi] bbox` | viết `--bbox=` có dấu `=` khi kinh độ tây âm |
| Mã chồng ảnh | có | `geoeyes opendata stacks` | `[acquire] opendata = "<source>:<name>"` | ví dụ `iceye:x53-sm-ar-26-28.2n016.7w` |
| DEM | tự động (ICEYE, Umbra) | `[stack] dem` (dự án) hoặc `--dem` (fetch, mặc định `copernicus-30`) | bộ đệm `<workspace>/cache/dem` | cho độ cao thấp nhất / cao nhất của AOI để tính cửa sổ cắt |
| Lề cắt | tuỳ chọn | `[acquire] opendata_margin_m` hoặc `--margin` | mét quanh AOI | mặc định ICEYE 500 m, Umbra 50 m (`opendata/fetch.py MARGIN_M`); Capella không cắt |
| Tên dự án và phương pháp | có (project) | tự chọn | `geoeyes opendata project <stack> <name>`; `--method` | mặc định `ps_lite` cho Capella và Umbra, `psi` cho ICEYE |
| Ghi công | có (khi công bố) | giấy phép của nhà cung cấp | "© ICEYE", "© Capella Space", "© Umbra" trên bản đồ và báo cáo | ICEYE lưu ý danh mục mở có thể chứa sản phẩm thử nghiệm |

Danh sách kiểm tra:

- [ ] `geoeyes opendata sources` cho thấy thời điểm `synced` gần đây và số cảnh của mỗi nguồn.
- [ ] Chồng ảnh là *supported* (`--supported`) và đủ ngày (≥ 3; thực tế từ 15 trở lên cho `psi`, chồng spotlight
      ngắn dùng `ps_lite`).
- [ ] AOI nằm trong vùng phủ chung của mọi ngày (đường viền đỏ trên web app).
- [ ] Umbra: AOI nhỏ (điểm ảnh 0,15 m: 200 m × 200 m ≈ 1300 × 1500 điểm ảnh) và nằm trên công trình ổn định.
- [ ] Ổ đĩa: Capella tải nguyên cảnh, 0,3–1,5 GB mỗi ngày.

## 3. Phương pháp

**Chỉ mục.** `sync` duyệt từng danh mục (`opendata/crawl.py`), chỉ tải các URL item chưa có trong chỉ mục (item STAC
của các danh mục này không đổi; 32 truy vấn song song) và bỏ các item đã bị gỡ. Mỗi item thành một bản ghi cảnh:
nguồn, mã, URL item, thời điểm, vệ tinh, chế độ chụp, hướng bay, phía nhìn, góc tới, phương vị nhìn, phân cực, vệt
mặt đất của nhà cung cấp (`capella:rgt_id`), bbox, vùng phủ, định dạng sản phẩm và URL tài sản (`opendata/sources.py`).
Item ICEYE cần tài sản `slc-cog` và `slc-json`, Capella cần `sar:product_type = SLC` kèm một tài sản phân cực, Umbra
cần tài sản `*SICD*.nitf`. Sau `sync`, tâm các chồng ảnh được đặt tên bằng mã hoá địa lý ngược (Nominatim, dự phòng
Photon, ≤ 1 truy vấn/giây, lưu đệm theo tâm làm tròn 0,1°).

**Chồng ảnh** (`opendata/stacks.py`, chỉ dựa trên hình học STAC).

1. Nhóm cảnh theo nguồn, theo vệ tinh (ICEYE: mỗi chồng một vệ tinh) hoặc vệt mặt đất của nhà cung cấp (Capella;
   Umbra trộn nhiều vệ tinh), chế độ chụp, hướng bay, phía nhìn.
2. Trong một nhóm, theo thứ tự thời gian, cảnh nhập vào cụm đầu tiên mà cảnh tham chiếu (cảnh sớm nhất của cụm) có góc
   tới chênh trong `incidence_tol` (ICEYE, Capella 1°; Umbra 4°), phương vị nhìn chênh trong `azimuth_tol` (3°) và
   vùng phủ chồng nhau ≥ 50 % vùng phủ nhỏ hơn.
3. Mỗi ngày một cảnh (cảnh đầu). Có `--bbox` thì chỉ tính các cảnh có vùng phủ chứa trọn AOI; chồng ảnh được giữ nếu
   còn ≥ `--min-scenes` (3) ngày. Cụm được lập từ mọi cảnh nên mã không phụ thuộc AOI.
4. Mã: `<source>:<platform>-<mode>-<pass><look>-<incidence>-<lat><lon>[-t<băm của vệt mặt đất>]`, ví dụ
   `iceye:x53-sm-ar-26-28.2n016.7w` (X53, stripmap, quỹ đạo lên, nhìn phải, 26°, 28,2° N 16,7° W); cụm thứ hai trùng
   mọi trường được thêm `-2`. Phần tóm tắt: các ngày, ngày đầu / cuối, khoảng cách ngày trung vị và nhỏ nhất, dải góc
   tới, vùng phủ chung (giao của mọi vùng phủ), `supported` (nguồn có bộ đọc GeoEyes).

**Tải ảnh** (`opendata/fetch.py`), mỗi ngày một thư mục `<root>/YYYYMMDD/`:

- ICEYE SLC-COG: cửa sổ TIFF phủ AOI, tính bằng mô hình RPC của sản phẩm trên lưới 11 × 11 điểm của AOI ở độ cao
  elipxoit thấp nhất và cao nhất của DEM (−50 m / +50 m; không có DEM: độ cao trung bình cảnh ± 300 m), cộng lề (số
  mẫu theo phương nhìn ngang = lề·sin(góc tới) / kích thước điểm ảnh range, số dòng = lề / kích thước điểm ảnh
  azimuth), đọc theo dải 512 dòng bằng truy vấn HTTP range rồi ghi thành SLC-COG nhỏ hơn; thêm `geoeyes:crop` vào
  JSON. Cửa sổ nhỏ hơn 64 × 64 điểm ảnh nghĩa là AOI không nằm trong cảnh.
- Umbra SICD: tìm tệp NITF trong `sar-data/task-data/<umbra:task_id>/` (lần thu cách item không quá 10 phút), cửa sổ
  tính từ phép chiếu ảnh SICD ở cùng các độ cao, đọc từng dòng, ghi thành `*SICD*.tif` (complex64) + XML của mảnh
  cắt (`FirstRow / FirstCol`).
- Capella: GeoTIFF SLC và `*_extended.json` như nhà cung cấp phát hành.
- `opendata.json` (chồng ảnh, AOI, lề, item, số byte) được ghi khi một ngày tải xong; thư mục có cùng yêu cầu thì không
  tải lại.

**Trong một dự án.** `[acquire] opendata` bật pha `acquire` (khi `[acquire] archive` để trống). Pha này tính lại chồng
ảnh với AOI của dự án (`min_scenes = 1`), giữ các cảnh phủ trọn AOI, áp `date_range` và `max_per_month`, rồi tải vào
`<workspace>/archive/<sensor>/<track_id>/`. Dấu vân tay của pha là danh sách item, AOI và lề: một ngày mới trên danh
mục (sau `sync`) chỉ tải riêng ngày đó và `build_stack` thêm nó theo kiểu gia tăng. Phần còn lại theo
[insar-processing.md](insar-processing.md), kèm các kiểm tra hình học của bộ dựng (ICEYE: hướng bay ≤ 2°, khoảng cách
gần ≤ 3 %, PRF ≤ 0,5 % so với tham chiếu; Umbra: góc tới ≤ 3°, tham chiếu ở góc tới trung tâm).

## 4. Các bước triển khai

1. **Lập chỉ mục danh mục.** `geoeyes opendata sync` (khoảng 1–2 phút lần đầu, các lần sau vài giây) → in số cảnh,
   số mới, số bị gỡ, số không đọc được của từng nguồn. `geoeyes opendata sources` cho biết trạng thái. Web app: mở
   Projects → *Open data* là tự làm (và mỗi ngày một lần); *Refresh the list* để làm ngay.
2. **Tìm chồng ảnh.** `geoeyes opendata stacks --supported` (tất cả), hoặc `geoeyes opendata stacks --bbox=-16.68,28.24,
   -16.60,28.30` (phủ một vùng); bộ lọc `--source`, `--from`, `--to`, `--mode`, `--min-scenes`. Các cảnh:
   `geoeyes opendata scenes --bbox=...`. Web app: danh sách xếp theo số ngày, mỗi chồng một chấm trên bản đồ (ICEYE
   xanh lam, Capella cam, Umbra tím).
3. **Xem chi tiết.** `geoeyes opendata show <stack id>`: JSON gồm các ngày, vệ tinh, góc tới, khoảng cách ngày, bbox, cảnh.
4. **Tạo dự án.** `geoeyes opendata project <stack id> <name> --bbox=W,S,E,N [--method psi|ps_lite]` (vài giây) →
   `projects/<name>/project.toml` có `[aoi] bbox`, `[[tracks]] sensor, direction`, `[acquire] opendata`. Web app: bấm
   một chồng ảnh → vùng đề xuất (ICEYE khoảng 3 km quanh tâm, Umbra khoảng 150 m, Capella gần hết vùng phủ) và dung
   lượng tải → *Draw another area* nếu cần → đặt tên → *Process this stack* (ghi dự án với `[atmosphere] method =
   "none"` và mở quy trình xử lý của nó).
5. **Chạy.** `geoeyes run <name>`: `acquire` tải ảnh (ICEYE khoảng 10 MB mỗi ngày cho 1,5 km × 1,5 km, Umbra khoảng
   30 MB cho 200 m × 200 m, Capella 0,3–1,5 GB mỗi ngày; ../guide/opendata.md §5), sau đó xử lý như
   [insar-processing.md](insar-processing.md).
6. **Chỉ tải** (không tạo dự án): `geoeyes opendata fetch <stack id> --bbox=... [--track-id ID] [--margin M]
   [--dem copernicus-30]` → `<workspace>/archive/<sensor>/<sensor>-<asc|desc>/YYYYMMDD/`.

## 5. Kết quả và cách đọc

| Tệp | Nội dung |
|---|---|
| `<workspace>/cache/opendata/<source>.json` | thời điểm `synced` và các bản ghi cảnh |
| `<workspace>/cache/opendata/places.json` | tên địa danh của tâm các chồng ảnh ("" = không có tên, ví dụ trên biển) |
| `<archive>/<sensor>/<track_id>/YYYYMMDD/` | ICEYE `ICEYE_*_SLC.tif` + `.json`; Umbra `*SICD*.tif` + `.xml` (hoặc `.nitf`); Capella `.tif` + `_extended.json`; `opendata.json` |
| `projects/<name>/project.toml` | khai báo tối giản; phần còn lại lấy từ preset của vệ tinh |

Các cột của `stacks`: mã, số ngày, ngày đầu..cuối, khoảng cách ngày trung vị (ngày), dải góc tới, địa danh, "(search
only: no reader)" khi chưa hỗ trợ. Các chồng ảnh đã biết ngày 2026-10-28 (../guide/opendata.md §7): 72 chồng có
≥ 3 ngày (65 Capella, 2 ICEYE, 5 Umbra); ví dụ `iceye:x53-sm-ar-26-28.2n016.7w`, Tenerife, 19 ngày, cách nhau 1 ngày,
B⊥ −873..+75 m.

## 6. Kiểm tra chất lượng

- Trước khi xử lý: các ngày và khoảng cách giữa chúng (`show`), dải góc tới (dải rộng trong chồng spotlight làm mất
  độ nhất quán).
- Sau `acquire`: thư mục ngày nào cũng có `opendata.json`; dung lượng đúng như dự kiến.
- Log của `build_stack`: các dòng "scene left out (not the reference geometry)" và B⊥ của từng ngày; các ngày ICEYE
  chụp bằng chùm khác (PRF khác) bị loại có chủ đích (Tenerife 2026-02-27..03-01: độ nhất quán 0,16–0,23 so với
  0,4–0,8).
- Kiểm tra chồng ảnh tự chạy với các vệ tinh này: độ lệch < 0,1 điểm ảnh, không ngày nào chỉ toàn nhiễu
  ([stack-qc.md](stack-qc.md)).

## 7. Hạn chế và lỗi thường gặp

- Chồng ảnh chỉ được tìm theo hình học STAC; đường cơ sở vuông góc chỉ biết sau khi đọc sản phẩm.
- Mã chồng ảnh lấy từ cảnh sớm nhất của cụm: nếu danh mục thêm một cảnh sớm hơn, mã sẽ đổi.
- Đặt đồng thời `[acquire] archive` và `opendata` thì pha `acquire` bị tắt.
- Umbra: các lượt chụp lặp lệch góc nhìn 1–2° trong khi khẩu độ góc chỉ khoảng 4,5°, đường cơ sở hàng km (độ cao ứng
  với một vân dưới một mét), mặt nước và bãi container mất nhất quán: chỉ kỳ vọng độ nhất quán trên công trình.
- Danh mục mở có thể chứa sản phẩm thử nghiệm; bộ đọc từ chối hướng ảnh hay loại sản phẩm lạ thay vì đoán.
- Tên địa danh cần mạng lúc `sync`; `stacks` chỉ đọc bộ đệm.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- Chọn AOI trên bản đồ, bên trong vùng phủ chung; với ICEYE giữ vài km (tải phần cắt), với Umbra vài trăm mét trên
  nhà, đường, bến cảng.
- Chồng Umbra ở Mỹ: `[stack] dem = "lidar-3dep"`; cố định `[network] reference` ở góc tới trung tâm nếu không muốn lựa
  chọn tự động (`lasvegas_umbra`: `reference = 2025-08-03`, 42,0°, mọi cảnh trong phạm vi 3°).
- ICEYE theo preset của COSMO-SkyMed (liên kết pha + lọc Gauss sau liên kết, `max_perp_m = 1000`; tuỳ chọn thử
  nghiệm `unwrap_align_constant` đang tắt, muốn thử thì đặt `"y"`, xem [insar-processing.md](insar-processing.md) §3).
- Một nguồn mới cần một mục `Source` (gốc danh mục, hàm chuẩn hoá, dung sai), một hàm tải và một bộ đọc vệ tinh.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/opendata/{sources,crawl,index,stacks,fetch,places}.py`, `controller/phases/acquire.py`,
  `cli/main.py` (`cmd_opendata`), `api/opendata.py`, `webapp/src/pages/OpenData.tsx`, `sensors/iceye/slc_cog.py`,
  `sensors/sicd/`, `processing/stack/native/{stripmap,sicd_stack}.py`.
- Hướng dẫn: ../guide/opendata.md. Quyết định: ../architecture/decisions.md ADR-028, ADR-029.
- Skill: [insar-processing.md](insar-processing.md), [stack-qc.md](stack-qc.md).
- NGA SICD Volume 3 (phép chiếu ảnh); trang chương trình dữ liệu mở của ICEYE, Capella, Umbra (giấy phép CC-BY 4.0).
