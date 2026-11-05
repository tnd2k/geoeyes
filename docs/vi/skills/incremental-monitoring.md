# Skill: xử lý gia tăng, giám sát và cảnh báo sớm

> Bản dịch của [docs/en/skills/incremental-monitoring.md](../../en/skills/incremental-monitoring.md). Dịch ngày 2026-11-01.

> Giữ dự án luôn cập nhật khi có ảnh mới (thêm một ngày chụp trong vài phút thay vì chạy lại toàn bộ), cảnh báo biến
> dạng trên sản phẩm mới nhất, và chuyển kết quả cho người không dùng GIS (Google Earth, 3D Tiles); đặt hàng sản phẩm
> tầng đối lưu GACOS cho các ngày mới. Trạng thái: vận hành với Sentinel-1 và engine `ps`. Kiểm tra gần nhất
> 2026-11-01. CLI: `geoeyes plan / run` (tự chạy gia tăng), `geoeyes gacos-order`. Web app: trang dự án → tab
> Monitoring (lần chụp sắp tới, lịch chạy, quy tắc cảnh báo).

## 1. Khi nào dùng

- Dự án đã chạy đầy đủ một lần và ảnh mới tiếp tục về (S1: 6–12 ngày một lần): thêm chúng với chi phí thấp, tạo phiên
  bản sản phẩm mới, kiểm tra các quy tắc cảnh báo.
- Cần cảnh báo sớm: các điểm có ngày mới nhất lệch khỏi xu thế, hoặc có vận tốc vượt một giới hạn.
- Cần chia sẻ vận tốc với người chỉ có Google Earth hoặc trình duyệt.
- Không dùng cho: lần chạy đầu (xem [insar-processing.md](insar-processing.md)); dự án có liên kết pha hoặc dùng
  `ps_lite` (không có cập nhật điểm: mỗi ngày mới là một lần chạy engine đầy đủ, riêng chồng ảnh vẫn được mở rộng
  gia tăng).

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Dự án đã chạy đầy đủ | có | [insar-processing.md](insar-processing.md) | `ps_runs/<track_id>/state.h5`, `manifest.json` có `config_fingerprint` | bản cập nhật nối tiếp lần chạy này |
| Ảnh mới | có | S1: ASF qua `acquire`; vệ tinh khác: thư mục `YYYYMMDD/` mới; dữ liệu mở: `geoeyes opendata sync` | như [insar-processing.md](insar-processing.md) §2 | `[acquire] date_range` phải bao các ngày mới (dời ngày cuối về sau) |
| `EARTHDATA_TOKEN` | có (S1) | NASA Earthdata | biến môi trường / `.env` | burst và POEORB |
| Thiết lập gia tăng | tuỳ chọn | mặc định là đủ | `[stack] incremental = true`, `[ps_update] enabled = true`, `full_every = 4` | |
| Quy tắc cảnh báo | tuỳ chọn | ngưỡng của bạn | `[postprocess.alerts] rules = [{ name, kind, threshold, min_points, bbox }]` | tab Monitoring cũng ghi được |
| Lịch chạy | tuỳ chọn | Windows Task Scheduler (từ web app) hoặc cron | tác vụ `GeoEyes\<project>` | web app chỉ đặt được trên Windows |
| Sản phẩm GACOS | tuỳ chọn | đặt hàng tại http://www.gacos.net (không có API), gửi qua e-mail | `[atmosphere.gacos] dir`: `<YYYYMMDD>.ztd` + `.ztd.rsc`, hoặc `<YYYYMMDD>.ztd.tif` | kèm `[atmosphere] method = "gacos"` |
| Định dạng xuất | tuỳ chọn | — | `[export] formats = ["gpkg", "pmtiles", "kmz", "3dtiles"]` | mặc định `["gpkg", "pmtiles"]` |
| Máy chủ web | cho cảnh báo, trình xem 3D | `geoeyes serve` | http://localhost:8765 | cảnh báo do máy chủ tính |

Danh sách kiểm tra:

- [ ] Lần chạy đầy đủ gần nhất *done*; `geoeyes plan <project>` thấy các ngày mới và, ở dòng `ps`, có
      `incremental update: N new date(s)`.
- [ ] `[acquire] date_range` phủ các ngày mới; cùng ngày tham chiếu, AOI, DEM, dải con như lần dựng trước.
- [ ] Đã lưu quy tắc cảnh báo (tab Monitoring hoặc `project.toml`).
- [ ] GACOS: đã có sản phẩm của các ngày mới trong `[atmosphere.gacos] dir` (`geoeyes gacos-order` liệt kê ngày còn thiếu).

## 3. Phương pháp

**Chồng ảnh gia tăng** (`controller/phases/build_stack.py`, `reusable`). Với `[stack] incremental = true`, lần dựng
mới chép lại các ngày đã khớp của kho cũ khi kho đó dựng với cùng ngày tham chiếu, AOI, DEM và dải con (dấu vân tay
chồng ảnh tính lại bằng chữ ký cảnh đã lưu), cảnh tham chiếu không đổi, và các tệp của chính ngày đó (S1: chỉ các
burst mà chồng ảnh dùng, cùng tệp annotation) giữ nguyên tên và kích thước. Ngày S1 đã khớp khi chưa có POEORB sẽ
được làm lại khi quỹ đạo chính xác được công bố (kiểm tra với ngày đã ≥ 15 ngày tuổi). Với `[network] reference =
"auto"`, ngày tham chiếu của lần dựng đầu được giữ.

**Cập nhật điểm gia tăng** (`processing/ps/update.py`, engine `geoeyes-ps-update/1`). Dùng khi chỉ thêm các ngày sau
ngày cuối của lần chạy `ps` trước. Giữ lại: các điểm, sai số góc nhìn K của chúng (từ scla = K·B⊥), số hạng ảnh chủ C,
tham chiếu và mô hình vận tốc. Với mỗi ngày mới d và mỗi điểm:

```
φ_obs  = arg(slc_ref · conj(slc_d))
φ_topo = K · B⊥_d                               B⊥_d from the stack height sensitivity kh
φ_pred = −(v·t_d + c) / (λ/4π)                  linear fit of the previous series
r      = wrap(φ_obs − φ_topo − φ_pred − C)
φ_uw   = φ_topo + φ_pred + C + unwrap_space(r)  IRLS on the unwrap grid, each point snapped to φ_obs + 2πk
d      = −(φ_uw − φ_topo − APS − C) · λ/4π
```

- Giải chập theo không gian: lưới `[ps] unwrap_grid_size` (mặc định 10 m), lọc trước Gauss với cửa sổ cố định 16 và α
  0,8 (không dùng `unwrap_gold_n_win`), trọng số = bình phương độ nhất quán của ô đã làm trơn (kẹp trong 0,05–1), IRLS
  tinh chỉnh, có tôn trọng `unwrap_align_constant`.
- APS của ngày mới: mô hình thời tiết (ERA5 / CERRA / GACOS) khi có số liệu cho > 50 % số điểm và cho phương sai phần
  dư nhỏ hơn khớp tuyến tính pha – độ cao; nếu không thì dùng khớp tuyến tính.
- Quy về tham chiếu như engine (điểm tham chiếu hoặc trung bình cảnh); vận tốc, gia tốc và RMSE khớp được tính lại trên
  mọi ngày, trọng số theo nhiễu pha từng ngày (ngày mới: nhiễu trung vị); hiệu chỉnh thông cao của vận tốc từ engine
  được giữ nguyên; SCN của các ngày mới bằng 0.

Chạy đầy đủ thay vì cập nhật khi: tham số thay đổi (`[ps]`, `[selection]`, `[atmosphere]`, `[ps_lite]`, phiên bản
engine), sang chồng ảnh khác (tham chiếu mới), các ngày của lần chạy trước bị khớp lại, có ngày mới đứng trước ngày
cuối, bật liên kết pha, engine `ps_lite`, số ngày thêm từ lần chạy đầy đủ gần nhất vượt `full_every`, `[ps_update]
enabled = false`, hoặc `--force ps`.

