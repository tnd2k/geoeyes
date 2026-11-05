# Skill: nhận biết và hiệu chỉnh pha tầng điện ly

> Bản dịch của [docs/en/skills/ionosphere.md](../../en/skills/ionosphere.md). Dịch ngày 2026-11-01.

> Phân biệt mặt nghiêng do tầng điện ly với chuyển dịch, tầng đối lưu, quỹ đạo hay bậc giữa các dải con; khử nó khỏi
> chồng ảnh Sentinel-1 bằng tách phổ theo phương nhìn ngang (split-spectrum); chấp nhận hoặc bác bỏ kết quả.
> Trạng thái: đang vận hành cho Sentinel-1 IW với bộ dựng chồng ảnh `native`; chưa có hiệu chỉnh cho vệ tinh khác
> (stripmap, băng L). Đối chiếu với mã lần gần nhất 2026-11-01. Thiết lập: `[stack] ionosphere`,
> `ionosphere_model`, `ionosphere_smooth_m`. Web app: dự án → Settings; các phép kiểm tra nằm trong báo cáo sản
> phẩm; Principles → chương 6 (`#/learn-ionosphere`).

## 1. Khi nào dùng

- **Câu hỏi.** Mặt nghiêng rộng hay bậc thẳng trên bản đồ vận tốc có phải do tầng điện ly không, và sau hiệu chỉnh
  đã hết chưa?
- **Quyết định hỗ trợ.** Bật `[stack] ionosphere = "split_spectrum"` (và chọn mô hình nào), giữ bước khử mặt phẳng
  khi phân tách hai hướng chụp, hay tìm nguyên nhân khác (tầng đối lưu, giải chập pha).
- **Nghi tầng điện ly** khi có từ hai yếu tố trở lên ([hướng dẫn](../guide/ionosphere.md) §1): vĩ độ từ 5–25° (đỉnh
  dị thường xích đạo) hoặc vùng cực; giờ địa phương từ chiều tới đầu đêm (S1 quỹ đạo lên ≈ 18:00); gần cực đại mặt
  trời (chu kỳ 25: 2024–2026); băng L; vùng rộng hơn 10 km. Phép kiểm tra trong báo cáo coi sản phẩm là có rủi ro
  khi |vĩ độ| < 30° và giờ bay qua trung bình theo giờ địa phương trong khoảng 14:00–23:00 (`report/qc.py`).
- **Không dùng cho** các mảng 1–10 km hay tín hiệu tương quan với độ cao (tầng đối lưu: [atmosphere.md](atmosphere.md)),
  hay cho chồng ảnh không phủ các ngày cần xét. Với vệt quỹ đạo không phải Sentinel-1, thiết lập này bị bỏ qua.

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Các burst SLC Sentinel-1 IW của vệt quỹ đạo | có | pha `acquire` tải từ ASF theo `[acquire] date_range` và `relative_orbit` của vệt; cần token NASA Earthdata | `archive/sentinel1/<track_id>/<year>/<SLC>/` (`bursts.json`, `IWn_POL_<burst>.tiff`, XML); token trong `EARTHDATA_TOKEN` (biến toàn máy hoặc `.env`) | độ rộng băng tần phương nhìn ngang phải có trong annotation, nếu không bước dựng dừng (`DataError`) |
| Quỹ đạo chính xác (POEORB) | có | tự tải bằng cùng token | `<workspace>/cache/orbits` | pha hình học phải chính xác: khoảng một nửa sai số của nó lọt vào ước lượng |
| Bộ dựng chồng ảnh `native` | có | `[stack] engine = "native"` (mặc định) | project.toml | không hỗ trợ chồng ảnh SNAP |
| Hướng chụp thứ hai trên cùng vùng | rất nên có | một vệt khác (lên + xuống) trong cùng dự án | `[[tracks]]` | phép thử quyết định: mặt nghiêng chỉ thấy ở một hướng chụp thì không thể là chuyển dịch |
| Trạm GNSS | tuỳ chọn | NGL ([gnss-calibration.md](gnss-calibration.md)) | – | kiểm tra gradient độc lập |
| Mức TEC (GIM, CODE IONEX) | tuỳ chọn | nguồn ngoài (ví dụ tệp IONEX của CODE / CDDIS) | GeoEyes không đọc | chỉ cho mức TEC (2,5° × 5°), không cho gradient trên 15 km |

Danh sách kiểm tra trước khi chạy:

- [ ] vệt quỹ đạo là Sentinel-1 IW, bộ dựng chồng ảnh `native`;
- [ ] lần chụp thuộc nhóm rủi ro (giờ địa phương, vĩ độ) hoặc đã thấy mặt nghiêng chỉ ở một hướng chụp;
- [ ] đã đặt token Earthdata; có quỹ đạo chính xác;
- [ ] có hướng chụp thứ hai hoặc GNSS để đánh giá kết quả.

