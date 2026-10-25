> Bản tiếng Việt của [README.md](README.md); bản gốc tiếng Anh là bản chuẩn (ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.
> Thuật ngữ: xem [bảng thuật ngữ Anh – Việt](docs/vi/GLOSSARY.md).

# GeoEyes

Xử lý chuỗi thời gian InSAR: từ cảnh SAR thô đến sản phẩm chuyển dịch có quản lý phiên bản và báo cáo.

- **Cảm biến**: Sentinel-1 IW (lấy theo burst từ ASF), COSMO-SkyMed và Capella stripmap; tự đồng đăng ký ảnh, không cần SNAP.
- **Phương pháp**: điểm tán xạ bền vững (PS) theo kiểu StaMPS (`psi`); liên kết pha (phase linking) kết hợp điểm tán
  xạ phân bố (DS) (`psds`); `ps_lite` cho chồng ảnh Capella ngắn; hiệu chỉnh khí quyển bằng ERA5 / GACOS.
- **Đầu ra**: sản phẩm bất biến (điểm và chuỗi thời gian dạng GeoParquet, raster COG, STAC item); xuất dữ liệu GIS
  (GeoPackage kèm sẵn kiểu hiển thị QGIS, PMTiles); báo cáo khoa học PDF; báo cáo nhận dạng gương phản xạ góc (corner reflector);
  danh mục toàn không gian làm việc (STAC + DuckDB).
- **Ứng dụng web**: cây dự án, bản đồ hiển thị hàng triệu điểm, chuỗi thời gian, so sánh sản phẩm, ảnh bản đồ,
  giám sát (lần chụp Sentinel-1 sắp tới, lần chạy theo lịch, cảnh báo biến dạng), phân vùng nguy cơ.
- **Phân vùng nguy cơ có xét lượng mưa**: xác định mức nguy cơ sụt lún và trượt lở chậm từ cường độ InSAR, góc
  biến dạng hoặc độ dốc, cùng liên hệ mưa – biến dạng đã kiểm định (CHIRPS v3). Phương pháp, nguồn và kế hoạch nghiên cứu xem ở
  [docs/vi/research/rainfall-insar-hazard.md](docs/vi/research/rainfall-insar-hazard.md).

## Cài đặt

```
conda create -n geoeyes python=3.11 gdal rasterio geopandas -c conda-forge
conda activate geoeyes
pip install -e .[era5,web,dev]
copy .env.example .env      # rồi đặt GEOEYES_WORKSPACE (và EARTHDATA_TOKEN nếu dùng Sentinel-1)
```

## Sử dụng

Mỗi dự án là một thư mục `<workspace>/projects/<name>/` có tệp `project.toml` (preset cảm biến + các giá trị ghi đè).
Cách khai báo dự án và chỗ đặt dữ liệu thô: [docs/vi/guide/projects-and-data.md](docs/vi/guide/projects-and-data.md).

```
geoeyes check  <project>        # kiểm tra môi trường và cấu hình
geoeyes plan   <project>        # xem sẽ chạy gì: dữ liệu mới, tham số đã đổi, pha nào đã cập nhật
geoeyes run    <project>        # acquire -> build_stack -> [phase_linking] -> ps -> build_product -> export -> report
geoeyes status <project>
geoeyes report <project>        # dựng lại báo cáo PDF cho sản phẩm mới nhất
geoeyes cr-report <project>     # nhận dạng gương phản xạ góc (Sentinel-1)
geoeyes hazard <project>        # phân vùng nguy cơ có xét lượng mưa cho sản phẩm mới nhất (--set cell_m=50 ...)
geoeyes gnss   <project>        # so sánh với trạm GNSS của NGL; hiệu chỉnh theo GNSS (--set radius_m=200 ...)
geoeyes catalog search --bbox W,S,E,N    # tìm sản phẩm của mọi dự án trong một khu vực
geoeyes serve --open            # mở ứng dụng web tại http://localhost:8765
```

Một pha chỉ chạy lại khi đầu vào hoặc tham số của nó thay đổi. Lần chụp mới được nối thêm vào chồng ảnh, không dựng lại từ đầu
(trừ khi đổi ngày tham chiếu thì dựng lại toàn bộ).

## Cấu trúc

| Đường dẫn | Nội dung |
|---|---|
| `src/geoeyes/` | gói chính: `config`, `controller`, `sensors`, `geometry`, `processing`, `products`, `export`, `report`, `validation`, `catalog`, `ancillary`, `api` (back end web), `io`, `workspace`, `cli` |
| `tests/unit` | test nhanh (`pytest tests/unit`) |
| `tests/parity` | so sánh từng bước engine PS với các lần chạy StaMPS cũ (cần có đầu ra cũ) |
| `tests/golden` | chạy trọn quy trình rồi đối chiếu với kết quả tham chiếu đã lưu (cần `GEOEYES_TEST_DATA`) |
| `docs/guide` | hướng dẫn sử dụng: khai báo dự án và dữ liệu |
| `docs/research` | ghi chú nghiên cứu: phương pháp, nguồn, kế hoạch (phân vùng nguy cơ từ mưa và InSAR; kiểm định và hiệu chỉnh theo GNSS) |
| `docs/architecture` | kiến trúc, quyết định kiến trúc (ADR), bảng chuyển đổi tệp |
| `docs/en/refactor/TODO.md` | kế hoạch và tiến độ tái cấu trúc; `webapp-plan.md`: ứng dụng web |
| `webapp/` | front end ứng dụng web (React + TypeScript), build ra `src/geoeyes/api/static`; chạy bằng `geoeyes serve` |

Sản phẩm dùng tiếng Anh (ADR-015). Giấy phép do chủ dự án quyết định sau (ADR-019).