**Cảnh báo** (`api/monitor.py`). Các quy tắc trong `[postprocess.alerts]`, tính trên sản phẩm mới nhất của mỗi vệt:

| `kind` | Giá trị xét tại mỗi điểm | Kích hoạt khi |
|---|---|---|
| `velocity_below` / `velocity_above` | `vel_los_mm_yr` | ≥ `min_points` điểm có giá trị ≤ / ≥ `threshold` (mm/năm) |
| `deviation_below` / `deviation_above` | chuyển dịch của ngày mới nhất trừ đường bình phương tối thiểu qua các ngày trước (mm) | ≥ `min_points` điểm có giá trị ≤ / ≥ `threshold` (mm) |

`min_points` mặc định 10; tuỳ chọn `bbox = [west, south, east, north]` giới hạn vùng điểm; quy tắc độ lệch cần ít nhất 7
ngày. Kết quả cho số điểm vượt ngưỡng, số điểm được xét, giá trị cực trị và trọng tâm các điểm vượt. Quy tắc do máy chủ
web tính (tab Monitoring, danh sách dự án), không phải do `geoeyes run`; không gửi e-mail (ADR-008).

**Lần chụp sắp tới** (vệt S1): lần chụp cuối của mỗi vệ tinh trong kho ảnh + các bước 12 ngày (bỏ vệ tinh không thấy
trong 60 ngày), đánh dấu *planned* / *not planned* theo kế hoạch chụp của ESA.

**Lịch chạy** (Windows): tác vụ `GeoEyes\<project>` chạy `python -m geoeyes.cli.main --workspace <ws> run <project>`
hằng ngày hoặc hằng tuần lúc `HH:MM` (mặc định 02:00, thứ Hai), khi người dùng đang đăng nhập. Hệ điều hành khác: cron.

**Xuất dữ liệu** (`export/`). `kmz`: vận tốc raster hoá theo kích thước ký hiệu thành lớp phủ mặt đất (cạnh dài ≤ 4000
điểm ảnh) theo các lớp của kiểu hiển thị QGIS, có chú giải, và 1.500 điểm nhanh nhất của cả hai chiều dưới dạng
placemark kèm số liệu và biểu đồ chuyển dịch nhỏ. `3dtiles`: đám mây điểm 3D Tiles 1.0, ô gốc 40.000 điểm và các ô con
≤ 150.000 điểm, toạ độ ECEF ở độ cao elipxoit (độ cao trên EGM96 + độ cao geoid), màu theo lớp vận tốc, vận tốc / độ
cao / độ nhất quán cho từng điểm, `viewer.html` dùng CesiumJS 1.120. `pmtiles`: vector tile (QGIS 3.32+, chế độ chia ô
của web app). Tất cả dùng Pretty Breaks, 10 lớp trên min–max, `jet_r`.

**Đặt hàng GACOS** (`geoeyes gacos-order`, `processing/atmosphere/gacos.py`): vùng = AOI ± 0,1°, thời điểm = giờ UTC
trung bình của các lần chụp, các ngày chưa có sản phẩm trong `[atmosphere.gacos] dir`. Với `select = "auto"`, GACOS
chỉ được dùng cho giao thoa đồ mà nó giải thích phần dư tốt hơn khớp tuyến tính.

## 4. Các bước triển khai

1. **Làm một lần:** đặt `[export] formats`, quy tắc cảnh báo (tab Monitoring → *Deformation alerts* → *Save rules*,
   hoặc sửa `[postprocess.alerts]`), và lịch chạy (tab Monitoring → *Scheduled run*: tần suất, ngày, giờ → *Save*).
