# Skill: lún lệch dọc hạ tầng tuyến và độ lún cố kết còn lại

> Bản dịch của [docs/en/skills/lines-and-consolidation.md](../../en/skills/lines-and-consolidation.md). Dịch ngày 2026-11-01.

> Lập trắc dọc tốc độ lún InSAR dọc đê, nền đắp, đường sắt và đường chính (OpenStreetMap), đánh dấu những đoạn lún
> thay đổi đủ nhanh dọc tuyến để gây hại; riêng phần cố kết thì khớp một đường cong cố kết cho các ô đang lún để ước
> tính độ lún còn lại và thời gian cần để lún hết.
> Trạng thái: sàng lọc đang vận hành (v1, 2026-10-26). Đối chiếu với mã lần gần nhất 2026-11-01.
> Lệnh `geoeyes lines`, `geoeyes consolidation`; web app **Phân tích chuyên sâu → Phân tích chuyên đề**, các lớp "Hạ
> tầng tuyến" và "Lún còn lại".

## 1. Khi nào dùng

- **Hạ tầng tuyến.** Điều gây hại cho đê, đường ray hay đường bộ là độ lún *thay đổi dọc theo tuyến*: chỗ trũng trên
  đỉnh đê là nơi nước tràn qua đầu tiên; chỗ trũng dưới đường ray làm cong ray. Dùng `lines` để tìm các đoạn đó và độ
  hạ đỉnh trong một khoảng thời gian.
- **Cố kết.** Đất yếu dưới tải trọng mới lún nhanh lúc đầu rồi chậm dần, tiến tới một giá trị cuối; còn sụt lún do
  khai thác nước ngầm kéo dài chừng nào còn bơm. Dùng `consolidation` để tách hai trường hợp và ước tính độ lún cuối
  cùng, độ lún còn lại của các ô đang lún tiến tới giới hạn.
- **Không dùng cho.** Các đoạn võng dài, thoải trên nhiều kilômét (β chỉ xét cục bộ ở 100 m: hãy dùng độ hạ đỉnh),
  các tuyến không có trên OSM, hay đọc cố kết trên chuỗi chưa chứa đoạn uốn của đường cong (thường một năm là chưa
  đủ).

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Sản phẩm điểm | có, cho `lines` | [insar-processing.md](insar-processing.md) | `projects/<name>/products/<id>/points.parquet` có `lon`, `lat`, `vel_los_mm_yr`, `los_u` | Mật độ PS trên công trình quyết định độ phủ |
| Các tuyến OSM | có, cho `lines` (tự động) | Overpass API (`overpass-api.de`), một truy vấn trên khung bao của sản phẩm | bộ đệm `<workspace>/cache/osm/overpass_<hash>.json` | ODbL, ghi nguồn © OpenStreetMap contributors. Xoá tệp đệm để đọc lại OSM |
| Phân vùng nguy cơ của sản phẩm | có, cho `consolidation` | [hazard-zoning.md](hazard-zoning.md): `geoeyes hazard <project> --product <id>` | `projects/<name>/analyses/hazard/<id>/` (`hazard.json`, `cells.parquet`, `cells_ts.npy`) | Dùng chuỗi của ô, `rate_mm_yr` và `mode`. Cần ≥ 8 lần chụp |
| Tuyến đê tốt hơn | tuỳ chọn | Tuyến đê chính thức, hoặc dò đỉnh đê từ DEM (nghiên cứu L1) | Mã không đọc trực tiếp: bổ sung vào OSM, hoặc so sánh bên ngoài GeoEyes | Hà Nội: mới có 15,7 km đê trên bản đồ, phủ 21 % (ghi chú nghiên cứu §4.1) |
| Tham số | tuỳ chọn | – | `[postprocess.lines]`, `[postprocess.consolidation]` | Khoá lạ làm lệnh dừng |

Danh sách kiểm tra trước khi chạy:

- [ ] Truy cập được Overpass API (lần đầu; máy chủ giảm tải bằng mã 429/504, mã thử lại 3 lần).
- [ ] Đã biết tham chiếu của sản phẩm; tốc độ dọc tuyến là tương đối so với tham chiếu đó.
- [ ] Với cố kết: phân vùng là bản mới nhất, có ≥ 8 lần chụp, và khoảng thời gian bao được hằng số thời gian dự kiến.
- [ ] Chấp nhận giả định chỉ có chuyển dịch thẳng đứng (v_LOS / l_u), hoặc có kết quả tách thành phần để so sánh
  ([decompose-and-soft-soil.md](decompose-and-soft-soil.md)).

## 3. Phương pháp

### 3.1 Hạ tầng tuyến (`src/geoeyes/ml/lines.py`, `LinesParams`)

1. **Các way OSM** trên khung bao sản phẩm: `man_made=dyke` hoặc `highway` có tên bắt đầu bằng "Đê " → `dyke`;
   `railway=rail` → `railway`; `embankment=yes` trên đường bộ → `embankment`; `highway=motorway|trunk|primary` →
   `road` (chỉ khi `roads` = true). Các way cùng loại, cùng tên (hoặc `ref`) chung nút đầu/cuối được nối tham lam
   thành một tuyến.
2. **Trạm** cách nhau `step_m` (50 m) dọc mỗi tuyến (tuyến ngắn hơn một bước bị bỏ). Tại mỗi trạm lấy trung vị của
   v_vert = v_LOS / max(l_u, 0,2) của các điểm trong bán kính `buffer_m` (30 m), nếu có ≥ `min_points` (3). Dấu
   GeoEyes: âm = lún.
3. **Góc biến dạng** giữa các trạm cách nhau `span_m` (100 m) (k = round(span/step) trạm):

       β = |v(x + L) − v(x)| · horizon_yr / (1000 · L)       horizon_yr = 10

   phân lớp theo `distortion_breaks` (1/500, 1/300, 1/150): 0 dưới giới hạn an toàn (Bjerrum), 1 vượt giới hạn đó,
   2 nứt, 3 hư hại kết cấu (Skempton & MacDonald). Trạm bị **đánh dấu** khi lớp ≥ 1.
4. **Độ hạ đỉnh** của mỗi tuyến: max(0, −min v) × `horizon_yr` (mm), tại trạm lún nhanh nhất.

### 3.2 Cố kết (`src/geoeyes/ml/consolidation.py`, `ConsolidationParams`)

1. Độ lún s = −d (dương xuống), đặt bằng 0 ở ngày đầu, cho mọi ô của phân vùng.
2. **Ô ứng viên:** `mode = subsidence` và `rate_mm_yr` ≤ −`min_rate_mm_yr` (2 mm/năm).
3. **Khớp** (Terzaghi 1925, bậc một): s(t) = c + A·(1 − e^(−t/τ)); τ trên lưới cấp số nhân 80 giá trị từ 0,05 đến
   30 năm, (c, A) bằng bình phương tối thiểu cho mỗi τ; giữ τ tốt nhất. Đồng thời khớp đường thẳng s = a + b·t.
4. **Đang cố kết** khi thoả cả: là ứng viên; ΔBIC = BIC_thẳng − BIC_cong ≥ `min_delta_bic` (6), với k = 2 cho đường
   thẳng và 3 cho đường cong; A > 0; 0,05 năm < τ < `max_tau_factor` (5) × khoảng thời gian.
5. **Kết quả:** độ lún cuối = c + A; còn lại sau ngày cuối T = A·e^(−T/τ); t90 kể từ nay = max(0, τ·ln 10 − T).
6. **Kiểm tra (dự báo):** cả hai mô hình khớp trên m = max(6, round(`train_share` 0,7 × n)) lần chụp đầu rồi dự báo
   phần còn lại (cần ≥ 3 lần chụp kiểm tra); báo sai số tuyệt đối trung bình và tỉ lệ ô mà đường cong thắng.
