# Skill: kiểu chuyển dịch, chuyển dịch từng công trình và rủi ro công trình

> Bản dịch của [docs/en/skills/behaviour-and-risk.md](../../en/skills/behaviour-and-risk.md). Dịch ngày 2026-11-01.

> Cho biết mỗi ô của phân vùng nguy cơ chuyển dịch theo kiểu nào (ổn định, đều, theo mùa, nhanh dần, chậm dần, khởi
> phát, bước nhảy, kèm thời điểm thay đổi), tính vận tốc và độ nghiêng của từng công trình có điểm tán xạ bền vững,
> rồi kết hợp nguy cơ với những gì nằm trên mặt đất để xếp mức rủi ro cho từng công trình.
> Trạng thái: sàng lọc đang vận hành (v1, 2026-10-26). Đối chiếu với mã lần gần nhất 2026-11-01.
> Lệnh `geoeyes behaviour`, `geoeyes buildings`, `geoeyes risk`; web app **Phân tích chuyên sâu → Phân tích chuyên
> đề**, các lớp "Kiểu chuyển dịch", "Thời điểm thay đổi", "Rủi ro công trình".

## 1. Khi nào dùng

- **Kiểu chuyển dịch** (`behaviour`). Hai ô cùng tốc độ có thể cần xử lý khác nhau: nén chặt đều đặn, chuyển dịch
  mới khởi phát sau thi công, chu kỳ theo mùa, hay chuyển dịch đang tắt dần. Dùng để tìm điểm khởi phát và gia tốc,
  và để phát hiện những lần chụp làm lệch nhiều ô cùng lúc.
- **Công trình** (`buildings`). Vận tốc và độ nghiêng của từng công trình có đủ điểm tán xạ bền vững (PS): công trình
  nào lún hoặc nghiêng vượt ngưỡng hư hại.
- **Rủi ro** (`risk`). Một bãi đất trống và một trường học cùng lún nhanh có cùng mức nguy cơ nhưng rủi ro rất khác.
  Dùng để xếp thứ tự công trình cần kiểm tra.
- **Không dùng cho.** Đánh giá kết cấu (không có loại kết cấu, móng hay số người sử dụng), dự báo hư hại, hay đọc
  lớp trên chuỗi ngắn hơn khoảng một năm (theo mùa) hoặc dưới 9 lần chụp (bị từ chối).

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Phân vùng nguy cơ của sản phẩm | có, cho `behaviour` và `risk` | [hazard-zoning.md](hazard-zoning.md): `geoeyes hazard <project> --product <id>` | `projects/<name>/analyses/hazard/<id>/` (`hazard.json`, `cells.parquet`, `cells_ts.npy`) | Behaviour dùng chuỗi và ngưỡng ổn định; risk dùng mức, lớp, ngưỡng và ma trận |
| Sản phẩm điểm | có, cho `buildings` | [insar-processing.md](insar-processing.md) | `projects/<name>/products/<id>/points.parquet` có `lon`, `lat`, `vel_los_mm_yr`, `los_u` | PS trên mái và tường; sản phẩm chỉ có DS cho ít công trình |
| Đường bao công trình Overture | có, cho `buildings` và `risk` (tự động) | PMTiles công trình của Overture Maps, bản `2026-10-21.0`, đọc từng ô zoom 14 qua HTTP | bộ đệm `<workspace>/cache/overture/<release>/` | Giấy phép ODbL + CC BY 4.0: ghi nguồn Overture, OpenStreetMap, Google, Microsoft |
| Phân tích công trình | nên có, cho `risk` | `geoeyes buildings <project> --product <id>` | `projects/<name>/analyses/buildings/<id>/buildings.parquet` | Thiếu thì mọi công trình lấy mức của ô (có cảnh báo) |
| Chiều cao GlobalBuildingAtlas | tuỳ chọn, bật mặc định | Lớp `gba-buildings` của Source Cooperative (`tge-labs/globalbuildingatlas-lod1`), xem [exposure-and-flood-layers.md](exposure-and-flood-layers.md) | `[postprocess.risk] gba_heights = true`; bộ đệm `<workspace>/cache/sourcecoop/` | Bổ sung chiều cao còn thiếu trong Overture. Lỗi mạng thì giữ nguyên chiều cao cũ |
| Tham số | tuỳ chọn | – | `[postprocess.behaviour]`, `[postprocess.risk]`; `buildings` chỉ nhận `--set` (không có mục trong project.toml) | Khoá lạ làm `behaviour` và `risk` dừng |

