# Skill: kiểm định bằng gương phản xạ góc (Sentinel-1)

> Bản dịch của [docs/en/skills/corner-reflector.md](../../en/skills/corner-reflector.md). Dịch ngày 2026-11-01.

> Kiểm tra xem các gương phản xạ góc tam diện (corner reflector) đã lắp có hiện ra đúng chỗ và đủ mạnh trên mọi lần
> chụp Sentinel-1 hay không: hướng đặt cần có, RCS dự kiến so với RCS đo, vị trí đỉnh phản xạ, tỉ số tín hiệu trên
> nền (SCR) và độ nhất quán tại gương. Trạng thái: đang vận hành cho burst Sentinel-1 IW (chuyển từ báo cáo CR cũ, đã
> đối chiếu trùng khớp từng bit về RCS, SCR và độ nhất quán). Đối chiếu với mã lần gần nhất 2026-11-01. Lệnh
> `geoeyes cr-report`. Web app: dự án → **Validation** → Corner reflectors → **Build CR report**.

## 1. Khi nào dùng

- **Câu hỏi.** Mỗi gương có thấy được trên mỗi lần chụp không, có đặt đúng hướng cho vệt quỹ đạo đó không, có ổn
  định giữa các lần chụp không? Đỉnh phản xạ nằm ở đâu so với vị trí đã đo? Cần đặt gương thế nào cho một vệt quỹ đạo?
- **Quyết định hỗ trợ.** Chỉnh lại hướng hoặc độ nghiêng của gương; giữ gương làm điểm tham chiếu hay làm mục tiêu
  đặt cạnh trạm GNSS (bước nghiên cứu G4 trong [gnss-calibration.md](gnss-calibration.md)); chấp nhận một lần chụp
  vào chuỗi số liệu của gương.
- **Nên dùng** sau khi lắp hoặc dời gương, sau mỗi chuyến thực địa (kèm nhật ký lắp đặt), và để tính trước hướng
  đặt cho một vệt quỹ đạo mới (bảng `pointing` dùng được cả trước khi lắp).
- **Mã chưa làm:** chuỗi chuyển dịch của gương (đọc điểm gần gương nhất trong sản phẩm), vệ tinh khác ngoài
  Sentinel-1, dữ liệu phân cực chéo (chỉ VV).

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Danh sách gương | có | đo thực địa (GNSS) từng gương | CSV, đường dẫn trong `[validation.corner_reflector] points` (tương đối so với thư mục dự án, ví dụ `geom/points.csv`). Cột (không phân biệt hoa thường): bắt buộc `lon`/`longitude`, `lat`/`latitude`; tuỳ chọn `name`/`id`/`target_name`, `height`/`h`/`elevation`/`elev`/`alt`/`altitude`/`altitude_m` (độ cao ellipsoid, m), `edge_m`/`size_m`/`edge`/`target_size_m` | thiếu độ cao thì dùng 0 m (có cảnh báo): sai độ cao làm lệch vị trí dự đoán; thiếu tên thì đặt `CR<dòng>` |
| Nhật ký lắp đặt | tuỳ chọn, rất nên có | ghi chép thực địa mỗi lần lắp hoặc chỉnh | CSV trong `[validation.corner_reflector] setup` (ví dụ `geom/cr_setup.csv`). Cột: `valid_from`/`from`/`date`/`datetime` (`YYYY-MM-DD[ HH:MM]`, giờ địa phương), `face_azimuth_deg`/`azimuth_deg`/`azimuth`, `base_tilt_deg`/`tilt_deg`/`tilt`; tuỳ chọn `name`/`id` (mặc định `*` = mọi gương), `note`/`ghi_chu`/`description` | mỗi dòng có hiệu lực tới dòng kế tiếp của cùng gương; không có dòng nào thì coi gương đã đặt đúng hướng cần có (`setup_source = "assumed"`) |
| Múi giờ của nhật ký | tuỳ chọn | – | `[validation.corner_reflector] timezone` (tên IANA) | mặc định `Asia/Ho_Chi_Minh` |
| Chiều dài cạnh mặc định | tuỳ chọn | bản vẽ gương: cạnh trong của tam diện tam giác | `[validation.corner_reflector] edge_m` | mặc định 0,8 m |
| Khoảng ngày | tuỳ chọn | – | `start`, `end` (`YYYY-MM-DD`) | mặc định `start` = ngày trước dòng nhật ký đầu tiên; `end` để mở |
| Burst Sentinel-1 phủ các gương | có | pha `acquire` tải từ ASF (`[acquire] date_range`, `relative_orbit` của vệt), token NASA Earthdata trong `EARTHDATA_TOKEN`; AOI phải chứa các gương | `archive/sentinel1/<track_id>/…/<SLC>/` gồm `bursts.json`, `IWn_VV_<burst>.tiff`, `<SLC>_VV.xml` (annotation và calibration), hoặc thư mục trong `[acquire] archive` | chỉ đọc burst VV; chỉ các vệt Sentinel-1 của dự án |
| Gói Python `typst` | cho bản PDF | có trong môi trường `insar` | – | `--no-pdf` chỉ ghi JSON, CSV và hình |