## 3. Phương pháp

### 3.1 Tách phổ phương nhìn ngang (Gomba et al. 2016), `processing/stack/native/iono.py`

- Hai băng con, tâm ở f_L = f₀ − B/3 và f_H = f₀ + B/3, mỗi băng rộng B/3 (vát cosin trên 10 % độ rộng); B là độ
  rộng băng phương nhìn ngang nhỏ nhất đã xử lý của các dải con được dùng.
- Mỗi giao thoa đồ băng con φ_k = φ_nd·f_k/f₀ + φ_iono·f₀/f_k. Cả hai băng con được làm phẳng bằng pha hình học
  của **toàn băng** (phép lấy mẫu lại đã đưa tiếng vọng của ảnh phụ về đúng điểm ảnh của ảnh tham chiếu).
- Pha tầng điện ly tại f₀:
  φ_iono = f_L·f_H / (f₀·(f_H² − f_L²)) · (φ_L·f_H − φ_H·f_L), tính dưới dạng a·φ_L − b·(φ_H − φ_L) với
  a = f_L·f_H/(f₀(f_H + f_L)) và b = f_L²·f_H/(f₀(f_H² − f_L²)). Nhiễu bị khuếch đại ≈ f₀/(2(f_H − f_L)), khoảng 90 lần.
- **Ô.** Các tổng được lập trên ô thô 450 m (số điểm ảnh gộp = 450 m / bước phương bay × 450 m / bước phương nhìn
  ngang trên mặt đất, ≈ 32 × 122 điểm ảnh) trên **toàn bộ các burst**, không chỉ vùng cắt (≈ 45 × 175 km ở Hà Nội).
- **Ô được dùng.** Độ nhất quán băng thấp ≥ 0,3 (khi đó φ_L được giải chập bằng IRLS có trọng số) và độ nhất quán
  chéo giữa hai băng g ≥ 0,7; ít hơn 30 ô như vậy thì ngày đó báo lỗi.
- **Hồi quy.** Bình phương tối thiểu có trọng số g²/(1 − g²) (mẫu số tối thiểu 10⁻³), 4 vòng loại các ô lệch quá
  3 × 1,4826 · MAD, rồi tính giá trị trên vùng cắt. `ionosphere_model`:
  - `local` (mặc định): một mặt phẳng đặt tâm ở vùng cắt, mỗi ô nhân thêm trọng số exp(−d²/(2·s²)) với
    s = `ionosphere_smooth_m` (10 000 m);
  - `plane` / `quadratic`: một mặt trên toàn bộ các burst;
  - `smooth`: một mặt Gauss có độ rộng `ionosphere_smooth_m`.
- **Khử.** Pha được trừ khỏi SLC ảnh phụ đã lưu: slc·exp(j(φ_iono + bậc dải con)).

### 3.2 Bậc giữa các dải con, `s1_stack.py`

Với mỗi đường nối dải con nằm trong vùng cắt (cách mép ít nhất 44 cột), theo từng ngày: pha của giao thoa đồ phía
phải so với phía trái, mỗi bên 40 cột, bỏ 4 cột ở chỗ cắt, theo khối 32 dòng, lấy trung bình có trọng số là độ nhất
quán của khối. Kết quả: bậc (rad), độ đồng thuận (0–1), số khối.

- độ đồng thuận < 0,3 hoặc ít hơn 8 khối: không đo được, giữ nguyên bậc và ghi cảnh báo;
- các bậc cộng dồn từ phía gần và được khử so với dải con rộng nhất (dải neo);
- việc căn đường nối được làm trên mọi chồng ảnh Sentinel-1 `native`, có hay không có tách phổ. Khi tách phổ, bậc
  còn được trừ khỏi băng con thấp trước khi ước lượng (`WideArea.shift`); nếu không, khoảng một nửa bậc sẽ lọt vào
  φ_iono.

### 3.3 Tiêu chí chấp nhận, `report/qc.py`

| Phép kiểm tra | Đạt | Cần xem lại |
|---|---|---|
| Chênh gradient vận tốc với một vệt khác, từng trục (trên vùng chung, mỗi bên ≥ 1000 điểm) | < 0,3 mm/năm/km | > 0,5 |
| Bậc vận tốc qua đường nối dải con (các điểm trong 0,08° góc tới mỗi bên, mỗi bên ≥ 50) | < 2 mm/năm | > 4 |
| Phân tách không khử mặt phẳng: tương quan đông/đứng | \|r\| < 0,3 | > 0,5 |
| Phân tách: tỉ lệ ô có chuyển dịch đông–tây đáng kể | < 10 % | > 15 % |
| Theo từng ngày, mặt nghiêng còn lại trong giao thoa đồ so với gradient tầng điện ly đã khử (≥ 6 ngày) | \|r\| < 0,3 | > 0,5: sai tỉ lệ |

