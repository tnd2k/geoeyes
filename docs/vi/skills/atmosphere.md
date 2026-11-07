# Skill: hiệu chỉnh tầng đối lưu (ERA5, CERRA, GACOS)

> Bản dịch của [docs/en/skills/atmosphere.md](../../en/skills/atmosphere.md). Dịch ngày 2026-11-01.

> Chọn mô hình thời tiết khử tốt nhất độ trễ tầng đối lưu (nhiễu khí quyển, APS) khỏi một sản phẩm điểm, thử nó
> trên sản phẩm mà không phải xử lý lại, rồi áp dụng. Trạng thái: đang vận hành (ERA5, CERRA, GACOS); HRRR, CARRA
> và BARRA2 mới chỉ được liệt kê. Đối chiếu với mã lần gần nhất 2026-11-01. Lệnh `geoeyes atmosphere`,
> `geoeyes gacos-order`. Web app: trang dự án → thẻ **Atmosphere**.

## 1. Khi nào dùng

- **Câu hỏi.** Mô hình thời tiết có giải thích phần khí quyển trong pha đã giải chập tốt hơn đường hồi quy pha –
  độ cao tuyến tính của bộ xử lý không, và mô hình nào tốt nhất?
- **Quyết định hỗ trợ.** Giá trị của `[atmosphere] method` (`none`, `era5`, `cerra`, `gacos`) và `select`
  (`auto`, `all`) trước lần chạy cuối của dự án.
- **Nên dùng** sau khi bộ xử lý `ps` (kiểu StaMPS) đã cho một sản phẩm, khi bản đồ vận tốc có các mảng loang hoặc
  tín hiệu tương quan với độ cao, ở vùng núi, mùa mưa, hoặc với chồng ảnh ngắn.
- **Không dùng cho**
  - mặt nghiêng (ramp) 10–100 km dọc phương bay trên các lần chụp Sentinel-1 chiều tối ở vĩ độ thấp: đó là tầng
    điện ly ([ionosphere.md](ionosphere.md));
  - các ô nhiễu loạn vài km: không mô hình nào phân giải được (§7);
  - sản phẩm `ps_lite` với `geoeyes atmosphere`: phép so sánh cần `phase/unwrapped` trong `state.h5` của lần chạy
    `ps`. Bản thân `ps_lite` vẫn nhận `[atmosphere] method` (§3.5).

## 2. Dữ liệu cần chuẩn bị

