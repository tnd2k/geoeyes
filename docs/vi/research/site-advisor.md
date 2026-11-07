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
- [x] **V3** (xong 2026-11-07) Web app: `GET /api/projects/{name}/advise` và `POST /api/advise {bbox}`
  (`api/advise.py`, cùng code với CLI); `components/AdvisorPanel.tsx`.
  - Form cài đặt: bảng ở trên các mục (tóm tắt khu vực, thay đổi đề xuất với "dùng" / "đưa tất cả vào form", các
    giá trị đã đúng như luật, ghi chú, giá trị không có luật, "đo lại khu vực"); dưới mỗi trường là giá trị của
    luật, xanh khi đã đúng, vàng kèm "dùng" khi chưa. "dùng" chỉ điền vào bản nháp: chưa ghi gì cho tới khi bấm Lưu.
  - Wizard tạo dự án: "Hỏi bộ tư vấn khu vực" sau bước chọn vùng; phương pháp, khí quyển và số ảnh mỗi tháng điền
    vào các ô của chúng (mặc định ERA5 của wizard được thay ở đồng bằng phẳng), các giá trị khác ghi vào
    project.toml sau khi tạo nếu đánh dấu ô chọn.
  - Test `tests/unit/api/test_api_advise.py` (dự án, áp dụng qua endpoint cài đặt, bbox).
- [x] **Luật theo cảm biến** (2026-11-08, sau khi thử bộ luật trên một dự án COSMO-SkyMed ở trung tâm Hà Nội). Bộ luật
  đầu tiên rút từ các dự án Sentinel-1; với CSK, `urban-psi` tắt liên kết pha, trái với chuỗi CSK của chủ dự án.
  Giờ có 18 luật: `urban-psi` chỉ cho băng C; `csk-chain` giữ liên kết pha và lọc Gauss σ 1.5 cho COSMO-SkyMed;
  `s1-every-date` (max_per_month = 0) chỉ cho Sentinel-1, `soft-urban-subsidence` giữ ghi chú về điểm tham chiếu cho
  mọi cảm biến; `long-gap` so khoảng trống lớn nhất với chu kỳ chụp của cảm biến (`data.gap_ratio > 4`) và ghi λ/4
  theo băng. `data.sensor` / `data.band` lấy từ cấu hình khi chưa có stack. CSK Hà Nội khi đó: một thay đổi
  (`ps.subtr_tropo` y -> n), liên kết pha và σ 1.5 đã đúng như preset.
- [x] **V4** (xong 2026-11-07) `geoeyes advise --learn [--lang vi] [--out report.md]` (`advisor/learn.py`): mọi dự án
  của workspace qua bộ luật. Dự án đã xong (có sản phẩm) được tính là bằng chứng, dự án khác chỉ được liệt kê. Các
  mục: dự án, luật (áp dụng ở đâu, giá trị giữ đúng / đặt khác trong dự án đã xong), chỗ dự án đã xong khác luật,
  khoá [ps] engine không đọc, giá trị đặt ở từ hai dự án đã xong trở lên mà chưa có luật (ứng viên luật mới), luật
  chưa áp dụng ở đâu.
  - Báo cáo đầu tiên (2026-11-07, 2 dự án đã xong): không dự án đã xong nào khác luật. Phát hiện thêm: `[ps]
    da_threshold` trong hcm_d18 và hp_maychai **không được engine đọc** (ngưỡng nằm ở `[selection] da_threshold`; ở
    đó vô hại vì 0.42 là mặc định). Engine giờ ghi log các khoá `[ps]` nó không đọc (`processing/ps/params.py`
    `OPTIONAL`, `unknown_keys`), và bộ tư vấn liệt kê chúng kèm khoá đúng.
- [x] **V5** (xong 2026-11-07) MCP server cục bộ `geoeyes mcp` (`advisor/mcp.py`, chỉ dùng thư viện chuẩn: JSON-RPC 2.0
  qua stdin / stdout). Các công cụ, chỉ đọc: `explain_param`, `site_profile`, `advise`, `list_rules`. Bộ tư vấn không
  bao giờ gọi mô hình; server chỉ cho Claude đọc nó. Đăng ký trong Claude Code:
  - CLI: `claude mcp add geoeyes-advisor -- geoeyes --workspace <workspace> mcp`;
  - hoặc file `.mcp.json` ở thư mục gốc repo (không đưa vào git: đường dẫn riêng của máy):
    `{"mcpServers": {"geoeyes-advisor": {"type": "stdio", "command": "<env>/Scripts/geoeyes.exe",
    "args": ["--workspace", "<workspace>", "mcp"]}}}`; Claude Code hỏi cho phép một lần.

## 4. Độ khó

Trung bình. V0 chủ yếu là viết; V1 dùng lại bộ đọc có sẵn (chỉ WorldCover và khí hậu ERA5 là phải tải mới); V2
vài trăm dòng. Phần khó không phải code mà là chính các luật: chúng phải nói đúng kinh nghiệm của chủ dự án, nên
V2 được duyệt từng luật.