Ví dụ:

```toml
[validation.corner_reflector]
points = "geom/points.csv"
setup = "geom/cr_setup.csv"
timezone = "Asia/Ho_Chi_Minh"
edge_m = 0.8
start = ""
end = ""
```

Danh sách kiểm tra trước khi chạy:

- [ ] độ cao là độ cao **ellipsoid** (không phải so với geoid), tính bằng mét, đo tại gương;
- [ ] `edge_m` là cạnh trong của tam diện (riêng từng gương hoặc mặc định);
- [ ] nhật ký lắp đặt ghi giờ địa phương theo đúng `timezone`, mỗi lần thay đổi một dòng;
- [ ] kho lưu trữ có các lần chụp trong khoảng ngày, với burst phủ các gương.

## 3. Phương pháp

Với từng gương và từng lần chụp (`validation/corner_reflector/pipeline.py`):

1. **Định vị.** Range-Doppler trên quỹ đạo của burst (véc-tơ trạng thái trong annotation của burst; `scenes()` không
   áp quỹ đạo chính xác): thời điểm zero-Doppler và khoảng cách nghiêng của gương tại độ cao của nó cho ra (dòng, cột),
   dải con và burst, góc phương vị và góc ngẩng LOS (mặt đất → vệ tinh) và góc tới. Lần chụp nào không phủ gương thì
   bỏ qua.
2. **Ô ảnh và hiệu chuẩn bức xạ.** Đọc một ô ±48 dòng × ±192 cột; β⁰ = |DN|² / A² với A lấy từ bảng beta-nought
   trong khối calibration.
3. **RCS (phương pháp năng lượng tích phân, `measure.py`).** Tìm đỉnh trong ±1 dòng × ±2 cột quanh vị trí dự đoán
   (`CELL_SEARCH`); năng lượng búp chính trong cửa sổ 3 × 5 trừ mức nền (trung vị β⁰ của ô ảnh, bỏ hình chữ thập
   ±4 dòng / ±10 cột quanh đỉnh), nhân diện tích điểm ảnh (bước phương nhìn ngang × bước phương bay):
   RCS = 10·log₁₀[(Σβ⁰ − 15·nền)·Δr·Δa] dBsm; SCR = năng lượng / (15·nền·Δr·Δa) tính bằng dB. Vị trí đỉnh dưới điểm
   ảnh bằng parabol. Một vùng tìm rộng hơn (±2 × ±8, `NEAR_SEARCH`) để phát hiện vật tán xạ mạnh hơn ở gần.
4. **Vị trí.** Đỉnh được mã hoá địa lý tại độ cao của gương; độ lệch bắc/đông và tổng (m) so với vị trí đã đo.
5. **RCS dự kiến (`trihedral.py`, Knott).** Các cạnh của tam diện đặt trên tấm đế, mặt mở hướng `face_azimuth_deg`,
   đế nghiêng `base_tilt_deg` (nâng cạnh trước): góc ngẩng trục chính = 35,26° + độ nghiêng. Với các cosin chỉ phương
   l ≤ m ≤ n của hướng radar trên ba cạnh và cạnh trong a:
   A = 4·l·m·a²/(l+m+n) nếu l+m ≤ n, ngược lại A = a²·[(l+m+n) − 2/(l+m+n)]; RCS = 4π·A²/λ²; bằng 0 khi l ≤ 0 (vệ
   tinh nhìn vào mặt sau). Trên trục chính RCS = 4π·a⁴/(3λ²) (≈ 27,5 dBsm với a = 0,8 m ở băng C).
