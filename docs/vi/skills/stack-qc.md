# Skill: kiểm tra chất lượng khớp ảnh của chồng ảnh

> Bản dịch của [docs/en/skills/stack-qc.md](../../en/skills/stack-qc.md). Dịch ngày 2026-11-01.

> Chồng ảnh đã khớp đủ tốt để xử lý chưa? Với mỗi ngày so với ảnh tham chiếu: biên độ, giao thoa đồ pha chập, độ
> nhất quán, độ lệch còn lại sau khớp ảnh và tương quan biên độ. Trạng thái: vận hành (mới, 2026-11). Kiểm tra gần
> nhất 2026-11-01. CLI: `geoeyes stack-qc <project> [--stack ID]`. Web app: trang dự án → tab Stack (*Check the
> stack* / *Check again*).

## 1. Khi nào dùng

- Sau `build_stack` và trước engine điểm: một ngày khớp sai làm hỏng giao thoa đồ của ngày đó và, qua bước giải chập,
  hỏng cả chuỗi.
- Khi sản phẩm trông bất thường (một ngày toàn nhiễu, bản đồ vận tốc vỡ thành khối) và cần biết lỗi nằm ở chồng ảnh
  hay ở bước xử lý PS.
- Sau khi thay đổi cách khớp ảnh (`[stack] coreg_model`, phiên bản engine mới, thêm cảnh).
- Kết quả giúp quyết định: xử lý tiếp, bỏ một ngày (`[acquire] date_range`, xoá thư mục của ngày, `[ps_lite]
  exclude_dates`) hay sửa bước khớp ảnh. Công cụ này không đánh giá SLC đã liên kết pha (`slc_linked`) hay việc chọn PS.

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Chồng ảnh đã khớp | có | pha `build_stack` của [insar-processing.md](insar-processing.md) | `projects/<name>/stacks/<stack_id>/stack.zarr` có `slc` (date, y, x) | mã chồng ảnh `<track_id>-ref<YYYYMMDD>` |
| Ngày tham chiếu | tự động | thuộc tính `reference_date` của chồng ảnh | — | nếu thiếu: ngày có |B⊥| nhỏ nhất |
| `bperp`, `kh` | tuỳ chọn | bộ dựng chồng ảnh ghi ra | biến của chồng ảnh | không có `kh` thì độ cao ứng với một vân để trống; không có `bperp` thì bằng 0 |
| Kích thước điểm ảnh, góc tới | tuỳ chọn | thuộc tính `azimuth_pixel_spacing_m`, `range_pixel_spacing_m`, biến `geometry_incidence` (nếu không có: thuộc tính `incidence_deg`, rồi 40°) | — | quyết định số điểm ảnh gộp |
| Ổ đĩa | có | — | `stacks/<stack_id>/qc/` | mỗi ngày ba PNG + `qc.json`, vài MB |

Danh sách kiểm tra:

- [ ] `build_stack` ở trạng thái *done* trong `geoeyes status <project>`.
- [ ] Đã biết mã chồng ảnh (tên thư mục trong `stacks/`), hoặc để lệnh tự lấy mọi chồng ảnh của dự án.
- [ ] Sentinel-1: kiểm tra không tự chạy (chồng ảnh lớn); phải chạy tay.

## 3. Phương pháp

Mã: `src/geoeyes/processing/stack/qc.py` (`stack_qc(store, size=1200, crop=2048)`).

1. **Số điểm ảnh gộp.** Khoảng cách theo phương nhìn ngang trên mặt đất g_r = r / max(sin θ, 0,2), θ là góc tới trung
   vị của dòng giữa; kích thước mặt đất của một điểm ảnh đầu ra c = max(n_y·a, n_x·g_r) / `size`; số điểm ảnh gộp
   (l_y, l_x) = (round(c / a), round(c / g_r)), tối thiểu 1. Ảnh có cạnh dài khoảng 1200 điểm ảnh, ô mặt đất vuông.
2. **Biên độ** của từng ngày: 10·log10(Σ|s|² / (l_y·l_x)) tính bằng dB, hiển thị giãn 2–98 % (chỉ cho ảnh).
3. **Giao thoa đồ** so với tham chiếu, đúng như đã lưu: I = Σ_gộp r·conj(s). SLC trong chồng ảnh đã khử pha hình học
   (quỹ đạo + DEM): phần còn lại là địa hình DEM chưa mô tả hết, chuyển dịch, khí quyển và nhiễu. Pha chập arg I hiển
   thị từ −π đến π.
4. **Độ nhất quán** trên các điểm ảnh gộp: γ = |Σ r·s*| / sqrt(Σ|r|² · Σ|s|²); mỗi ngày có `coherence_mean` và
   `coherence_p90`.