7. **Asaoka (1978)**, web app vẽ cho từng ô: số đọc lấy mẫu lại mỗi round(khoảng thời gian/8) ngày, kẹp trong 12–60
   ngày; đường sᵢ = β₀ + β₁·sᵢ₋₁; độ lún cuối = β₀/(1 − β₁) khi 0 < β₁ < 1. Không dùng để phân lớp.

## 4. Các bước triển khai

1. **Hạ tầng tuyến.** `geoeyes lines <project> --product <id>` (ví dụ `--set roads=false`, `--set span_m=200`).
   Web: Phân tích chuyên đề → lớp "Hạ tầng tuyến" → **Lập trắc dọc hạ tầng tuyến**. Khoảng một phút ở lần đầu
   (Overpass), sau đó dùng bộ đệm.
   Ghi ra `projects/<name>/analyses/lines/<id>/`: `stations.parquet`, `lines.parquet`, `lines.json`,
   `manifest.json`.
2. **Phân vùng** (cho cố kết): `geoeyes hazard <project> --product <id>` ([hazard-zoning.md](hazard-zoning.md)).
3. **Cố kết.** `geoeyes consolidation <project> --product <id>` (ví dụ `--set min_rate_mm_yr=5`).
   Web: lớp "Lún còn lại" → **Phân tích cố kết**. Vài giây (theo chú thích trên web app).
   Ghi ra `projects/<name>/analyses/consolidation/<id>/`: `consolidation.parquet`, `consolidation.json`,
   `manifest.json`.
4. Tuỳ chọn: `geoeyes geology` đọc `consolidation.parquet` để kiểm tra c_v suy ra
   ([decompose-and-soft-soil.md](decompose-and-soft-soil.md)).

## 5. Kết quả và cách đọc

**`stations.parquet`**: `line`, `chainage_m`, `lon`, `lat`, `n_points`, `v_vert_mm_yr`, `beta` (NaN ở k trạm đầu và
nơi trạm không có tốc độ), `beta_class` (−1 không có giá trị, 0–3).

**`lines.parquet`**: `line`, `kind`, `name`, `length_m`, `stations`, `covered_share`, `v_min_mm_yr`,
`v_median_mm_yr`, `beta_max`, `flagged`, `loss_mm` (độ hạ đỉnh đê hoặc mặt ray trong khoảng thời gian xét).

**`lines.json`**: `by_kind` (số tuyến, km, tỉ lệ phủ, số trạm bị đánh dấu), `hotspots` (20 tuyến bị đánh dấu có β lớn
nhất), ghi nguồn.

**`consolidation.parquet`** (mỗi ô phân vùng một dòng): `consolidating`, `tau_yr`, `settled_mm`, `final_mm`,
`remaining_mm`, `t90_from_now_yr`, `c_mm`, `A_mm`, `delta_bic`. Các giá trị này là **độ lún, dương xuống** (không
theo dấu GeoEyes). **`consolidation.json`**: `sinking_cells`, `consolidating`, `remaining_mm` (trung vị, p90, max),
`tau_yr_median`, `check` (`mae_curve_mm`, `mae_line_mm`, `curve_better_share`).

Cách đọc: một đoạn xám trên tuyến là thiếu dữ liệu, không phải ổn định. Ô đang cố kết với τ ngắn và gần như không còn
lún là một tải trọng đã lún gần xong (Hà Nội, ghi chú nghiên cứu §4.2).

## 6. Kiểm tra chất lượng

- **Độ phủ** theo từng loại (`covered_share`) trước khi coi một tuyến là an toàn.
- **Trạm bị đánh dấu** đối chiếu trên bản đồ: một trạm đơn lẻ giữa hai trạm lân cận phủ tốt là hợp lý; trạm ở rìa
  vùng phủ có thể là nhiễu.
