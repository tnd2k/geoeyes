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
- [ ] **V1** Hồ sơ khu vực: `advisor/profile.py`, dùng lại các bộ đọc địa hình, địa chất, lớp phủ; cache trong
  `cache/advisor/`. Kiểm thử trên các AOI đã biết (HCM, Hà Nội, Quảng Nam, Mexico City).
- [ ] **V2** Luật: `rules.toml` + bộ đánh giá nhỏ (`advisor/rules.py`), và `geoeyes advise`. Bộ luật đầu tiên lấy từ
  cài đặt hiện tại của chủ dự án; kiểm tra tái tạo được hcm_d18 và hp_maychai.
- [ ] **V3** Web app: bảng Tư vấn trong wizard và form cài đặt, áp dụng từng trường / tất cả, en + vi.
- [ ] **V4** Báo cáo `--learn` so luật với các dự án đã xong.
- [ ] **V5** (tuỳ chọn) MCP server cục bộ `geoeyes-advisor` với các công cụ `explain_param`, `site_profile`, `recipe`.

## 4. Độ khó

Trung bình. V0 chủ yếu là viết; V1 dùng lại bộ đọc có sẵn (chỉ WorldCover và khí hậu ERA5 là phải tải mới); V2
vài trăm dòng. Phần khó không phải code mà là chính các luật: chúng phải nói đúng kinh nghiệm của chủ dự án, nên
V2 được duyệt từng luật.