Danh sách kiểm tra trước khi chạy:

- [ ] Phân vùng nguy cơ là bản mới nhất (chạy lại behaviour và risk sau mỗi lần phân vùng lại).
- [ ] Phân vùng có ≥ 9 lần chụp (behaviour từ chối nếu ít hơn); khoảng thời gian ≥ 0,9 năm cho mô hình theo mùa.
- [ ] Phân vùng đã tham chiếu về nền ổn định (`reference_bbox` hoặc `gnss_tie`): risk kế thừa các mức của nó.
- [ ] Truy cập được kho Overture (lần đầu) và Source Cooperative (chiều cao).
- [ ] Đã chạy `geoeyes buildings` trước `geoeyes risk`, để công trình có điểm riêng được tính từ chính các điểm đó.

## 3. Phương pháp

### 3.1 Kiểu chuyển dịch (`src/geoeyes/ml/behaviour.py`, `BehaviourParams`)

Chuỗi của mỗi ô (`cells_ts.npy`, dấu GeoEyes, t tính bằng năm từ ngày đầu) được khớp bình phương tối thiểu với:

| Lớp | Mô hình | Số tham số k |
|---|---|---|
| ổn định / đều | d = a / d = a + b·t | 1 / 2 |
| theo mùa | d = a + b·t + c·sin 2πt + e·cos 2πt (chỉ khi khoảng thời gian ≥ `min_span_seasonal_yr` 0,9) | 4 |
| nhanh dần / chậm dần | d = a + b·t + c·t² | 3 |
| khởi phát | d = a + b·t + h·(t − t₀)₊ | 4 (tính cả t₀) |
| bước nhảy | d = a + b·t + δ·H(t − t₀) | 4 (tính cả t₀) |

- BIC = n·ln(RSS/n) + k·ln n (Schwarz 1978). Mô hình phức tạp có BIC thấp nhất chỉ được giữ khi nó hạ BIC so với
  đường thẳng ít nhất `min_delta_bic` (6, mức "mạnh" theo Kass & Raftery 1995).
- Nếu không: "đều" khi |b| ≥ ngưỡng ổn định của ô trong phân vùng (`stable_mm_yr`, tức max(2, 2σ)), ngược lại "ổn
  định".
- "Nhanh dần" khi |b + 2c·t_cuối| > |b| (chuyển dịch tăng lên, theo cả hai chiều), ngược lại "chậm dần";
  `acc_mm_yr2` = 2c.
- t₀ được thử ở mọi lần chụp, chừa `edge_epochs` (3) lần mỗi bên. Cần ít nhất 2·`edge_epochs` + 3 = 9 lần chụp.
- **Ngày thay đổi chung.** Một ngày bị cảnh báo và đưa vào `shared_change_dates` khi số khởi phát + bước nhảy ở ngày
  đó đạt ≥ max(20, 5 × trung vị theo ngày) và ≥ 25 % tổng số thay đổi: khả năng cao là do một lần chụp (khí quyển,
  giải chập pha) chứ không phải mặt đất.

### 3.2 Công trình (`src/geoeyes/ml/buildings.py`, `analyse`)

- Điểm nằm *trong* đường bao Overture được gán cho công trình đó; mỗi công trình cần `min_points` (3).
- v_vert = v_LOS / max(l_u, 0,2); `v_los`, `v_vert` là trung vị; `spread` = P90 − P10 của v_vert.
- **Độ nghiêng** (≥ `min_points_tilt` 8 điểm trải trên ≥ `min_extent_m` 20 m): mặt phẳng v = a + b·x + c·y;
  |∇v| = √(b² + c²) (mm/năm trên mét) chỉ được giữ khi ≥ `tilt_t` (3) lần sai số chuẩn của nó.
  `tilt_10yr` = |∇v| · 10 / 1000: độ nghiêng cứng, phân lớp theo `tilt_breaks` (1/500, 1/250, 1/100; Burland 1995).
