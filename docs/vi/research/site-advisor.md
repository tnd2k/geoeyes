# Bộ tư vấn khu vực: từ một khu vực ra công thức xử lý

Chủ dự án đề xuất ngày 2026-11-07. Có khoảng 120 tham số xử lý và rất dễ quên tham số nào dùng để làm gì. Mục
tiêu: chọn một khu vực là thấy ngay khu vực đó cần xử lý những gì (hiệu chỉnh nào, phương pháp nào) và đặt tham
số ra sao, kèm lý do của từng lựa chọn. Phải chạy **không cần LLM**, nên không tốn token: luật cố định dựa trên các
đặc trưng đo được của khu vực.

## 1. Những gì đã có

- Mỗi trường trong form đã có một dòng giải thích (`api/settings.py` `FIELDS`, `PS_GROUPS`, tiêu đề tiếng Việt).
- Các chế độ `auto` dựa trên dữ liệu, thực chất đã là luật theo khu vực trong engine: `scla_deramp = "auto"`,
  `subtr_tropo` / `[atmosphere] select = "auto"`, `[sbas] troposphere = "auto"` (chênh cao < 100 m → tắt),
  `max_topo_err = "auto"`, `unwrap_time_win = "auto"`.
- Lớp dữ liệu nền: địa hình (`landslide/terrain.py`), địa chất (`ancillary/geology.py`), lớp phủ và các biến
  (`landslide/predictors.py`, `ml/layers.py`), mặt nạ nước, tải DEM.
- Thói quen đặt tham số của chủ dự án: lưới unwrap 10 m (HCM 50 m), PL `ad` + `adaptive`, unwrap IRLS, chuỗi CSK
  không wavelet / FAMM.

Còn thiếu: một nơi nối đặc trưng khu vực với tham số, và nói rõ vì sao.

## 2. Thiết kế

Ba phần, đều là Python thuần và tệp dữ liệu.

1. **Danh mục tham số** `advisor/params.toml` (TOML như phần còn lại của dự án), mỗi tham số một mục: section, key, pha, mục đích, lợi ích,
   cái giá / rủi ro, giá trị thường dùng, tham số liên quan, en + vi. Phần help của form sinh ra từ đây (một nguồn
   thay vì hai).
2. **Hồ sơ khu vực** `geoeyes.advisor.profile(bbox, sensor)` → một dict nhỏ các đặc trưng đo được, cache theo AOI:
   - địa hình: chênh cao p5–p95, độ dốc trung vị, tỉ lệ dốc > 20°;
   - lớp phủ: tỉ lệ đô thị / thực vật / đất canh tác / nước (ESA WorldCover);
   - khí hậu: lớp Köppen, độ ẩm trung bình và mùa mưa (khí hậu ERA5);
   - địa chất: tỉ lệ trầm tích mềm (lớp địa chất có sẵn);
   - dữ liệu: cảm biến, bước sóng, số ảnh, chu kỳ lặp, độ trải baseline (từ tìm kiếm ASF hoặc stack).
3. **Luật** `advisor/rules.toml`: `if` (điều kiện trên hồ sơ) → `set` (giá trị tham số) + `why` (en + vi)
   + `source` (bài báo, ADR hoặc dự án đã rút ra kinh nghiệm). Ví dụ:
   - đô thị > 0.5 → `method = psi`, `da_threshold = 0.4`, `unwrap_grid_size = 10`;
   - thực vật > 0.5 và băng C → `psds`, bật phase linking (`ad`, `adaptive`), hoặc `sbas`;
   - chênh cao > 500 m → `[atmosphere] method = era5`, `subtr_tropo = auto`; chênh cao < 100 m → tắt tầng đối lưu;
   - trầm tích mềm > 0.3 và đô thị (HCM, Hà Nội) → lún nhanh: `unwrap_ps_rate`, `unwrap_grid_size = 50` cho HCM,
     `scn_time_fit = linear`;
   - phần lớn dốc > 20° → chế độ trượt lở: chiếu theo hướng dốc trong `hazard`, cả quỹ đạo lên + xuống;
   - dưới khoảng 20 ảnh → cảnh báo (phép thử SHP và tốc độ điểm kém tin cậy; `ps_lite` chỉ dành cho Capella / Umbra,
     schema từ chối nó với Sentinel-1).
   Luật có thứ tự; luật sau, cụ thể hơn, ghi đè luật trước; xung đột được liệt kê, không bị giấu.

