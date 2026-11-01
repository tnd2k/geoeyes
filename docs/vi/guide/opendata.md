# Dữ liệu mở: tìm và xử lý chồng ảnh SAR mở

Hướng dẫn này dành cho người muốn xử lý dữ liệu băng X độ phân giải cao mà không phải mua. Nó liệt kê các catalog mở
mà GeoEyes tìm kiếm, cách nhận ra một chồng ảnh chụp lặp, và các bước từ lúc tìm kiếm đến khi có dự án đã xử lý.
Thiết kế: [ADR-028](../architecture/decisions.md).

## Nội dung

1. [Các catalog](#1-các-catalog)
2. [Thế nào là một chồng ảnh](#2-thế-nào-là-một-chồng-ảnh)
3. [Dùng dòng lệnh](#3-dùng-dòng-lệnh)
4. [Dùng web app](#4-dùng-web-app)
5. [Bước acquire tải những gì](#5-bước-acquire-tải-những-gì)
6. [ICEYE SLC-COG](#6-iceye-slc-cog)
6b. [Umbra SICD](#6b-umbra-sicd)
7. [Các chồng ảnh đã biết (tháng 10/2026)](#7-các-chồng-ảnh-đã-biết-tháng-102026)

## 1. Các catalog

| Nguồn | Catalog (STAC tĩnh trên AWS, CC-BY 4.0) | Sản phẩm phức | GeoEyes |
|---|---|---|---|
| ICEYE Open Data | `iceye-open-data-catalog` (us-west-2) | SLC-COG: GeoTIFF biên độ + pha, metadata STAC | xử lý được (`iceye`) |
| Capella Space Open Data | `capella-open-data` (us-west-2) | SLC GeoTIFF + `*_extended.json` | xử lý được (`capella`, method `ps_lite`) |
| Umbra Open Data | `umbra-open-data-catalog` (us-west-2) | SICD NITF (PFA spotlight, 0,15 m) | xử lý được (`umbra`, method `ps_lite`) |

Không cần tài khoản. Khi công bố kết quả, hãy ghi nguồn ("© ICEYE", "© Capella Space", "© Umbra"). ICEYE lưu ý rằng
catalog mở của họ có thể chứa sản phẩm thử nghiệm.

## 2. Thế nào là một chồng ảnh

Giao thoa cần các lần chụp lặp: cùng quỹ đạo (lệch trong vài trăm mét), cùng dải quét, cùng hướng nhìn. Chỉ dựa vào
item STAC, các ảnh được gom thành một chồng khi có chung:

- nguồn và **vệ tinh** (ICEYE, Umbra: mỗi vệ tinh có vết quỹ đạo riêng) hoặc **vết quỹ đạo lặp** do nhà cung cấp
  đặt (Capella `capella:rgt_id`, có thể gồm nhiều vệ tinh);
- chế độ chụp, chiều bay và hướng nhìn;
- góc tới chênh không quá **±1°** và phương vị nhìn chênh không quá **±3°** so với ảnh đầu tiên của chồng;
- vùng phủ chồng lên vùng phủ của ảnh đầu tiên **ít nhất 50 %** diện tích của ảnh nhỏ hơn.

Đường cơ sở vuông góc chỉ biết được khi đọc sản phẩm: `build_stack` ghi chúng vào log và loại các ảnh lệch hình học
so với ảnh chủ (`check_geometry`). Id của chồng ảnh được tạo từ ảnh đầu tiên và không phụ thuộc vào vùng tìm kiếm:
`iceye:x53-sm-ar-26-28.2n016.7w` = ICEYE-X53, stripmap, quỹ đạo lên, nhìn phải, góc tới 26°, tâm tại 28,2° B
16,7° T. Id của Capella kết thúc bằng một mã băm ngắn của vết quỹ đạo.

## 3. Dùng dòng lệnh

```
geoeyes opendata sync                                    # lập chỉ mục mọi catalog (lần đầu khoảng 1–2 phút)
geoeyes opendata sources                                 # số ảnh mỗi nguồn, lần đồng bộ gần nhất
geoeyes opendata stacks --supported                      # mọi chồng ảnh GeoEyes xử lý được
geoeyes opendata stacks --bbox=-16.68,28.24,-16.60,28.30 # các chồng ảnh có ảnh phủ vùng này
geoeyes opendata show iceye:x53-sm-ar-26-28.2n016.7w     # ngày chụp, vệ tinh, góc tới, vùng phủ
geoeyes opendata project iceye:x53-sm-ar-26-28.2n016.7w tenerife_iceye --bbox=-16.645,28.215,-16.630,28.228
geoeyes run tenerife_iceye
```

Viết `--bbox=` có dấu bằng: nếu không, giá trị bắt đầu bằng `-` (kinh độ tây) sẽ bị hiểu nhầm là một tuỳ chọn.
`geoeyes opendata fetch <id> --bbox=...` tải ảnh mà không tạo dự án
(`<workspace>/archive/<sensor>/<sensor>-<asc|des>/`).

Dự án do `opendata project` tạo ra:

```toml
[aoi]
bbox = [-16.645, 28.215, -16.63, 28.228]

[[tracks]]
sensor = "iceye"
direction = "ascending"

[acquire]
opendata = "iceye:x53-sm-ar-26-28.2n016.7w"
# opendata_margin_m = 500        # lề quanh AOI khi sản phẩm cắt được (ICEYE)
# date_range = [2026-02-18, 2026-02-21]
# max_per_month = 0
```

## 4. Dùng web app

Tab **Dữ liệu mở** của trang **Dự án** (thanh trên cùng; hoặc liên kết "Tạo từ dữ liệu mở" phía trên danh sách dự án). Không cần tự tìm: server tự lập chỉ mục các catalog ngay lần đầu mở trang,
sau đó mỗi ngày một lần (*Làm mới danh sách* để làm ngay), và liệt kê mọi chồng ảnh GeoEyes xử lý được, gọi theo
địa danh ("Los Angeles, California, United States"; tên lấy từ OpenStreetMap qua Nominatim hoặc Photon), chồng
nhiều ngày chụp nhất lên đầu. Trên bản đồ, mỗi chồng ảnh là một chấm (ICEYE xanh dương, Capella cam, Umbra tím;
chấm càng lớn càng nhiều ngày chụp), phóng to thì thấy vùng phủ. Các bộ lọc (chữ, nguồn, chế độ chụp, "chỉ trong một
vùng") là tuỳ chọn.

Bấm vào một chồng ảnh (trong danh sách hoặc trên bản đồ): bản đồ phóng tới đó, một vùng xử lý được đề xuất sẵn
(ICEYE: khoảng 3 km quanh tâm, chỉ tải phần này; Capella: phần lớn vùng phủ, vì đằng nào cũng tải nguyên cảnh) kèm
dung lượng cần tải, và tên dự án được điền sẵn. *Vẽ vùng khác* để đổi vùng, rồi *Xử lý chồng ảnh này*: dự án được tạo
và trang xử lý của nó mở ra.

## 5. Bước acquire tải những gì

Với `[acquire] opendata`, bước `acquire` lấy các ảnh của chồng **phủ toàn bộ AOI** (sau đó lọc theo `date_range` và
`max_per_month`) và ghi mỗi ngày một thư mục, `<archive>/<sensor>/<track>/YYYYMMDD/`, kèm `opendata.json` khi tải
xong. Thư mục đã tải với cùng item, AOI và lề sẽ không tải lại; khi catalog có ngày mới (sau
`geoeyes opendata sync`), bước này chỉ chạy lại cho ngày đó, và `build_stack` thêm ngày đó theo kiểu gia tăng.

| Nguồn | Phần được tải | Dung lượng mỗi ngày |
|---|---|---|
| ICEYE | cửa sổ phủ AOI + `opendata_margin_m`, đọc bằng HTTP range từ COG | khoảng 10 MB cho 1,5 km × 1,5 km, khoảng 3,6 GB cho nguyên cảnh stripmap |
| Umbra | cửa sổ phủ AOI + `opendata_margin_m` (mặc định 50 m), đọc từng dòng bằng HTTP range từ file SICD NITF | khoảng 30 MB cho 200 m × 200 m, khoảng 7 GB cho nguyên cảnh |
| Capella | nguyên SLC và metadata mở rộng | khoảng 0,3–1,5 GB |

Cửa sổ ICEYE được tính bằng mô hình RPC của sản phẩm ở độ cao DEM thấp nhất và cao nhất trong AOI (`[stack] dem`):
ở vùng núi lửa, cửa sổ cự ly rộng ra theo địa hình.

## 6. ICEYE SLC-COG

- Hai kênh uint16 `AMPLITUDE` và `PHASE` với scale / offset của GDAL (pha −π..π): mẫu = biên độ · e^(j·pha). Bước
  lượng tử pha 16 bit là 0,005°, không đáng kể.
- Ảnh lưu kiểu **shadows-down**: hàng TIFF là mẫu cự ly (gần → xa), cột TIFF là dòng phương vị (sớm → muộn). Trình
  đọc chuyển vị về quy ước GeoEyes (dòng = phương vị).
- Hình học: `iceye:zero_doppler_start_datetime`, mỗi dòng 1 / `iceye:processing_prf`, `iceye:range_near`,
  `sar:pixel_spacing_range` (nghiêng), vector trạng thái quỹ đạo chính xác trong ECEF, đa thức Doppler centroid. Đã
  kiểm tra với RPC đi kèm sản phẩm: sai lệch < 0,3 pixel theo cả hai chiều.
- Ảnh đã cắt mang `geoeyes:crop` (hàng / cột của vùng cắt trong TIFF gốc) trong `*_SLC.json`.

## 6b. Umbra SICD

- SICD = NITF 2.1 chứa ảnh phức (I / Q float32) và XML SICD. GeoEyes tự đọc cả hai (`sensors/sicd`), từ file cục bộ
  hoặc trực tiếp trên S3 (HTTP range). Item STAC của Umbra không có liên kết file: file SICD nằm trong
  `sar-data/task-data/<umbra:task_id>/`.
- Ảnh Umbra là **spotlight, polar format (PFA) trên mặt phẳng nghiêng**, không phải lưới zero-Doppler: hình học theo
  phép chiếu ảnh của SICD (đường đồng mức R / Ṙ tại thời điểm giữa khẩu độ), đã đối chiếu với sarpy của NGA. Chồng
  ảnh do `processing/stack/native/sicd_stack.py` dựng (thiết kế: [ADR-029](../architecture/decisions.md)).
- Đừng kỳ vọng coherence cao trừ trên công trình ổn định: các lần chụp lặp lệch góc nhìn 1–2° trong khi khẩu độ góc
  chỉ khoảng 4,5°, đường cơ sở tới vài km (độ cao mơ hồ dưới 1 m với 7 km), và mặt nước / bãi container thay đổi giữa
  các ngày. Giữ AOI nhỏ (pixel 0,15 m: 200 m × 200 m đã là 1300 × 1500 pixel) và đặt trên nhà, đường, cầu cảng.

## 7. Các chồng ảnh đã biết (tháng 10/2026)

Theo `geoeyes opendata stacks` ngày 28/10/2026 (72 chồng ảnh có ≥ 3 ngày chụp: 65 Capella, 2 ICEYE, 5 Umbra):

| Chồng ảnh | Ngày chụp | Khoảng thời gian | Cách nhau | Ghi chú |
|---|---|---|---|---|
| `iceye:x53-sm-ar-26-28.2n016.7w` | 19 | 11/02 → 01/03/2026 | 1 ngày | Tenerife (Teide), stripmap 3 m, B⊥ −873..+75 m, có kèm interferogram / coherence của ICEYE |
| `iceye:x53-sm-dl-14-21.2s055.6e` | 4 | 19/03 → 27/05/2026 | 5 ngày | Réunion (Piton de la Fournaise), góc tới dốc 14,5° |
| Capella, 34,8° B 118,1° T | 95 | 11/2024 → 11/2025 | 3 ngày | spotlight, chồng ảnh mở dài nhất |
| Capella, 19,4° B 155,3° T | 35–60 | 2025 | 3 ngày | Kīlauea, quỹ đạo lên và xuống |
| `capella:c14-sm-al-41-19.4n099.0w-…` | 18 | 26/06 → 15/08/2024 | 3 ngày | Mexico City, stripmap (dữ liệu của `mexico_capella`) |