| Hạng mục | Bắt buộc? | Nguồn / cách lấy | Định dạng, đặt ở đâu | Ghi chú |
|---|---|---|---|---|
| Sản phẩm của bộ xử lý `ps` | có, cho `geoeyes atmosphere` | `geoeyes run <project>` ([insar-processing.md](insar-processing.md)) | `products/<id>/`, manifest trỏ tới `ps_runs/<id>/state.h5` | cần `phase/unwrapped`, `phase/scla`, `phase/aps_linear`, `ps/bperp` |
| Thời điểm chụp (UTC) của từng ngày | có | thuộc tính `sensing_mid_utc` của chồng ảnh (bộ dựng `native`), nếu không có thì lấy dấu thời gian trong tên cảnh (CSK, Capella, S1) | tự động; nếu thiếu: `[atmosphere.era5] fallback_utc = "HH:MM:SS"` | khoá dự phòng nằm trong `era5` nhưng mọi mô hình và `gacos-order` đều dùng |
| Tài khoản và khoá Copernicus CDS (ERA5, CERRA) | cho `era5`, `cerra` | đăng ký tại https://cds.climate.copernicus.eu, chép personal access token ở trang hồ sơ | `~/.cdsapirc` (Windows: `C:\Users\<bạn>\.cdsapirc`): hai dòng `url: https://cds.climate.copernicus.eu/api` và `key: <token>` | chấp nhận giấy phép của **từng** bộ dữ liệu một lần trên web CDS (`reanalysis-era5-pressure-levels`, `reanalysis-cerra-pressure-levels`); `geoeyes check` báo có `~/.cdsapirc` hay không |
| Gói Python `cdsapi` | cho `era5`, `cerra` | có sẵn trong môi trường `insar` | – | – |
| Bộ đệm ERA5 | tự động | tải theo từng (ngày, giờ) | `<workspace>/cache/era5/<YYYYMMDD>/era5_pl_<YYYYMMDD>_<HH>00.nc`, hoặc `[atmosphere.era5] cache` | tệp đã có nhưng không phủ vùng (của dự án khác) sẽ được tải lại |
| Bộ đệm CERRA | tự động | mỗi thời điểm phân tích một GRIB toàn miền (~125 MB) | `<workspace>/cache/cerra/<YYYYMMDD>/cerra_pl_<YYYYMMDD>_<HH>00.grib`, yêu cầu CDS đang chờ ghi trong `pending.json`; hoặc `[atmosphere.cerra] cache` | dùng chung cho mọi dự án ở châu Âu; công bố sau ngày chụp 1–2 tháng |
| Sản phẩm GACOS | cho `gacos` | đặt hàng trên http://www.gacos.net (không có API): vùng, giờ UTC, danh sách ngày lấy từ `geoeyes gacos-order`; nhận qua e-mail | giải nén vào một thư mục: `<YYYYMMDD>.ztd` + `<YYYYMMDD>.ztd.rsc`, hoặc `<YYYYMMDD>.ztd.tif`; đặt `[atmosphere.gacos] dir` | ngày nào không có tệp thì giữ APS tuyến tính |
| `[aoi] bbox` | cho `gacos-order` | project.toml | `[aoi] bbox = [W, S, E, N]` | vùng đặt hàng = bbox + 0,1° |

Danh sách kiểm tra trước khi chạy:

- [ ] dự án đã có sản phẩm `ps` (`geoeyes status <project>`);
- [ ] `geoeyes check` thấy `~/.cdsapirc`, và đã chấp nhận cả hai giấy phép CDS (ERA5, CERRA);
- [ ] các ngày nằm trong phạm vi của mô hình: ERA5 từ 1940 đến khoảng 6 ngày trước, CERRA từ 1984-09 đến khoảng 45
      ngày trước và chỉ trong miền của nó, GACOS từ 2016 (danh mục trong `processing/atmosphere/models.py`);
- [ ] với GACOS: thư mục có mỗi ngày một tệp và `[atmosphere.gacos] dir` trỏ đúng tới đó;
- [ ] chồng ảnh không có thời điểm chụp theo ngày (chồng ảnh cũ) đã đặt `[atmosphere.era5] fallback_utc`.

## 3. Phương pháp

### 3.1 Độ trễ thiên đỉnh tại từng điểm (ERA5, CERRA)

Tính theo từng cột mô hình (TRAIN `aps_weather_model_SAR.m`, Jolivet et al. 2011), trong `era5/delays.py`:

1. nhiệt độ T, độ ẩm tương đối RH và địa thế vị ở mọi mực áp suất được nội suy song tuyến tới điểm; địa thế vị đổi
   sang độ cao hình học với gia tốc trọng trường phụ thuộc vĩ độ;
2. lấy mẫu lại profile mỗi 15 m, lên tới `Z_TOP` = 15 km;
3. áp suất hơi nước e = RH/100 · e_sat(T) (pha trộn nước/băng giữa 250,16 và 273,16 K);
4. độ trễ ướt ZWD(h) = 10⁻⁶ ∫ₕ^15 km [(k₂ − k₁·R_d/R_v)·e/T + k₃·e/T²] dz, độ trễ thuỷ tĩnh
   ZHD(h) = 10⁻⁶ · k₁·R_d/g · (P(h) − P(15 km)), với k₁ = 0,776, k₂ = 0,716, k₃ = 3,75·10³ (Pa, K),
   R_d = 287,05, R_v = 461,495;
5. cả hai được lấy mẫu lại mỗi 5 m và đọc tại độ cao của điểm (cắt ở 0 m).