6. **Dung sai.** `within_tolerance` khi |đo − dự kiến| ≤ 3 dB (`TOLERANCE_DB`).
7. **Hướng đặt cần có.** Cho từng gương và vệt quỹ đạo, từ lần chụp mới nhất: phương vị mặt mở = phương vị LOS, góc
   ngẩng trục chính = góc ngẩng LOS, độ nghiêng đế = góc ngẩng LOS − 35,26°.
8. **Độ nhất quán.** Theo gương, vệt quỹ đạo và dải con: mọi cặp ngày khi có tối đa 10 ngày (`MAX_PAIRS_ALL`), nhiều
   hơn thì chỉ các cặp liên tiếp. Ô ảnh được khử ramp phương bay (Doppler TOPS), khớp bằng tương quan chéo biên độ
   (dưới điểm ảnh, dịch Fourier), khử vân trội trong từng khối 32 × 128, độ nhất quán tính trong cửa sổ 3 × 5: tại
   đỉnh của gương, và trung vị / P90 trên ô ảnh (bỏ 8 dòng và 24 cột ở mép).

## 4. Các bước triển khai

1. **Cấu hình** `[validation.corner_reflector]` (Settings → project.toml trên web app, hoặc sửa tệp) và đặt các CSV
   vào dự án (ví dụ `geom/`).
2. **Bảo đảm đã có burst**: `geoeyes run <project> --only acquire` (hoặc chạy đầy đủ) với `date_range` phủ khoảng ngày.
3. **Chạy.**
   ```
   geoeyes cr-report <project> [--track ID] [--no-pdf]
   ```
   Web: dự án → **Validation** → Corner reflectors → **Build CR report** (chạy nền; nhật ký hiện trong lúc chạy). Mỗi
   vệt Sentinel-1 một báo cáo. Thời gian: mỗi gương và mỗi lần chụp một ô ảnh, cộng các cặp tính độ nhất quán; ngắn so
   với xử lý, chưa đo ở đây. CLI in cho từng vệt `<n> observation(s), <k> within tolerance -> <pdf>`.
4. **Đọc** báo cáo trong thẻ Validation (danh sách báo cáo, bảng, hình, PDF) hoặc trong thư mục dưới đây.

Các tệp ghi ra trong `<project>/validation/corner_reflector/<YYYYmmdd-HHMMSS>_<track>/`:
`cr_report.json`, `observations.csv`, `coherence.csv`, `pointing.csv`, `<name>_chips.png`, `<name>_rcs.png` cho
từng gương, `cr_report.pdf` (Typst).

## 5. Kết quả và cách đọc

| Trường (`observations.csv`) | Ý nghĩa |
|---|---|
| `date`, `acquired_utc`, `acquired_local`, `platform`, `track`, `direction`, `swath`, `burst` | lần chụp |
| `los_azimuth_deg`, `los_elevation_deg`, `incidence_deg` | hướng tới vệ tinh tại gương |
| `setup_face_azimuth_deg`, `setup_base_tilt_deg`, `setup_source` (`log` \| `assumed`), `setup_note` | cách đặt gương dùng để tính RCS dự kiến |
| `expected_dbsm`, `measured_dbsm`, `difference_db`, `within_tolerance` | RCS dự kiến so với đo; dự kiến `-inf` = vệ tinh nhìn mặt sau ("CR faces away") |
| `scr_db` | tỉ số tín hiệu trên nền; càng cao pha càng sạch |
| `offset_north_m`, `offset_east_m`, `offset_m` | đỉnh đo được trừ vị trí đã đo thực địa |
| `nearby_dbsm`, `nearby_offset_m` | phản xạ mạnh nhất trong ±2 × ±8 điểm ảnh |

`pointing.csv`: phương vị mặt mở, góc ngẩng trục chính, độ nghiêng đế cần có cho từng gương và vệt. `coherence.csv`:
`at_reflector`, `area_median`, `area_p90`, `offset_az_px`, `offset_rg_px` cho từng cặp ngày. Hình: ô ảnh β⁰ với vị
trí dự đoán và vị trí đo; RCS theo ngày với giá trị dự kiến, dải ± 3 dB và đường trục chính. Phần tóm tắt của PDF nêu
cho từng gương: tỉ lệ trong dung sai, khoảng độ lệch vị trí và độ nhất quán, các ngày nhìn mặt sau, các lần đặt giả
định, các vật tán xạ mạnh hơn ở gần.