5. **Độ lệch còn lại** trên một vùng cắt ở giữa, độ phân giải đầy đủ (2048 × 2048, hoặc cả ảnh nếu nhỏ hơn):
   - độ lệch nguyên thô (`sicd_stack.coarse_offset`, cửa sổ `min(1024, crop)`): tương quan pha của log(1+|a|) trên 9
     cửa sổ đặt ở 25 / 50 / 75 % mỗi trục; một cửa sổ được tính nếu sai số < 0,97 và ảnh phụ có ≤ 20 % giá trị 0;
     lấy trung vị; chỉ chấp nhận khi ≥ max(2, một nửa số cửa sổ) khớp nhau trong 3 điểm ảnh, nếu không thì bằng 0;
   - nếu độ lệch thô bằng 0: đo phần dư dưới điểm ảnh (`stripmap.residual_offset`): tương quan pha biên độ trên các ô
     256 điểm ảnh, bước 128, nội suy lên 20 lần, bỏ ô có > 5 % giá trị 0, giữ ô có sai số < 0,9, lấy trung vị của
     ≥ 4 ô, nếu không thì bằng 0;
   - ghi thành `offset_lines`, `offset_samples` (điểm ảnh; quy ước: cộng vào dòng / cột của ảnh phụ).
6. **Tương quan biên độ** trên vùng cắt: hệ số tương quan Pearson giữa log(1+|r|) và log(1+|s|).
7. **Độ cao ứng với một vân**: HoA = 2π / trung vị |kh| trên 128 × 128 điểm ảnh ở tâm vùng cắt (m); `bperp_m` lấy từ
   chồng ảnh.

Cách xếp loại trong bảng của web app (`webapp/src/components/StackQc.tsx`):

| Chỉ số | Tốt | Cần xem lại | Xấu |
|---|---|---|---|
| max(|offset_lines|, |offset_samples|) | ≤ 0,1 điểm ảnh | ≤ 1 điểm ảnh | > 1 điểm ảnh |
| `coherence_mean` | ≥ 0,4 | ≥ 0,2 | < 0,2 |

`build_stack` tự chạy kiểm tra ở cuối pha với mọi vệ tinh trừ Sentinel-1 và ghi cảnh báo khi độ lệch lớn nhất vượt
1 điểm ảnh ("the coregistration failed for some of them"); kiểm tra có lỗi cũng không làm hỏng bước dựng.

Test đơn vị (`tests/unit/processing/test_stack_qc.py`) dựng một chồng ảnh tổng hợp 3 ngày (1200 × 1000 điểm ảnh, một
dải vân, các mục tiêu sáng): ngày khớp đúng phải cho độ nhất quán > 0,6 và độ lệch < 0,2 điểm ảnh, ngày bị dịch 40
dòng cho độ nhất quán < 0,3 và độ lệch 40 ± 1 dòng, và phải ghi ra đủ ba PNG cùng `qc.json`.

## 4. Các bước triển khai

1. **Chạy kiểm tra.** `geoeyes stack-qc <project>` (mọi chồng ảnh trong `stacks/`) hoặc `--stack <stack_id>` (lặp lại
   được). Khoảng một đến hai phút cho chồng spotlight (`api/app.py`); lâu hơn với chồng S1 lớn (mỗi ngày được đọc
   trọn một lần). Web app: tab Stack → *Check the stack*; nếu có nhiều chồng ảnh, chọn trong danh sách trước.
2. **Đọc bảng.** CLI in cho mỗi ngày: `Bperp`, `HoA`, độ nhất quán trung bình (p90), độ lệch dòng / cột, tương quan
   biên độ, và thư mục kết quả. Web app: cùng bảng đó, tô màu theo các ngưỡng trên.
3. **Xem ảnh.** Bấm vào dòng của một ngày: biên độ, giao thoa đồ, độ nhất quán cạnh nhau; bấm vào ảnh để xem cỡ đầy đủ.
4. **Quyết định.** Mọi thứ tốt → `geoeyes run <project>` chạy tiếp đến `ps`. Có ngày xấu → xem §6.
5. **Sau khi dựng lại,** kiểm tra lần nữa: trang web báo "The stack was rebuilt after this check" khi kho chồng ảnh mới
   hơn `qc.json` quá 60 giây.

Tệp ghi ra: `stacks/<stack_id>/qc/amp_<date>.png`, `ifg_<date>.png`, `coh_<date>.png` (không có cho ngày tham chiếu)
và `qc.json`.

## 5. Kết quả và cách đọc

`qc.json` (schema `geoeyes.stack_qc/1`): `stack`, `created`, `reference_date`, `shape`, `looks`, `image_shape`,
`crop` (dòng / cột của vùng cắt), `orientation` (hình học radar: dòng = phương bay, cột = phương nhìn ngang) và
`dates`: `date`, `days` (tính từ ngày đầu), `reference`, `bperp_m`, và với các ngày phụ `coherence_mean`,
`coherence_p90`, `height_of_ambiguity_m`, `offset_lines`, `offset_samples`, `amplitude_corr`.