- **Góc biến dạng** (schema `buildings/2`, 2026-11-05): phần dư r của mặt phẳng; `beta_10yr` = P90 của
  |r_i − r_j| / d_ij trên các cặp cách nhau ≥ `min_pair_m` (5 m) × 10 / 1000 (góc xoay tương đối, đã bỏ độ nghiêng
  cứng); chỉ giữ khi ≥ `beta_t` (2) lần ngưỡng nhiễu (`distortion_noise`). Phân lớp theo `distortion_breaks`
  (1/500, 1/300, 1/150: Bjerrum 1963; Skempton & MacDonald 1956). Sản phẩm ghi trước thay đổi này chứa độ nghiêng
  trong `beta_10yr`; cần chạy lại.

### 3.3 Rủi ro (`src/geoeyes/ml/risk.py`, `RiskParams`)

- **Nguy cơ H (0–4).** Mặc định: mức của ô phân vùng chứa trọng tâm công trình (`source = "cell"`); không có ô →
  chưa đánh giá (`none`). Dùng InSAR riêng (`source = "building"`) khi công trình có ≥ `min_points_own` (5) điểm và
  không nằm trong ô trượt lở: I từ −`v_vert` với `subsidence_breaks` và ngưỡng ổn định của phân vùng (≥ 2 mm/năm); S
  = lớp lớn hơn giữa `beta_10yr` và `tilt_10yr` của chính nó khi có ý nghĩa, nếu không lấy S của ô; H = `matrix`[I][S] của phân vùng.
- **Mức độ phơi nhiễm E (1–3).** Tổng diện tích sàn = diện tích chiếm đất × số tầng; số tầng = max(1, round(chiều
  cao / `floor_height_m` 3)). Chiều cao: Overture, nếu không có thì GlobalBuildingAtlas (`gba_heights`), nếu vẫn
  không có thì số tầng trung vị của các công trình có chiều cao (2 nếu không công trình nào có). E1 < 300 m² ≤ E2 <
  3000 m² ≤ E3 (`exposure_breaks_m2`).
- **Tính dễ tổn thương V (1–3).** V3 nếu cao ≥ `tall_m` (21) hoặc √diện tích ≥ `long_m` (30); V1 nếu diện tích <
  `small_m2` (60) và chiều cao không vượt 2 × `floor_height_m` (không rõ chiều cao thì coi là thấp); còn lại V2.
- **Hệ quả và rủi ro:**

  | C | V1 | V2 | V3 |
  |---|---|---|---|
  | E1 | 1 | 1 | 2 |
  | E2 | 1 | 2 | 3 |
  | E3 | 2 | 3 | 3 |

  | R | C1 | C2 | C3 |
  |---|---|---|---|
  | H0 rất thấp | 0 | 0 | 1 |
  | H1 thấp | 0 | 1 | 1 |
  | H2 trung bình | 1 | 2 | 2 |
  | H3 cao | 2 | 3 | 4 |
  | H4 rất cao | 3 | 4 | 4 |

Cơ sở đã công bố: Berti et al. 2013 (phân lớp tự động chuỗi thời gian PS), Schwarz 1978, Kass & Raftery 1995,
Burland & Wroth 1974, Peduto et al. 2017, thuật ngữ UNDRR 2016.

## 4. Các bước triển khai

1. **Phân vùng.** `geoeyes hazard <project> --product <id>` ([hazard-zoning.md](hazard-zoning.md)).
2. **Kiểu chuyển dịch.** `geoeyes behaviour <project> --product <id>` (ví dụ `--set min_delta_bic=10`).
   Web: Phân tích chuyên đề → lớp "Kiểu chuyển dịch" → **Phân loại kiểu chuyển dịch**. Chạy trong vài giây (mọi ô
   khớp cùng lúc; vài phần mười giây cho 45 000 ô, ghi chú nghiên cứu §2.2).
   Ghi ra `projects/<name>/analyses/behaviour/<id>/`: `behaviour.parquet`, `behaviour_fit.npy`, `behaviour.json`,
   `manifest.json`.