2. **Mỗi lần có ảnh mới** (theo lịch hoặc chạy tay):
   - `geoeyes plan <project>`: "N new acquisition(s) on ASF"; `build_stack … incremental: K coregistered date(s)
     kept`; `ps … incremental update: N new date(s)`.
   - `geoeyes run <project>`. Thời gian cho một ngày mới (Hà Nội S1 quỹ đạo lên 128, 26 ngày, khoảng 730.000 điểm;
     ../guide/incremental.md): `acquire` chỉ tải burst mới, `build_stack` khoảng 3 phút (ước tính), `ps` 45 giây,
     `build_product` + `export` + `report` 2 phút. Ba ngày: `ps` 62 giây.
   - Ghi ra: các ngày mới trong `stacks/<stack_id>/stack.zarr`; `ps_runs/<track_id>/` được ghi đè tại chỗ (`state.h5`,
     `points.parquet`, `timeseries.parquet`, `manifest.json`); một sản phẩm mới `products/<…>_v<N+1>/`; dữ liệu xuất
     và báo cáo của nó.
3. **Cứ sau `full_every` ngày** (hoặc khi đổi tham số) pha `ps` chạy đầy đủ (Hà Nội: 12 phút).
4. **Đọc cảnh báo:** tab Monitoring (`geoeyes serve`, rồi mở dự án). Một quy tắc độ lệch bị kích hoạt cần được đối
   chiếu với lần chụp kế tiếp và với vệt còn lại trước khi hành động.
5. **Chia sẻ:** `exports/<product>/<product>.kmz` mở bằng Google Earth; trình xem 3D tại
   `http://localhost:8765/api/projects/<project>/exports/<product>/3dtiles/viewer.html` (do `geoeyes serve` phục vụ).
6. **GACOS:** `geoeyes gacos-order <project> [--track ID]` in vùng (N, S, W, E), giờ UTC và các ngày (20 ngày một khối)
   để dán vào biểu mẫu; giải nén sản phẩm vào thư mục `[atmosphere.gacos] dir`, đặt `[atmosphere] method = "gacos"`
   (thay đổi `[atmosphere]` khiến lần `ps` sau chạy đầy đủ).

## 5. Kết quả và cách đọc

| Tệp / trường | Nội dung |
|---|---|
| `ps_runs/<track_id>/manifest.json` → `metrics.update` | `base_run` (lần chạy đầy đủ gần nhất), `dates_since_full`, `added` (các ngày thêm bằng cập nhật), `weather_aps` (các ngày dùng mô hình thời tiết) |
| `ps_runs/<track_id>/manifest.json` → `engine` | `geoeyes-ps-update/1` sau một lần cập nhật, mã engine sau lần chạy đầy đủ |
| `products/<…>_v<N>/` | mỗi lần chạy một phiên bản mới; các phiên bản cũ được giữ |
| Kết quả cảnh báo | `name`, `kind`, `threshold`, `min_points`, `n` (số điểm vượt), `of` (số điểm được xét), `triggered`, `worst`, `lon`, `lat`, `date` (quy tắc độ lệch), `note` ("fewer than 7 dates") |
| `exports/<id>/<id>.kmz` | lớp phủ + chú giải + placemark |
| `exports/<id>/3dtiles/` | `tileset.json`, `tiles/*.pnts`, `viewer.html` |

Độ lệch −10 mm trên 30 điểm ở ngày mới nhất nghĩa là các điểm đó lún thêm 10 mm so với dự báo theo xu thế: có thể là
chuyển dịch thật, cũng có thể là khí quyển của riêng ngày đó.

## 6. Kiểm tra chất lượng

- Thử nghiệm giữ lại dữ liệu (hold-out) của bản cập nhật (Hà Nội quỹ đạo lên 128, ../guide/incremental.md): thêm 1
  ngày, chuyển dịch của ngày mới so với chạy đầy đủ r 0,92, độ lệch chuẩn 2,7 mm, 0,5 % số điểm lệch quá nửa chu kỳ,
  độ lệch chuẩn vận tốc 0,6 mm/năm; thêm 3 ngày r 0,83–0,93, độ lệch chuẩn 2,7–3,6 mm, tới 1,2 %, độ lệch chuẩn vận tốc
  1,4 mm/năm. Một phần chênh lệch đến từ việc lần chạy đầy đủ ước lượng lại các điểm, K và APS.
