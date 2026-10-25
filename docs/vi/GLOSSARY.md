# Bảng thuật ngữ Anh – Việt (GeoEyes)

> Dùng chung cho mọi bản dịch tiếng Việt trong `docs/vi/` và cho giao diện web. Bản gốc tiếng Anh là bản chuẩn
> (ADR-015); bản tiếng Việt là bản dịch, ghi ngày dịch ở đầu mỗi tệp.

Quy ước chung:

- Giữ nguyên tiếng Anh: tên mã, tệp, lệnh, tham số cấu hình (`cell_m`, `gnss_tie`…), tên phần mềm, tên vệ tinh,
  tên trạm, các viết tắt chuẩn (InSAR, PS, DS, LOS, GNSS, DEM, CRD, FDR, SCN, APS, ADA, PSI, SBAS, MIDAS, NGL,
  CHIRPS, ERA5, IGS20, STAC, COG, GeoParquet), tài liệu tham khảo (tác giả, tên bài, tạp chí, DOI).
- Lần đầu gặp một viết tắt trong mỗi tài liệu: viết tiếng Việt kèm viết tắt trong ngoặc, ví dụ "hướng nhìn của
  vệ tinh (LOS)".
- Đơn vị giữ nguyên: mm/yr → mm/năm, mm/yr² → mm/năm², km², °.
- Số thập phân dùng dấu phẩy trong câu văn tiếng Việt (12,5 mm); trong bảng số liệu và mã giữ dấu chấm nếu là
  giá trị kỹ thuật được sao chép.

| Tiếng Anh | Tiếng Việt |
|---|---|
| ground motion / deformation | chuyển dịch mặt đất / biến dạng |
| displacement | chuyển dịch |
| (land) subsidence | sụt lún (đất) |
| uplift / heave | nâng (trồi) |
| landslide / slow-moving landslide | trượt lở / trượt lở chậm |
| hazard / hazard zoning / hazard level | nguy cơ / phân vùng nguy cơ / mức nguy cơ |
| susceptibility | tính nhạy cảm (khả năng xảy ra) |
| risk / exposure / vulnerability | rủi ro / mức độ phơi nhiễm / tính dễ tổn thương |
| intensity (class) | cường độ (lớp cường độ) |
| secondary class | lớp phụ |
| angular distortion | góc biến dạng (độ lệch góc) |
| differential settlement | lún lệch |
| line of sight (LOS) | hướng nhìn của vệ tinh (LOS) |
| velocity / rate | vận tốc / tốc độ |
| acceleration | gia tốc |
| time series | chuỗi thời gian |
| zero-referencing / time zero | đặt mốc 0 / mốc thời gian 0 |
| reference point / reference area / reference date | điểm tham chiếu / vùng tham chiếu / ngày tham chiếu |
| scene mean | trung bình cảnh |
| stable ground | nền ổn định |
| persistent scatterer (PS) | điểm tán xạ bền vững (PS) |
| distributed scatterer (DS) | điểm tán xạ phân bố (DS) |
| coherence / temporal coherence | độ kết hợp / độ kết hợp thời gian |
| interferogram | giao thoa đồ |
| stack / coregistration | chồng ảnh / đồng đăng ký ảnh |
| phase unwrapping | giải chập pha |
| atmospheric phase screen (APS) | nhiễu khí quyển (APS) |
| spatially correlated noise (SCN) | nhiễu tương quan không gian (SCN) |
| ascending / descending | quỹ đạo lên / quỹ đạo xuống |
| track / burst / subswath | vệt quỹ đạo / burst / dải con |
| acquisition | lần chụp (ảnh chụp) |
| product / product version | sản phẩm / phiên bản sản phẩm |
| native (engine, stack, pipeline) | giữ nguyên `native`: phần xử lý viết riêng trong GeoEyes, không qua SNAP |
| workspace / project | không gian làm việc / dự án |
| phase (of the pipeline) | pha (của quy trình) |
| pipeline / controller | quy trình xử lý / bộ điều khiển |
| run / re-run | chạy / chạy lại |
| rainfall / monthly rainfall / annual rainfall | lượng mưa / mưa tháng / tổng mưa năm |
| cumulative rainfall departure (CRD) | độ lệch mưa tích luỹ (CRD) |
| lag | độ trễ |
| rainfall coupling | liên hệ mưa – biến dạng |
| sensitivity (k) | độ nhạy (k) |
| climate normal | chuẩn khí hậu |
| dry year (P10) / wet year (P90) | năm khô (P10) / năm ướt (P90) |
| surrogate (phase-randomised) | chuỗi thay thế (xáo pha ngẫu nhiên) |
| false discovery rate (FDR) | tỉ lệ phát hiện sai (FDR) |
| significance / p-value | ý nghĩa thống kê / giá trị p |
| leave-one-out | kiểm tra chéo bỏ-một (leave-one-out) |
| calibration / tie | hiệu chỉnh / gắn (vào GNSS) |
| ramp / offset | mặt nghiêng (ramp) / độ lệch (offset) |
| monument (GNSS) | mốc trạm (GNSS) |
| plate motion | chuyển động mảng kiến tạo |
| slope / aspect / steepest descent | độ dốc / hướng sườn / hướng dốc nhất |
| cell / grid | ô / lưới |
| threshold | ngưỡng |
| matrix | ma trận |
| very low / low / moderate / high / very high | rất thấp / thấp / trung bình / cao / rất cao |
| not assessed | chưa đánh giá |
| limitation | hạn chế |
| research sequence | trình tự nghiên cứu |
| acceptance criterion | tiêu chí chấp nhận |
| golden test / parity test | test chuẩn (golden) / test đối chiếu (parity) |
| architecture decision record (ADR) | bản ghi quyết định kiến trúc (ADR) |
| corner reflector | gương phản xạ góc (corner reflector) |
| alert / monitoring | cảnh báo / giám sát |
| report | báo cáo |
| export | xuất dữ liệu |
| map image / legend / scale bar | ảnh bản đồ / chú giải / thước tỉ lệ |