Kết quả: một **công thức** — giá trị từng tham số, kèm lý do và luật đã đặt nó, cùng phần khác biệt so với
`project.toml` hiện tại. Chủ dự án áp dụng một lần bấm hoặc từng trường.

### Hiển thị ở đâu, không tốn token

- Web app: wizard (dự án mới) và form cài đặt, bảng "Tư vấn" cạnh mỗi mục; mỗi trường hiện "đề xuất: X, vì …".
- CLI: `geoeyes advise <project>` hoặc `geoeyes advise --bbox W S E N`, dạng văn bản hoặc TOML.
- MCP (tuỳ chọn, bước V5): một MCP server cục bộ nhỏ bọc cùng các hàm đó, để Claude tra danh mục và công thức khi
  cần. Bộ luật không bao giờ gọi LLM; MCP chỉ cho LLM đọc khi muốn.

### Học từ các dự án đã xong

Mỗi dự án đã có `project.toml` và kết quả QC. Lệnh `geoeyes advise --learn` gom các cài đặt chủ dự án giữ lại
sau khi xem xét (hcm_d18, hp_maychai, mexico_s1, hanoi_s1…) cùng hồ sơ khu vực, và chỉ ra chỗ luật khác với cái
thực sự đã dùng. Luật được sửa tay từ báo cáo đó; không tự khớp (quá ít dự án).

## 3. Các bước (duyệt sau mỗi bước)

- [x] **V0** (xong 2026-11-07) Danh mục: `src/geoeyes/advisor/params.toml`, 105 mục (help, dùng để, rủi ro,
  thường dùng, liên quan; en + vi), đọc bởi `advisor/catalog.py`, form ("vì sao?" dưới mỗi trường, tìm trong nội
  dung) và `geoeyes params`; test `tests/unit/advisor/test_param_catalog.py`. Ban đầu: viết `params.yaml` cho mọi trường trong form (từ `FIELDS`, tài liệu StaMPS và các ADR), sinh
  help của form từ đó. Không đổi hành vi.