ERA5: 20 mực áp suất (1000 đến 100 hPa), vùng = bbox của các điểm ± `buffer_deg` (2,0°), mỗi giờ. CERRA: 19 mực
(không có 650/550 hPa nhưng có 825 hPa), lưới Lambert 5,5 km, 3 giờ một lần, đọc trên cửa sổ quanh các điểm ±3 ô.

**Thời gian.** Mỗi lần chụp lấy hai thời điểm phân tích kẹp hai bên (1 giờ với ERA5, 3 giờ với CERRA), trọng số
tuyến tính; bỏ thời điểm thứ hai khi lần chụp cách thời điểm thứ nhất khoảng một phút trở xuống.

### 3.2 GACOS

Lưới độ trễ thiên đỉnh toàn phần của ngày được nội suy song tuyến tới các điểm; giá trị 0 là không có dữ liệu.
Không cần nội suy theo độ cao: GACOS đã tính sẵn ở mặt đất.

### 3.3 Từ độ trễ thiên đỉnh sang pha giao thoa

`slant.py`: độ trễ nghiêng = độ trễ thiên đỉnh / cos θ (θ = góc tới, cắt trong [0,05; π/2 − 0,01] rad);
φ_SAR = −4π/λ · độ trễ nghiêng; giao thoa đồ k của chồng ảnh (ảnh tham chiếu r) nhận φ_k = φ_SAR[r] − φ_SAR[k].
Thành phần: `[atmosphere.era5] component = total` (mặc định), `hydro` hoặc `wet` (ERA5 và CERRA).

Sau đó `centre_weather` cộng thêm, cho từng giao thoa đồ, hằng số làm (pha đã giải chập − mô hình) có trung bình 0
trên các điểm, giống hệ số chặn của APS tuyến tính. Thiếu bước này, độ lệch chung toàn cảnh của mô hình sẽ dịch
mọi điểm ở ngày đó.

### 3.4 Chọn theo từng giao thoa đồ: `select`

Trong bộ xử lý `ps` (`processing/ps/aps.py`), ở lượt giải chập thứ hai (`[ps] subtr_tropo = "y"`, mặc định):

- APS tuyến tính là đường bình phương tối thiểu có trọng số φ = a·h + b cho từng giao thoa đồ (`[ps] aps_non_defo`:
  chỉ hồi quy trên một đa giác nền không biến dạng);
- `select = "auto"` (mặc định): `choose_aps` lấy pha đã giải chập ở lượt 1, trừ chuyển dịch tuyến tính và sai số
  góc nhìn (sai số DEM) của từng điểm (ma trận mũ h), rồi với mỗi giao thoa đồ so phương sai đã khử trung bình của
  phần dư khi trừ APS thời tiết và khi trừ APS tuyến tính, các giao thoa đồ khác giữ lựa chọn hiện tại (hạ theo toạ
  độ, tối đa 5 vòng, trên tối đa 200 000 điểm). Mô hình được giữ ở nơi phương sai nhỏ hơn; nơi khác, và nơi mô hình
  không có dữ liệu, dùng APS tuyến tính;
- `select = "all"`: dùng mô hình ở mọi nơi có dữ liệu, còn lại dùng tuyến tính.

Nhật ký in mỗi giao thoa đồ một dòng (`APS <date>: weather|linear (residual …, − weather …, − linear … rad2)`), và
`summary.json` của lần chạy liệt kê `aps.weather_ifgs`.

### 3.5 Các bộ xử lý khác

- `ps_lite`: cùng các mô hình; với `auto`, mô hình được giữ ở giao thoa đồ nào nó tốt hơn **không** trừ APS
  (`ps_lite` không có APS tuyến tính); tuỳ chọn `[ps_lite] tropo` riêng của nó là một hồi quy pha – độ cao khác,
  nằm trong bước giải chập.
- Cập nhật gia tăng (`processing/ps/update.py`): mỗi ngày mới dùng mô hình nếu mô hình phủ hơn 50 % số điểm và
  phương sai phần dư nhỏ hơn khi dùng APS tuyến tính.