Giữa hai ngưỡng thì trạng thái là `borderline`.

## 4. Các bước triển khai

1. **Chẩn đoán trước khi hiệu chỉnh** ([hướng dẫn](../guide/ionosphere.md) §3):
   - mặt phẳng vận tốc của từng vệt: `geoeyes decompose <project>` in mặt nghiêng của mọi sản phẩm và cảnh báo khi
     một sản phẩm trải quá `ramp_warning_mm_yr` (5) và gấp đôi sản phẩm kia;
   - theo từng giao thoa đồ, mặt nghiêng đã có sẵn trong `phase/unwrapped` của `ps_runs/<track>/state.h5` chưa?
   - giờ bay qua theo giờ địa phương (`sensing_mid_utc` của chồng ảnh) và mức TEC;
   - ESD theo từng ngày (`esd_shift` của chồng ảnh) so với mặt nghiêng dọc phương bay của ngày đó;
   - một đường thẳng dọc phương bay: so cột của nó với `subswath_columns` của chồng ảnh. Nếu trùng đường nối thì đó
     là bậc dải con, không phải tầng điện ly và càng không phải đứt gãy.
2. **Bật hiệu chỉnh** (thẻ Settings hoặc project.toml):
   ```toml
   [stack]
   ionosphere = "split_spectrum"      # none (default) | split_spectrum
   ionosphere_model = "local"         # local (default) | plane | quadratic | smooth
   ionosphere_smooth_m = 10000
   ```
3. **Dựng lại chồng ảnh.** `geoeyes run <project> --track <track> --force build_stack`. Khi `ionosphere_key` (cách
   làm, mô hình, bán kính) thay đổi, bộ dựng khớp ảnh lại mọi ngày, sau đó `ps` và sản phẩm chạy tiếp. Thời gian:
   một lần dựng chồng ảnh đầy đủ cộng thêm lọc và lấy mẫu lại băng con cho mọi burst; chưa đo riêng.
4. **Đọc nhật ký**, mỗi ngày một dòng:
   ```
   2025-10-04: ionosphere gradient (az, rg) [-0.1342, 0.0014] ± [0.0161, 0.0142] rad/km at the crop, 3898 cells over [45.6, 174.9] km
   2026-07-02 seam IW3: interferogram phase step -2.298 rad (consistency 0.96, 32 blocks) removed
   ```
   (ví dụ lấy từ [hướng dẫn](../guide/ionosphere.md) §4.2–4.3).
5. **Đánh giá.** Báo cáo sản phẩm (`products/<id>/report.pdf`, phần kiểm tra chất lượng) theo tiêu chí ở §3.3; trên
   web app, Principles → chương 6 cho gradient theo ngày, giờ địa phương, ESD và bậc đường nối của một chồng ảnh.
6. **Nếu vẫn không đạt:** `[postprocess.decompose] deramp = "plane"` khử một mặt phẳng khỏi từng sản phẩm trước khi
   phân tách (nó cũng khử luôn độ nghiêng thật của vùng: phải ghi rõ trong báo cáo).

## 5. Kết quả và cách đọc

| Ở đâu | Nội dung |
|---|---|
| biến `iono` của chồng ảnh (date, y, x), rad | pha tầng điện ly đã khử, tại f₀ |
| biến `iono_cells` của chồng ảnh | các tổng thô theo ngày (low, high·conj(low), \|low\|, \|cross\|): có thể hồi quy mô hình khác về sau mà không phải đọc lại SLC |
| thuộc tính `ionosphere_per_date[date]` | `rad_per_km_az_rg` (gradient tại vùng cắt), `se_rad_per_km_az_rg`, `cells`, `kept`, `area_km`, `noise_rad`, `model` |
| thuộc tính `ionosphere_bandwidth_hz`, `ionosphere_looks`, `ionosphere_model`, `ionosphere_smooth_m`, `ionosphere_key` | những gì đã chạy |
| thuộc tính `subswath_phase_offsets[date][IWn]` | `rad`, `consistency`, `blocks`, cùng `anchor` |
| phần kiểm tra chất lượng của báo cáo | `pass` / `borderline` / `review` / `info` cho từng tiêu chí ở §3.3 |

Cách đọc: gradient tính bằng rad/km tại f₀; nhân λ/(4π) (4,41 mm/rad ở băng C) ra mm/km theo LOS. Sai số hình thức
khoảng 0,015 rad/km là bình thường; `noise_rad` ≈ 10 rad mỗi ô cũng bình thường (hệ số khuếch đại ~90 lần được bù
bằng hàng nghìn ô). Ít hơn vài trăm ô `kept` hoặc ± trên 0,05 rad/km: ngày đó ước lượng yếu, kiểm tra độ nhất quán.