3. **Công trình.** `geoeyes buildings <project> --product <id>` (ví dụ `--set min_points_tilt=10 --set tilt_t=4`).
   Chỉ có trên CLI. Lần đầu tải các ô Overture trên vùng sản phẩm (có bộ đệm). Ghi ra
   `projects/<name>/analyses/buildings/<id>/`: `buildings.parquet`, `buildings.json`, `manifest.json`.
4. **Rủi ro.** `geoeyes risk <project> --product <id>` (ví dụ `--set gba_heights=false`).
   Web: lớp "Rủi ro công trình" → **Đánh giá rủi ro công trình**. Đọc các ô Overture (đã đệm) và chiều cao
   GlobalBuildingAtlas. Ghi ra `projects/<name>/analyses/risk/<id>/`: `risk.parquet`, `risk.json`, `manifest.json`.
5. Thời gian chạy của `buildings` và `risk` chưa đo; nó tăng theo số công trình (Hanoi S1: 450 198; Mexico S1:
   1 663 658) và lần tải đầu.

## 5. Kết quả và cách đọc

**`behaviour.parquet`** (mỗi ô phân vùng một dòng, cùng thứ tự): `class` (hoặc `not assessed`), `class_id`,
`change_date` (khởi phát/bước nhảy), `rate_mm_yr`, `rate_before_mm_yr` / `rate_after_mm_yr` (khởi phát),
`acc_mm_yr2` (nhanh dần/chậm dần), `seasonal_amp_mm`, `jump_mm` (bước nhảy), `delta_bic`. `behaviour_fit.npy` = mô
hình được giữ của mỗi ô. `behaviour.json`: `counts`, `changes_by_month`, `shared_change_dates`, `warnings`. Dấu: âm
= lún hoặc xuôi dốc; "nhanh dần" là lún nhanh hơn với ô đang lún và nâng nhanh hơn với ô đang nâng.

**`buildings.parquet`**: `id` (mã GERS của Overture), `lon`, `lat`, `area_m2`, `height_m`, `n`, `v_los`, `v_vert`,
`spread`, `tilt`, `tilt_se`, `beta_10yr`. `buildings.json`: tổng số, `with_tilt`, `beta_over_1_500`, phiên bản và
ghi nguồn.

**`risk.parquet`** (mỗi công trình Overture một dòng): `id`, `lon`, `lat`, `area_m2`, `height_m`, `floors`,
`height_known`, `height_source` (`overture` / `gba` / `assumed`), `source` (`building` / `cell` / `none`),
`points`, `v_vert_mm_yr`, `beta_10yr`, `hazard`, `exposure`, `vulnerability`, `consequence`, `risk` (0–4, −1 chưa
đánh giá). `risk.json`: `by_risk`, `footprint_km2_by_risk`, `by_source`, `height_known_share`, `height_from_gba`,
`median_floors_assumed`, ghi nguồn, cảnh báo.

Cách đọc: mức rủi ro cho biết nên kiểm tra ở đâu trước, không cho biết cái gì sẽ nứt. Ở Mexico S1 (ghi chú nghiên
cứu §4), phần lớn công trình ở mức trung bình hoặc cao là do nguy cơ (lún đều 100–350 mm/năm sau khi gắn vào GNSS),
không phải do bản thân công trình.

## 6. Kiểm tra chất lượng

- **Ngày thay đổi chung.** Kiểm tra mọi ngày trong `shared_change_dates` trước khi đọc khởi phát và bước nhảy
  (Hanoi S1: 2026-09-09; Mexico S1: 2024-06-08; Hanoi CSK: 2014-01-10). Bước nhảy vài mm giữa hai ngày thường là lỗi
  giải chập pha hơn là chuyển dịch thật.
- **Số lớp so với khoảng thời gian.** Dưới 0,9 năm không có lớp theo mùa; với một năm, theo mùa và khởi phát có thể
  lẫn nhau (ghi chú nghiên cứu §5).