### 3.6 Thử các mô hình trên một sản phẩm (`geoeyes atmosphere`)

`validation/atmosphere.py`, không xử lý lại gì:

1. đọc `phase/unwrapped − phase/scla` của lần chạy `ps`; lấy mẫu tối đa `max_points` (200 000, `seed` 0) điểm có
   pha hữu hạn;
2. phần dư r = pha đó trừ chuyển dịch tuyến tính và sai số DEM của từng điểm, khử trung bình theo giao thoa đồ;
3. với `none`, `linear` và từng mô hình (`models = "auto"`: các mô hình dùng được trong danh mục, thêm `gacos` khi
   đã đặt `[atmosphere.gacos] dir`), tính phần dư sau khi trừ APS (khử trung bình như trong bộ xử lý; dùng tuyến
   tính ở nơi mô hình không có dữ liệu);
4. mỗi mô hình: `std_mm` theo giao thoa đồ (độ lệch chuẩn của r × λ/4π), `median_std_mm`, `reduction_pct` = trung
   vị theo các giao thoa đồ của 100·(1 − σ²_mô hình / σ²_none), `best_ifgs` (số giao thoa đồ mà nó cho độ lệch
   chuẩn nhỏ nhất), `r_height` (tương quan phần dư với độ cao), `aps_std_mm`, `coverage`;
5. bản đồ trên lưới kinh vĩ `grid` × `grid` (256): phần dư quan sát, APS và phần dư sau từng mô hình.

Mô hình nào lỗi (thiếu khoá CDS, không có dữ liệu) được ghi vào `errors` và không chặn các mô hình khác.

## 4. Các bước triển khai

1. **Kiểm tra quyền truy cập.** `geoeyes check <project>`: dòng `~/.cdsapirc (Copernicus CDS key for ERA5)`.
2. **Xem phạm vi phủ.** Web app: dự án → **Atmosphere** → chọn sản phẩm. Bảng liệt kê mọi mô hình với vùng, ngày
   và cách truy cập (`downloaded by GeoEyes`, `ordered on the website…`, `outside its area`,
   `dates not published yet`, `not supported yet`), kèm bản đồ miền CERRA.
3. **Đặt hàng GACOS (tuỳ chọn, ngoài châu Âu).**
   ```
   geoeyes gacos-order <project> [--track ID]
   ```
   in ra cho từng vệt quỹ đạo: vùng (N/S/W/E = bbox ± 0,1°), giờ UTC trung bình của các ngày, và các ngày chưa có
   trong `[atmosphere.gacos] dir` (mỗi khối 20 ngày, để dán vào biểu mẫu). Nhập vào http://www.gacos.net, giải nén
   sản phẩm nhận qua e-mail vào thư mục, đặt `dir`. Thời gian giao hàng tuỳ GACOS.
4. **Thử các mô hình.**
   ```
   geoeyes atmosphere <project> [--product ID] [--set models=["era5","cerra"]] [--set max_points=200000] [--set grid=256]
   ```
   hoặc nút **Try the models** trong thẻ (chạy nền). Thời gian chủ yếu do tải dữ liệu: mỗi ngày và mỗi giờ phân tích
   một tệp ERA5, mỗi ngày hai tệp CERRA 125 MB (mỗi lần chạy chỉ chờ trong hàng đợi CDS tối đa `max_wait_min` = 20
   phút; chạy lại để lấy nốt). Khi đã có trong bộ đệm: vài phút. Ghi ra
   `analyses/atmosphere/<product>/atmosphere.json` và `grids.npz`. CLI in cho từng mô hình
   `median_std_mm (reduction_pct %)`.
5. **Áp dụng.** Nút **Use** trên dòng mô hình (đặt `[atmosphere] method` và bắt đầu chạy), hoặc sửa `project.toml`:
   ```toml
   [atmosphere]
   method = "era5"          # none | era5 | cerra | gacos
   select = "auto"
   era5 = { component = "total", buffer_deg = 2.0, workers = 4 }
   cerra = { max_wait_min = 20 }
   gacos = { dir = "D:/data/gacos/<project>_<track>" }
   ```
   rồi `geoeyes run <project>`. Các bước 1–5 của bộ xử lý `ps` lấy lại từ checkpoint
   (`ps_runs/<id>/checkpoints/step<N>.json`), nên chỉ bước giải chập và các bước sau chạy lại. Một phiên bản sản phẩm
   mới được ghi ra.