- **Kiểm tra cố kết.** Phép kiểm tra luôn nghiêng về đường cong trên các ô đã chọn (thiên lệch do chọn mẫu, ghi chú
  nghiên cứu §3.3). Nó cho biết đường cong có dự báo được không, không cho biết cách đọc có đúng không.
- **τ so với khoảng thời gian.** τ gần một nửa khoảng thời gian (Mexico S1: τ ≈ 0,27 năm trên sáu tháng) cũng giải
  thích được bằng bơm nước chậm lại theo mùa hoặc một tải trọng mới: cần xác nhận bằng chuỗi dài hơn.
- **Độ hợp lý của c_v** qua `geoeyes geology`: giá trị nằm xa ngoài 0,1–10 m²/năm bác bỏ bề dày hoặc cách đọc cố kết.

## 7. Hạn chế và lỗi thường gặp

- Độ đầy đủ của OSM: đường sắt và đường chính được vẽ tốt, đê thì không (thường chỉ có con đường trên đỉnh đê).
- Mái đê và nền đắp cho ít điểm tán xạ.
- Tốc độ là tương đối so với tham chiếu của sản phẩm và chỉ là thẳng đứng khi giả định không có chuyển dịch ngang.
- β chỉ phát hiện chỗ uốn ở thang `span_m`.
- Khoá bộ đệm Overpass là chính truy vấn (khung bao và `roads`): đổi `roads` sẽ tải lại; các chỉnh sửa mới trên OSM
  không được thấy cho tới khi xoá tệp đệm.
- Cố kết cần đoạn uốn nằm trong dữ liệu; nén thứ cấp (từ biến) chưa được mô hình hoá, nên độ lún cuối là cận dưới
  nơi từ biến đáng kể.
- Chạy lại cố kết sau khi chạy lại phân vùng (nó đọc `cells_ts.npy` và `rate_mm_yr`).

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- **Cần đổi:** `step_m` và `buffer_m` theo mật độ điểm (băng X dày: nhỏ hơn); `span_m` theo thang uốn của công trình;
  `horizon_yr` theo tầm quy hoạch; `roads = false` để chỉ giữ đê, đường sắt, nền đắp.
- **Cách đặt tên tại chỗ:** quy tắc nhận đê dựa vào tên bắt đầu bằng "Đê " (Việt Nam); nơi khác chỉ đọc đê từ
  `man_made=dyke`.
- **Cố kết:** cần chuỗi nhiều năm (nghiên cứu C1: từ 3 năm Sentinel-1 hoặc COSMO-SkyMed trên các khu đô thị mới).
  Tăng `min_rate_mm_yr` nơi tham chiếu chưa chắc chắn.
- **Kết quả đã có** (ghi chú nghiên cứu §4): Hanoi S1, 582 tuyến, một trạm vượt 1/500 (đường Đỗ Mười, β 1/446);
  Mexico City S1, 570 tuyến, β lớn nhất 1/127 trên Autopista México – Puebla.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/ml/lines.py`, `consolidation.py`; `src/geoeyes/hazard/zoning.py` (`classify`);
  `src/geoeyes/api/behaviour.py` (bảng thông tin ô, bước Asaoka); `webapp/src/pages/Hazard.tsx`, `LearnLines.tsx`
  (Nguyên lý, chương 4); test `tests/unit/ml/test_lines_consolidation.py`.
- Nghiên cứu: [../research/lines-and-consolidation.md](../research/lines-and-consolidation.md).
- Skill: [hazard-zoning.md](hazard-zoning.md), [behaviour-and-risk.md](behaviour-and-risk.md) ("chậm dần" là dạng mà
  cố kết mô tả chính xác hơn), [decompose-and-soft-soil.md](decompose-and-soft-soil.md).
- Bài báo: Terzaghi 1925; Asaoka 1978 (*Soils and Foundations* 18(4):87); Skempton & MacDonald 1956; Bjerrum 1963;
  Kass & Raftery 1995; Tan 1971 (phương pháp hyperbol, nghiên cứu C3).