- **Độ nghiêng.** Chỉ dùng giá trị `tilt` (đã lọc theo `tilt_t`); so `beta_10yr` với 1/500 và 1/300.
- **Độ phủ chiều cao.** `height_known_share` trong `risk.json`: dưới 50 % thì có cảnh báo. Ở Hà Nội, Overture có chiều
  cao cho 1,4 % công trình, lên 67 % khi thêm GlobalBuildingAtlas ([../guide/opendata.md](../guide/opendata.md)).
- **Cơ cấu nguồn.** `by_source`: chỉ công trình có điểm riêng mới được đánh giá riêng (2 % ở Hà Nội, 1 % ở Mexico,
  ghi chú nghiên cứu §5); số còn lại mang giá trị trung bình của ô 100 m.
- **Tham chiếu của phân vùng.** Nếu phân vùng chỉ tương đối theo trung bình cảnh, nguy cơ và do đó rủi ro bị lệch;
  sửa phân vùng trước.

## 7. Hạn chế và lỗi thường gặp

- Bộ mô hình: ô chậm dần rồi đổi chiều có thể bị đọc là chậm dần; ô có hai lần thay đổi chỉ giữ lần mạnh nhất.
- Phải chạy lại behaviour, risk và consolidation sau khi chạy lại phân vùng (risk đọc mức của các ô).
- `beta_10yr` của công trình luôn dùng 10 năm, bất kể `horizon_yr` mà phân vùng đã dùng.
- Nguy cơ từ điểm riêng dùng phép chiếu thẳng đứng v_LOS / l_u (một hướng chụp); công trình trong ô trượt lở luôn
  lấy mức của ô.
- Phơi nhiễm và tính dễ tổn thương chỉ là đại lượng thay thế: không có loại kết cấu, móng hay số người sử dụng.
- `geoeyes buildings` không có mục `[postprocess.buildings]`: tham số chỉ qua `--set`, và khoá sai báo lỗi đối số
  Python.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- **Cần đổi:** các ngưỡng của `[postprocess.risk]` (`floor_height_m`, `tall_m`, `long_m`, `small_m2`,
  `exposure_breaks_m2`) theo quỹ nhà tại chỗ; `gba_heights = false` nơi GlobalBuildingAtlas kém; `min_points_own`
  theo mật độ điểm của vệ tinh (băng X cho nhiều điểm trên mỗi mái hơn băng C).
- **Giữ nguyên được:** bộ mô hình, quy tắc BIC, ma trận hệ quả và ma trận rủi ro.
- **Vệ tinh:** chồng ảnh băng X ngắn (vài tuần) chỉ cho lớp ổn định/đều; tối thiểu một năm dữ liệu băng C mới có lớp
  theo mùa.
- **Kết quả đã có** (ghi chú nghiên cứu §4): Mexico City S1 có 42 371 trên 44 219 ô "đều"; Hanoi S1 phần lớn ổn định,
  có 308 ô theo mùa.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/ml/behaviour.py`, `buildings.py`, `risk.py`, `overture.py`; `src/geoeyes/opendata/coop.py`
  (`fill_heights`); `src/geoeyes/ml/__init__.py` (`run_behaviour`, `run_buildings`, `run_risk`);
  `src/geoeyes/api/behaviour.py`; `webapp/src/pages/Hazard.tsx`, `LearnBehaviour.tsx` (Nguyên lý, chương 3);
  test `tests/unit/ml/test_behaviour_risk.py`.
- Nghiên cứu: [../research/behaviour-and-risk.md](../research/behaviour-and-risk.md),
  [../research/rainfall-insar-hazard.md](../research/rainfall-insar-hazard.md) (bước R6).
- Hướng dẫn: [../guide/opendata.md](../guide/opendata.md) (các lớp Source Cooperative).
- Skill: [hazard-zoning.md](hazard-zoning.md), [exposure-and-flood-layers.md](exposure-and-flood-layers.md),
  [lines-and-consolidation.md](lines-and-consolidation.md).
- Bài báo: Berti et al. 2013 (*NHESS* 13:1945); Schwarz 1978 (*Ann. Stat.* 6:461); Kass & Raftery 1995 (*JASA*
  90:773); Burland & Wroth 1974; Peduto et al. 2017 (*Eng. Geol.* 218:117); Skempton & MacDonald 1956; Bjerrum
  1963; UNDRR 2016 (A/71/644).