## 6. Kiểm tra chất lượng

- Mọi tiêu chí ở §3.3 đều `pass`, hoặc `borderline` có giải thích.
- Tương quan theo ngày giữa mặt nghiêng còn lại và gradient đã khử thấp (|r| < 0,3). Nếu đây là tiêu chí duy nhất đạt,
  phần còn lại **không phải** tầng điện ly: xem tầng đối lưu, giải chập pha, các ngày bất thường.
- Bậc đường nối: dự kiến có hai mức (≈ 0 hoặc một hằng số); bậc vận tốc ở đường nối giảm dưới 2 mm/năm.
- Số liệu tham chiếu Hà Nội asc 128 ([hướng dẫn](../guide/ionosphere.md) §6): bậc đường nối +8,0 → +1,4 mm/năm;
  gradient gx/gy +0,75/−1,50 → −0,49/−0,77 mm/năm/km, so với −0,02/−0,20 của desc 091; tỉ lệ ô chuyển dịch ngang
  41 % → 11,5 %.

## 7. Hạn chế và lỗi thường gặp

- Tách phổ ở băng C rất nhiễu: chỉ ước lượng được các dạng trơn (một mặt phẳng cục bộ), không ước lượng được bong
  bóng plasma sau hoàng hôn cỡ vài km.
- `local` giả định tầng điện ly gần như tuyến tính trong khoảng ~10 km quanh vùng cắt.
- Nhấp nháy tầng điện ly (scintillation) làm mất tương quan pha; tách phổ không sửa được.
- Bậc dải con chỉ đo được khi cả hai phía đường nối có độ nhất quán cao (đô thị), không đo được trên đồng ruộng hay
  mặt nước. Nguyên nhân gốc của nó chưa rõ.
- Tách phổ khử một tín hiệu có thật (Hà Nội: gradient dọc phương bay bị khử dao động 0,49 mm/km giữa các ngày), nhưng
  mặt nghiêng còn lại ở Hà Nội không tán sắc: nhiều khả năng là tầng đối lưu buổi tối.
- Docstring của `iono.py` vẫn ghi "quadratic by default"; mặc định thật là `local` (cả schema lẫn hàm).
- GeoEyes chưa có hiệu chỉnh tầng điện ly cho vệ tinh stripmap hay spotlight (CSK, Capella, ICEYE, Umbra, TerraSAR-X)
  hay cho ALOS (băng L): với các vệ tinh này thiết lập bị bỏ qua mà không báo.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- **Vĩ độ thấp, chụp lúc chạng vạng (S1 quỹ đạo lên ở Đông Nam Á, Mỹ Latinh):** bật ngay từ lần dựng đầu.
- **Vĩ độ trung bình, chụp lúc rạng sáng:** để `none`; xem dòng "Ionospheric correction" trong báo cáo.
- **Vùng cắt lớn hoặc tầng điện ly yên:** `plane` hoặc `quadratic`; **độ nhất quán cao, cần giữ cấu trúc nhỏ:**
  `smooth`.
- **Giữ nguyên được:** các tiêu chí ở §3.3 và trình tự chẩn đoán.
- **Thói quen tại chỗ:** `projects/hanoi_s1` đặt `ionosphere = "split_spectrum"` và `[postprocess.decompose] deramp =
  "plane"`; không đọc gradient bắc – nam của riêng vệt quỹ đạo lên.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/processing/stack/native/iono.py`, `src/geoeyes/processing/stack/native/s1_stack.py`
  (`seam_step`, vòng lặp tách phổ), `src/geoeyes/controller/phases/build_stack.py`,
  `src/geoeyes/config/schema.py` (`StackSection`), `src/geoeyes/report/qc.py`, `src/geoeyes/learn/ionosphere.py`,
  `webapp/src/pages/LearnIonosphere.tsx`, `src/geoeyes/ml/decompose.py` (`deramp`, `ramp_warning_mm_yr`).
- Hướng dẫn và ghi chú: [../guide/ionosphere.md](../guide/ionosphere.md),
  [../research/two-geometries-and-soft-soil.md](../research/two-geometries-and-soft-soil.md) §4.2.
- Skill: [insar-processing.md](insar-processing.md), [atmosphere.md](atmosphere.md),
  [decompose-and-soft-soil.md](decompose-and-soft-soil.md), [gnss-calibration.md](gnss-calibration.md).
- Bài báo: Gomba G, Parizzi A, De Zan F, Eineder M, Bamler R (2016) Toward operational compensation of ionospheric
  effects in SAR interferograms: the split-spectrum method. *IEEE TGRS* 54(3):1446–1461.