- Log của bản cập nhật: mỗi ngày một dòng "unwrapped residual … rad (std), APS weather|linear, median motion vs
  prediction … mm"; chênh trung vị lớn ở một ngày là khí quyển hoặc lỗi giải chập cho đến khi ngày sau xác nhận.
- So bản đồ vận tốc của phiên bản mới với phiên bản trước (cùng lớp màu, toàn dải min–max).
- Đọc phần kiểm tra chất lượng trong báo cáo của mỗi sản phẩm mới.

## 7. Hạn chế và lỗi thường gặp

- Bản cập nhật không tìm được điểm ổn định mới hay bỏ điểm đã mất, không ước lượng lại K và APS của các ngày cũ, không
  tách được SCN của các ngày mới (bằng 0): vì vậy cần `full_every`.
- Có liên kết pha hoặc dùng `ps_lite`: không có cập nhật điểm; mỗi ngày mới chạy engine đầy đủ.
- ERA5 của vài ngày gần nhất có thể chưa công bố: bản cập nhật quay về APS tuyến tính cho ngày đó.
- Cảnh báo chỉ được tính khi máy chủ web được hỏi (trang đang mở); một lần chạy theo lịch chỉ tạo sản phẩm, không gửi
  thông báo. Dòng chữ "after every run" ở tab Monitoring chỉ đúng khi trang được xem.
- Tác vụ theo lịch chỉ chạy khi người dùng đang đăng nhập; hệ điều hành khác dùng cron.
- Dự báo lần chụp sắp tới và đặt lịch từ web app: chỉ Sentinel-1 / Windows.
- `viewer.html` mở trực tiếp từ đĩa không đọc được tile; hãy mở qua máy chủ.
- Đổi `[atmosphere]` (ví dụ chuyển sang GACOS) hay bất kỳ thay đổi nào trong `[ps]` đều khiến lần chạy sau là chạy đầy đủ.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- Chọn `full_every` theo độ chính xác cần: 1 ngày mỗi lần cập nhật giữ r ≈ 0,92 ở Hà Nội; nhiều ngày hơn thì kém đi
  (xem trên).
- Đặt ngưỡng cảnh báo từ chính nhiễu của sản phẩm: `vel_std_median_mm_yr` và sigma phần dư ở vùng ổn định; `min_points`
  đủ lớn để một cụm nhiễu không kích hoạt; mỗi công trình (đê, sân bay) một `bbox`.
- Bản cập nhật dùng `unwrap_grid_size` của dự án (TP.HCM: 50 m, nơi khác 10 m) và `unwrap_align_constant`.
- Vệ tinh thương mại: ngày mới là thư mục `YYYYMMDD/` mới; khi có liên kết pha (preset COSMO-SkyMed, ICEYE) mỗi ngày
  mới là một lần chạy đầy đủ.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/processing/ps/update.py`, `controller/pipeline.py` (`PointEngine.update_plan`, `note`),
  `controller/phases/build_stack.py` (`reusable`, `orbit_upgrades`), `api/monitor.py`, `api/app.py`
  (`/api/projects/{name}/monitor`, `/alerts`, `/schedule`), `webapp/src/components/Monitor.tsx`,
  `export/{kmz,tiles3d,pmtiles,styles}.py`, `processing/atmosphere/gacos.py`, `cli/main.py` (`cmd_gacos_order`).
- Hướng dẫn: ../guide/incremental.md, ../guide/atmosphere.md, ../guide/projects-and-data.md.
- Skill: [insar-processing.md](insar-processing.md), [atmosphere.md](atmosphere.md), [stack-qc.md](stack-qc.md).
- Yu et al. 2018 (GACOS); OGC 3D Tiles 1.0; Hooper 2008 (giải chập không gian – thời gian của StaMPS).
