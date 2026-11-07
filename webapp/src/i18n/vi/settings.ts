// The project settings form (geoeyes.api.settings): section titles in pipeline order, the [ps] groups by StaMPS
// step and the help line of every parameter. Parameter names ([section] key) stay in English: they are the TOML keys.
export const SETTINGS: Record<string, string> = {
  // section titles, numbered by the pipeline phase that reads them
  Project: "Dự án",
  "Area of interest": "Vùng quan tâm",
  "1 · Acquisition": "1 · Tải ảnh",
  "2 · Stack: interferogram network": "2 · Stack: mạng giao thoa",
  "2 · Stack: coregistration": "2 · Stack: đồng đăng ký",
  "3 · Phase linking (distributed scatterers)": "3 · Liên kết pha (điểm phân tán)",
  "4 · PS step 1 · candidates": "4 · PS bước 1 · điểm ứng viên",
  "4 · PS step 2 · temporal coherence and DEM error": "4 · PS bước 2 · độ nhất quán thời gian và sai số DEM",
  "4 · PS step 3 · point selection": "4 · PS bước 3 · chọn điểm",
  "4 · PS step 4 · weeding": "4 · PS bước 4 · lọc điểm",
  "4 · PS step 5 · reference area": "4 · PS bước 5 · vùng tham chiếu",
  "4 · PS step 6 · unwrapping": "4 · PS bước 6 · giải chập pha (unwrap)",
  "4 · PS step 7 · DEM error, orbit ramps and atmosphere": "4 · PS bước 7 · sai số DEM, ramp quỹ đạo và khí quyển",
  "4 · PS step 7 · weather-model atmosphere": "4 · PS bước 7 · khí quyển từ mô hình thời tiết",
  "4 · PS step 8 · spatially correlated noise (SCN)": "4 · PS bước 8 · nhiễu tương quan không gian (SCN)",
  "4 · PS · memory and compatibility": "4 · PS · bộ nhớ và tương thích",
  "4 · SBAS (in place of PS when method = sbas)": "4 · SBAS (thay cho PS khi method = sbas)",
  "4 · Point engine (StaMPS parameters)": "4 · Bộ xử lý điểm (tham số StaMPS)",
  "5 · Export": "5 · Xuất dữ liệu",
  "6 · Report": "6 · Báo cáo",

  // project, AOI, acquisition, stack
  "Free text shown in the tree, the overview and the report": "Mô tả tự do, hiện trong cây dự án, trang tổng quan và báo cáo",
  "psi: persistent scatterers; psds: PS + distributed scatterers (phase linking)":
    "psi: điểm tán xạ bền vững; psds: PS + điểm phân tán (liên kết pha)",
  "West, south, east, north (WGS84 degrees)": "Tây, nam, đông, bắc (độ WGS84)",
  "Sentinel-1 acquisitions between these dates are downloaded from ASF": "Tải từ ASF các lần chụp Sentinel-1 trong khoảng ngày này",
  "Keep the first N acquisitions of each month (0 = all)": "Giữ N lần chụp đầu tiên của mỗi tháng (0 = tất cả)",
  "Folder of raw scenes shared by projects ('' = workspace archive)":
    "Thư mục ảnh gốc dùng chung giữa các dự án ('' = kho của workspace)",
  "Reference date of the stack ('auto' = the most central acquisition)": "Ngày ảnh chủ của stack ('auto' = ngày nằm giữa nhất)",
  "Largest perpendicular baseline kept (m)": "Đường cơ sở vuông góc lớn nhất được giữ (m)",
  "Largest temporal baseline kept (days, 0 = no limit)": "Đường cơ sở thời gian lớn nhất được giữ (ngày, 0 = không giới hạn)",
  "srtm-1 or copernicus-30 (downloaded when missing), a folder of .hgt or a GeoTIFF":
    "srtm-1 hoặc copernicus-30 (tự tải khi chưa có), một thư mục .hgt hoặc một GeoTIFF",
  "Enhanced spectral diversity (Sentinel-1 azimuth fine coregistration)":
    "Enhanced spectral diversity (đồng đăng ký tinh theo phương vị của Sentinel-1)",
  "Range, azimuth looks (1, 1 = full resolution)": "Số look theo cự ly, phương vị (1, 1 = độ phân giải đầy đủ)",
  "Keep coregistered dates when the stack is extended (same reference)":
    "Giữ các ngày đã đồng đăng ký khi mở rộng stack (cùng ảnh chủ)",

  // [selection], [phase_linking]
  "Amplitude dispersion threshold of the PS candidates": "Ngưỡng phân tán biên độ (DA) của điểm PS ứng viên",
  "Robust amplitude dispersion (median / MAD)": "Phân tán biên độ bền vững (trung vị / MAD)",
  "Minimum coherence of a distributed scatterer": "Độ nhất quán tối thiểu của một điểm phân tán",
  "Mask water before the selection": "Che vùng nước trước khi chọn điểm",
  "Phase linking of distributed scatterers before the point engine": "Liên kết pha các điểm phân tán trước bộ xử lý điểm",
  "Phase linking estimator": "Bộ ước lượng liên kết pha",
  "Statistically homogeneous pixels: ad = Anderson-Darling, ks = Kolmogorov-Smirnov":
    "Pixel đồng nhất thống kê (SHP): ad = Anderson-Darling, ks = Kolmogorov-Smirnov",
  "Half window of the SHP search (rows, columns)": "Nửa cửa sổ tìm SHP (hàng, cột)",
  "Significance level of the SHP test": "Mức ý nghĩa của phép thử SHP",
  "Minimum number of SHP for a distributed scatterer": "Số SHP tối thiểu cho một điểm phân tán",
  "PS below this amplitude dispersion keep their own SLC (0 = link all)":
    "PS có DA dưới ngưỡng này giữ SLC gốc của mình (0 = liên kết tất cả)",
  "Gaussian post-filter of the linked phase (0 = off)": "Lọc Gauss sau liên kết pha (0 = tắt)",

  // [atmosphere], [export], [report]
  "Weather-model APS for step 7: none, era5 (needs ~/.cdsapirc), cerra or gacos":
    "APS từ mô hình thời tiết cho bước 7: none, era5 (cần ~/.cdsapirc), cerra hoặc gacos",
  "auto: weather correction kept only where it reduces the phase; all: everywhere":
    "auto: chỉ giữ hiệu chỉnh thời tiết ở những giao thoa đồ mà nó làm giảm pha; all: dùng cho mọi giao thoa đồ",
  "GIS formats written for each product": "Các định dạng GIS được xuất cho mỗi sản phẩm",
  "Folder the PDF report is also copied to ('' = none)": "Thư mục nhận thêm một bản báo cáo PDF ('' = không)",

  // [ps] step 2
  "Largest DEM error searched (m); auto = median height of ambiguity / 4 (baselines about their median); auto_master = the same about the master (legacy CSK / ICEYE)":
    "Sai số DEM lớn nhất được tìm (m); auto = trung vị độ cao mơ hồ / 4 (B⊥ tính quanh trung vị); auto_master = như trên nhưng tính quanh ảnh chủ (CSK / ICEYE cũ)",
  "Grid cell (m) of the adaptive phase filter that estimates the neighbourhood phase":
    "Ô lưới (m) của bộ lọc pha thích nghi dùng để ước lượng pha lân cận",
  "Weighting of the PS in that filter: P-square (coherence) or SNR": "Trọng số PS trong bộ lọc đó: P-square (độ nhất quán) hoặc SNR",
  "Window (grid cells) of the CLAP adaptive filter": "Cửa sổ (số ô lưới) của bộ lọc thích nghi CLAP",
  "Low-pass wavelength (m) of the CLAP filter": "Bước sóng thông thấp (m) của bộ lọc CLAP",
  "CLAP: weight of the adaptive (spectral) part": "CLAP: trọng số của phần thích nghi (phổ)",
  "CLAP: exponent of the spectral weighting": "CLAP: số mũ của trọng số phổ",
  "Stop iterating when the mean temporal coherence changes less than this":
    "Dừng lặp khi độ nhất quán thời gian trung bình thay đổi ít hơn giá trị này",
  "Most iterations of the coherence estimation": "Số vòng lặp tối đa khi ước lượng độ nhất quán",
  "y: score the DEM-error fit for ambiguity and regularise it spatially (legacy CSK)":
    "y: chấm điểm độ mơ hồ của phép khớp sai số DEM và làm trơn theo không gian (CSK cũ)",
  "Ambiguity thresholds from the data (with dem_error_ambiguity)": "Ngưỡng độ mơ hồ lấy từ dữ liệu (khi bật dem_error_ambiguity)",
  "Ambiguity score below which the DEM error is rejected": "Điểm mơ hồ dưới ngưỡng này thì loại sai số DEM",
  "Ambiguity score above which the DEM error is trusted": "Điểm mơ hồ trên ngưỡng này thì tin sai số DEM",
  "Weight of the spatial regularisation of the DEM error": "Trọng số làm trơn không gian của sai số DEM",
  "Iterations of the spatial regularisation": "Số vòng lặp làm trơn không gian",

  // [ps] step 3
  "PERCENT: share of random phase allowed; DENSITY: random points per km²":
    "PERCENT: tỷ lệ pha ngẫu nhiên cho phép; DENSITY: số điểm ngẫu nhiên trên mỗi km²",
  "PERCENT: % of the selected points allowed to be random phase": "PERCENT: % số điểm được chọn được phép là pha ngẫu nhiên",
  "DENSITY: random-phase points per km² allowed": "DENSITY: số điểm pha ngẫu nhiên cho phép trên mỗi km²",
  "Lowest coherence threshold, whatever the amplitude dispersion": "Ngưỡng độ nhất quán thấp nhất, bất kể DA",
  "Drop points whose coherence varies more than this between iterations (0 = off)":
    "Loại điểm có độ nhất quán dao động quá giá trị này giữa các vòng lặp (0 = tắt)",
  "How the random-phase histogram is scaled: low_coherence or population (legacy CSK)":
    "Cách chuẩn hoá histogram pha ngẫu nhiên: low_coherence hoặc population (CSK cũ)",
  "SLC oversampling factor (1 = none)": "Hệ số lấy mẫu dày của SLC (1 = không)",
  "Re-estimate the coherence of the selected points with their neighbourhood phase":
    "Ước lượng lại độ nhất quán của các điểm đã chọn bằng pha lân cận",

  // [ps] step 4
  "Time window (days) of the smoothing used to judge the phase noise of a point":
    "Cửa sổ thời gian (ngày) của phép làm trơn dùng để đánh giá nhiễu pha của một điểm",
  "Drop points whose phase noise (rad) against their neighbours is above this":
    "Loại điểm có nhiễu pha (rad) so với lân cận lớn hơn giá trị này",
  "Drop points at zero height (sea, DEM voids)": "Loại điểm có độ cao bằng 0 (biển, lỗ trống DEM)",
  "Of adjacent pixels keep only the best one": "Trong các pixel liền kề chỉ giữ pixel tốt nhất",
  "Points kept per group of adjacent pixels": "Số điểm giữ lại trong mỗi nhóm pixel liền kề",
  "Drop points that are noisy against their neighbours": "Loại các điểm nhiễu so với lân cận",

  // [ps] step 5
  "Centre (lon, lat) of the reference area; 0, 0 = no area (all points, or ref_auto)":
    "Tâm (kinh độ, vĩ độ) của vùng tham chiếu; 0, 0 = không đặt vùng (mọi điểm, hoặc ref_auto)",
  "Radius (m) of the reference area around that centre; inf = all points":
    "Bán kính (m) của vùng tham chiếu quanh tâm đó; inf = mọi điểm",
  "y: reference = the stable periphery of the scene (when no centre is given)":
    "y: tham chiếu = vùng rìa ổn định của cảnh (khi không đặt tâm)",

  // [ps] step 6
  "n: the grid unwraps the phase of each point (StaMPS default); y: the smoother patch phase, then each point's residual (legacy)":
    "n: lưới giải chập pha của chính từng điểm (mặc định StaMPS); y: giải chập pha patch đã làm trơn rồi cộng phần dư của từng điểm (cách cũ)",
  "Cell (m) of the unwrapping grid (10 m usual; 50 m HCMC)": "Ô lưới giải chập pha (m) (thường 10 m; TP.HCM 50 m)",
  "Filter the grid phase before unwrapping": "Lọc pha lưới trước khi giải chập",
  "Grid prefilter: gaussian, goldstein (coherence-adaptive) or none": "Bộ lọc lưới: gaussian, goldstein (thích nghi theo độ nhất quán) hoặc none",
  "σ of the Gaussian prefilter (m); auto = (unwrap_gold_n_win / 8) × 10 m, the same at any grid size; cells = the legacy σ in cells (grows with the grid)":
    "σ của bộ lọc Gauss (m); auto = (unwrap_gold_n_win / 8) × 10 m, như nhau ở mọi cỡ lưới; cells = σ cũ tính theo ô (to lên theo cỡ lưới)",
  "y: filter the unit phasor of each cell (a cell of many points no longer outweighs its neighbours)":
    "y: lọc phasor đơn vị của từng ô (ô có nhiều điểm không còn lấn át ô bên cạnh)",
  "Window (cells) of the Goldstein filter; also sets the Gaussian σ in auto":
    "Cửa sổ (số ô) của bộ lọc Goldstein; cũng quyết định σ Gauss ở chế độ auto",
  "Strength of the Goldstein filter (0-1)": "Độ mạnh của bộ lọc Goldstein (0-1)",
  "Coherence below which the Goldstein filter acts at full strength": "Dưới mức độ nhất quán này bộ lọc Goldstein lọc ở độ mạnh tối đa",
  "Time window (days) of the space-time unwrapping; auto = a quarter of the data span (at least 4 sampling intervals, 60-730)":
    "Cửa sổ thời gian (ngày) của giải chập không gian–thời gian; auto = một phần tư khoảng thời gian dữ liệu (ít nhất 4 chu kỳ chụp, 60-730)",
  "Estimate the look-angle (DEM) error in the space-time unwrapping": "Ước lượng sai số góc nhìn (DEM) trong giải chập không gian–thời gian",
  "Unwrap each grid edge in time by its linear rate first (keeps fast motion)":
    "Giải chập từng cạnh lưới theo thời gian bằng tốc độ tuyến tính của nó trước (giữ được chuyển động nhanh)",
  "Largest rate searched for an edge (mm/yr, line of sight)": "Tốc độ lớn nhất được tìm cho một cạnh (mm/năm, theo LOS)",
  "The IRLS takes the cycle count of each grid step from the edge model": "IRLS lấy số chu kỳ của từng bước lưới từ mô hình cạnh",
  "Linear rate of every point from the point network, removed before the grid and added back (a road faster than its cell keeps its cycles); auto = with >= unwrap_ps_rate_min_ifg interferograms and a reliable network":
    "Tốc độ tuyến tính của từng điểm lấy từ mạng điểm, trừ đi trước khi lên lưới rồi cộng lại (một con đường lún nhanh hơn ô của nó không mất chu kỳ); auto = khi có ≥ unwrap_ps_rate_min_ifg giao thoa đồ và mạng đủ tin cậy",
  "Longest arc (m) between two points of that network": "Cạnh dài nhất (m) giữa hai điểm của mạng đó",
  "Fewest interferograms for unwrap_ps_rate = auto": "Số giao thoa đồ tối thiểu để unwrap_ps_rate = auto được bật",
  "Most iterations of the IRLS spatial unwrapping": "Số vòng lặp tối đa của giải chập không gian IRLS",
  "IRLS stops below this residual (rad)": "IRLS dừng khi phần dư nhỏ hơn giá trị này (rad)",
  "IRLS weight floor": "Trọng số tối thiểu của IRLS",
  "Align the IRLS constant before snapping to the wrapped phase (avoids one-cycle region slips near ±π)":
    "Căn hằng số IRLS trước khi khớp về pha gói (tránh cả vùng lệch một chu kỳ khi pha gần ±π)",

  // [ps] step 7, 8
  "Remove the atmosphere (APS) from the velocity: linear in height, or the weather model of [atmosphere]; n on flat deltas, where it can absorb subsidence (v-do)":
    "Trừ khí quyển (APS) khỏi vận tốc: tuyến tính theo độ cao, hoặc mô hình thời tiết của [atmosphere]; đặt n ở vùng đồng bằng phẳng, nơi nó có thể nuốt mất lún (v-do)",
  "Orbit ramps: n = keep, y = remove a plane per interferogram, auto = remove the part that changes between dates":
    "Ramp quỹ đạo: n = giữ, y = trừ một mặt phẳng cho mỗi giao thoa đồ, auto = trừ phần thay đổi giữa các ngày",
  "auto may also remove a steady planar trend without a stable area": "Cho phép auto trừ cả xu hướng mặt phẳng ổn định khi không có vùng ổn định",
  "Time window (days) of the SCN temporal filter (step 8)": "Cửa sổ thời gian (ngày) của bộ lọc SCN theo thời gian (bước 8)",
  "Spatial wavelength (m) of the SCN filter": "Bước sóng không gian (m) của bộ lọc SCN",
  "SCN temporal low-pass: linear (keeps the trend) or mean (StaMPS)": "Lọc thông thấp thời gian của SCN: linear (giữ xu hướng) hoặc mean (StaMPS)",

  // [ps] memory, compatibility
  "Points per block in step 2 (memory)": "Số điểm mỗi khối ở bước 2 (bộ nhớ)",
  "Points per block in step 3 (memory)": "Số điểm mỗi khối ở bước 3 (bộ nhớ)",
  "Interferograms per block in step 4 (memory)": "Số giao thoa đồ mỗi khối ở bước 4 (bộ nhớ)",
  "y: reproduce the legacy engine with its bugs (parity tests only)": "y: tái tạo engine cũ cùng các lỗi của nó (chỉ cho test parity)",
};