## 5. Kết quả và cách đọc

| Tệp / trường | Ý nghĩa |
|---|---|
| `atmosphere.json` → `models.<m>.median_std_mm` | độ tản mát trung vị (mm, theo LOS) của phần dư còn lại; càng nhỏ càng tốt |
| `models.<m>.reduction_pct` | tỉ lệ trung vị phương sai phần dư được khử so với không trừ APS; âm = mô hình thêm nhiễu |
| `models.<m>.best_ifgs` | số giao thoa đồ mà mô hình này để lại ít tản mát nhất |
| `models.<m>.r_height` | theo từng giao thoa đồ, tương quan phần dư với độ cao; gần 0 sau một mô hình tốt |
| `models.<m>.coverage` | tỉ lệ cặp (điểm, giao thoa đồ) mà mô hình có giá trị |
| `errors`, `catalogue`, `acquisition_utc`, `span_days` | lỗi, phạm vi phủ của mô hình, thời điểm chụp đã dùng, độ dài chồng ảnh |
| `grids.npz` (`obs`, `aps__<m>`, `res__<m>`) | bản đồ từng giao thoa đồ, mm; trong thẻ, ba bản đồ dùng chung một thang màu |
| nhật ký chạy / `ps_runs/<id>/summary.json` → `aps` | sau khi áp dụng: `method`, `select`, `weather_ifgs` (các ngày đã dùng mô hình) |

Thẻ đánh dấu mô hình tốt nhất (`median_std_mm` nhỏ nhất) và mô hình đang dùng (`in use`). Chồng ảnh ngắn hơn 90
ngày có cảnh báo: vài mm khí quyển thành hàng chục mm/năm.

## 6. Kiểm tra chất lượng

- `reduction_pct` của mô hình được chọn lớn hơn của `linear`, và `best_ifgs` chiếm phần rõ rệt trong số giao thoa đồ.
- Với `select = "auto"`, tỉ lệ giao thoa đồ giữ mô hình được báo cáo. Ghi trong chú thích của dự án: Mexico City S1
  asc 078, ERA5 được chọn ở 5 trên 15; Mexico City Capella, 10 trên 17 (`project.toml` của `projects/mexico_s1`,
  `mexico_capella`).
- Trên bản đồ vài giao thoa đồ: APS của mô hình có hình dạng giống phần dư quan sát (theo địa hình, mảng lớn); phần
  dư sau đó phẳng hơn.
- Sau khi chạy lại: bản đồ vận tốc mất các mảng bám theo địa hình hoặc theo một ngày riêng; so hai phiên bản
  (Explorer, so sánh sản phẩm) và so với GNSS ([gnss-calibration.md](gnss-calibration.md)).
- Không có dòng mô hình nào có `coverage` thấp xa dưới 1 bị che bởi trung vị đẹp (thiếu ngày GACOS hoặc CERRA).

## 7. Hạn chế và lỗi thường gặp

- **Độ phân giải.** Mô hình khử được phần trễ phân tầng theo độ cao và nhiễu loạn lớn hơn vài ô của nó. Ô nhiễu loạn
  vài km (vùng núi, đối lưu) nhỏ hơn ô CERRA (5,5 km) và nhỏ hơn rất nhiều ô ERA5 (~31 km). Ở Tenerife (ICEYE, 15
  ngày, 2026-02), ±2,5 mm khí quyển như vậy thành ±60 mm/năm ([hướng dẫn](../guide/atmosphere.md) §5): kéo dài chồng
  ảnh có ích hơn mô hình mịn hơn.