## 6. Kiểm tra chất lượng

- RCS đo nằm trong ±3 dB so với dự kiến ở các lần chụp mà gương quay về; thiếu hụt có hệ thống nghĩa là đặt sai
  hướng, sai `edge_m`, hoặc trong gương có rác/nước.
- `offset_m` nhỏ và ổn định giữa các ngày; lệch không đổi gợi ý sai độ cao hoặc sai vị trí đo. (Tham chiếu: bản chuyển
  mã khớp báo cáo cũ trong phạm vi ≤ 6 mm về vị trí đỉnh, trên S1D vệt 91, 3 ngày; `docs/en/refactor/TODO.md`.)
- `scr_db` cao và độ nhất quán `at_reflector` cao rõ rệt so với `area_median` của ô ảnh.
- `nearby_dbsm` gần gương không vượt `measured_dbsm` + 1 dB: nếu vượt, có thể một công trình đang lấn át ô đó.
- Các dòng có `setup_source = "assumed"` chỉ là kỳ vọng, chưa phải kiểm tra: bổ sung nhật ký.

## 7. Hạn chế và lỗi thường gặp

- Chỉ Sentinel-1 IW, chỉ VV, burst lấy từ kho lưu trữ; vệ tinh khác bị bỏ qua và dự án không có S1 thì báo lỗi.
- Dùng quỹ đạo trong annotation của burst, không dùng POEORB (sai khác định vị ở mức của báo cáo cũ).
- Sai độ cao làm dời vị trí dự đoán, nên vùng tìm (±1 × ±2 điểm ảnh) có thể trượt đỉnh.
- Gương quay về một hướng bay thì không có RCS dự kiến ở hướng bay kia: đó là bình thường.
- Vùng tìm cố định trong một ô phân giải; vật tán xạ mạnh hơn ngoài vùng đó chỉ được báo cáo, không được dùng.
- Mô-đun này không tính chuỗi chuyển dịch của gương: đọc điểm gần gương nhất trong sản phẩm. `[selection]
  forced_points` có trong schema nhưng các bộ xử lý chưa đọc (2026-11-01).

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- Điểm đặt mới: đổi `timezone`, lập `points` (độ cao ellipsoid!) và `setup`, đặt AOI và `date_range` sao cho burst phủ
  các gương. Chạy một lần trước khi lắp để có `pointing.csv` cho từng vệt quỹ đạo.
- Đặt gương cạnh ăng-ten GNSS để giải bài toán mốc trạm (bước nghiên cứu G4: tiêu chí gương − GNSS < 2 mm/năm,
  [../research/gnss-insar-calibration.md](../research/gnss-insar-calibration.md) §9).
- Vệ tinh khác (CSK, Capella, ICEYE): mô-đun này chưa hỗ trợ.
- Giữ nguyên được: dung sai (3 dB), vùng tìm, cách tính độ nhất quán.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/validation/corner_reflector/__init__.py` (`build_cr_report`, cấu hình),
  `inputs.py`, `pipeline.py`, `measure.py`, `trihedral.py`, `s1burst.py`, `report.py`, `cr_report.typ`;
  `src/geoeyes/cli/main.py` (`cmd_cr_report`); `webapp/src/components/Validation.tsx`; test
  `tests/unit/validation/test_corner_reflector.py`.
- Hướng dẫn: [../guide/projects-and-data.md](../guide/projects-and-data.md) §4.
- Skill: [gnss-calibration.md](gnss-calibration.md), [insar-processing.md](insar-processing.md).
- Bài báo: Knott EF, Shaeffer JF, Tuley MT (2004) *Radar Cross Section*, 2nd ed., SciTech (RCS của tam diện).
  Parker AL et al. (2017) *Sensors* 17:1753; Mahapatra P et al. (2018) *J. Geodesy* 92:21–32 (gương và bộ phát đáp
  đặt cùng GNSS; DOI ở §11 của ghi chú nghiên cứu GNSS).
