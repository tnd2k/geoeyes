> Bản dịch tiếng Việt của [`docs/en/architecture/ARCHITECTURE.md`](../../en/architecture/ARCHITECTURE.md) (bản gốc tiếng Anh là bản chuẩn, ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.

# GeoEyes — Kiến trúc mục tiêu

> Trạng thái: **Thiết kế v0.1 (2026-10-21)** — chưa triển khai.
> Tài liệu liên quan: [`decisions.md`](decisions.md) (ADR) · [`migration-map.md`](migration-map.md) (tệp cũ → mới) · [`../refactor/TODO.md`](../refactor/TODO.md) (tiến độ).
>
> Tài liệu này mô tả **đích đến**. Mỗi lần tái cấu trúc phải đưa mã về đúng vị trí và đúng hợp đồng (giao diện) nêu ở đây. Nếu thực tế buộc phải làm khác, hãy cập nhật tài liệu này và thêm một bản ghi quyết định kiến trúc (ADR) trước, rồi mới sửa mã.

---

## Mục lục

1. [Mục tiêu & phạm vi](#1-mục-tiêu--phạm-vi)
2. [Tóm tắt hiện trạng](#2-tóm-tắt-hiện-trạng)
3. [Nguyên tắc kiến trúc](#3-nguyên-tắc-kiến-trúc)
4. [Cấu trúc repo & package](#4-cấu-trúc-repo--package)
5. [Mô hình miền](#5-mô-hình-miền)
6. [Controller — Bộ điều khiển pha xử lý](#6-controller--bộ-điều-khiển-pha-xử-lý)
7. [Cảm biến](#7-cảm-biến)
8. [Processing — chuỗi xử lý lõi](#8-processing--chuỗi-xử-lý-lõi)
9. [Hậu xử lý](#9-hậu-xử-lý)
10. [Lưu trữ: định dạng & lược đồ](#10-lưu-trữ-định-dạng--lược-đồ)
11. [Không gian làm việc, lưu trữ dài hạn & truy xuất](#11-không-gian-làm-việc-lưu-trữ-dài-hạn--truy-xuất)
12. [Ghi log & khả năng quan sát](#12-ghi-log--khả-năng-quan-sát)
13. [Báo cáo khoa học (PDF)](#13-báo-cáo-khoa-học-pdf)
14. [Cấu hình](#14-cấu-hình)
15. [Ứng dụng: CLI, QGIS](#15-ứng-dụng-cli-qgis-bỏ-gui-webapp-xây-dựng-lại-sau)
16. [Kiểm thử & chất lượng](#16-kiểm-thử--chất-lượng)
17. [Phụ thuộc](#17-phụ-thuộc)
18. [Sẵn sàng cho AI](#18-sẵn-sàng-cho-ai)
19. [Lộ trình chuyển đổi](#19-lộ-trình-chuyển-đổi)
20. [Thuật ngữ](#20-thuật-ngữ)

---

## 1. Mục tiêu & phạm vi

**GeoEyes** là hệ thống xử lý chuỗi thời gian InSAR khép kín (PSI / SBAS / PS-DS): đi từ ảnh SAR thô đến sản phẩm biến dạng đã kiểm soát chất lượng, rồi lưu trữ dài hạn và lập báo cáo khoa học.

### Mục tiêu

| # | Mục tiêu | Thước đo |
|---|---|---|
| G1 | Một package `geoeyes` duy nhất, phân lớp rõ, không dùng mẹo `sys.path` | 0 lệnh `sys.path.insert/append`; `import-linter` kiểm tra phụ thuộc giữa các lớp |
| G2 | Mỗi thuật toán một bản triển khai; khác biệt cảm biến nằm trong `SensorProfile` | Hết tệp trùng lặp theo cảm biến (`flow.py` ×4, `synth_sbas_pairs.py` ×3, tomo ×2…) |
| G3 | Đọc thẳng định dạng gốc của cảm biến, không bắt buộc SNAP GPT | Mặc định backend `native`; `snap` chỉ là backend chuyển tiếp |
| G4 | Định dạng lưu trữ hiện đại, có lược đồ, tự mô tả | Zarr / HDF5 có lược đồ / GeoParquet / COG / STAC; hết `.h5` giả danh `.mat` |
| G5 | Lưu trữ dài hạn, truy xuất theo không gian/thời gian/thuộc tính | Danh mục STAC + chỉ mục DuckDB; sản phẩm bất biến, có checksum |
| G6 | Tái lập được | Mỗi sản phẩm có manifest: đầu vào, tham số, phiên bản mã, hash |
| G7 | Báo cáo PDF có hàm lượng khoa học, người ngoài đọc hiểu được quy trình & kết quả | Cấu trúc báo cáo §13 |
| G8 | Log đầy đủ, có cấu trúc | Thư viện không `print`; mỗi lần chạy một log JSONL |

### Các cảm biến bắt buộc

Sentinel-1 (TOPS IW) · COSMO-SkyMed (Stripmap/Spotlight, CSG) · **ALOS-PALSAR** (băng L; ALOS-2 trước, ALOS-4/ALOS-1 sau — ADR-013) · Capella (Spotlight/Stripmap) · TerraSAR-X/TanDEM-X.

Ngôn ngữ của mã nguồn, log, tài liệu và báo cáo: **tiếng Anh** (ADR-015).

### Ngoài phạm vi (đã loại bỏ)

- Xuất bản lên PostGIS / GeoServer (`to_postgis`, `to_geoserver`, `_publish_*`, `publish_status.json`, `dbschema`, `map_id`) — ADR-007.
- Thông báo qua Teams / Telegram / SMTP / webhook (`modules/ops/notify.py`) — ADR-008. Thay bằng ghi log đầy đủ.
- Mọi nhãn `vinsar`, `VINSAR_*` và tên tổ chức cũ — ADR-001.

---

## 2. Tóm tắt hiện trạng

Phần này chỉ nêu những điểm ảnh hưởng đến thiết kế (chi tiết từng tệp: [`migration-map.md`](migration-map.md)).

| Lĩnh vực | Hiện trạng | Hệ quả thiết kế |
|---|---|---|
| Điều phối | `vinsar.py` ~700 dòng gói trong một hàm; các giai đoạn nối cứng bằng `if control[...]`; phase linking chen vào giữa snap2stamps bằng cách **tạm ghi đè `control.json` + bản sao lưu** | Cần một DAG pha đúng nghĩa (§6) |
| Tiền xử lý | `modules/snap2stamps/{s1,tsx,csk,capella}`: gọi `gpt` qua tiến trình con, dùng graph XML có thay placeholder; dữ liệu trung gian BEAM-DIMAP (`process/` ~70 GB mỗi dự án) | Backend `stack` có 2 engine: `snap` (tạm thời) và `native` (§8.3) |
| Đọc dữ liệu gốc | Đã có nhưng rải rác: annotation XML của TSX, thuộc tính HDF5 của CSK (h5py), JSON mở rộng của Capella, burst S1 (stsa); 4 bộ nội suy quỹ đạo khác nhau | Gom về `sensors/*` + `geometry/orbit` (§7, §8.3) |
| Capella | Quy trình SNAP+StaMPS trong `snap2stamps/capella` (TC **trước** IFG); quy trình PS tham chiếu đơn `modules/ps_stack` (GUI `tools/ps_stack_gui.py`) chạy trên ảnh đã đồng đăng ký trong hình học radar; công cụ khảo sát `tools/capella_ifg_gui.py` | `ps_stack` → `processing/ps_lite` = quy trình Capella (ADR-020); bỏ GUI (ADR-022) |
| Chuyển giao → StaMPS | `stamps_prep.py`: `rslc/diff0/geo` kiểu GAMMA + `pscands.1.*` big-endian + các tệp nhị phân `selpsc_patch`, `calamp`… | Thay bằng `selection/` đọc thẳng từ StackStore (§8.5) |
| Engine StaMPS | 4 × `flow.py` (10–17 nghìn dòng); capella↔csk lệch nhau 71 dòng (rho, nhiễu weed, diag); s1↔capella/csk lệch ~2400 dòng (lọc trước giải chập pha, trọng số amb, bố cục IW); tsx là nhánh cũ, thiếu SBAS/bước 8; `sbas_mintpy_mixin.py` không nơi nào import | Một engine `processing/ps` hợp nhất **s1 + csk**, khác biệt chuyển thành tham số (§8.6); Capella tách khỏi StaMPS (ADR-020) |
| Phase linking / DS | `phase_linking/{s1,csk,capella}` (csk ≈ bản sao của s1), `python/s1/vsar`, `python/{s1,capella}/tomo` (tệp nhị phân giống hệt từng byte) ; **ghi đè RSLC tại chỗ + `.rslc.bak`** | Một package `processing/phase_linking` duy nhất, ghi kết quả thành biến mới trong chồng ảnh (§8.4) |
| Hậu xử lý | `phasingpy.py` 9039 dòng, `StaMPSEXE` ~110 phương thức; chọn backend qua biến môi trường `INSAR_ITYPE` ngay lúc import | Tách theo miền (§9) |
| Trạng thái | `control/<p>/config.json` giữ `current_result`, bị ghi từ nhiều nơi | Thay bằng manifest + trạng thái không gian làm việc (§10.6) |
| Ghi log | ~4600 lệnh `print`; tee stdout ở 3 chỗ khác nhau; 12 tệp dùng `logging` | Ghi log tập trung (§12) |
| Báo cáo | ReportLab, thiên về vận hành (các cổng G0–G6, quy trình vận hành cũ) | Báo cáo khoa học (§13) |

---

## 3. Nguyên tắc kiến trúc

1. **Phân lớp một chiều.** Lớp trên chỉ import lớp dưới, không bao giờ ngược lại (§4.2). Có kiểm tra tự động.
2. **Thuật toán không biết đến tệp.** Hàm xử lý nhận và trả về đối tượng trong bộ nhớ (`xarray.Dataset`, `numpy`, `PointSet`…). Chỉ `io/` biết định dạng tệp. Pha (phase) là chỗ nối thuật toán với kho lưu trữ (store).
3. **Khác biệt cảm biến là dữ liệu, không phải nhánh mã.** Cấm viết `if itype == 3` ngoài `sensors/`. Thuật toán lấy tham số từ `SensorProfile` / cấu hình.
4. **Bất biến & có phiên bản.** Không bao giờ sửa tại chỗ dữ liệu thô hay sản phẩm. Mỗi lần chạy lại sinh một phiên bản mới. Không có `.bak`.
5. **Tái lập được.** Mỗi artifact có manifest: đầu vào (hash), tham số (hash), phiên bản mã, môi trường.
6. **Chạy tiếp dựa vào artifact, không dựa vào cờ.** Một pha coi là xong khi artifact đầu ra đã có và hash đầu vào khớp.
7. **Cấu hình chỉ có một nguồn chuẩn.** `project.toml` (người dùng viết) → kiểm tra theo lược đồ → một đối tượng `ProjectConfig` bất biến truyền xuống các tầng dưới. Không module nào tự đọc tệp cấu hình.
8. **Thư viện không `print`, không `sys.exit`, không tự đọc biến môi trường.** Dùng `logging`, ném ngoại lệ có kiểu, nhận thiết lập qua tham số.
9. **GPU là tuỳ chọn.** Kernel nào cũng có đường chạy CPU; chọn GPU qua `core.compute` (§8.9).
10. **Dùng chung một bộ thuật ngữ.** `reference/secondary` (không dùng `master/slave`), `track`, `stack`, `pair`, `epoch` (§20).

---

## 4. Cấu trúc repo & package

### 4.1 Cây thư mục

```
geoeyes/                                  (gốc repo)
├─ pyproject.toml                         package, extras, ruff, pytest, import-linter
├─ README.md · CHANGELOG.md · LICENSE
├─ src/geoeyes/
│  ├─ __init__.py · _version.py
│  │
│  ├─ core/                               ── Lớp 0: không phụ thuộc phần nào khác của geoeyes
│  │  ├─ logging.py                       cấu hình logging, ngữ cảnh (run_id, phase, track, tile)
│  │  ├─ errors.py                        GeoEyesError, ConfigError, DataError, PhaseError…
│  │  ├─ types.py                         Epoch, BBox, OrbitDirection, LookSide, TrackId, PointId
│  │  ├─ units.py · timeutil.py           datenum/ordinal ↔ datetime, mm/rad/m
│  │  ├─ geodesy.py                       ellipsoid WGS84, ECEF↔LLH, ENU, geoid
│  │  ├─ compute.py                       chọn backend numpy/cupy, thiết bị, worker pool
│  │  └─ hashing.py                       hash tệp/mảng/tham số cho manifest
│  │
│  ├─ config/                             ── Lớp 1
│  │  ├─ schema.py                        các model pydantic: ProjectConfig và các mục của nó
│  │  ├─ loader.py                        đọc project.toml + preset + giá trị ghi đè (theo dải con)
│  │  ├─ settings.py                      biến môi trường GEOEYES_* (pydantic-settings)
│  │  ├─ presets/{sentinel1,cosmo_skymed,alos,capella}.toml
│  │  └─ migrate.py                       in.json + control.json (cũ) → project.toml
│  │
│  ├─ io/                                 ── Lớp 1: nơi DUY NHẤT biết định dạng tệp
│  │  ├─ stack.py                         StackStore (Zarr)
│  │  ├─ state.py                         StateStore (HDF5 có lược đồ)
│  │  ├─ points.py                        PointStore (GeoParquet) + TimeSeriesStore
│  │  ├─ raster.py                        RasterStore (COG)
│  │  ├─ manifest.py                      đọc/ghi Manifest, ghi nguyên tử
│  │  ├─ stac.py                          STAC Item/Collection
│  │  ├─ iso19139.py                      XML ISO 19115/19139 (từ metadata_writer)
│  │  ├─ fs.py                            fsspec: cục bộ / S3 / MinIO
│  │  └─ legacy/                          ĐỌC định dạng cũ (chỉ để chuyển đổi & so sánh)
│  │     ├─ dimap.py · envi.py            BEAM-DIMAP, ENVI .img/.hdr
│  │     ├─ gamma.py                      .rslc/.diff/.base/.par (big-endian)
│  │     ├─ stamps_mat.py                 .mat & .h5 giả danh .mat (từ mat_io)
│  │     ├─ stamps_layout.py              INSAR_*_vN/{input,raw,process,output}
│  │     └─ convert.py                    định dạng cũ → định dạng mới
│  │
│  ├─ workspace/                          ── Lớp 1
│  │  ├─ layout.py                        các đường dẫn chuẩn trong không gian làm việc (§11.1)
│  │  ├─ project.py                       Project = cấu hình + bố cục + trạng thái
│  │  └─ lock.py                          khoá chạy theo dự án/vệt quỹ đạo
│  │
│  ├─ geometry/                           ── Lớp 2: hình học SAR thuần (lõi của engine native)
│  │  ├─ orbit.py                         StateVectors, nội suy Hermite/Lagrange, zero-Doppler
│  │  ├─ dem.py                           tải/cache/cắt DEM (SRTM, Copernicus GLO-30), geoid
│  │  ├─ rdr2geo.py · geo2rdr.py          range-Doppler thuận/nghịch
│  │  ├─ baseline.py                      Bperp, Bpar, HoA, độ kết hợp mô hình hoá
│  │  ├─ lut.py                           LUT mã hoá địa lý (lat/lon/hgt/inc/heading cho từng pixel)
│  │  └─ los.py                           vector LOS, phép chiếu ENU↔LOS (từ cr_los, gnss_los_compare)
│  │
│  ├─ sensors/                            ── Lớp 2
│  │  ├─ base.py                          SensorProfile, SceneMetadata, AcquisitionMode
│  │  ├─ registry.py                      get_sensor("sentinel1"), detect_sensor(path)
│  │  ├─ sentinel1/   safe.py annotation.py bursts.py orbits.py search.py profile.py
│  │  ├─ cosmo_skymed/ hdf5.py archive.py profile.py
│  │  ├─ alos/        ceos.py profile.py          (ALOS-2 PALSAR-2 L1.1 trước; ALOS-4, ALOS-1 dạng plug-in)
│  │  ├─ capella/     slc.py stac.py profile.py
│  │  └─ terrasar_x/  annotation.py cosar.py profile.py
│  │
│  ├─ processing/                         ── Lớp 3: chuỗi xử lý lõi
│  │  ├─ acquire/      search.py download.py ingest.py archive_index.py
│  │  ├─ network/      reference.py pairs.py
│  │  ├─ stack/
│  │  │  ├─ engine.py                     protocol StackEngine
│  │  │  ├─ native/   coregister.py resample.py tops.py interferogram.py coherence.py multilook.py filters.py
│  │  │  └─ snap/     gpt.py graphs/*.xml importer.py      (backend chuyển tiếp, sẽ bị xoá)
│  │  ├─ phase_linking/ shp.py estimators.py filters.py ds.py runner.py
│  │  ├─ selection/   amplitude.py candidates.py masks.py tiles.py
│  │  ├─ ps/                              engine StaMPS hợp nhất
│  │  │  ├─ params.py state.py driver.py merge.py plotting.py
│  │  │  ├─ steps/ s1_load.py s2_gamma.py s3_select.py s4_weed.py s5_correct.py
│  │  │  │         s6_unwrap.py s7_scla.py s8_scn.py
│  │  │  └─ sbas.py closure.py
│  │  ├─ ps_lite/     geometry.py candidates.py unwrap.py invert.py runner.py   (quy trình Capella, từ modules/ps_stack — ADR-020)
│  │  ├─ unwrap/      irls.py grid.py triangulation.py components.py
│  │  ├─ atmosphere/  era5/ gacos/ linear.py tca.py
│  │  ├─ inversion/   sbas.py temporal.py l1regls.py velocity.py
│  │  └─ masking/     water.py model.py      (U-Net phân loại nước)
│  │
│  ├─ postprocess/                        ── Lớp 4 (từ phasingpy.py)
│  │  ├─ pointset.py                      PointSet: thuộc tính + chuỗi thời gian trong bộ nhớ
│  │  ├─ timeseries/  smoothing.py seasonal.py decomposition.py kalman.py velocity.py
│  │  ├─ quality/     dem_error.py geolocation.py residuals.py outliers.py sigsolv.py
│  │  ├─ geometry/    decompose3d.py merge_subswath.py overlap.py
│  │  ├─ reference.py                     điểm tham chiếu, đặt mốc 0
│  │  └─ alerts.py                        cảnh báo biến dạng (từ ops/alerts + _apply_alert_levels)
│  │
│  ├─ hazard/                             ── Lớp 4: phân vùng nguy cơ có xét lượng mưa (ADR-024)
│  │  ├─ coupling.py terrain.py zoning.py assess.py   → <project>/analyses/hazard/<product_id>/
│  │
│  ├─ validation/                         ── Lớp 4: kiểm chứng bên ngoài (gnss/: so sánh và hiệu chỉnh theo NGL, ADR-025)
│  │  ├─ gnss/        compare.py sources.py     (crlink, gnss_los_compare)
│  │  └─ corner_reflector/ detection.py pta.py rcs.py measure.py report.py
│  │
│  ├─ products/                           ── Lớp 5
│  │  ├─ schema.py                        các cột chuẩn của PointProduct (§10.4)
│  │  ├─ metrics.py                       QualityMetrics (cho báo cáo & danh mục)
│  │  └─ builder.py                       PointSet + raster + siêu dữ liệu → Product bất biến
│  │
│  ├─ export/                             ── Lớp 5: các định dạng dẫn xuất
│  │  ├─ vector.py (GPKG/SHP/CSV) · styles.py (QML/SLD) · las.py · heatmap.py
│  │
│  ├─ catalog/                            ── Lớp 5: lưu trữ dài hạn & truy xuất
│  │  ├─ stac_catalog.py index.py query.py archive.py retention.py
│  │
│  ├─ report/                             ── Lớp 5
│  │  ├─ collect.py figures/ templates/ render.py
│  │
│  ├─ controller/                         ── Lớp 6
│  │  ├─ phase.py artifacts.py planner.py pipelines.py runner.py
│  │  ├─ guard.py history.py progress.py preflight.py scaffold.py schedule.py benchmark.py
│  │  └─ phases/   (bộ điều hợp Phase cho từng bước, §6.4)
│  │
│  └─ cli/                                ── Lớp 7
│     └─ main.py                          `geoeyes ...` (§15.1)
│
├─ apps/                                  ── Lớp 7: các ứng dụng nằm ngoài package lõi
│  └─ qgis/   ps_plotter/ ts_decompose/    (bỏ GUI desktop; webapp xây dựng lại sau — ADR-022)
├─ LICENSE                                giấy phép GeoEyes (ADR-019)
├─ third_party/                            mã nguồn đưa kèm (vendored), giữ LICENSE gốc
│  └─ appsigsolv/                          appsigsolv 0.1.0   (Triangle được thay bằng scipy Delaunay)
├─ tests/ unit/ golden/ contract/ fixtures/
├─ docs/  architecture/ refactor/ user/ science/
├─ scripts/  bootstrap.ps1 bootstrap.sh check_quality.ps1
└─ notebooks/
```

Dữ liệu (`data/ process/ results/ logs/ .cache/ control/`) **không còn** nằm trong repo mà chuyển sang không gian làm việc (§11).

### 4.2 Quy tắc phụ thuộc giữa các lớp

```
 7  cli · apps(qgis; webapp trong tương lai)
 6  controller
 5  products · export · catalog · report
 4  postprocess · validation
 3  processing
 2  geometry · sensors
 1  config · io · workspace
 0  core
```

- Lớp N chỉ import các lớp < N. Trong cùng một lớp: chỉ import khi không sinh vòng phụ thuộc.
- `apps/*` (và webapp sau này) chỉ dùng API công khai: `geoeyes.controller`, `geoeyes.catalog`, `geoeyes.io`, `geoeyes.report`, `geoeyes.config`.
- `processing` **không** import `postprocess`; `postprocess` **không** import `controller`.
- CI kiểm tra bằng `import-linter` (hợp đồng “layers”).

---

## 5. Mô hình miền

```
Project ─┬─ ProjectConfig
         ├─ Track* ──── Scene* (thô, bất biến)
         │     └─ Stack* ── Network(reference, pairs)
         │            ├─ SLC stack (đã đồng đăng ký)    ┐
         │            ├─ IFG stack + độ kết hợp         │ StackStore (Zarr)
         │            ├─ Linked phase (tuỳ chọn)        │
         │            ├─ Geometry (lat/lon/hgt/inc/LUT)┘
         │            └─ PsRun* ── PsState (HDF5) ── tiles
         └─ Product* (bất biến, có phiên bản) ── PointSet + Rasters + Metadata + Report
Run* ── PhaseRecord* ── Artifact*
```

| Đối tượng | Định nghĩa | Định danh |
|---|---|---|
| `Project` | Một vùng nghiên cứu (AOI) + cấu hình | `project` (slug `[a-z0-9_-]{1,64}`) |
| `Track` | Một hình học quan sát cố định: cảm biến + chiều quỹ đạo + quỹ đạo tương đối (+ frame) | `s1-desc-018`, `csk-asc-xxx`, `alos2-asc-148` |
| `Scene` | Một ảnh SLC gốc (một epoch) | `track_id/20240626` + ID sản phẩm gốc |
| `Stack` | Các cảnh của một vệt quỹ đạo (với S1 là một dải con), đã đồng đăng ký về một ảnh tham chiếu | `stack_id = <track>[-<iw>]-<ref_date>-<hash6>` |
| `Network` | Ảnh tham chiếu + danh sách cặp ảnh (PSI tham chiếu đơn, SBAS, dư thừa) | nằm trong stack |
| `PsRun` | Một lần chạy engine PS/SBAS trên một stack với một bộ tham số | `psrun_id` |
| `PointSet` | Tập các điểm đo (PS/DS) + chuỗi thời gian, trong bộ nhớ | — |
| `Product` | Kết quả cuối cùng, **bất biến**, có phiên bản | `<project>_<track>_<method>_<first>_<last>_v<N>` |
| `Run` | Một lần gọi bộ điều khiển | `run_id = YYYYMMDDTHHMMSS-<rand4>` |
| `Artifact` | Bất kỳ đầu ra nào của một pha, kèm loại + đường dẫn + hash | `ArtifactRef(kind, uri, sha256)` |

Ánh xạ từ khái niệm cũ: dự án con `<name>_ASC/_DESC` → `Track`; `INSAR_<date>_NORMAL_vN` → `Stack` + `PsRun` + `Product`; `current_result` → `workspace state` (sản phẩm mới nhất theo từng vệt quỹ đạo, §10.6); `PATCH_n` → `tile`.

---

## 6. Controller — Bộ điều khiển pha xử lý

Thay cho `vinsar.py`. Bộ điều khiển **không chứa thuật toán**; nó chỉ lập kế hoạch, canh giữ, thực thi và ghi nhận.

### 6.1 Hợp đồng `Phase`

```python
class ArtifactKind(StrEnum):
    RAW_SCENES = "raw_scenes"; NETWORK = "network"
    SLC_STACK = "slc_stack"; IFG_STACK = "ifg_stack"; GEOMETRY = "geometry"
    LINKED_STACK = "linked_stack"; CANDIDATES = "candidates"
    PS_STATE = "ps_state"; UNWRAPPED = "unwrapped"; APS = "aps"; TIMESERIES = "timeseries"
    POINTSET = "pointset"; WATER_MASK = "water_mask"
    PRODUCT = "product"; REPORT = "report"; EXPORT = "export"

@dataclass(frozen=True)
class PhaseContext:
    project: Project          # cấu hình + bố cục
    track: Track | None       # None với các pha cấp dự án (decompose_3d, report)
    run: RunRecord            # run_id, logger, tiến độ
    inputs: Mapping[ArtifactKind, ArtifactRef]

class Phase(Protocol):
    name: ClassVar[str]
    scope: ClassVar[Literal["track", "project"]]
    requires: ClassVar[tuple[ArtifactKind, ...]]
    produces: ClassVar[tuple[ArtifactKind, ...]]
    def enabled(self, cfg: ProjectConfig) -> bool: ...
    def fingerprint(self, ctx: PhaseContext) -> str: ...      # hash(hash đầu vào + tham số liên quan + phiên bản pha)
    def is_done(self, ctx: PhaseContext) -> bool: ...         # artifact tồn tại & fingerprint khớp
    def run(self, ctx: PhaseContext) -> Mapping[ArtifactKind, ArtifactRef]: ...
```

### 6.2 Danh sách pha chuẩn

| # | Pha | Phạm vi | Yêu cầu | Tạo ra | Thay thế |
|---|---|---|---|---|---|
| 1 | `acquire` | track | — | RAW_SCENES | `_1_download`, CSK `_1_subset` (giải nén), Capella STAC, nạp TSX |
| 2 | `plan_network` | track | RAW_SCENES | NETWORK | `*_master_sel.py` ×4, `synth_sbas_pairs` ×3, `_maybe_filter_pairs_by_extent` |
| 3 | `build_stack` | track | RAW_SCENES, NETWORK | SLC_STACK, GEOMETRY | split/apply-orbit/back-geocoding/ESD/coreg/TC (SNAP); Capella: đồng đăng ký không TC (đầu vào của `ps_stack` hiện tại) |
| 4 | `interferograms` | track | SLC_STACK, GEOMETRY, NETWORK | IFG_STACK | graph `Interferogram`/`TopoPhaseRemoval`, StampsExport |
| 5 | `phase_linking` *(tuỳ chọn)* | track | SLC_STACK, NETWORK | LINKED_STACK | `phase_linking/*`, `vsar`, `tomo` |
| 6 | `water_mask` *(tuỳ chọn)* | track | SLC_STACK, GEOMETRY | WATER_MASK | `masking/processor` |
| 7 | `select_candidates` | track | SLC_STACK/LINKED_STACK, IFG_STACK, GEOMETRY, [WATER_MASK] | CANDIDATES | `stamps_prep`, `prestamps/*`, các tệp nhị phân `selpsc/calamp/psc*` |
| 8 | `ps_estimate` | track | CANDIDATES | PS_STATE | StaMPS bước 1–5 |
| 9 | `unwrap` | track | PS_STATE | UNWRAPPED | bước 6 (lượt 1) |
| 10 | `atmosphere` *(tuỳ chọn)* | track | UNWRAPPED, GEOMETRY | APS | `_ensure_tca_for_tropo_method`, `_aps_linear`, ERA5/GACOS |
| 11 | `invert` | track | UNWRAPPED, [APS] | TIMESERIES | bước 6 lượt 2 (`subtr_tropo`), 7, 8, SBAS/MintPy |
| 12 | `postprocess` | track | TIMESERIES, GEOMETRY, [WATER_MASK] | POINTSET | `phasingpy._process_single_orbit` (dem_err, lonlat_err, làm trơn, thành phần mùa, cảnh báo…) |
| 13 | `validate` *(tuỳ chọn)* | track | POINTSET | POINTSET (+chỉ số) | `crlink`, so sánh GNSS |
| 14 | `merge_subswaths` *(S1)* | track | POINTSET×IW | POINTSET | `_merge_subswath_outputs`, `_merge_overlap_*` |
| 15 | `decompose_3d` *(≥2 vệt quỹ đạo)* | project | POINTSET×track | POINTSET (EW/UD) | `_run_3d_decomposition` |
| 16 | `build_product` | track/project | POINTSET | PRODUCT | `ps_export_gis` (phần “nguồn gốc dữ liệu”), siêu dữ liệu |
| 17 | `report` | project | PRODUCT* + manifest của lần chạy | REPORT | `ops/run_report` |
| — | `export` *(theo yêu cầu)* | product | PRODUCT | EXPORT | phần GPKG/SHP/CSV/QML/LAS của `ps_export_gis` |
| — | `archive` *(theo yêu cầu)* | product | PRODUCT | — | mới (§11) |

Ghi chú:
- Các pha 8–11 là engine StaMPS được bọc lại; ranh giới pha trùng với các điểm “chạy tiếp” vốn có của StaMPS (sau bước 5, sau bước 6, sau bước 8). Trong mỗi pha vẫn có điểm kiểm tra theo từng bước (thay cho `left-off.txt`).
- Khi bật `atmosphere`, lượt 2 của bước 6/7 (`subtr_tropo=y`) thuộc pha `invert` — hết cảnh logic rải rác kiểu “ensure pass1 before step6y”.
- PSDS/ComSAR = `phase_linking` (bộ ước lượng `psds`/`comsar`) + cùng chuỗi 7–11. Bỏ cặp `TomoSARControl` + `PSDS_Prep` riêng.

### 6.3 Các preset quy trình xử lý

`pipelines.py` định nghĩa DAG theo `project.method`:

```
psi    : acquire → plan_network → build_stack → interferograms → [water_mask] → select_candidates
         → ps_estimate → unwrap → [atmosphere] → invert → postprocess → [validate]
         → [merge_subswaths] → build_product → [decompose_3d] → report
sbas   : như psi; plan_network xây dựng mạng đường đáy ngắn; invert dùng SBAS/MintPy
psds   : như psi + phase_linking (bộ ước lượng EMI/EVD/…) trước select_candidates
comsar : như psds với bộ ước lượng comsar
capella: acquire → plan_network → build_stack (hình học radar, không TC) → select_candidates (ps_lite)
         → ps_lite → [phase_linking] [atmosphere] → postprocess → build_product → report   (ADR-020)
```

Pha `ps_lite` (thay các pha 8–11 trong preset `capella`): cần `SLC_STACK`, `GEOMETRY`, `CANDIDATES` → sinh `TIMESERIES`. Thuật toán lấy từ `modules/ps_stack.run_stack`: epoch tham chiếu tách khỏi ảnh master dùng khi đồng đăng ký; pha tham chiếu tính từ DEM; chọn PS theo D_A kết hợp phân tập phổ theo range; giải chập pha IRLS tinh chỉnh hai lượt, có periodogram sai số độ cao; bình phương tối thiểu có trọng số (vận tốc, ΔH, số hạng tham chiếu); APS bằng lọc Gauss không gian; trọng số chất lượng riêng cho từng giao thoa đồ.

Preset theo cảm biến: **Capella → chỉ dùng `capella`** (không qua engine StaMPS — ADR-020); S1, CSK, TSX, ALOS → `psi` / `sbas` / `psds` / `comsar`. Cảm biến khác vẫn bật được ps_lite nếu muốn, nhưng không phải mặc định.

Người dùng bật/tắt pha tuỳ chọn trong mục `[pipeline]` của `project.toml` (thay cho `control.json`). Trước khi chạy, bộ lập kế hoạch kiểm tra các điều kiện `requires` đã đủ chưa và báo lỗi rõ ràng (thay cho `validate_control`).

### 6.4 Runner & guard

```
geoeyes run <project> [--track T] [--from PHASE] [--to PHASE] [--only PHASE] [--force PHASE] [--dry-run]

Runner.run():
  cfg   = config.load(project)                       # kiểm tra lược đồ
  plan  = planner.plan(cfg, from_, to, only)          # DAG đã cắt tỉa, theo từng vệt quỹ đạo
  with guard.acquire(project, tracks):                # khoá + bản ghi lần chạy + ngữ cảnh log
      for phase, track in plan.topological():
          ctx = PhaseContext(...)
          if not force and phase.is_done(ctx): record SKIPPED; continue
          with run.phase(phase.name, track):          # tệp log + tiến độ + thời gian + chỉ số
              refs = phase.run(ctx)
          manifest.record(phase, refs, fingerprint)
  report phase (nếu có trong kế hoạch) · history.finish(status)
```

- `--publish-only` cũ → bỏ (chức năng xuất bản đã bỏ). `--start-step N` cũ → `--from unwrap|invert|…`; riêng `ps_estimate` có `--ps-step` để gỡ lỗi.
- Khoá: `workspace/<project>/.state/locks/<track>.lock` (từ `ops/lock.py`).
- Các pha chạy **chung một tiến trình**; pha nặng tự dùng worker pool của `core.compute`. Webapp gọi `geoeyes run` thành tiến trình con tách rời (giữ mô hình `job_launcher` hiện tại).
- Không ghi đè `control.json` khi đang chạy; cấu hình giữ bất biến suốt một lần chạy.

### 6.5 Vận hành (từ `modules/ops`)

| Thành phần | Giữ / thay đổi |
|---|---|
| `lock.py` | → `workspace/lock.py` |
| `run_history.py` | → `controller/history.py` (bản ghi lần chạy = manifest của lần chạy, §10.6) |
| `progress.py` | → `controller/progress.py`; **bỏ** `StdoutWatcher` & hook monkey-patch — tiến độ đọc từ log sự kiện có cấu trúc (§12) |
| `preflight.py` | → `controller/preflight.py` (`geoeyes check`) ; bỏ kiểm tra SNAP khi engine là `native` |
| `validation.py` | → thay bằng lược đồ pydantic + bộ lập kế hoạch |
| `scaffold.py` | → `controller/scaffold.py` (`geoeyes init`) |
| `schedule.py` | → `controller/schedule.py` (giữ lại: chạy lại định kỳ, tên tác vụ `GeoEyes_<project>`) |
| `benchmark.py` | → `controller/benchmark.py` |
| `health.py` | → `products/metrics.py` (tính chỉ số chất lượng **ngay trong** quy trình xử lý, không đọc lại `.mat`) |
| `alerts.py` | → `postprocess/alerts.py` (quy tắc) + `catalog/query.py` (so sánh phiên bản) |
| `log_rotation.py`, `logpaths.py` | → `core/logging.py` + `catalog/retention.py` |
| `notify.py` | **Xoá** (ADR-008) |
| `run_report.py` | → `report/` (thiết kế lại, §13) |

---

## 7. Cảm biến

### 7.1 Hợp đồng

```python
class AcquisitionMode(StrEnum): TOPS = "tops"; STRIPMAP = "stripmap"; SPOTLIGHT = "spotlight"; SLIDING_SPOTLIGHT = "sliding_spotlight"

@dataclass(frozen=True)
class SceneMetadata:
    sensor: str; platform: str; mode: AcquisitionMode; polarization: str
    start: datetime; stop: datetime; direction: OrbitDirection; look_side: LookSide
    relative_orbit: int | None; frame: int | None
    wavelength_m: float; range_pixel_m: float; azimuth_pixel_m: float
    prf_hz: float; range_sampling_hz: float; near_range_m: float
    azimuth_time_interval_s: float; doppler_centroid: Poly2D; fm_rate: Poly2D | None
    state_vectors: StateVectors; footprint: Polygon
    bursts: tuple[Burst, ...] | None          # chỉ với TOPS
    calibration: CalibrationLUT | None
    source_uri: str; source_id: str

class SensorReader(Protocol):
    def detect(self, path: str) -> bool: ...
    def read_metadata(self, path: str) -> SceneMetadata: ...
    def read_slc(self, path: str, window: Window | None = None, burst: int | None = None) -> np.ndarray: ...  # complex64

@dataclass(frozen=True)
class SensorProfile:
    name: str; band: Literal["C","X","L"]; modes: frozenset[AcquisitionMode]
    reader: SensorReader
    defaults: Mapping[str, Any]               # tham số mặc định theo cảm biến (rho, weed, half_win…)
    orbit_source: OrbitSource                 # embedded | precise_download
    archive: ArchiveHandler | None            # giải nén rar/zip/tar
```

### 7.2 Từng cảm biến

| Cảm biến | Định dạng gốc | Bộ đọc | Quỹ đạo | Ghi chú |
|---|---|---|---|---|
| **Sentinel-1** IW SLC | SAFE (.zip): `measurement/*.tiff` CInt16, `annotation/*.xml`, `calibration/*.xml` | `sentinel1/safe.py` đọc qua `/vsizip/` (đã có ví dụ ở `cr_report/s1slc.py`); `bursts.py` thay `stsa` | POEORB/RESORB `.EOF` tải từ Copernicus Data Space; `orbits.py` (thay Apply-Orbit-File) | TOPS: deramp/ESD (§8.3). Tìm và tải từ ASF (`asf_search`) |
| **COSMO-SkyMed** (CSK & CSG) | HDF5 L1A SCS_B/SCS_U; thường đóng gói trong `.rar` | `cosmo_skymed/hdf5.py` (h5py; phần đọc thuộc tính đã có ở `csk/_2_master_sel.py`) ; `archive.py` (UnRAR/7z/bsdtar) | State vector nhúng sẵn (thuộc tính HDF5) | Stripmap/Spotlight. CSG (thế hệ 2) đặt tên thuộc tính khác → bộ đọc tự xử lý |
| **ALOS-PALSAR** (làm sau cùng; xác định thế hệ theo dữ liệu mẫu) | ALOS-1/2: CEOS L1.1 SLC (`LED-*`, `IMG-HH-*`, `TRL-*`, `VOL-*`); ALOS-4: **định dạng L1.1 cần xác minh với JAXA** | `alos/ceos.py` (**mới**), bộ đọc plug-in cho từng thế hệ | Nhúng trong tệp leader | Băng L: ít mất kết hợp trên vùng thực vật; tầng điện ly ảnh hưởng đáng kể → split-spectrum (nguyên mẫu `tools/_split_spectrum_common.py`); ScanSAR chưa thuộc phạm vi ban đầu |
| **Capella** | SLC GeoTIFF CInt16 + `*_extended.json` (STAC) | `capella/slc.py` (từ `bperp_bpar_from_capella_extended_json`, `fdc_hz_from_capella_extended_json`, `_update_doppler_coefficients`; xem thêm `capella_ifg_gui.load_slc/parse_extended_json`) | State vector trong JSON mở rộng | Spotlight độ phân giải cao; tải qua STAC; preset quy trình `capella` (ADR-020); **hình học radar — không TC trước IFG** (ADR-005) |
| **TerraSAR-X / TanDEM-X** | `TSX1_SAR__*` / `TDX1_SAR__*`: annotation XML + COSAR | `terrasar_x/` (bộ phân tích XML đã có ở `tsx/_1_master_sel.py`) | Nhúng sẵn | Giữ **hình học bản đồ** (TC trước IFG) đến khi xác minh xong (ADR-005); dùng engine PS hợp nhất, không kéo theo nhánh `flow.py` cũ |

### 7.3 Khác biệt giữa các cảm biến đã phát hiện → chuyển thành `defaults`

| Tham số | Hiện trạng | Mục tiêu |
|---|---|---|
| `rho` (khoảng cách nghiêng tham chiếu) | capella: `parms['center_range_slc']`, dự phòng 730000; csk: gán cứng 780000 | Tính từ `SceneMetadata.near_range_m` + hình học; bỏ hằng số |
| lượt lọc nhiễu weed | csk tự tắt khi `weed_standard_dev`,`weed_max_noise` ≥ π (capella: luôn bật — nay không còn liên quan) | `defaults.ps.weed.*` trong preset |
| `half_win` của phase linking | capella [5,5]; s1/csk [7,7] | `defaults.phase_linking.half_window` |
| `robust_da` | mặc định cho CSK, Capella | `defaults.selection.robust_da` (CSK); Capella dùng tiêu chí D_A + phân tập phổ của ps_lite |
| lọc goldstein/gaussian trước giải chập pha, trọng số amb | nhánh csk/capella của `flow.py` | Tham số chung `ps.unwrap_grid_filter`, `ps.dem_error_ambiguity` — áp dụng được cho S1/CSK/TSX/ALOS. **Không chuyển Wavelet/FAMM sang, không dùng ở đâu cả** (chủ dự án, 2026-10-24) |
| Engine PS | 4 × `flow.py` + `ps_stack` | Capella → `ps_lite`; các cảm biến còn lại → `ps` (StaMPS) |
| Bố cục IW | s1 có `IW*/raw`; cảm biến khác không có | Stack theo dải con thành khái niệm chung (`Stack.subswath`) |
| NL-InSAR | chỉ csk | Bộ lọc tuỳ chọn trong `phase_linking.filters` |
| Hình học xử lý IFG | TSX, Capella: TC **trước** IFG (hình học bản đồ); S1, CSK: hình học radar | `stack.geometry`: `radar` cho S1, CSK, ALOS, Capella; `map` cho TSX đến khi xác minh xong (ADR-005) |

---

## 8. Processing — chuỗi xử lý lõi

### 8.1 `acquire`

- `search.py`: hợp đồng `SceneSearch.search(aoi, date_range, track) -> list[SceneRef]` — S1 (ASF), Capella (STAC). CSK/ALOS/TSX: chỉ nạp từ kho lưu trữ.
- `download.py`: tải tiếp khi đứt, thử lại, kiểm tra toàn vẹn (`verify_slc_zip_integrity`), giới hạn số cảnh mỗi tháng (`max_per_month`).
- `ingest.py`: đưa cảnh vào `raw/` của không gian làm việc (hoặc chỉ **tham chiếu** tới kho dùng chung, không sao chép).
- `archive_index.py`: chỉ mục kho ảnh thô dùng chung giữa các dự án (thay `ImageryDB` SQLite + `_shared_repo`). Kho lưu **ảnh thô**, không lưu sản phẩm split của SNAP.

### 8.2 `network`

- `reference.py`: **một** thuật toán chọn ảnh tham chiếu (thay 4 phiên bản cũ): cực đại hoá tổng độ kết hợp mô hình hoá (Bperp, Btemp, ΔfDC) — `geometry/baseline.py`. Cho phép cố định ảnh tham chiếu trong cấu hình.
- `pairs.py`: PSI (tham chiếu đơn), SBAS (ngưỡng Bperp/Btemp, Delaunay, k láng giềng gần nhất), cặp dư thừa (từ `synth_sbas_pairs` ×3), lọc theo tỉ lệ phủ AOI (`extent_min_ratio`).
- Đầu ra `NETWORK`: bảng `pairs.parquet` (ref, sec, bperp, btemp, dfdc, coh_model) + `network.json`.

### 8.3 `stack` — engine

```python
class StackEngine(Protocol):
    name: ClassVar[str]                       # "native" | "snap"
    def build(self, scenes, network, aoi, dem, cfg) -> tuple[StackRef, GeometryRef]: ...
    def interferograms(self, stack, geometry, network, cfg) -> StackRef: ...
```

**Engine `native`** (mục tiêu, ADR-006):

| Bước | Module | Ghi chú kỹ thuật |
|---|---|---|
| Quỹ đạo | `geometry/orbit.py` | Hermite bậc ba / Lagrange 8 điểm; quỹ đạo chính xác cho S1 |
| DEM | `geometry/dem.py` | Copernicus GLO-30 (mặc định), SRTM 1″; geoid EGM96/EGM2008 → độ cao ellipsoid; cache theo từng mảnh |
| Hình học tham chiếu | `geometry/rdr2geo.py` | lat/lon/hgt/góc tới/heading cho từng pixel ảnh tham chiếu → `GEOMETRY` |
| Đồng đăng ký hình học | `stack/native/coregister.py` | geo2rdr cho từng ảnh secondary → độ lệch range/azimuth suy từ DEM |
| Tinh chỉnh | `coregister.py` | Stripmap/Spotlight: tương quan chéo biên độ phần dư (không kết hợp); TOPS: **ESD** trên vùng chồng phủ giữa các burst (cần đạt ~0,001 px theo azimuth) |
| Lấy mẫu lại | `stack/native/resample.py` | sinc/Lanczos bảo toàn pha; TOPS: deramp → lấy mẫu lại → reramp |
| TOPS | `stack/native/tops.py` | chọn burst theo AOI, deburst, ghép dải con (tuỳ chọn) |
| Giao thoa đồ | `stack/native/interferogram.py` | `ref × conj(sec)`; trừ pha trái đất phẳng + pha địa hình tính từ hình học; đầu ra là pha **đã khử địa hình** + độ kết hợp |
| Multilook / lọc | `multilook.py`, `filters.py` | Goldstein, boxcar, gaussian (gom từ `unwrap_2d_goldstein`, `_ifg_common`) |
| Độ kết hợp | `coherence.py` | ước lượng theo cửa sổ/thích nghi |

Mã hiện có cần gom về: `modules/ps_stack/stack.py` + `utils/flat_earth.py` (hình học lưới pixel trên DEM, range theo từng epoch, pha tham chiếu — đang dùng trong quy trình Capella), `tools/capella_ifg_gui.py` (để tham khảo: đồng đăng ký bằng tương quan chéo, Lanczos, goldstein), `snap2stamps/capella/bin/_2_coreg_ifg.py` (`PythonTerrainCorrection`, `RangeDopplerGeocoding`, `OpenTopographyDem` — hiện đang “ngủ đông”), `utils/flat_earth.py`, `utils/cr_los.py` (`solve_zero_doppler`), `s1/bin/_2_master_sel.py` (`_interpolate_orbit`, `_zero_doppler_state`).

Kernel: NumPy + **Numba** (CPU), CuPy (GPU tuỳ chọn) qua `core/compute.py`. Xử lý theo khối (chunk Zarr) để không bị giới hạn bởi bộ nhớ.

**Engine `snap`** (chuyển tiếp): bọc các graph hiện có; gpt chạy xong thì `importer.py` đọc BEAM-DIMAP rồi ghi vào StackStore. Nhờ vậy, mọi bước phía sau dùng định dạng mới ngay từ đầu, và so sánh được native ↔ snap trên cùng một định dạng. Engine này sẽ bị xoá khi native đạt các tiêu chí (§16.3).

### 8.4 `phase_linking`

Hợp nhất `modules/phase_linking/*`, `python/s1/vsar/*`, `python/{s1,capella}/tomo/*`, `tools/phase_link_viewer.py` (EVD/EMI/PTA), `tools/_nlinsar_common.py`.

| Module | Nội dung |
|---|---|
| `shp.py` | Kiểm định SHP: KS, AD (`adtest`), BWS (`bwstest`) |
| `estimators.py` | EVD, EMI, MLE, PTA, ADAPTIVE, PSDS, ComSAR (ministack) |
| `filters.py` | NL-InSAR, lọc hậu kỳ gaussian |
| `ds.py` | Chọn DS (BroNum, độ kết hợp — `DSFilter`), trộn PS+DS |
| `runner.py` | Vòng lặp theo tile, CPU/GPU |

Đầu ra: biến `slc_linked` (complex64) + `coh_pl`, `bronum`, `shp_count` ghi vào **chính** StackStore đó. **Không** ghi đè RSLC, không `.bak`, không `.done`.

### 8.5 `selection` (thay `stamps_prep` + `prestamps` + các tệp nhị phân)

- `amplitude.py`: hiệu chỉnh biên độ (`calamp`), D_A, D_A bền vững (Python thuần, thay `calamp.exe`).
- `candidates.py`: chọn ứng viên PS (D_A) / SB (`selsbc`) / DS (từ phase linking), các điểm bắt buộc giữ.
- `masks.py`: AOI, mặt nước (U-Net hoặc mặt nạ tĩnh), vùng loại trừ.
- `tiles.py`: chia tile có chồng phủ (thay `PATCH_n`, `patch.in`, `patch_noover.in`, `_8_find_optimal_patches`).
- Đầu ra `CANDIDATES`: một PointStore (ij, lon, lat, hgt, da, type, …) + chỉ số pixel để engine PS đọc pha từ StackStore. **Hết** `pscands.1.*` big-endian, `*.in`, `width.txt`, `rsc.txt`…

Các tệp nhị phân `selpsc_patch`, `selsbc_patch`, `psclonlat`, `pscdem`, `pscphase`, `calamp` (+ bản trùng trong `capella/tomo`) sẽ bị xoá khi bản Python cho kết quả giống hệt (golden).

### 8.6 `ps` — engine StaMPS hợp nhất

Dùng cho S1, CSK, TSX, ALOS (Capella dùng `ps_lite` — ADR-020). Nguồn: lấy `python/s1/stamps/flow.py` làm **nền** (đầy đủ nhất), đưa các tính năng của nhánh `csk/stamps/flow.py` vào dưới dạng tham số (lọc goldstein trước giải chập pha — không chuyển wavelet/FAMM, trọng số amb, `_build_ifg_coh_grid`, `_regularize_k_ps_spatial`…); không cần đọc thêm `capella/stamps/flow.py` (≈ csk); từ tsx không lấy gì, trừ `_destripe_unwrapped_grid`, `_aps_fill_nan`, `_temporal_irls_phase_gpu` khi cần.

```
ps/
  params.py      Parms (từ prestamps/ps_parms.py): ~120 tham số StaMPS, giữ tên gốc để dễ truy vết
  state.py       PsState: lược đồ biến của từng bước (§10.3), đọc/ghi qua io.state
  steps/
    s1_load.py      ps_load_initial / sb_load_initial          → ps1, ph1, bp1, da1, la1, hgt1, inc1
    s2_gamma.py     ps_est_gamma_quick                          → pm1
    s3_select.py    ps_select                                   → select1
    s4_weed.py      ps_weed                                     → ps2, ph2, pm2, bp2, hgt2, la2, inc2, weed2
    s5_correct.py   ps_correct_phase, calc_ifg_std, ghép tile   → rc2, ifgstd2
    s6_unwrap.py    ps_unwrap (lưới, nội suy, không gian-thời gian, hàm chi phí thống kê, IRLS), sửa mạng SBAS, closure
    s7_scla.py      calc_scla, smooth_scla, setref, deramp, nghịch đảo epoch SBAS, vận tốc
    s8_scn.py       scn_filt
  sbas.py        hàm hỗ trợ SBAS (từ các hàm `_sb_*` + `sbas_mintpy_mixin.py`)
  closure.py     hiệu chỉnh closure-phase kiểu MintPy (`_mintpy_correct_phuw_sb_after_unwrap`, l1regls)
  merge.py       ghép tile (ps_merge_patches)
  driver.py      run(state, steps, cfg) — thay thế `run_normal` + `StaMPSStep.run`
  plotting.py    từ plot_stamps.py (các hình chuẩn — cũng được báo cáo sử dụng)
```

Nguyên tắc:
- Mỗi bước là một **hàm thuần**: `def weed(state: PsState, p: Parms, compute: Compute) -> PsState`.
- Biến lưu đúng **hình dạng tự nhiên** (không `(1,1)`, không `ps['n_ps'][0][0]`). Tên biến giữ như StaMPS để tiện đối chiếu với tài liệu khoa học.
- Điểm kiểm tra theo từng bước nằm trong `PsState` (thay cho `left-off.txt`, `no_ps_info`, `psver`).
- Bỏ datenum của MATLAB: ngày lưu dạng `datetime64[D]` (nhờ đó hết lẫn lộn ordinal với datenum trong `phasingpy._d_column_labels_from_ts_day_array`).
- Tam giác hoá: `unwrap/triangulation.py` dùng `scipy.spatial.Delaunay` (lấy cạnh từ `simplices`), thay tệp nhị phân Triangle (ADR-019). Đã kiểm tra trên dữ liệu golden: mạng cạnh tương đương → kết quả giải chập pha nằm trong dung sai.

### 8.7 `unwrap`, `atmosphere`, `inversion`

| Package | Nguồn | Ghi chú |
|---|---|---|
| `unwrap/irls.py` | `irls_solver.py` + `irls_solver_capella.py` | gộp thành một bộ giải có tuỳ chọn |
| `unwrap/grid.py` | `utils/unwrap_grid.py` | |
| *(đã bỏ)* | `unwrap_2d_pipeline.py` + `_da/_gaussian/_geotiff/_plot/_gis_export` | quy trình 2D riêng cho Capella, nay không cần nữa (ADR-020); `_goldstein` → `stack/native/filters.py`, `_coherence` → `stack/native/coherence.py` |
| `atmosphere/era5/`, `gacos/` | `meteo/aps_era5`, `aps_gacos` | ghi APS thẳng vào PsState, không qua `tca*.mat`; thời điểm chụp lấy từ `SceneMetadata` (bỏ `capella_time.py`, `csk_time.py`) |
| `atmosphere/linear.py` | `_aps_linear` | |
| `inversion/` | `sbas_inversion`, `sbas_temporal`, `mintpy_l1regls` (viết lại sạch), `step7_velocity`, `mintpy_flow` | xem giấy phép §17 |

### 8.8 `masking`

`masking/model.py` (U-Net), `water.py` (dự đoán + mặt nạ tĩnh). Đây là pha ML đầu tiên, làm khuôn mẫu cho các thành phần AI sau này (§18).

### 8.9 Tính toán & GPU

`core/compute.py`:
```python
@dataclass(frozen=True)
class Compute:
    backend: Literal["numpy", "cupy"]; device: int | None; workers: int; memory_gb: float
    def xp(self): ...            # numpy hoặc cupy
```
- Kernel mảng: NumPy/Numba (CPU) ↔ CuPy (GPU). Torch chỉ dùng cho mô hình ML (U-Net, NL-InSAR) — ADR-014.
- Mục cấu hình `[compute]` thay cho `*_use_gpu`, `phase_linking.use_gpu`, `nlinsar.device`, `clap_gpu_only`, `topofit_gpu_only` (vốn không nơi nào đọc).

---

## 9. Hậu xử lý

Thay cho `phasingpy.py`. Đầu vào: `TIMESERIES` (PsState) + `GEOMETRY`; đầu ra: một `PointSet`. **Giữa các bước không đọc/ghi tệp.**

```python
@dataclass
class PointSet:
    attrs: pd.DataFrame          # 1 dòng / điểm, các cột theo products/schema.py
    dates: np.ndarray            # datetime64[D], T
    disp: np.ndarray             # (N, T) mm, LOS (+ hướng về vệ tinh)
    disp_std: np.ndarray | None
    crs: str = "EPSG:4326"
    meta: dict                   # vệt quỹ đạo, điểm tham chiếu, quy ước dấu, đơn vị
```

| Module | Hàm (nguồn trong `StaMPSEXE`) |
|---|---|
| `timeseries/smoothing.py` | `_hampel_filter`, `_adaptive_savgol`, `_smooth_timeseries_yearly_gaussian`, `_smooth_timeseries_trend_preserving`, `_apply_ts_smooth_candidate`, `_auto_select_ts_smooth` |
| `timeseries/seasonal.py` | `extract_seasonal`, `_fit_annual_seasonal` |
| `timeseries/decomposition.py` | `_ts_update_ts_decomposition`, `update_ts_auto`, `compute_trend_from_result`, `utils/ts_decomposition.py` |
| `timeseries/kalman.py` | `utils/kalman_ts.py` |
| `timeseries/velocity.py` | `_recompute_velocity`, `_compute_fit_rmse`, `_compute_psi_from_phuw`, `_apply_dtr_detrend`, `_apply_omt_refinement` |
| `quality/dem_error.py` | `ps_dem_err`, `_k_ps_uw_per_ps_for_dem`, `_estimate_dem_err_time_domain`, `_evaluate_dem_err_rmse`, `_mask_dem_err_outliers` |
| `quality/geolocation.py` | `ps_lonlat_err`, `_terrain_slope_aspect_knn` |
| `quality/residuals.py` | `_compute_ps_residuals`, `_compute_residual_sigma`, `_spatial_std_vlos_mm_yr` |
| `quality/outliers.py` | `_filter_isolated_points`, `_filter_height_outliers`, `_dedup_by_lonlat_tolerance` |
| `quality/sigsolv.py` | `_apply_sigsol_cleaning` + `third_party/appsigsolv` (DIA/OMT) |
| `geometry/merge_subswath.py` | `_merge_subswath_outputs`, `_merge_subswath_dem_tifs`, `_subswath_outputs_ready` |
| `geometry/overlap.py` | `_merge_overlap_timeseries`, `_merge_overlap_seamline` |
| `geometry/decompose3d.py` | `_run_3d_decomposition`, `_decompose_vlos_and_displacement`, `_compute_has_matrix_eu`, `_fast_interpolate`, `_finalize_3d_results`, `_*3d_output*` (fingerprint → manifest) |
| `reference.py` | `_zero_reference_first_valid`, chọn/đổi điểm tham chiếu |
| `alerts.py` | `_load_alert_config`, `_extract_alert_scalar`, `_apply_alert_levels` + các quy tắc từ `ops/alerts.py` |
| `export/*` | phần ghi tệp của `ps_export_gis` (≈1270 dòng), `ps_export_gis_capella_2d_lon_geo`, `_write_vlos_qgis_style`, `_pretty_breaks`, `_save_*_shp/_tif`, `_save_height_point_cloud`, `_save_ps_heatmap_tif`, `_csvtoshp` |
| **Xoá** | `_publish_*`, `_upload_*_postgis`, `_publish_desc_heatmap_to_geoserver`, `_publish_with_rollback`, `_publish_project_ids`, `_merged_publish_ready`, `_ensure_gnss_shp`(nếu chỉ phục vụ xuất bản) |
| **Thay bằng workspace/manifest** | `_normalize_to_main_folder`, `_discover_current_result_base`, `_detect_result_folders`, `_find_latest_result_folders`, `_is_stamps_complete`, `_archive_settings_to_output`, `_make_export_log_path` |

Chọn backend qua biến môi trường `INSAR_ITYPE` lúc import → **bỏ hẳn**.

---

## 10. Lưu trữ: định dạng & lược đồ

### 10.1 Tổng quan

| Loại | Định dạng | Kho | Lý do |
|---|---|---|---|
| Ảnh thô | Giữ nguyên định dạng nhà cung cấp (SAFE zip, HDF5, CEOS, GeoTIFF) | `raw/` (chỉ đọc) | Không sửa dữ liệu thô |
| Stack SLC/IFG/độ kết hợp/hình học | **Zarr v3** (chia chunk, nén Blosc-zstd) | `StackStore` | Ghi song song theo chunk, đọc trễ qua xarray/dask, hợp với lưu trữ đối tượng |
| Trạng thái engine PS | **HDF5** có lược đồ (`h5py`) | `StateStore` | Nhiều mảng cỡ vừa, truy cập ngẫu nhiên, mỗi tile một tệp, mở được bằng HDFView |
| Điểm đo | **GeoParquet 1.1** | `PointStore` | Dạng cột, nén tốt, DuckDB/GeoPandas/QGIS đọc trực tiếp |
| Chuỗi thời gian của điểm | **Parquet** dạng dài (long format) | `TimeSeriesStore` | Truy vấn theo điểm/ngày bằng DuckDB |
| Raster sản phẩm | **COG** (GeoTIFF tối ưu cho đám mây) | `RasterStore` | Chuẩn GIS, đọc từng phần qua HTTP |
| Siêu dữ liệu tra cứu | **STAC 1.x** Item/Collection | danh mục | Chuẩn mở cho dữ liệu quan sát Trái Đất (EO) |
| Siêu dữ liệu tuân thủ | XML ISO 19115/19139 | sản phẩm | Đáp ứng yêu cầu hiện hành |
| Nguồn gốc dữ liệu | `manifest.json` | mọi artifact | Tái lập, chạy tiếp, kiểm toán |
| Xuất GIS | GPKG / SHP / CSV / QML / LAS | `exports/` | Dữ liệu dẫn xuất, tạo lại được |

Quy ước chung: UTF-8; thời gian theo ISO 8601 UTC; ngày chụp kiểu `datetime64[D]`; CRS ghi rõ trong siêu dữ liệu (EPSG:4326 cho lon/lat; hình học radar ghi `crs="radar"` + LUT); đơn vị đặt trong `attrs["units"]`; dấu LOS: **dương = về phía vệ tinh** (ghi trong siêu dữ liệu và nhắc lại trong báo cáo).

### 10.2 `StackStore` (Zarr)

```
stacks/<stack_id>/stack.zarr/
  zarr.json                       attrs: stack_id, track, sensor, mode, subswath, reference_date,
                                         wavelength_m, range/azimuth spacing, engine, engine_version,
                                         dem, created, manifest_sha256
  slc            (date, y, x)     complex64   chunks (1, 1024, 1024)
  slc_linked     (date, y, x)     complex64   [phase_linking]
  amp_cal        (date)           float32     hệ số hiệu chỉnh biên độ
  ifg            (pair, y, x)     complex64   đã loại trái đất phẳng + địa hình
  coherence      (pair, y, x)     float16/32
  mean_amp, amp_disp  (y, x)      float32
  coh_pl, bronum, shp_count (y,x) float32/uint16  [phase_linking]
  water_prob     (y, x)           float32     [water_mask]
  geometry/ lat lon hgt incidence heading slant_range (y, x) float32/64
  coords: date (datetime64[D]), pair (str "YYYYMMDD_YYYYMMDD"), pair_ref, pair_sec,
          bperp (pair|date) float32, btemp (pair) int16, y, x (int, pixel radar)
```

- Chia chunk theo không gian (1024×1024, 1 ngày) để xử lý theo khối; kích thước chunk chỉnh được.
- **Đã triển khai (S1 native, `processing/stack/native/s1_stack.py`)**: `slc` lưu ở dạng *đã làm phẳng* — pha hình học 4π/λ(R_sec − R_ref) đã khử sẵn, nên giao thoa đồ bất kỳ = `slc[i]·conj(slc[j])`, không cần biến `ifg` riêng; thêm `bperp (date,y,x)` và `esd_shift (date)`; trục `y` là dòng azimuth đã deburst của ảnh tham chiếu, cắt theo AOI.
- Một stack = một vệt quỹ đạo (+ một dải con với S1).
- API của `StackStore`: `open(stack_id) -> xr.Dataset` (đọc trễ), `write_var(name, da, region=…)`, `has(name)`, `fingerprint(name)`.

### 10.3 `StateStore` (HDF5, engine PS)

```
ps_runs/<psrun_id>/
  manifest.json
  params.json                     Parms đầy đủ (giữ tên StaMPS)
  tiles/<tile_id>.h5              /step1/{ij,lonlat,ph,bperp,da,la,hgt,inc,day,...}
                                  /step2/{coh_ps,K_ps,C_ps,...}  /step3/{ix,...}  /step4/{...}
                                  /step5/{ph_rc,ifg_std,...}
                                  attrs trên mỗi dataset: units, description, stamps_name
  merged.h5                       /step5…/step8 sau khi ghép: ph_uw, scla, scn, aps, ts, velocity…
  figures/                        PNG theo từng bước (từ plotting.py) — đầu vào cho báo cáo
```

Lược đồ định nghĩa trong `processing/ps/state.py` (tên biến → dtype, hình dạng, đơn vị, mô tả). Bộ nạp định dạng cũ (`io/legacy/stamps_mat.py`) ánh xạ `ps1.mat`, `pm2.mat`, `phuw2.mat`… sang lược đồ này.

**ps_lite (Capella) dùng chung cấu trúc lưu trữ** — chỉ khác lược đồ trong tệp trạng thái:

```
ps_runs/<psrun_id>/                     engine = "ps_lite" (ghi trong manifest)
  manifest.json · params.json           params = các tham số [ps_lite] (tên theo run_stack)
  state.h5                              thay thế ps_stack.npz:
    /candidates/{line,sample,da,sd,amp}           /geometry/{kh,h_ortho,lat,lon}
    /phase/{wrapped,grid,unwrapped,tropo_removed}  /reference/{phase,lat,lon,n_ps}
    /inversion/{v_mm_yr,v_std_mm_yr,dh_m,c_rad,rmse_mm,phase_std,disp_mm,aps,tcoh}
    coords: date, ifg_date (datetime64[D]), ref_date
  pairs.parquet                         thay thế pairs.csv: chất lượng theo từng giao thoa đồ (bperp, hoa, unwrap_rms, phase_std, used, tropo…)
  figures/                              ảnh xem nhanh
```

Dù engine là `ps` hay `ps_lite`, artifact `TIMESERIES` đều vào `postprocess` qua cùng một bộ điều hợp → `PointSet` → `products/<product_id>/`, với **cùng** bộ `points.parquet` / `timeseries.parquet` / COG / STAC / ISO / manifest / báo cáo (§10.4–10.6). Danh mục, webapp, báo cáo và xuất dữ liệu không cần phân biệt cảm biến hay engine; manifest ghi `engine` để truy vết.

### 10.4 `PointStore` & `TimeSeriesStore` (GeoParquet / Parquet)

`points.parquet` — một dòng/điểm (lược đồ `products/schema.py`, có phiên bản):

| Cột | Kiểu | Mô tả |
|---|---|---|
| `point_uid` | string | ID ổn định qua các phiên bản (§11.5) |
| `track_id` · `stack_id` | string | |
| `geometry` | Point (WKB, EPSG:4326) | |
| `lon` `lat` | float64 | |
| `height_m` · `height_err_m` | float32 | độ cao ellipsoid đã hiệu chỉnh sai số DEM |
| `type` | category | PS / DS / FORCED |
| `vel_los_mm_yr` · `vel_std_mm_yr` | float32 | |
| `acc_los_mm_yr2` | float32 | |
| `temporal_coherence` | float32 | |
| `amp_dispersion` | float32 | |
| `dem_err_m` | float32 | |
| `seasonal_amp_mm` · `seasonal_phase_day` | float32 | |
| `fit_rmse_mm` · `residual_sigma_mm` | float32 | |
| `los_e` `los_n` `los_u` | float32 | vector đơn vị LOS |
| `incidence_deg` · `heading_deg` | float32 | |
| `alert_level` · `cluster_id` | int8 / int32 | |
| `vel_ew_mm_yr` `vel_ud_mm_yr` | float32 | chỉ có ở sản phẩm 3D |
| `extra_*` | | cột mở rộng, không phá lược đồ |

`timeseries.parquet` — dạng dài, sắp xếp theo `point_uid, date`:

| `point_uid` | `date` (date32) | `disp_mm` (float32) | `disp_std_mm` (float32, null) | `flags` (uint8) |

Vì sao chọn dạng dài: cả hai kiểu truy vấn “chuỗi thời gian của điểm X” và “mọi điểm tại ngày D” đều nhanh trong DuckDB; dạng rộng `DYYYYMMDD` chỉ còn trong tệp xuất (để tương thích plugin QGIS cũ).

### 10.5 `RasterStore` (COG)

`velocity.tif`, `velocity_std.tif`, `coherence_mean.tif`, `ps_density.tif`, `heatmap.tif`, `dem_ps.tif` — float32, nén DEFLATE/ZSTD, có overview, khai báo rõ nodata, EPSG:4326 hoặc UTM tuỳ AOI.

### 10.6 Manifest & trạng thái

`manifest.json` (mọi artifact: stack, ps_run, product, run):

```json
{
  "schema": "geoeyes.manifest/1",
  "kind": "product",
  "id": "mexico_capella-asc-xxx_psi_20240626_20240815_v3",
  "created": "2026-10-21T08:00:00Z",
  "software": {"geoeyes": "1.0.0", "python": "3.11.9", "packages": {"numpy": "...", "...": "..."}},
  "run_id": "20261021T080000-a1b2",
  "inputs":  [{"kind": "timeseries", "uri": "ps_runs/…/merged.h5", "sha256": "…"}],
  "params":  {"sha256": "…", "snapshot": "params.json"},
  "outputs": [{"path": "points.parquet", "sha256": "…", "bytes": 123}],
  "metrics": {"n_points": 41234, "vel_std_median_mm_yr": 1.2, "...": "..."},
  "phases":  [{"name": "postprocess", "fingerprint": "…", "status": "ok", "duration_s": 312}]
}
```

`workspace/<project>/.state/state.json` (thay `config.json` + `current_result`): stack hiện hành / sản phẩm mới nhất của từng vệt quỹ đạo; **chỉ** bộ điều khiển được ghi (ghi nguyên tử).

### 10.7 Dữ liệu cũ (legacy)

- **Không** chuyển đổi kết quả cũ; các dự án chạy lại từ ảnh thô (ADR-017). Ảnh thô trong `data/` chuyển vào `$WS/archive`.
- `io/legacy/*` **chỉ đọc**, phục vụ hai việc: test chuẩn (golden) (so đầu ra cũ ↔ mới) và engine `snap` chuyển tiếp (nhập DIMAP). Sẽ xoá khi xong Giai đoạn 5.
- Vẫn giữ `geoeyes migrate config` (in.json + control.json → project.toml).

---

## 11. Không gian làm việc, lưu trữ dài hạn & truy xuất

### 11.1 Bố cục không gian làm việc

Mã nguồn và dữ liệu tách hẳn khỏi nhau. Thư mục gốc dữ liệu: `GEOEYES_WORKSPACE` (ví dụ `D:/geoeyes-data`).

```
$GEOEYES_WORKSPACE/
├─ archive/                              KHO ẢNH THÔ dùng chung cho mọi dự án (bất biến)
│  └─ <sensor>/<track>/<YYYY>/<scene_id>/…    + archive_index.parquet
├─ projects/<project>/
│  ├─ project.toml                       cấu hình (người dùng)
│  ├─ aoi.geojson
│  ├─ raw/                               liên kết/tham chiếu tới cảnh trong archive/ (không sao chép)
│  ├─ stacks/<stack_id>/                 stack.zarr · network/ · manifest.json         [HOT]
│  ├─ ps_runs/<psrun_id>/                params.json · tiles/*.h5 · merged.h5 · figures/  [HOT]
│  ├─ products/<product_id>/             BẤT BIẾN                                        [WARM]
│  │    points.parquet · timeseries.parquet · rasters/*.tif
│  │    item.json (STAC) · metadata.xml (ISO 19139) · manifest.json · report.pdf
│  ├─ exports/<product_id>/              gpkg · shp · csv · qml · las (có thể tạo lại)       [TMP]
│  ├─ runs/<run_id>/                     manifest.json · log.jsonl · logs/<phase>.log · progress.json · preflight.json
│  └─ .state/                            state.json · locks/
├─ catalog/                              catalog.json (gốc STAC) · index.duckdb
└─ cache/                                dem/ · orbits/ · era5/ · gacos/ (có thể xoá bất cứ lúc nào)
```

### 11.2 Các tầng lưu trữ & vòng đời

| Tầng | Nội dung | Vòng đời | Dung lượng ước tính (dựa trên dự án `mexico` hiện tại) |
|---|---|---|---|
| **Archive** (lạnh) | ảnh thô | Lưu vĩnh viễn, hoặc chỉ giữ tham chiếu nếu đã có kho ngoài (ASF/Capella tải lại được) | ~40 GB / dự án |
| **Hot** | `stacks/`, `ps_runs/` | Tái lập được từ archive + cấu hình → **xoá được** khi sản phẩm đã duyệt; giữ phiên bản mới nhất của mỗi vệt quỹ đạo để giám sát tiếp | thay `process/` (~70 GB BEAM-DIMAP) bằng Zarr nén — dự kiến nhỏ hơn nhiều |
| **Warm** (sản phẩm) | `products/` | **Bất biến, lưu vĩnh viễn**; có checksum | MB – vài GB / phiên bản |
| **Tmp** | `exports/`, `cache/` | Xoá tuỳ ý | — |
| **Logs** | `runs/` | Giữ trong `GEOEYES_LOG_RETENTION_DAYS` (mặc định 365) — manifest giữ vĩnh viễn, log văn bản nén gzip sau 30 ngày | nhỏ |

`catalog/retention.py` áp dụng chính sách này (`geoeyes catalog prune --dry-run`) và không bao giờ xoá sản phẩm đang được `state.json` tham chiếu hoặc đã gắn nhãn `approved`.

### 11.3 Danh mục & chỉ mục

- **STAC tĩnh**: `catalog/catalog.json` → mỗi dự án một Collection → mỗi sản phẩm một Item. Phần mở rộng: `sar`, `sat`, `processing`, `projection`, `file` (checksum), `version`. Asset: `points`, `timeseries`, `velocity`, `report`, `metadata`.
- **Chỉ mục DuckDB** (`catalog/index.duckdb`, phần mở rộng `spatial`): bảng `products` (lấy từ STAC), các view `points` / `timeseries` đọc thẳng tệp Parquet (không nhân bản dữ liệu). Chỉ mục **dựng lại được hoàn toàn** từ STAC + Parquet, nên không phải nguồn dữ liệu gốc và không cần sao lưu.
- Không cần máy chủ cơ sở dữ liệu (thay PostGIS) — chỉ một tệp, chạy ngoại tuyến, vẫn nhanh với hàng chục triệu điểm.

### 11.4 Truy xuất

```bash
geoeyes catalog list [--project P] [--track T] [--since 2025-01-01]
geoeyes catalog search --bbox lon1,lat1,lon2,lat2 --date 2024-06..2024-12 --min-vel -10
geoeyes catalog ts <point_uid> [--product latest|<id>] [--format csv|json]
geoeyes catalog diff <product_a> <product_b>          # thay thế ops/alerts.compare & tools/regression_check
geoeyes catalog export <product_id> --format gpkg|shp|csv|las [--crs EPSG:xxxx]
geoeyes catalog bundle <product_id> -o file.zip       # gói bàn giao: dữ liệu + STAC + ISO + báo cáo + SHA256SUMS
geoeyes catalog verify [<product_id>]                 # kiểm tra checksum toàn bộ kho
geoeyes catalog prune [--dry-run]
```

API Python tương ứng (`geoeyes.catalog.query`): `search(...) -> list[ProductRef]`, `points(product, bbox=None, where=None) -> gpd.GeoDataFrame`, `timeseries(point_uids, product=None) -> pd.DataFrame`. Backend của webapp cũng dùng chính API này (thay `shapefile_reader`, `inversion_reader` đọc `.mat`, `results_manager`).

### 11.5 Định danh điểm ổn định (`point_uid`)

Dùng để so sánh và ghép chuỗi thời gian giữa các lần chạy giám sát:
`point_uid = <track_id>:<geohash9(lat,lon)>:<round(height_m)>` (≈5 m) + khử trùng lặp trong cùng một sản phẩm. `catalog diff` ghép điểm giữa 2 sản phẩm theo `point_uid`; nếu không khớp thì lùi về láng giềng gần nhất (KD-tree, ngưỡng tuỳ chỉnh). ADR-018.

### 11.6 Sao lưu & lưu trữ bên ngoài

- `io/fs.py` dùng `fsspec`: có thể đặt `products/` và `archive/` trên NAS/S3/MinIO (khai báo URI qua `GEOEYES_ARCHIVE_URI`, `GEOEYES_PRODUCTS_URI`).
- Nên áp dụng quy tắc 3-2-1 cho `products/` + `archive/` (khi ảnh thô không tải lại được: CSK, ALOS, TSX). `stacks/`, `ps_runs/`, `cache/`, `index.duckdb` **không** cần sao lưu.
- Báo cáo có thể tự động chép tới một thư mục chỉ định (`[report].copy_to`) — thay `VINSAR_EVIDENCE_DIR`.

---

## 12. Ghi log & khả năng quan sát

- **Thư viện**: `log = logging.getLogger(__name__)`; cấm `print` (quy tắc ruff `T20`). Khoảng ~4600 lệnh `print` sẽ được thay dần.
- **Cấu hình tập trung một chỗ** trong `core/logging.py`, CLI/bộ điều khiển gọi đúng một lần:
  - Console: định dạng dễ đọc, mức INFO (CLI `-v/-q`).
  - `runs/<run_id>/log.jsonl`: mọi bản ghi dưới dạng JSON (ts, level, logger, msg, run_id, phase, track, tile, step, duration_ms, extra).
  - `runs/<run_id>/logs/<phase>[_<track>].log`: bản văn bản cho từng pha (thay `logs/<p>/workflow/<stage>_<ts>.log`).
- **Ngữ cảnh** qua `contextvars` (run_id, phase, track, tile, step) — tự gắn vào mọi bản ghi, kể cả bản ghi từ tiến trình worker (QueueHandler).
- **Tiến trình con** (gpt, triangle, unrar): đọc stdout/stderr từng dòng → ghi log qua logger `geoeyes.ext.<tool>`.
- **Sự kiện có cấu trúc** (`log.info("...", extra={"event": "phase_end", ...})`): `phase_start/phase_end/step_end/progress/metric/warning_quality`. `progress.json` và thống kê thời gian (thay `timing_log.py`, `processing_times.csv`, `StdoutWatcher`) đều **suy ra** từ các sự kiện này.
- Lỗi: ngoại lệ có kiểu + traceback đầy đủ trong log; `manifest.json` của lần chạy ghi `status`, `failed_phase`, `error`.
- Đã bỏ: `_TeeStream`, `console_log._Tee`, `_ThreadScopedStdout`, việc chuyển hướng stdout toàn cục.

---

## 13. Báo cáo khoa học (PDF)

### 13.1 Mục tiêu

Người **không tham gia xử lý**, chỉ cần đọc báo cáo, phải trả lời được: dùng dữ liệu nào, xử lý ra sao, kết quả chính là gì, tin cậy đến đâu và hạn chế ở chỗ nào. Đồng thời, báo cáo phải đủ chi tiết kỹ thuật để chuyên gia InSAR thẩm định và tái lập.

### 13.2 Cấu trúc

| Mục | Nội dung | Nguồn dữ liệu |
|---|---|---|
| **Trang bìa** | Tên dự án, AOI, cảm biến/vệt quỹ đạo, khoảng thời gian, ID sản phẩm, phiên bản phần mềm, ngày tạo | manifest |
| **Tóm tắt (1 trang)** | 3–5 phát hiện chính (vận tốc lớn nhất, vùng biến dạng, xu hướng), bảng số liệu chính (số điểm, mật độ, vận tốc min/trung vị/max, độ bất định trung vị), bản đồ thu nhỏ, **nhận định độ tin cậy** (cao/trung bình/thấp + lý do) | metrics, product |
| **1. Khu vực & dữ liệu** | Bản đồ AOI; bảng cảnh (ngày, ID, chế độ, phân cực); trục thời gian các lần chụp; **biểu đồ đường đáy** (Bperp–thời gian) + mạng cặp ảnh; mức phủ | NETWORK, SceneMetadata |
| **2. Phương pháp** | **Sơ đồ chuỗi xử lý sinh tự động** từ DAG đã chạy; mô tả từng bước (đồng đăng ký, IFG, phase linking, chọn PS/DS, giải chập pha, APS, nghịch đảo, hậu xử lý) kèm tham số chính và **trích dẫn khoa học**; bảng tham số chính; chỗ khác mặc định | manifest phases, params |
| **3. Đánh giá chất lượng** | Phân bố độ kết hợp (histogram, theo cặp); mật độ PS/DS; độ kết hợp thời gian; độ lệch chuẩn IFG; sai số khép pha & tỉ lệ cặp lỗi giải chập pha; hiệu quả hiệu chỉnh khí quyển (mức giảm phương sai); RMS phần dư; phân bố sai số DEM; độ ổn định điểm tham chiếu | QualityMetrics, figures |
| **4. Kết quả** | Bản đồ vận tốc LOS (+ bản đồ độ bất định); histogram vận tốc; chuỗi thời gian các điểm/cụm tiêu biểu (tự chọn theo cụm/cảnh báo); vùng cảnh báo; 3D EW/UD nếu có 2 vệt quỹ đạo | product |
| **5. Kiểm chứng** *(nếu có)* | So sánh GNSS/CR: biểu đồ phân tán, độ chệch, RMSE, bảng trạm | validation |
| **6. Diễn giải & hạn chế** | Quy ước dấu LOS, điểm tham chiếu, độ nhạy theo hướng (không nhạy với chuyển dịch Bắc–Nam), khí quyển còn sót, vùng mất kết hợp, khuyến nghị sử dụng | template + metrics |
| **Phụ lục A** | Toàn bộ tham số (phần khác preset) | params |
| **Phụ lục B** | Nguồn gốc dữ liệu: danh sách cảnh + checksum, phiên bản phần mềm/thư viện, môi trường, thời gian chạy từng pha | manifest |
| **Phụ lục C** | Danh sách tệp sản phẩm + SHA-256; định dạng & cách đọc (GeoParquet/COG/STAC) | manifest |
| **Phụ lục D** | Thuật ngữ & tài liệu tham khảo | tĩnh |
| **Phụ lục E** *(tuỳ chọn)* | Thông tin vận hành: preflight, thời gian chạy từng pha, tài nguyên máy (bỏ mã quy trình vận hành/cổng/ký duyệt — ADR-016) | run manifest |

Tài liệu tham khảo cố định trong template (BibTeX): Ferretti et al. 2001 (PS), Hooper et al. 2004/2007 (StaMPS), Berardino et al. 2002 (SBAS), Ferretti et al. 2011 (SqueeSAR), Ansari et al. 2018 (EMI/sequential), Yunjun et al. 2019 (MintPy), Goldstein & Werner 1998, Prats-Iraola et al. 2012 (TOPS ESD), Jolivet et al. 2011/2014 (APS kiểu ERA5/GACOS), Yu et al. 2018 (GACOS). Chỉ trích dẫn những bước thực sự có chạy.

### 13.3 Kỹ thuật

- **Thu thập** (`report/collect.py`): chỉ đọc manifest + `QualityMetrics` + sản phẩm — **không** đọc lại `.mat`/log thô. Chỉ số đã được tính **ngay trong** quy trình xử lý (`products/metrics.py`).
- **Hình** (`report/figures/`): matplotlib, phong cách thống nhất (phông chữ, bảng màu không gây hiểu sai: `RdBu_r` đối xứng quanh 0 cho vận tốc, `viridis` cho độ kết hợp), xuất dạng vector (PDF/SVG) để in sắc nét; bản đồ có thước tỉ lệ, mũi tên chỉ Bắc, chú thích hướng LOS & heading.
- **Kết xuất**: **Typst** (gói PyPI `typst`, tệp nhị phân độc lập, chạy tốt trên Windows; xử lý tốt công thức toán & trích dẫn) — ADR-010. Template đặt trong `report/templates/*.typ`, dữ liệu truyền vào dưới dạng JSON.
- **Ngôn ngữ**: tiếng Anh (ADR-015), không i18n.
- Đầu ra: `products/<id>/report.pdf` + `report.json` (dữ liệu đã dùng). Lúc nào cũng tạo lại được bằng `geoeyes report <product_id>`.
- Báo cáo CR (`cr_report/report.py`) dùng chung engine & phong cách.

---

## 14. Cấu hình

### 14.1 `project.toml` (thay thế `in.json` + `control.json` + `config.json`)

```toml
schema = "geoeyes.project/1"

[project]
name = "mexico"
method = "psi"                    # psi | sbas | psds | comsar
description = "..."
# organization = { name = "...", email = "..." }   # tuỳ chọn; chỉ dùng cho thông tin liên hệ trong ISO 19139 (ADR-016)

[aoi]
bbox = [-99.2, 19.3, -99.0, 19.5]   # hoặc file = "aoi.geojson"

[[tracks]]
sensor = "capella"
direction = "ascending"
# sentinel1: relative_orbit, frame, subswaths = ["IW1","IW2"]

[acquire]
date_range = ["2024-06-01", "2024-12-31"]
max_per_month = 0
archive = "shared"                # shared | project

[network]
reference = "auto"                # hoặc "2024-06-26"
max_perp_m = 150
max_temporal_days = 0
extent_min_ratio = 0.95
sbas = { max_perp_m = 200, max_temporal_days = 96, redundant = true }

[stack]
engine = "native"                 # native | snap (chuyển tiếp)
dem = "copernicus-glo30"
multilook = [1, 1]

[phase_linking]
enabled = false
estimator = "emi"                 # evd | emi | mle | pta | psds | comsar
half_window = [7, 7]
shp_test = "ks"                   # ks | ad | bws

[selection]
da_threshold = 0.4
robust_da = true
forced_points = ""
water_mask = "model"              # none | model | static

[ps]                              # tham số StaMPS — giữ tên gốc trong các bảng con
[ps.gamma]  ...
[ps.weed]   ...
[ps.unwrap] ...
[ps.scla]   ...
[ps.scn]    ...

[atmosphere]
method = "era5"                   # none | linear | era5 | gacos | era5+linear

[postprocess]
smoothing = "auto"
seasonal = true
decompose_3d = "auto"
alerts = "alerts.toml"

[validation]
gnss = { enabled = false, source = "sftp" }

[report]
copy_to = ""

[export]
formats = ["gpkg"]

[compute]
backend = "auto"                  # auto | numpy | cupy
workers = 0                       # 0 = tự động
memory_gb = 0

[pipeline]                        # thay thế control.json
water_mask = true
validate = false
from = ""                         # giá trị mặc định tuỳ chọn cho `geoeyes run`

[overrides.IW1]                   # trộn sâu theo từng dải con (giữ tính năng apply_subswath_overrides)
ps.weed.noisy_check = false
```

- `config/schema.py`: pydantic v2, kiểm tra kiểu, miền giá trị và ràng buộc chéo (thay `validation.py`); sinh JSON Schema cho webapp (thay `settingsSchema.ts` viết tay).
- Preset theo cảm biến: `config/presets/<sensor>.toml` (thay `presets/*.json` + `_comment` + `"__unset__"`).
- `geoeyes migrate config control/<project>/` chuyển `in.json` + `control.json` cũ sang `project.toml`.

### 14.2 Biến môi trường (`GEOEYES_*`, **chỉ** đọc trong `config/settings.py`)

| Biến | Dùng cho |
|---|---|
| `GEOEYES_WORKSPACE` | thư mục gốc của không gian làm việc |
| `GEOEYES_ARCHIVE_URI`, `GEOEYES_PRODUCTS_URI` | lưu trữ bên ngoài (tuỳ chọn) |
| `GEOEYES_LOG_LEVEL`, `GEOEYES_LOG_RETENTION_DAYS` | ghi log |
| `GEOEYES_SNAP_GPT` | chỉ dùng với engine `snap` |
| *(webapp sau này tự định nghĩa biến riêng)* | |
| `EARTHDATA_TOKEN`, `CDSAPI_*` / `~/.cdsapirc`, `GACOS_*`, `OT_API_KEY`, `CDSE_*` (quỹ đạo) | thông tin xác thực bên thứ ba — giữ tên chuẩn của nhà cung cấp |
| `GEOEYES_GNSS_SFTP_{HOST,PORT,USER,PASS,REMOTE_FILE}` | nguồn GNSS (kiểm chứng) |

Đã bỏ: `VINSAR_PYTHON` (dùng `sys.executable`/venv), `VINSAR_NOTIFY_*`, `VINSAR_SMTP_*`, `VINSAR_PUBLISH_*`, `VINSAR_EVIDENCE_DIR` (→ `[report].copy_to`), `VINSAR_REGRESSION_DIR`, `VINSAR_TRIGGER`, `VINSAR_JOB_ID` (→ tham số CLI), `INSAR_ITYPE`, `INSAR_SUBSWATH_FILTER` (→ `--track`), `CloudIP`, `DBUser`, `DBName`, `DBPass`, `DBPort`, các biến GeoServer.

---

## 15. Ứng dụng: CLI, QGIS (bỏ GUI, webapp xây dựng lại sau)

### 15.1 CLI `geoeyes`

```
geoeyes init <project> --sensor S [--aoi FILE]      tạo project.toml từ một preset
geoeyes check [<project>]                           kiểm tra trước (preflight) môi trường + dự án
geoeyes plan <project>                              in DAG sẽ chạy (dry-run)
geoeyes run <project> [--track] [--from|--to|--only|--force]
geoeyes status <project>                            trạng thái pha/vệt quỹ đạo, lần chạy gần nhất
geoeyes report <product_id>
geoeyes catalog …                                   (§11.4)
geoeyes migrate config|legacy …
geoeyes schedule install|remove|list <project>
geoeyes benchmark
```

Dùng `typer` (hoặc `argparse` nếu muốn bớt một phụ thuộc). Xoá `vinsar.py`; không giữ lớp tương thích (shim).

### 15.2 Webapp — xây dựng lại sau (ADR-022)

Webapp hiện tại được đóng băng, không chuyển đổi; sẽ thiết kế và xây dựng lại khi phần lõi hoàn thành. Phần lõi chuẩn bị trước bằng các hợp đồng ổn định:
- Chạy & giám sát: `geoeyes run` (tiến trình con tách rời) + `runs/<run_id>/{manifest.json, log.jsonl, progress.json}`.
- Dữ liệu: `geoeyes.catalog.query` (search, points, timeseries, diff) — không đọc tệp nội bộ.
- Cấu hình: JSON Schema sinh từ `geoeyes.config.schema` → biểu mẫu tự động.
- Báo cáo: `geoeyes.report`.
Những điểm đáng học lại từ webapp cũ (dự báo lượt bay qua của S1, lượng mưa CHIRPS, báo cáo CR chạy nền, log trực tiếp qua SSE) sẽ ghi vào `docs/en/refactor/webapp-notes.md` khi bắt đầu xây dựng lại.

### 15.3 GUI desktop — đã bỏ (ADR-022)

Xoá toàn bộ `tools/*_gui.py`, `tools/*viewer*.py`, `modules/pta/cr_target_gui.py`. Thuật toán mà quy trình xử lý cần đã có sẵn (hoặc đã chuyển) vào thư viện; chỉ `_split_spectrum_common.py` được chuyển sang (→ `atmosphere/ionosphere.py`). Các CLI bảo trì trở thành lệnh `geoeyes`. Phần trực quan hoá kiểm soát chất lượng (QC) chuyển sang: hình trong báo cáo (§13), QGIS (đọc GeoParquet/GPKG), notebook và webapp sau này.

### 15.4 Plugin QGIS (`apps/qgis`)

Đọc GeoParquet (QGIS ≥3.30 đã hỗ trợ) hoặc tệp GPKG xuất ra; plugin phân tách dùng cùng mô hình với `postprocess/timeseries/seasonal.py` (đã ghi chú phải giữ đồng bộ).

---

## 16. Kiểm thử & chất lượng

### 16.1 Các tầng kiểm thử

| Loại | Thư mục | Nội dung |
|---|---|---|
| Unit | `tests/unit/<package>/` | hàm thuần: quỹ đạo, hình học, bộ ước lượng, các bước PS, làm trơn… |
| Contract | `tests/contract/` | mọi Store đọc/ghi đúng lược đồ; mọi `SensorReader` trả `SceneMetadata` hợp lệ; mọi `Phase` khai báo requires/produces nhất quán |
| Golden | `tests/golden/` | bộ dữ liệu nhỏ cho từng cảm biến (S1, CSK, Capella, ALOS) → so đầu ra với bản tham chiếu, trong dung sai |
| Ranh giới | `import-linter` | quy tắc phân lớp §4.2 |
| CLI | `tests/cli/` | các lệnh `geoeyes` (init, plan, run --dry-run, catalog) |

### 16.2 Bộ dữ liệu golden

- Mỗi cảm biến một stack nhỏ đã cắt (≤ 10–15 epoch, AOI ~ 2×2 km) — đủ chạy trọn quy trình trong vài phút.
- Lưu ngoài repo (`GEOEYES_TEST_DATA`), kèm manifest + checksum.
- Chỉ số so sánh: số điểm PS (±%), vận tốc (RMSE, độ chệch), chuỗi thời gian (RMSE), độ kết hợp (chênh lệch trung vị), pha IFG (độ lệch chuẩn vòng của hiệu pha).

### 16.3 Tiêu chí chuyển đổi native ↔ SNAP

| Chỉ số | Ngưỡng đề xuất |
|---|---|
| Độ lệch đồng đăng ký còn sót (stripmap) | < 0.05 px |
| Độ lệch đồng đăng ký azimuth của TOPS sau ESD | < 0.002 px |
| Độ lệch chuẩn vòng của hiệu pha IFG (vùng độ kết hợp > 0.5) | < 0.3 rad |
| Chênh lệch trung vị độ kết hợp | < 0.02 |
| Vận tốc PS (các điểm chung) | RMSE < 1 mm/năm, độ chệch < 0.5 mm/năm |

### 16.4 Công cụ

`ruff` (lint + định dạng, kể cả `T20` cấm print trong `src/`), `mypy` áp dụng dần (chế độ nghiêm ngặt cho `core`, `io`, `config`, `controller`), `pytest` + `pytest-xdist`, `import-linter`, CI trên GitHub Actions (khi đã có git).

---

## 17. Phụ thuộc

`pyproject.toml` với các extra:

| Nhóm | Gói |
|---|---|
| core | numpy, scipy, pandas, xarray, zarr≥3, numcodecs, h5py, pyarrow, geopandas, shapely, pyproj, rasterio, numba, pydantic≥2, pydantic-settings, duckdb, fsspec, matplotlib, typst, lxml, tqdm (CLI), psutil |
| `[sar]` | asf-search, requests, tenacity, cdsapi, netcdf4 |
| `[gpu]` | cupy-cuda12x |
| `[ml]` | torch, torch-dct |
| `[gui]`, `[web]` | — (đã bỏ; webapp sau này tự khai báo phụ thuộc riêng) |
| `[snap]` | (không có gói; phải cài SNAP riêng) — chỉ cho engine chuyển tiếp |
| `[cr]` | sct[recommended], sct-sentinel1-reader, sct-cosmo-reader |
| `[gnss]` | paramiko |
| dev | pytest, pytest-xdist, ruff, mypy, import-linter |

Đã bỏ: `reportlab` (→ typst), `SQLAlchemy` (đã bỏ PostGIS), `geocoder`, `pyperclip`, `jenkspy` (thay bằng phân lớp quantile/pretty-breaks tự viết, hoặc giữ nếu cần Jenks), `stsa` (phụ thuộc git — thay bằng đọc thẳng annotation của SAFE), `PyWavelets`/`statsmodels`/`cvxopt`/`joblib` (xem xét lại khi chuyển mã: chỉ giữ nếu thực sự dùng).

**Giấy phép** (ADR-019): GeoEyes dùng giấy phép riêng. Triangle → `scipy.spatial.Delaunay`. Bình phương tối thiểu chính quy hoá L1 được viết lại sạch từ thuật toán (không giữ dòng mã nào chuyển từ MintPy/CVXOPT) → bỏ `cvxopt` nếu không còn nơi nào dùng. appsigsolv: kiểm tra giấy phép khi chuyển vào `third_party/`.

---

## 18. Sẵn sàng cho AI

Đợt tái cấu trúc này không xây dựng AI, nhưng chừa sẵn các điểm mở rộng để kế hoạch AI sau này không phải đập bỏ kiến trúc:

| Điểm mở rộng | Đã có sẵn nhờ thiết kế |
|---|---|
| **Dữ liệu huấn luyện** | Sản phẩm bất biến + GeoParquet/Zarr có lược đồ + danh mục truy vấn được → `geoeyes.ml.datasets` dựng bộ dữ liệu từ danh mục (điểm, chuỗi thời gian, mảnh IFG/độ kết hợp) |
| **Nhãn** | Thêm kho `labels/` (GeoParquet: point_uid/polygon, nhãn, nguồn, người gán nhãn) đặt cạnh sản phẩm |
| **Mô hình** | `models/<name>/<version>/` + manifest (dữ liệu huấn luyện, chỉ số, hash trọng số) — theo khuôn U-Net phân loại nước (`masking/checkpoint`) |
| **Suy luận** | Mỗi mô hình là một `Phase` (`requires`/`produces`), cắm vào DAG như mọi pha khác |
| **Tính toán** | `core.compute` + extra `[ml]` (torch), tách khỏi các kernel xử lý |
| **Báo cáo** | `report.json` có cấu trúc → có thể sinh tự động phần diễn giải (có kiểm soát) |

Các ứng dụng AI tiềm năng (kế hoạch sau sẽ đánh giá): phát hiện lỗi giải chập pha, phân loại PS/DS & loại điểm nhiễu, hiệu chỉnh khí quyển bằng học máy, phát hiện bất thường/điểm gãy trong chuỗi thời gian, dự báo biến dạng, tự động diễn giải kết quả trong báo cáo, phân đoạn mặt nước/thực vật.

---

## 19. Lộ trình chuyển đổi

Thứ tự (chi tiết & tiến độ trong [`TODO.md`](../refactor/TODO.md)):

1. **Lưới an toàn** — sao lưu, `pyproject.toml`, bộ dữ liệu golden + test chuẩn (golden) trên mã hiện tại.
2. **Khung & I/O** — `core`, `config`, `io` (+ bộ đọc định dạng cũ & bộ chuyển đổi), `workspace`. Mã cũ bắt đầu import qua package mới.
3. **Bộ điều khiển** — bọc các giai đoạn hiện có thành Phase, giữ nguyên hành vi; thôi ghi đè `control.json`.
4. **Hợp nhất xử lý** — các cảm biến; engine `snap` ghi vào StackStore; `selection` thay `stamps_prep`; hợp nhất `flow.py` (s1 + csk → engine `ps`; chuyển tsx sang; bỏ capella); phase linking/vsar/tomo; `ps_stack` → `ps_lite` (quy trình Capella, không qua StaMPS).
4b. **ALOS-PALSAR** — làm sau cùng, khi các cảm biến khác đã ổn định (đã có dữ liệu mẫu).
5. **Hậu xử lý** — tách `phasingpy`; sản phẩm/xuất dữ liệu; bỏ chức năng xuất bản & thông báo.
6. **Engine native** — quỹ đạo/DEM/hình học → đồng đăng ký/lấy mẫu lại/IFG (stripmap trước: Capella/CSK/ALOS, rồi đến TOPS) → đạt §16.3 → đặt native làm mặc định → xoá engine snap.
7. **Lưu trữ dài hạn** — danh mục, chỉ mục, chính sách lưu giữ, gói bàn giao.
8. **Báo cáo khoa học.**
9. **Đổi tên & hoàn thiện** — GeoEyes, reference/secondary, dọn tools, type hint, tài liệu → `git init`.

Thứ tự 4 ↔ 6 là cố ý: trước hết hợp nhất mọi thứ **sau** stack trên định dạng mới (lấy SNAP làm nguồn), rồi mới thay phần **trước** stack bằng native. Như vậy mỗi lần chỉ thay đổi một biến số và luôn có bản tham chiếu golden để so sánh.

---

## 20. Thuật ngữ

| Thuật ngữ | Ý nghĩa | Thay thế |
|---|---|---|
| reference | ảnh tham chiếu của stack | master |
| secondary | các ảnh còn lại | slave |
| track | cảm biến + chiều quỹ đạo + quỹ đạo tương đối (vệt quỹ đạo) | dự án con `_ASC`/`_DESC` |
| stack | các ảnh SLC đã đồng đăng ký của một vệt quỹ đạo (+dải con) | `INSAR_*/raw`, `process/<p>/coreg` |
| pair | một cặp (reference, secondary) tạo thành một giao thoa đồ | `<m>_<s>` |
| tile | khối không gian được engine PS xử lý | `PATCH_n` |
| PS run | một lần chạy engine PS trên một stack | `INSAR_*/process` |
| product | kết quả cuối cùng bất biến, có phiên bản | `INSAR_*/output`, `current_result` |
| phase | một bước của bộ điều khiển (pha) | stage (`manager_run`, `stamps_run`…) |
| LOS (+) | chuyển dịch về phía vệ tinh mang dấu dương | — |