- [x] **V1** (xong 2026-11-07) Hồ sơ khu vực: `advisor/profile.py`, `geoeyes site <project> | --bbox=W,S,E,N
  [--lang vi] [--json]`; test `tests/unit/advisor/test_site_profile.py`.
  - địa hình: `ml.layers.terrain` trên ô 30 m (thô hơn khi quá 2,5 triệu ô); chênh cao p5–p95 như `[sbas]
    troposphere = auto`; độ dốc trung vị / p90, tỉ lệ > 20° và > 35°;
  - lớp phủ: tỉ lệ từ `ml.layers.worldcover`; địa chất: tỉ lệ GLiM (`landslide.predictors.lithology`), bở rời =
    "su";
  - khí hậu: một yêu cầu Open-Meteo ERA5 tại tâm (10 năm trọn vẹn mưa, nhiệt độ, độ ẩm theo ngày); lớp
    Köppen-Geiger tính từ khí hậu theo tháng (Peel và cs. 2007; khi cả hai tiêu chí mùa hè khô và mùa đông khô cùng
    đúng thì nửa năm mưa nhiều hơn quyết định), nên không phải tải bản đồ khí hậu;
  - dữ liệu: theo quỹ đạo từ stack QC (`stacks/*/qc/qc.json`: số ảnh, khoảng thời gian, chu kỳ, khoảng trống lớn
    nhất, B⊥ p5–p95, độ nhất quán trung vị, độ cao mơ hồ; băng từ bước sóng); chưa có stack thì lấy ngày trong cấu
    hình. Độ nhất quán QC bằng 1,0 ở mọi ngày được cảnh báo (gặp ở hp_maychai). Đếm số ngày trên ASF trước khi có
    stack để lại cho V2 nếu luật cần.
  - Cache: địa hình, lớp phủ, địa chất theo AOI + DEM trong `cache/advisor/site_*.json`; khí hậu ở dạng yêu cầu
    thô (các lớp tính lại); dữ liệu không cache. Phần nào lỗi thì được liệt kê trong `errors`.

  Các hồ sơ đầu tiên (2026-11-07):

  | AOI | chênh cao | dốc > 20° | lớp phủ | trầm tích bở rời | Köppen, mưa |
  |---|---|---|---|---|---|
  | hcm_d18 (TP.HCM tây nam) | 11,7 m | 0 % | đô thị 58 %, cây 17 % | 100 % | Aw, 1887 mm |
  | hp_maychai (Hải Phòng) | 10,2 m | 0 % | đô thị 44 %, nước 18 % | 100 % | Cwa, 1841 mm |
  | hanoi_s1_desc | 10,7 m | 0 % | đô thị 30 %, cây 29 %, ruộng 28 % | 100 % | Cwa, 1852 mm |
  | Nam Trà My (Quảng Nam) | 1162 m | 62 % | cây 90 % | 0 % | Af, 4328 mm |
  | Mexico City | 92 m | 1 % | đô thị 72 % | 86 % | Cwb, 789 mm |
- [x] **V2** (xong 2026-11-07, các luật chờ chủ dự án duyệt từng luật) Luật: `src/geoeyes/advisor/rules.toml` (16
  luật, 3 vùng đặt tên), bộ đánh giá `advisor/rules.py`, `geoeyes advise <project> | --bbox=W,S,E,N [--lang vi]
  [--json] [--apply]`; test `tests/unit/advisor/test_rules.py`.
  - Điều kiện có dạng `<metric> <op> <giá trị>` (không dùng eval); metric hồ sơ không có thì luật "không đánh giá".
  - Luật sau thắng; giá trị bị thay được hiển thị. Ghi chú chỉ khuyên, không đặt gì.
  - So với dự án: cần đổi, đã đúng như luật, và các giá trị trong project.toml không luật nào giải thích.
  - `--apply` ghi thay đổi qua code của form cài đặt (có kiểm tra, file cũ giữ trong `.state/`).

  Kết quả (2026-11-07): hcm_d18 và hp_maychai: **không cần đổi gì** (8 và 5 giá trị đã đúng như luật; còn lại không
  có luật: `da_threshold` 0.42 = mặc định, điểm tham chiếu SARPROZ của hcm_d18). hanoi_s1_desc: một thay đổi,
  `acquire.max_per_month` 2 -> 0 (soft-urban-subsidence); luật dữ liệu không đánh giá (chưa có stack). Nam Trà My:
  ERA5 + psds + liên kết pha (ad, adaptive) + DA 0.6 + copernicus-30, ghi chú về đối lưu nhiệt đới và lên + xuống.
- [ ] **V3** Web app: bảng Tư vấn trong wizard và form cài đặt, áp dụng từng trường / tất cả, en + vi.
- [ ] **V4** Báo cáo `--learn` so luật với các dự án đã xong.
- [ ] **V5** (tuỳ chọn) MCP server cục bộ `geoeyes-advisor` với các công cụ `explain_param`, `site_profile`, `recipe`.

## 4. Độ khó

Trung bình. V0 chủ yếu là viết; V1 dùng lại bộ đọc có sẵn (chỉ WorldCover và khí hậu ERA5 là phải tải mới); V2
vài trăm dòng. Phần khó không phải code mà là chính các luật: chúng phải nói đúng kinh nghiệm của chủ dự án, nên
V2 được duyệt từng luật.