- Giao thoa đồ: có vân hoặc pha trơn ở nơi độ nhất quán cao là ngày tốt; vân dày bám theo địa hình khi |B⊥| lớn (HoA
  nhỏ) là sai số DEM, không phải khớp sai.
- Ảnh độ nhất quán: mất nhất quán theo lớp phủ (mặt nước, thực vật) là bình thường; cả ngày tối đều thì không.
- Tương quan biên độ: so với cặp tốt nhất trong chồng; một ngày thấp hẳn các ngày khác trong khi ảnh biên độ vẫn thấy
  đúng các toà nhà là ngày khớp sai.
- Độ lệch: hàng chục điểm ảnh kèm giao thoa đồ toàn nhiễu = khớp ảnh thất bại ở ngày đó (trường hợp Umbra trước khi
  có tìm độ lệch thô: quỹ đạo đặt hai lần chụp cách nhau 15–25 m, ../guide/projects-and-data.md §5).

## 6. Kiểm tra chất lượng

Chấp nhận chồng ảnh khi mọi ngày phụ đều có: độ lệch ≤ 0,1 điểm ảnh, độ nhất quán và tương quan biên độ tương đương các
ngày có B⊥ và khoảng thời gian gần giống, giao thoa đồ nhất quán ở nơi ảnh biên độ cho thấy công trình ổn định. Sau đó:

- một ngày xấu, các ngày khác tốt: bỏ ngày đó (xoá thư mục hoặc loại bằng `date_range`; `ps_lite`:
  `[ps_lite] exclude_dates`) rồi dựng lại;
- độ lệch vài phần mười điểm ảnh tăng theo độ cao ở vùng dốc: thử `[stack] coreg_model = "terrain"`;
- nhiều ngày xấu: kiểm tra DEM, quỹ đạo (POEORB của S1), hình học cảnh (chùm, PRF, góc tới) và log của bước dựng.

## 7. Hạn chế và lỗi thường gặp

- Độ lệch đúng 0.00 có thể nghĩa là "không đo được": ít hơn 4 ô tương quan được (mặt nước, vùng cắt không có đối
  tượng) hoặc các cửa sổ thô không thống nhất. Hãy đọc cùng độ nhất quán và tương quan biên độ.
- Khi đã tìm được độ lệch thô, phần dư dưới điểm ảnh không được đo: giá trị là số nguyên.
- Độ lệch và tương quan biên độ chỉ lấy từ vùng cắt ở giữa; khớp sai ở chỗ khác (rìa ảnh, địa hình khác) chỉ thấy qua
  ảnh độ nhất quán và giao thoa đồ.
- Độ nhất quán ước lượng trên ít điểm ảnh gộp bị lệch lên; hãy so các ngày với nhau, không so với một giá trị tuyệt đối.
- Kiểm tra đọc `slc`, không đọc `slc_linked`: không nói gì về liên kết pha.
- Không tự chạy với Sentinel-1; kiểm tra chồng ảnh chỉ để tham khảo và không bao giờ chặn một lần chạy.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- Ngưỡng như nhau cho mọi vệ tinh; điều thay đổi là mức độ nhất quán kỳ vọng (băng X trên thực vật, khoảng thời gian
  dài, chênh góc nhìn của Umbra cho giá trị thấp ngay cả ở ngày tốt).
- Với chồng spotlight, một ngày nhất quán phải cho thấy nhà và đường của ảnh biên độ trên ảnh độ nhất quán.
- `size` và `crop` là đối số của hàm (`stack_qc(store, size=..., crop=...)`), không phải thiết lập của dự án.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/processing/stack/qc.py`, `processing/stack/native/sicd_stack.py` (`coarse_offset`),
  `processing/stack/native/stripmap.py` (`residual_offset`), `controller/phases/build_stack.py` (kiểm tra tự động),
  `cli/main.py` (`cmd_stack_qc`), `api/app.py` (`/api/projects/{name}/stacks`, `/stacks/{sid}/qc`),
  `webapp/src/components/StackQc.tsx`, `tests/unit/processing/test_stack_qc.py`.
- Hướng dẫn: ../guide/projects-and-data.md §5 (Checking the stack before the points). Quyết định: ADR-029.
- Skill: [insar-processing.md](insar-processing.md), [opendata-stacks.md](opendata-stacks.md).
- Touzi et al. 1999 (ước lượng độ nhất quán và độ lệch của nó); Guizar-Sicairos et al. 2008 (tương quan pha dưới điểm
  ảnh, dùng trong `skimage.registration.phase_cross_correlation`).
