> Bản dịch tiếng Việt của [`docs/en/architecture/decisions.md`](../../en/architecture/decisions.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.

# GeoEyes — Bản ghi quyết định kiến trúc (ADR)

> Trạng thái: **Accepted** (đã chốt) · **Proposed** (đề xuất; mặc định áp dụng nếu không ai phản đối) · **Open** (chờ chủ dự án quyết định).
> Muốn đổi một ADR đã Accepted thì thêm ADR mới ghi "Supersedes ADR-xxx", không sửa nội dung cũ.

| ADR | Tiêu đề | Trạng thái |
|---|---|---|
| 001 | Đặt tên sản phẩm là GeoEyes, bỏ nhãn VINSAR và nhãn của tổ chức cũ | Accepted |
| 002 | Gom về một gói `src/geoeyes`, không dùng `sys.path` | Accepted |
| 003 | Bộ điều khiển dựa trên DAG các pha | Accepted |
| 004 | Định dạng lưu trữ: Zarr / HDF5-schema / GeoParquet / COG / STAC | Accepted |
| 005 | Hình học radar: Capella bỏ TC trước IFG; TSX chưa bỏ | Accepted (Capella) / Open (TSX) |
| 006 | Engine native thay SNAP GPT; SNAP chỉ là backend chuyển tiếp | Accepted |
| 007 | Bỏ xuất bản lên PostGIS/GeoServer | Accepted |
| 008 | Bỏ thông báo; chuyển sang ghi log có cấu trúc | Accepted |
| 009 | Lưu trữ dài hạn: sản phẩm bất biến + STAC + DuckDB | Accepted |
| 010 | Báo cáo khoa học, kết xuất bằng Typst | Accepted |
| 011 | Cấu hình bằng `project.toml` + pydantic | Accepted |
| 012 | Thuật ngữ reference/secondary | Accepted |
| 013 | Phạm vi cảm biến: S1, CSK, ALOS-PALSAR, Capella, TSX | Accepted (thế hệ ALOS: Open) |
| 014 | GPU: CuPy cho kernel, torch chỉ dùng cho ML | Accepted |
| 015 | Ngôn ngữ: tiếng Anh | Accepted |
| 016 | Bỏ mã SOP và mọi thông tin tổ chức | Accepted |
| 017 | Dữ liệu cũ: chạy lại bằng quy trình xử lý mới | Accepted |
| 018 | `point_uid` ổn định | Accepted |
| 019 | Giấy phép riêng của GeoEyes; thay Triangle bằng Delaunay | Accepted |
| 020 | Quy trình Capella = phương pháp `ps_stack` (`ps_stack_gui.py`) | Accepted |
| 021 | Chưa dùng git cho tới khi repo sạch | Accepted |
| 022 | Bỏ GUI desktop; đóng băng webapp, xây lại sau | Accepted |
| 023 | Sentinel-1: tải theo từng burst (ASF burst API), xử lý native ngay trên burst | Accepted |
| 024 | Phân vùng nguy cơ có xét lượng mưa: phân tích tách khỏi sản phẩm, phương pháp ma trận, dùng CHIRPS, dự phòng ERA5 | Proposed |
| 025 | So sánh và hiệu chỉnh bằng GNSS của NGL; mặc định gắn theo phương đứng; phân vùng nguy cơ có thể dùng kết quả này | Proposed |
| 026 | Lọc thông thấp theo thời gian cho SCN: mặc định khớp tuyến tính cục bộ (khác StaMPS `ps_scn_filt`) | Accepted |
| 027 | Tiếng Việt: web song ngữ (EN / VI), bản dịch tiếng Việt của tài liệu; trung tâm thông báo | Accepted |

---

### ADR-027 — Giao diện và tài liệu tiếng Việt; trung tâm thông báo *(Accepted 2026-10-26, bổ sung cho ADR-015)*
**Bối cảnh.** Chủ dự án và người dùng dự kiến đều làm việc bằng tiếng Việt, trong khi ADR-015 chọn tiếng Anh làm
ngôn ngữ của sản phẩm (mã nguồn, log, báo cáo, tài liệu).
**Quyết định.**
- Tiếng Anh vẫn là ngôn ngữ gốc của mã nguồn, định danh, log, báo cáo PDF và các tài liệu trong `docs/`.
- Ứng dụng web **song ngữ**: `webapp/src/i18n.tsx` cung cấp `t("English text")`, lấy chính văn bản tiếng Anh làm
  khoá; mỗi phần giao diện có một module từ điển tiếng Việt (`webapp/src/i18n/vi/*.ts`). Thông điệp do máy chủ sinh
  ra được dịch ngay trong trình duyệt, theo câu chính xác hoặc theo mẫu (`i18n/vi/server.ts`). Nút chuyển EN / VI
  nằm trên thanh đầu trang, mỗi trình duyệt tự nhớ lựa chọn; mặc định theo ngôn ngữ của trình duyệt.
- Tài liệu gốc đặt trong `docs/en/`, **bản dịch** tiếng Việt trong `docs/vi/` (cùng cây thư mục), cùng với `README.vi.md`
  và `webapp/README.vi.md`; đầu mỗi tệp ghi bản gốc và ngày dịch, thuật ngữ thống nhất theo `docs/vi/GLOSSARY.md`.
  Sửa tài liệu tiếng Anh thì cập nhật luôn bản dịch (chỗ nào còn ngờ, bản tiếng Anh là chuẩn).
- Trung tâm thông báo trên web: cảnh báo từ các phân tích và các lần chạy / phân tích đã xong được đưa vào danh sách
  ở biểu tượng chuông (lưu theo trình duyệt), kèm toast và thông báo trên máy (Notification API của trình duyệt, sau
  khi người dùng cho phép); `/api/activity` trả về trạng thái các phân tích đang chạy nền.
**Hệ quả.** Mọi văn bản mới hiển thị cho người dùng đều phải đi qua `t()` và có mục tiếng Việt tương ứng; mọi thông
điệp mới của máy chủ hiển thị trên web phải có mục hoặc mẫu trong `server.ts`.

### ADR-026 — Lọc thông thấp theo thời gian cho SCN: khớp tuyến tính cục bộ *(Accepted 2026-10-25)*
**Bối cảnh.** Trên web app, chuỗi "đã loại SCN" của một điểm ở Mexico City (Sentinel-1, 6 tháng) cứ nằm quanh
0 mm, trong khi điểm đó lún 70 mm (trên toàn cảnh, hai chuỗi chỉ tương quan r ≈ −0,05). Bước 8 lọc thông cao pha
của các cạnh theo thời gian bằng **trung bình** có trọng số Gauss (cửa sổ `scn_time_win` = 365 ngày), giống hệt
StaMPS `ps_scn_filt.m` (Hooper 2006, đã đối chiếu với mã nguồn StaMPS hiện hành) và engine cũ, theo test đối chiếu
(parity) `test_step8_scn`. Trung bình có trọng số sẽ bị chệch ở bất cứ chỗ nào cửa sổ không bao đối xứng quanh xu
hướng: ở hai đầu mọi chuỗi, và trên toàn bộ chuỗi nếu chuỗi ngắn hơn cửa sổ. Khi đó biến dạng lọt sang phần
"nhiễu", nên vận tốc / chuỗi đã loại SCN mất luôn phần biến dạng ấy.
**Quyết định (chủ dự án).** Thêm tham số engine `[ps] scn_time_fit = "linear" | "mean"`, mặc định `linear`: thành
phần thông thấp là hệ số chặn của phép khớp tuyến tính cục bộ có trọng số Gauss (hồi quy đa thức cục bộ: Cleveland
1979, doi:10.1080/01621459.1979.10481038; Fan 1992, doi:10.1080/01621459.1992.10476255); cách này tái tạo chính xác
mọi xu hướng tuyến tính. `legacy_quirks = "y"` giữ `mean` để các test đối chiếu (parity) không đổi; cũng vì vậy mà
`scn_filt(time_fit=...)` mặc định là `mean`.
**Hệ quả.** Chỉ các sản phẩm SCN thay đổi (`phase/scn`, `v_scn_mm_yr`, `disp_scn_mm`); vận tốc và chuỗi chính giữ
nguyên. Tham số mới làm đổi mã băm tham số PS, nên `geoeyes plan` sẽ yêu cầu mọi dự án chạy lại pha `ps` (và các pha
sau đó) một lần. Với các đại lượng SCN, kết quả sẽ khác bước 8 của StaMPS.

### ADR-025 — So sánh và hiệu chỉnh GNSS từ NGL *(Proposed 2026-10-25)*
**Bối cảnh.** Sản phẩm chỉ là tương đối (so với một điểm hoặc với trung bình cảnh), trong khi cường độ nguy cơ cần
nền ổn định. Chủ dự án đặt câu hỏi: GNSS mở (Nevada Geodetic Laboratory) có dùng được để kiểm định và hiệu chỉnh
chuỗi InSAR không ([`docs/en/research/gnss-insar-calibration.md`](../research/gnss-insar-calibration.md)).
**Quyết định.**
- `geoeyes.validation.gnss` (tầng 4): danh sách trạm NGL, các bước nhảy (steps), IGS20 tenv3 và MIDAS được đọc qua
  https và lưu đệm trong `<workspace>/cache/gnss/ngl`; tại các bước nhảy / lần thay thiết bị, chuỗi được chia thành
  nhiều đoạn rồi nối lại với một xu hướng chung.
- So sánh từng trạm với trung vị của các điểm InSAR trong bán kính `radius_m`. GNSS được chiếu lên hướng nhìn của
  vệ tinh (LOS) đầy đủ hoặc **chỉ theo phương đứng (mặc định)**; cách sau triệt tiêu được chuyển động mảng kiến tạo,
  vốn đồng đều trên cả cảnh và không có mặt trong sản phẩm tương đối.
- Hiệu chỉnh `offset` (mặc định) | `plane` (≥ 3 trạm) | `epoch`; khi có từ hai trạm trở lên, kết quả luôn kèm kiểm
  tra chéo bỏ-một (leave-one-out). Kết quả ghi thành một phân tích (`analyses/gnss/<product_id>/`), không bao giờ
  ghi vào sản phẩm.
- Phân vùng nguy cơ chỉ áp dụng hiệu chỉnh này khi được yêu cầu (`[postprocess.hazard] gnss_tie = true`).
**Hệ quả.** Lệnh `geoeyes gnss`, API `/api/projects/{p}/products/{id}/gnss…`, bảng GNSS trong thẻ Validation của dự
án, các trạm GNSS và "GNSS tie" trên trang Hazard. Mexico City: gắn vào GNSS loại được độ lệch tham chiếu
130 mm/năm; Hanoi (một năm, hai trạm): không cải thiện nên không gắn.

### ADR-024 — Phân vùng nguy cơ có xét lượng mưa *(Proposed 2026-10-25)*
**Bối cảnh.** Trước đây lượng mưa chỉ hiện thành các cột mưa tháng bên dưới chuỗi thời gian. Chủ dự án muốn kết hợp
InSAR với lượng mưa để phân vùng nguy cơ sụt lún / trượt lở, theo một phương pháp truy vết được
([`docs/en/research/rainfall-insar-hazard.md`](../research/rainfall-insar-hazard.md)).
**Quyết định.**
- Gói mới `geoeyes.hazard` (tầng 4, ngang hàng postprocess / validation): đọc một sản phẩm rồi ghi một **phân tích**
  vào `<project>/analyses/hazard/<product_id>/` kèm manifest riêng. Sản phẩm vẫn bất biến, còn phân tích thì chạy lại
  được với tham số khác. Lệnh là `geoeyes hazard`; hiện chưa phải một pha của quy trình xử lý.
- Phương pháp: ma trận giữa cường độ InSAR (tốc độ theo hướng nguy cơ, được nâng lên theo kịch bản mưa và theo gia
  tốc) và một lớp phụ (góc biến dạng với sụt lún; tính nhạy cảm hoặc độ dốc với trượt lở), theo cách tiếp cận ma
  trận dựa trên PSI. Liên hệ mưa – biến dạng d = a + b·t + k·CRD(t − τ) được kiểm định bằng chuỗi thay thế (xáo pha
  ngẫu nhiên) và FDR trên toàn bản đồ. Mỗi giá trị mặc định hoặc có nguồn trích dẫn, hoặc được ghi rõ là lựa chọn cục
  bộ cần hiệu chỉnh.
- Lượng mưa: CHIRPS v3 theo từng pixel (mưa tháng + chuẩn khí hậu năm). Dữ liệu được đọc lần lượt từng tệp vì máy
  chủ giới hạn số luồng đọc song song, và được lưu đệm vĩnh viễn. Nếu không đọc được CHIRPS, hệ thống chuyển sang ERA5
  qua API lưu trữ Open-Meteo và lần chạy ghi rõ điều này.
- Tham số đặt trong `[postprocess.hazard]` (dict tự do, do `HazardParams` kiểm tra), giống `[postprocess.alerts]`.
**Hệ quả.** Thêm trang web **Hazard** và API `/api/projects/{p}/products/{id}/hazard…`. Cường độ chỉ có nghĩa khi so
với nền ổn định, nên sản phẩm lấy trung bình cảnh làm tham chiếu sẽ bị cảnh báo, còn `reference_bbox` dùng để đặt lại
tham chiếu cho chúng. Trình tự nghiên cứu R2–R6 (quy nguyên nhân, hiệu chỉnh, tính nhạy cảm, yếu tố kích hoạt, rủi
ro) vẫn còn bỏ ngỏ.

### ADR-001 — Tên sản phẩm GeoEyes
**Bối cảnh.** Có 611 chỗ trong 124 tệp mang nhãn `vinsar`/`VINSAR` hoặc tên tổ chức cũ, kể cả biến môi trường, trường API, khoá localStorage và giá trị mặc định của siêu dữ liệu ISO.
**Quyết định.** Tên sản phẩm `GeoEyes`; gói/CLI `geoeyes`; tiền tố biến môi trường `GEOEYES_`. Không giữ bí danh tương thích cho tên cũ (repo chưa phát hành). Không còn thông tin tổ chức mặc định nào (xem ADR-016).
**Hệ quả.** Các máy đang chạy phải cập nhật `.env` (đã có sẵn `geoeyes migrate env`). Bảng thay thế: `migration-map.md` §11.

### ADR-002 — Một gói duy nhất, src-layout
**Quyết định.** Cài `src/geoeyes/` bằng `pip install -e .`; xoá toàn bộ 107 chỗ dùng `sys.path.insert/append`; ứng dụng đặt trong `apps/`, mã nhúng từ bên ngoài đặt trong `third_party/`. Ranh giới giữa các tầng do `import-linter` kiểm tra.

### ADR-003 — Bộ điều khiển dựa trên DAG các pha
**Bối cảnh.** `vinsar.py` điều phối bằng một chuỗi `if control[...]`; phase linking phải chen vào giữa snap2stamps, nên mã tạm ghi đè `control.json` rồi khôi phục lại từ bản sao lưu.
**Quyết định.** Mỗi bước là một `Phase` khai báo `requires`/`produces`; bộ lập kế hoạch dựng DAG; chạy tiếp dựa trên artifact + fingerprint. Cấu hình bất biến trong suốt một lần chạy.
**Hệ quả.** Bỏ `__vinsar_bak`, `left-off.txt`, `--publish-only`; `--start-step` → `--from <phase>`.

### ADR-004 — Định dạng lưu trữ
**Quyết định.** Chồng ảnh: Zarr v3. Trạng thái engine PS: HDF5 có schema (giữ shape tự nhiên, đặt tên theo StaMPS, đơn vị ghi trong `attrs`). Điểm: GeoParquet; chuỗi thời gian: Parquet dạng long. Raster sản phẩm: COG. Siêu dữ liệu: STAC + ISO 19139. Nguồn gốc dữ liệu (provenance): manifest JSON. Với các định dạng cũ, chỉ giữ bộ đọc trong `io/legacy`.
**Các phương án đã cân nhắc.** Dùng HDF5 cho mọi thứ (đơn giản, như MintPy) — loại, vì với chồng ảnh lớn, HDF5 ghi song song và làm việc với kho lưu trữ đối tượng kém hơn Zarr. NetCDF — tương đương HDF5, không có lợi gì thêm.

### ADR-005 — Hình học radar *(Accepted cho Capella · Open cho TSX)*
**Bối cảnh.** S1/CSK tạo IFG trong hình học radar, còn TSX/Capella hiện hiệu chỉnh địa hình **trước** khi tạo IFG (hình học bản đồ, 2 m).
**Quyết định (2026-10-21).** S1, CSK, ALOS, **Capella**: xử lý trong hình học radar, mã hoá địa lý qua LUT (`GEOMETRY`) lúc dựng sản phẩm — Capella bỏ bước TC trước IFG. **TSX**: giữ hình học bản đồ (TC trước IFG) cho tới khi kiểm chứng xong; vì thế `StackEngine` hỗ trợ `stack.geometry = "radar" | "map"`, mặc định lấy theo preset của từng cảm biến (`terrasar_x` → `map`).
**Hệ quả.** Engine PS và khâu hậu xử lý phải chạy được với cả hai: ở chế độ `map`, `GEOMETRY` là một lưới bản đồ đều (lat/lon trực tiếp, không cần LUT). Test chuẩn (golden) của TSX chạy cả hai chế độ để sau này có cơ sở quyết định.

### ADR-006 — Engine native thay thế SNAP GPT
**Quyết định.** `StackEngine` có hai bản cài đặt: `native` (đích hướng tới) và `snap` (chuyển tiếp: chạy các graph cũ rồi nhập DIMAP vào StackStore). Native làm stripmap/spotlight trước (Capella, CSK, ALOS), TOPS sau. Khi đạt ngưỡng ở ARCHITECTURE §16.3 thì đổi mặc định, sau đó xoá `snap`.
**Các phương án đã cân nhắc.** ISCE3 / s1reader / COMPASS làm phụ thuộc lúc chạy — mạnh nhưng nặng (chỉ có trên conda, C++), khó tuỳ biến; chỉ giữ làm **tham chiếu kiểm chứng**, không phải phụ thuộc lúc chạy. Có thể dùng thư viện nhỏ cho các việc phụ (ví dụ tải quỹ đạo EOF).

### ADR-007 — Bỏ xuất bản lên PostGIS/GeoServer
**Quyết định.** Xoá `to_postgis`, `to_geoserver`, `_publish_*`, `publish_status.json`, `dbschema`, `map_id`, các biến môi trường DB/GeoServer và phụ thuộc SQLAlchemy. Việc truy xuất chuyển sang catalog (ADR-009).

### ADR-008 — Bỏ thông báo, ghi log có cấu trúc
**Quyết định.** Xoá `ops/notify.py` và mọi biến `VINSAR_NOTIFY_*`/`SMTP_*`. Ghi log tập trung: console + `log.jsonl` + log văn bản riêng cho từng pha; ngữ cảnh gồm run/phase/track/tile; cấm dùng `print` trong thư viện.

### ADR-009 — Lưu trữ dài hạn và truy xuất *(Proposed)*
**Quyết định đề xuất.** Sản phẩm bất biến, có phiên bản và checksum; catalog STAC tĩnh; chỉ mục DuckDB (spatial) đọc thẳng Parquet và dựng lại được; các tầng archive/hot/warm/tmp với chính sách lưu giữ; `fsspec` cho NAS/S3/MinIO; `catalog bundle` để bàn giao.
**Lý do.** Không cần máy chủ cơ sở dữ liệu; chỉ một tệp, chạy ngoại tuyến, đủ nhanh với hàng chục triệu điểm; dùng chuẩn mở.

### ADR-010 — Báo cáo khoa học, Typst *(Proposed)*
**Quyết định đề xuất.** Cấu trúc báo cáo theo ARCHITECTURE §13.2; dữ liệu chỉ lấy từ manifest + metrics + sản phẩm; hình matplotlib dạng vector; kết xuất bằng Typst (gói PyPI `typst`, binary tự chứa).
**Các phương án đã cân nhắc.** ReportLab (đang dùng) — dàn trang thủ công, không có phương trình/trích dẫn. LaTeX — chất lượng cao nhưng cài trên Windows rất nặng. WeasyPrint (HTML→PDF) — cần GTK trên Windows.
**Hệ quả.** Thông tin vận hành (các cổng G0–G6) chuyển thành phụ lục tuỳ chọn.

### ADR-011 — `project.toml` + pydantic *(Proposed)*
**Quyết định đề xuất.** Gộp `in.json` + `control.json` thành `project.toml`; thay `config.json` (trạng thái do quy trình xử lý ghi) bằng `.state/state.json` + manifest. Schema pydantic là nguồn chuẩn, từ đó sinh JSON Schema cho webapp. Giữ tên tham số StaMPS trong `[ps.*]`.

### ADR-012 — reference/secondary *(Proposed)*
**Quyết định đề xuất.** Thay `master/slave` trong mã, cấu hình, tên thư mục, tài liệu và báo cáo. Bộ đọc dữ liệu cũ vẫn hiểu tên cũ.

### ADR-013 — Phạm vi cảm biến *(Accepted · thế hệ ALOS: Open)*
**Quyết định (2026-10-21).** Sentinel-1, COSMO-SkyMed, ALOS-PALSAR, Capella, **TerraSAR-X (giữ lại)**. TSX được tái cấu trúc như các cảm biến khác (không mang nhánh TSX cũ của `flow.py` sang; TSX dùng engine PS hợp nhất nên tự động có SBAS/bước 8).
**Thế hệ ALOS (còn mở, không chặn tiến độ).** ALOS-1 PALSAR (2006–2011, chỉ còn dữ liệu lưu trữ), ALOS-2 PALSAR-2 (2014–, CEOS L1.1), ALOS-4 PALSAR-3 (phóng năm 2024; định dạng L1.1 cần kiểm chứng). Chủ dự án **đã có dữ liệu mẫu**; ALOS làm **sau cùng** (Phase 4b, khi S1/CSK/Capella/TSX đã ổn định) — đến lúc đó sẽ xác định thế hệ cụ thể từ dữ liệu mẫu. Bộ đọc thiết kế dạng plug-in cho từng thế hệ. ScanSAR chưa thuộc phạm vi ban đầu.

### ADR-014 — GPU *(Proposed)*
**Quyết định đề xuất.** Kernel mảng: NumPy/Numba (CPU) ↔ CuPy (GPU) qua `core.compute`. Torch chỉ dùng cho mô hình ML. Kernel nào cũng có đường chạy CPU.

### ADR-015 — Ngôn ngữ: tiếng Anh *(Accepted)*
**Quyết định (2026-10-21).** Mã, chú thích, docstring, log, CLI, tài liệu, báo cáo PDF: **tiếng Anh**. Báo cáo không cần i18n (bỏ `report/i18n/`). Các tài liệu kiến trúc hiện có (viết bằng tiếng Việt) sẽ được dịch sang tiếng Anh sau khi chủ dự án rà soát xong v0.1.
**Hệ quả.** Các chuỗi tiếng Việt trong mã hiện tại (báo cáo PDF, README của `modules/ops`, mẫu PR, giao diện webapp…) sẽ được dịch trong quá trình tái cấu trúc.

### ADR-016 — Bỏ mã SOP và thông tin tổ chức *(Accepted)*
**Quyết định (2026-10-21).** Dự án không còn gắn với tổ chức nào. Xoá mã quy trình vận hành cũ, các khối cổng/ký duyệt G0–G6 kiểu SOP, `VINSAR_EVIDENCE_DIR`, cùng mọi tên/e-mail của tổ chức. `[project].organization` chuyển thành **tuỳ chọn**; siêu dữ liệu ISO 19139 chỉ điền thông tin liên hệ khi có khai báo (STAC là siêu dữ liệu chính). Phụ lục vận hành của báo cáo chỉ còn preflight + thời gian chạy.

### ADR-017 — Dữ liệu cũ: chạy lại *(Accepted)*
**Quyết định (2026-10-21).** Không chuyển đổi kết quả cũ; các dự án được chạy lại từ ảnh gốc bằng quy trình xử lý mới.
**Hệ quả.** Bỏ `geoeyes migrate legacy` (bộ chuyển đổi). `io/legacy/*` chỉ giữ những **bộ đọc** cần để (1) test chuẩn (golden) so sánh đầu ra cũ ↔ mới, (2) engine `snap` chuyển tiếp nhập được DIMAP. Xoá `io/legacy` khi xong Phase 5. Phải giữ ảnh gốc trong `data/` (chuyển sang `$WS/archive`). Vẫn giữ `geoeyes migrate config` (in.json → project.toml) để khỏi phải viết lại cấu hình bằng tay.

### ADR-018 — `point_uid` ổn định *(Proposed)*
`<track_id>:<geohash9>:<round(height_m)>`, loại trùng trong phạm vi một sản phẩm; ghép điểm giữa các phiên bản theo uid, sau đó theo điểm lân cận gần nhất. Nhờ vậy theo dõi được chuỗi thời gian qua nhiều lần chạy giám sát.

### ADR-019 — Giấy phép riêng của GeoEyes *(Accepted)*
**Quyết định (2026-10-21).** GeoEyes dùng giấy phép riêng do chủ dự án soạn (`LICENSE` ở thư mục gốc).
- **Triangle** → thay bằng `scipy.spatial.Delaunay` (lấy các cạnh từ `simplices`); xoá `third_party/triangle` và các binary.
- **Bình phương tối thiểu có chính quy hoá L1** (`mintpy_l1regls.py`): bản thân thuật toán là kiến thức công khai, dùng tự do. Tuy vậy, tệp hiện tại là bản port mã nguồn (MintPy ← ví dụ của CVXOPT, cả hai đều GPL-3), nên cần **viết lại sạch** từ thuật toán (ví dụ ADMM/IRLS trên `scipy`, hoặc `cvxpy`/`scipy.optimize` nếu cần) thay vì giữ mã đã port; khi đó không còn ràng buộc GPL. Bỏ phụ thuộc `cvxopt` nếu không còn chỗ nào dùng.
- **appsigsolv**, `stsa`: kiểm tra giấy phép khi di chuyển; `stsa` được thay bằng bộ đọc annotation SAFE tự viết (ADR-006).

### ADR-020 — Quy trình Capella = phương pháp `ps_stack` *(Accepted, sửa đổi 2026-10-21)*
**Quyết định.** Quy trình Capella chính thức là phương pháp trong `modules/ps_stack` (GUI: `tools/ps_stack_gui.py`), **không phải** `tools/capella_ifg_gui.py`.

**Phương pháp (`ps_stack.run_stack`, hiện tại):**
1. Chồng ảnh: đọc các cặp đã đồng đăng ký `<coreg_master>_<sec>.dim` (hình học radar — `flat_earth.corner_check` từ chối dữ liệu đã hiệu chỉnh địa hình) thành các epoch trên lưới của ảnh coreg master; **epoch tham chiếu được chọn độc lập** với coreg master (`auto` = epoch có đường đáy vuông góc lớn nhất là nhỏ nhất).
2. Hình học: tính các điểm địa hình của lưới pixel trên DEM (một lần) và khoảng cách từ mọi epoch tới các điểm đó; mỗi giao thoa đồ có pha tham chiếu −4π/λ·(R_ref − R_k) và độ nhạy độ cao `kh`; quy ước dấu được phát hiện tự động.
3. Đọc dữ liệu một lượt duy nhất: D_A + **đa dạng phổ theo range** (sub-band) cho từng pixel → ứng viên PS → tối đa 1 PS mỗi ô → pha cuộn trừ pha tham chiếu.
4. Giải chập pha từng giao thoa đồ trên lưới PS bằng **IRLS tinh chỉnh hai lượt**: lượt 1 → ước sai số độ cao của PS bằng **periodogram** theo đường đáy; lượt 2 chạy trên pha đã loại độ cao, trọng số theo độ ổn định (Goldstein, chi phí không gian–thời gian, tuỳ chọn tầng đối lưu tuyến tính, loại mặt phẳng) → tinh chỉnh độ cao, khôi phục số nguyên chu kỳ (ambiguity) của từng PS.
5. Vùng tham chiếu (chọn tự động theo D_A hoặc do người dùng chỉ định); **nghịch đảo bình phương tối thiểu có trọng số** cho từng PS: vận tốc LOS, sai số độ cao, số hạng epoch tham chiếu; APS = phần dư sau khi lọc Gauss theo không gian (σ m); chất lượng từng giao thoa đồ (độ lệch chuẩn pha) → loại hoặc giảm trọng số; lọc PS theo độ ổn định pha và độ lệch chuẩn pha.
6. Đầu ra hiện tại: `ps.gpkg`, `ps_stack.npz`, `pairs.csv`, `summary.json`, PNG.

**Thiết kế mục tiêu.**
- `processing/ps_lite/` = phương pháp trên, tách theo bước: `geometry.py` (pha tham chiếu, `kh`, dấu — dùng `geometry/*`), `candidates.py` (D_A + đa dạng phổ, `calibration_factors`, `occupied_band`), `unwrap.py` (hai lượt + periodogram, dùng `unwrap/irls.py` và `unwrap/grid.py`), `invert.py` (vùng tham chiếu, LS có trọng số, bộ lọc không gian APS, chất lượng ifg), `runner.py` (thay `run_stack`).
- Đầu vào lấy từ StackStore (`SLC_STACK` + `GEOMETRY`) thay vì đọc thẳng `.dim`; đầu ra là một `PointSet` → `postprocess` → `build_product` (thay cho `ps.gpkg`/`npz`/`summary.json`). Bảng chất lượng theo cặp (`pairs.csv`) → `QualityMetrics` cho báo cáo.
- Preset `capella` trong `controller/pipelines.py`: `acquire → plan_network → build_stack (radar geometry, no TC) → select_candidates(ps_lite) → ps_lite → postprocess → build_product → report`. `phase_linking`, `atmosphere` (ERA5/GACOS) là plug-in tuỳ chọn.
- Tham số trong `[ps_lite]` của `project.toml` giữ nguyên tên và giá trị mặc định của `run_stack` (`da_max=0.4`, `sd_max=0.45`, `ps_cell=[4,6]`, `uw_cell=[16,24]`, `unwrap_method`, `tcoh_min=0.7`, `aps_sigma_m=1000`, …).
- **Capella không còn dùng engine StaMPS** (`processing/ps`, `flow.py`), chỉ dùng preset `capella`. Hệ quả: xoá `capella/stamps/flow.py` (phần đặc thù của nó đã có trong `csk/stamps/flow.py`, hai tệp chỉ khác nhau 71 dòng); phần chuyển giao sang StaMPS của Capella (`snap2stamps/capella/bin/_3_stamps_export.py`, `_4_stamps_prep.py`, `capella/stamps/synth_sbas_pairs.py`, `prestamps/capella_pscands_geo.py`, `capella/tomo/*`, `phasingpy.ps_export_gis_capella_2d_lon_geo`, `unwrap/irls_solver_capella.py` nếu ps_lite không dùng `unwrap_method="capella"`) bị xoá hoặc chỉ giữ phần dùng chung. Phần đồng đăng ký ảnh của `snap2stamps/capella` (chuyển TIF→DIMAP, vá Doppler, đồng đăng ký **không TC**) vẫn làm engine `snap` của `build_stack` cho tới Phase 5.
- ps_lite là engine độc lập, cũng dùng được cho cảm biến khác nếu muốn, nhưng mặc định chỉ dành cho Capella.
- **Bỏ `unwrap_2d_pipeline`** (quy trình giải chập pha 2D viết riêng cho Capella, 4913 dòng) cùng `unwrap_2d_{da,gaussian,geotiff,plot,gis_export}` và mọi thứ phụ thuộc vào nó (`phuw_2d.mat`, các tham số `unwrap_2d_*`, `phase_images/`). Giữ `unwrap_2d_goldstein` → `stack/native/filters.py`, `unwrap_2d_coherence` → `stack/native/coherence.py` (mã khác vẫn dùng).
- **Lưu trữ thống nhất.** Capella phải có cấu trúc lưu trữ giống mọi cảm biến khác: `stacks/<stack_id>/stack.zarr` → `ps_runs/<psrun_id>/` (manifest + params + `state.h5` theo schema ps_lite + `pairs.parquet`) → `products/<product_id>/` với cùng schema `points.parquet`/`timeseries.parquet`/COG/STAC/manifest/báo cáo. Giữa các engine chỉ khác nhau ở `state.h5` và trường `engine` của manifest (ARCHITECTURE §10.3).
- `tools/ps_stack_gui.py` → `apps/gui/ps_lite_viewer.py` (chọn epoch, tham số, chạy qua bộ điều khiển, xem bản đồ và chuỗi thời gian).
- `tools/capella_ifg_gui.py` **không** thuộc quy trình: giữ làm công cụ khám phá IFG (`apps/gui/ifg_explorer.py`); các thuật toán trong đó (đồng đăng ký bằng tương quan chéo, Lanczos, giải chập pha DCT/branch-cut…) chỉ là **tham chiếu** cho engine native (Phase 5), khi nào thực sự cần mới chuyển vào thư viện.

### ADR-023 — Sentinel-1 theo từng burst, native *(Accepted 2026-10-22)*
**Bối cảnh.** Một IW SLC đầy đủ nặng ~4,5–7 GB, trong khi một AOI thường chỉ cần vài burst (~150 MB/burst). ASF cung cấp burst SLC theo yêu cầu: `https://sentinel1-burst.asf.alaska.edu/<SLC>/<IWx>/<POL>/<burstIndex>.tiff` (GeoTIFF CInt16, 1 burst) + `.xml` cùng đường dẫn (siêu dữ liệu gộp của cả SLC: product annotation của mọi dải con, calibration, noise, rfi, manifest). Tìm kiếm: ASF search API `dataset=SLC-BURST` (lọc theo `fullBurstID` `<track>_<relBurst>_<IWx>`, AOI, ngày). Tải về cần `EARTHDATA_TOKEN` (Bearer) + cookie URS.
**Quyết định.**
- Luồng `acquire` của S1 tải **burst** chứ không tải SLC đầy đủ: chọn burst ID từ AOI một lần (cùng `relativeBurstID` cho mọi epoch → chồng ảnh nhất quán), tải `.tiff` + `.xml` (mọi burst của cùng SLC/pol dùng chung một tệp xml) vào `$WS/archive/sentinel1/<track>/<YYYY>/<SLC>/`.
- Engine `native` đọc thẳng burst (`sensors/sentinel1/burst.py`): annotation → timing, Doppler, FM rate, lưới định vị địa lý, cửa sổ hợp lệ; quỹ đạo chính xác (POEORB) tải riêng vào `cache/orbits`.
- SAFE dựng bằng `burst2safe` chỉ dùng để **đối chiếu golden/chéo** với quy trình SNAP cũ (SNAP TOPSAR-Split cần sản phẩm nhiều dải con → cần các burst cùng ID ở IW1–IW3).
- Không dùng thư viện `asf_search` (CMR lỗi trên máy này) — gọi API trực tiếp.
**Hệ quả.** Dữ liệu tải về nhẹ hơn ~20–40 lần; quy trình S1 native bắt đầu từ burst (Phase 5 được kéo lên sớm để chạy song song với Phase 4 cho S1).

### ADR-022 — Bỏ GUI desktop; webapp xây lại sau *(Accepted 2026-10-21)*
**Quyết định.**
- **GUI desktop**: xoá hẳn (`tools/*_gui.py`, các viewer, `modules/pta/cr_target_gui.py`) cùng các phụ thuộc chỉ GUI dùng (`customtkinter`, `pywinstyles`, `pyperclip`, có thể cả `opencv-contrib-python`). Thuật toán nào quy trình xử lý cần thì đã hoặc sẽ được chuyển vào thư viện (chỉ `_split_spectrum_common.py` cần port mới → `atmosphere/ionosphere.py`). Các CLI bảo trì → lệnh `geoeyes`.
- **Webapp**: không di chuyển. Đóng băng trong Phases 1–8 (không sửa, loại khỏi test), chuyển ra khỏi repo trước `git init` và giữ trong bản sao lưu. Sau này sẽ cùng chủ dự án xây lại trên API công khai của lõi (ARCHITECTURE §15.2).
**Hệ quả.** Phạm vi tái cấu trúc thu hẹp đáng kể; lõi không còn phải tương thích với API webapp cũ (ví dụ `v_vinsar_mm_yr`, router `results/publish`) → tự do đổi tên/đổi schema. Trực quan hoá QC dựa vào báo cáo PDF, QGIS và notebook.

### ADR-021 — Không dùng git cho tới khi repo sạch
**Quyết định (chủ dự án).** Không `git init` cho tới cuối Phase 9. Bù lại: sao lưu zip mã nguồn trước mỗi đợt thay đổi lớn; test chuẩn (golden) là lưới an toàn chính.