- **Đối lưu chiều tối vùng nhiệt đới.** ERA5 bỏ sót (Hà Nội quỹ đạo lên, [hướng dẫn tầng điện ly](../guide/ionosphere.md)
  §6); GACOS là phương án thay thế.
- **Độ trễ công bố và dung lượng CERRA.** 1–2 tháng sau ngày chụp; ~125 MB mỗi thời điểm phân tích; hàng đợi CDS có
  thể cần nhiều lần chạy (yêu cầu đang chờ giữ trong `pending.json`).
- **Sai thời điểm chụp.** `fallback_utc` sai thì mọi ngày lấy nhầm thời điểm phân tích.
- **Ngày thiếu dữ liệu** lặng lẽ quay về APS tuyến tính, chỉ có cảnh báo trong nhật ký: kiểm tra `coverage`.
- `geoeyes atmosphere` đọc lần chạy `ps` đứng sau sản phẩm; sau khi chạy lại phải chạy nó lần nữa trên sản phẩm mới.
- Biểu mẫu đặt hàng GACOS không có API: `gacos-order` chỉ in ra nội dung cần nhập.

## 8. Áp dụng cho vùng hoặc vệ tinh mới

- **Châu Âu, Bắc Phi, quần đảo Canary, Azores:** thử `cerra` so với `era5`.
- **Nơi khác (Việt Nam, Mexico):** `era5` (tự động) hoặc `gacos` (đặt hàng). Ngoài châu Âu, không có mô hình miễn
  phí nào mịn hơn ERA5 tải tự động được cho các ngày đã qua ([hướng dẫn](../guide/atmosphere.md) §2).
- **Vệ tinh:** không cần đổi gì khi chồng ảnh có `sensing_mid_utc` hoặc tên cảnh có dấu thời gian; nếu không, đặt
  `fallback_utc` bằng giờ bay qua.
- **Giữ nguyên được:** `select = "auto"` (bảo vệ trước mô hình sai ở vài ngày), `component = "total"`, các bộ đệm
  (dùng chung cho mọi dự án trong không gian làm việc).
- **Thói quen tại chỗ:** Hà Nội S1 và Mexico City (S1, Capella) dùng `era5`; dự án Hà Nội CSK giữ `none`.

## 9. Tài liệu tham khảo

- Mã: `src/geoeyes/processing/atmosphere/` (`models.py`, `weather.py`, `era5/`, `cerra.py`, `gacos.py`,
  `slant.py`, `times.py`), `src/geoeyes/processing/ps/aps.py`, `src/geoeyes/controller/phases/ps.py`
  (`weather_params`, mã cũ `a_e`, `a_eh`, `a_ew`, `a_gacos`), `src/geoeyes/validation/atmosphere.py`,
  `src/geoeyes/api/atmosphere.py`, `webapp/src/components/Atmosphere.tsx`, `src/geoeyes/config/schema.py`
  (`AtmosphereSection`).
- Hướng dẫn: [../guide/atmosphere.md](../guide/atmosphere.md), [../guide/incremental.md](../guide/incremental.md) §7
  (đặt hàng GACOS), [../guide/ionosphere.md](../guide/ionosphere.md).
- Skill: [insar-processing.md](insar-processing.md), [ionosphere.md](ionosphere.md),
  [gnss-calibration.md](gnss-calibration.md).
- Bài báo: Jolivet R, Grandin R, Lasserre C, Doin MP, Peltzer G (2011) Systematic InSAR tropospheric phase delay
  corrections from global meteorological reanalysis data. *GRL* 38:L17311. Yu C, Li Z, Penna NT, Crippa P (2018)
  Generic atmospheric correction model for InSAR observations (GACOS). *JGR Solid Earth* 123:9202–9222. Hersbach H
  et al. (2020) The ERA5 global reanalysis. *QJRMS* 146:1999–2049. Ridal M et al. (2024) CERRA, the Copernicus
  European Regional Reanalysis system. *QJRMS*. Bekaert DPS et al. (2015) Statistical comparison of InSAR
  tropospheric correction techniques (TRAIN). *RSE* 170:40–47.
