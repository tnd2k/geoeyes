# Kernel resample của stack native (cubic spline và Lanczos)

Bắt đầu ngày 2026-11-11. Chủ dự án đọc thấy VINSAR-VIPHAP 1.1.1 resample ảnh CSK bằng "Lanczos có xét tần số mang"
(`vinsar/core/csk_complex_resampling.py`, bán kính 4).

## Hiện trạng

| | GeoEyes (`processing/stack/native/stripmap.py`, `tops.py`) | VINSAR 1.1.1 |
|---|---|---|
| Tần số mang | Khử Doppler centroid **theo cự ly**, f_dc(τ) (đa thức "Centroid vs Range Time Polynomial" của CSK); với TOPS thì khử toàn bộ ramp phương vị | Khử một **hằng số** f_dc / PRF (chỉ hệ số đầu) |
| Kernel | Cubic B-spline (`scipy.ndimage.map_coordinates`, bậc 3, có prefilter) | Lanczos bán kính 4 (8 × 8 điểm), trọng số chuẩn hoá |

Trên ảnh CSK Hà Nội ngày 2011-07-01, f_dc thay đổi từ −751 đến −660 Hz dọc theo dải quét. Hằng số VINSAR dùng lệch
tối đa 57 Hz.

## Mô phỏng (script nháp `interp_cmp.py`, 2026-11-11)

Dùng tín hiệu phức giới hạn băng với thông số của ảnh trên: PRF 3071 Hz, băng phương vị 2580 Hz (lấy mẫu dư 1,19),
cự ly 117 / 146,25 MHz (1,25), trọng số Hamming 0,80 / 0,68. Nội suy tại 3000 vị trí lẻ ngẫu nhiên rồi so với giá
trị đúng. Mỗi ô ghi suy giảm độ kết hợp 1 − |γ| / sai số pha rms:

| Kernel | CSK phương vị | CSK cự ly | S1 IW phương vị | S1 IW cự ly |
|---|---|---|---|---|
| Cubic spline (GeoEyes hiện tại) | 2,0e-3 / 6,9° | 6,3e-4 / 4,1° | 9,3e-5 / 1,6° | 4,7e-4 / 2,9° |
| Lanczos r = 4 (VINSAR, tần số mang đúng) | 6,6e-4 / 4,0° | 1,3e-4 / 1,5° | 1,4e-5 / 0,7° | 4,4e-5 / 0,8° |
| Lanczos r = 8 | 6,0e-6 / 0,4° | 2,6e-6 / 0,2° | 6,2e-7 / 0,1° | 1,4e-6 / 0,2° |
| Cubic spline, không khử tần số mang | 7,2e-2 / 33° | — | — | — |

Khử tần số mang là yếu tố quan trọng nhất, và cả hai bên đều làm. Đứng thứ hai là kernel: Lanczos 4 tốt hơn
cubic spline 3–5 lần, còn Lanczos 8 tốt hơn Lanczos 4 thêm khoảng 100 lần. VINSAR ghi rằng "bán kính 4 đã kiểm
chứng tốt hơn 8/16/32", nhưng tín hiệu giới hạn băng cho kết quả ngược lại. Có thể họ chọn theo mức khớp với SARPROZ
chứ không theo độ chính xác (chưa kiểm tra). Về độ lớn: 6,9° ở băng X tương đương khoảng 0,3 mm LOS mỗi ảnh, nhỏ so
với mất kết hợp theo thời gian và nhiễu khí quyển.

## Kế hoạch

- **K0**: thêm `[stack] resample_kernel = "spline" | "lanczos"` (mặc định `spline`, để stack cũ giữ nguyên
  fingerprint) và `resample_radius` (mặc định 8). Dùng một hàm nội suy chung trong `native/common.py` cho bộ dựng
  stripmap (CSK, Capella, ICEYE), kèm unit test trên tín hiệu có tần số mang. TOPS, SICD và các sub-band tầng điện
  ly vẫn dùng spline cho đến K2.
- **K1**: chạy pipeline CSK Hà Nội (golden `csk_hanoi_pipeline`, ảnh trong `archive/cosmo_skymed/_incoming`) với
  spline, Lanczos 4 và Lanczos 8. So độ kết hợp giao thoa của stack, số PS và độ kết hợp theo thời gian, nhiễu vận
  tốc, mức khớp với golden, và thời gian dựng stack. **Điểm duyệt: chủ dự án xem kết quả.**
- **K2**: nếu K1 cho thấy có lợi, áp dụng cùng kernel cho `tops.resample_secondary` (và các sub-band tầng điện ly),
  rồi kiểm tra trên một stack S1 (dựng lại ql6_km124_141 hoặc hcm_d18).
- **K3**: đặt mặc định theo từng cảm biến (preset), tạo lại golden, cập nhật tài liệu (`projects-and-data.md`,
  danh mục tham số).

## Kết quả

**K0 (2026-11-11, chưa commit).** Thêm `[stack] resample_kernel` / `resample_radius` và hàm `native.common.interpolate`
(spline | lanczos, tách theo từng trục, xử lý theo lượt), dùng trong `stripmap.resample`. Fingerprint của stack chỉ
ghi kernel khi kernel khác `spline` (CSK / Capella / ICEYE). Test trong `tests/unit/processing/test_resample_kernel.py`
(tín hiệu 2D giới hạn băng: Lanczos 8 < Lanczos 4 < spline; tại vị trí nguyên trả đúng mẫu; ngoài ảnh trả 0). Toàn bộ
unit test: 463 đạt.

**K1 (2026-11-11).** Chạy golden `csk_hanoi_pipeline` (18 ảnh CSK HIMAGE, AOI 2,6 × 2,6 km, phase linking + lọc
Gauss, engine PS) bằng script nháp `k1_csk.py`, kết quả ở `geoeyes_workspace/tmp/k1/`:

| | spline | Lanczos 4 | Lanczos 8 |
|---|---|---|---|
| Thời gian đến build_product | 664 s | 1383 s | 1519 s |
| Số điểm (PS / DS) | 253.112 (230.713 / 22.399) | 253.124 (230.947 / 22.177) | 251.953 (229.711 / 22.242) |
| Độ kết hợp theo thời gian, trung vị | 0,5507 | 0,5516 | 0,5522 |
| Độ kết hợp stack 5 × 5, trung vị | 0,3051 | 0,3031 | 0,3018 |
| Chênh vận tốc của PS cách nhau < 30 m, NMAD | 0,382 mm/năm | 0,383 | 0,385 |

So trên cùng pixel với spline (PS / DS):
- Độ kết hợp theo thời gian: +0,0006 / +0,0005 (Lanczos 4) và +0,0007 / +0,0007 (Lanczos 8); tốt hơn ở 51 % số điểm.
- Fit RMSE: **+0,14 / +0,13 mm** (Lanczos 4) và **+0,10 / +0,06 mm** (Lanczos 8); thấp hơn chỉ ở 37–45 % số điểm.

Độ kết hợp stack đo bằng cửa sổ 5 × 5 thấp hơn khi dùng Lanczos. Điều này là dự kiến: spline làm mượt nhẹ ảnh nên
các pixel lân cận tương quan với nhau, khiến ước lượng độ kết hợp bị nâng lên. Vì vậy thước đo này không công bằng ở đây.

Nhận định: **trên dữ liệu CSK thật, Lanczos không cho cải thiện đo được.** Lợi ích trong mô phỏng (2e-3 độ kết hợp,
khoảng 0,3 mm mỗi ảnh) nhỏ hơn hai bậc so với mức mất kết hợp của stack này (độ kết hợp khoảng 0,3), nên không thấy
được; fit RMSE còn hơi kém hơn. Đổi lại thời gian chạy tăng 2–2,3 lần.

Vận tốc của cùng một PS chênh nhau 0,7–0,9 mm/năm (NMAD) giữa các kernel. Con số này lớn hơn nhiều so với phần sai số
nội suy giải thích được (khoảng 0,1 mm/năm). Như vậy chuỗi xử lý (unwrap, chọn DS, điểm tham chiếu) đang khuếch đại
những thay đổi nhỏ ở đầu vào. Độ nhạy này nên được xem xét riêng.

Phát hiện phụ: ngay cả lần chạy spline cũng không còn khớp golden ngày 2026-11-07 (RMSE vận tốc 0,297 > 0,2 mm/năm;
tỉ lệ khớp 0,98; độ cao và độ kết hợp vẫn trong giới hạn). Nguyên nhân là thay đổi trong engine PS từ sau ngày đó,
không phải do kernel.

**Quyết định (chủ dự án, 2026-11-11): mặc định `spline`.** Vẫn giữ tuỳ chọn Lanczos (`[stack] resample_kernel =
"lanczos"`, chỉ cho bộ dựng stripmap). Không làm K2 và K3. Hai việc còn mở: nguyên nhân golden bị lệch và độ nhạy của
chuỗi xử lý.
