// Hazard page (pages/Hazard.tsx).
export const HAZARD: Record<string, string> = {
  // levels and classes
  "Very low": "Rất thấp",
  Low: "Thấp",
  Moderate: "Trung bình",
  High: "Cao",
  "Very high": "Rất cao",
  "not assessed": "chưa đánh giá",
  "Hazard matrix": "Ma trận nguy cơ",
  intensity: "cường độ",
  "secondary class": "lớp phụ",
  MAP: "BẢN ĐỒ",
  "What this map shows": "Bản đồ này cho biết",
  subsidence: "sụt lún",
  landslide: "trượt lở",
  "above stability": "trên ngưỡng ổn định",
  stable: "ổn định",
  "Subsidence: angular distortion in {n} years": "Sụt lún: góc biến dạng sau {n} năm",
  "structural damage": "hư hại kết cấu",
  cracking: "nứt",
  "beyond the safe limit": "vượt giới hạn an toàn",
  "Landslide: susceptibility map, else slope classes {s}°": "Trượt lở: bản đồ tính nhạy cảm, nếu không có thì lớp độ dốc {s}°",
  "sinking / downslope, fast": "lún / trượt xuống dốc, nhanh",
  "about stable": "gần như ổn định",
  "rising / upslope": "nâng / ngược dốc",
  "more rain, more motion": "mưa nhiều, chuyển dịch nhiều",
  "more rain, less sinking / uplift": "mưa nhiều, lún ít hơn / nâng",
  "not significant / not assessed": "không có ý nghĩa / chưa đánh giá",
  "not significant": "không có ý nghĩa",
  "{n} month": "{n} tháng",
  "{n} months": "{n} tháng",
  "subsidence (vertical motion)": "sụt lún (chuyển dịch thẳng đứng)",
  "landslide (slope ≥ {s}°, motion down the slope)": "trượt lở (dốc ≥ {s}°, chuyển dịch xuống dốc)",
  "{n} warning(s): see the notifications": "{n} cảnh báo: xem trong mục thông báo",

  // the thematic maps
  "Hazard level": "Mức nguy cơ",
  "Intensity (InSAR)": "Cường độ (InSAR)",
  "Distortion / slope": "Biến dạng / độ dốc",
  Rate: "Tốc độ",
  "Rain coupling": "Liên hệ với mưa",
  "Rain lag": "Độ trễ theo mưa",
  Mode: "Loại quá trình",
  "The final level of each 100 m cell: how fast the ground moves (InSAR intensity) combined with what the motion can do (distortion for subsidence, slope for landslides).":
    "Mức nguy cơ cuối cùng của từng ô 100 m: mặt đất chuyển dịch nhanh đến đâu (cường độ InSAR) kết hợp với việc chuyển dịch đó có thể gây ra gì (biến dạng với sụt lún, độ dốc với trượt lở).",
  "Red cells need attention first: fast motion where it bends buildings or on steep ground.":
    "Ô đỏ cần chú ý trước tiên: chuyển dịch nhanh ở nơi làm cong vênh công trình hoặc trên sườn dốc.",
  "Read the level in the matrix: intensity (rows) × secondary class (columns).":
    "Đọc mức trong ma trận: cường độ (hàng) × lớp phụ (cột).",
  "Grey cells were not assessed (too few points, or a slope the satellite cannot see).":
    "Ô xám chưa được đánh giá (quá ít điểm, hoặc sườn dốc mà vệ tinh không nhìn thấy được chuyển dịch).",
  "How fast each cell moves in the direction that matters (sinking on flat ground, down the slope on hillsides), in four classes.":
    "Mỗi ô chuyển dịch nhanh đến đâu theo hướng đáng quan tâm (lún ở vùng bằng phẳng, xuống dốc ở sườn đồi), chia bốn lớp.",
  "I0: within the measurement noise (stable). I1 to I3: slow to fast motion.":
    "I0: nằm trong nhiễu đo (ổn định). I1 đến I3: chuyển dịch từ chậm đến nhanh.",
  "A cell goes up one class if its motion follows the rain and a dry or wet year would make it faster, or if it accelerates.":
    "Một ô được nâng thêm một lớp nếu chuyển dịch của nó theo mưa và một năm khô hoặc ướt sẽ làm nó nhanh hơn, hoặc nếu nó đang tăng tốc.",
  "Rates are relative to the product's reference: tie it to GNSS for absolute values.":
    "Tốc độ là tương đối so với tham chiếu của sản phẩm: gắn vào GNSS để có giá trị tuyệt đối.",
  "What the motion can do. Subsidence: how much the ground bends between neighbouring cells over the horizon (angular distortion, compared with building-damage limits). Landslides: how steep the ground is.":
    "Chuyển dịch có thể gây ra gì. Sụt lún: mặt đất bị uốn bao nhiêu giữa các ô kề nhau sau khoảng thời gian dự báo (góc biến dạng, so với các giới hạn gây hư hại công trình). Trượt lở: sườn dốc đến đâu.",
  "S1 and above: differential settlement beyond the safe limit for buildings (1/500); S3: structural damage (1/150).":
    "Từ S1 trở lên: lún lệch vượt giới hạn an toàn cho công trình (1/500); S3: hư hại kết cấu (1/150).",
  "Independent of the reference: it only uses differences between neighbouring cells.":
    "Không phụ thuộc tham chiếu: chỉ dùng chênh lệch giữa các ô kề nhau.",
  "The velocity of each cell in mm per year, along the expected motion: vertical on flat ground, down the slope on hillsides.":
    "Vận tốc của từng ô (mm/năm) theo hướng chuyển dịch dự kiến: thẳng đứng ở vùng bằng phẳng, xuống dốc ở sườn đồi.",
  "Red: sinking (or moving down the slope). Blue: rising (or apparent upslope motion). Grey: about stable.":
    "Đỏ: lún (hoặc trượt xuống dốc). Xanh: nâng (hoặc dịch chuyển ngược dốc biểu kiến). Xám: gần như ổn định.",
  "Values are relative to the product's reference area: a reference that moves shifts the whole map.":
    "Giá trị là tương đối so với vùng tham chiếu của sản phẩm: nếu tham chiếu chuyển dịch, cả bản đồ bị lệch theo.",
  "Where the ground motion follows the rainfall, after removing its steady trend: the correlation between the motion and the accumulated rainfall surplus or deficit of the previous months.":
    "Nơi chuyển dịch mặt đất đi theo lượng mưa, sau khi bỏ xu thế đều: tương quan giữa chuyển dịch và lượng mưa dư hoặc thiếu tích luỹ của các tháng trước.",
  "Only statistically significant cells are coloured (tested against random rainfall timing, corrected for the number of cells).":
    "Chỉ tô màu các ô có ý nghĩa thống kê (kiểm định với thời điểm mưa ngẫu nhiên, đã hiệu chỉnh theo số lượng ô).",
  "Red: more rain, more motion (e.g. wetter slopes slide faster). Blue: more rain, less sinking or uplift (e.g. aquifer recharge).":
    "Đỏ: mưa nhiều, chuyển dịch nhiều (ví dụ sườn ướt trượt nhanh hơn). Xanh: mưa nhiều, lún ít hơn hoặc nâng (ví dụ tầng chứa nước được bổ cập).",
  "Grey: no detectable link, or a series too short (less than a year).":
    "Xám: không phát hiện được liên hệ, hoặc chuỗi quá ngắn (dưới một năm).",
  "For cells where the motion follows the rain: how many months after the rain the motion responds.":
    "Với các ô có chuyển dịch theo mưa: chuyển dịch phản ứng sau mưa bao nhiêu tháng.",
  "0–1 month: fast response (shallow ground). Longer lags: deeper water, slower recharge or drainage.":
    "0–1 tháng: phản ứng nhanh (tầng nông). Trễ dài hơn: nước ở sâu hơn, bổ cập hoặc thoát nước chậm hơn.",
  "Only significant cells are coloured.": "Chỉ tô màu các ô có ý nghĩa thống kê.",
  "Which process each cell is assessed for, from the terrain slope.": "Mỗi ô được đánh giá theo quá trình nào, dựa trên độ dốc địa hình.",
  "Blue: flat ground, assessed as subsidence (vertical motion).": "Xanh: vùng bằng phẳng, đánh giá như sụt lún (chuyển dịch thẳng đứng).",
  "Orange: slopes above the threshold, assessed as landslide (motion down the slope).":
    "Cam: sườn dốc vượt ngưỡng, đánh giá như trượt lở (chuyển dịch xuống dốc).",

  // run panel
  "Hazard zoning": "Phân vùng nguy cơ",
  zoning: "phân vùng",
  "HAZARD ZONING · INSAR + RAINFALL": "PHÂN VÙNG NGUY CƠ · INSAR + LƯỢNG MƯA",
  Product: "Sản phẩm",
  "No product in the workspace": "Không gian làm việc chưa có sản phẩm",
  Cell: "Ô",
  Horizon: "Thời hạn",
  "Max lag": "Trễ tối đa",
  Rain: "Mưa",
  Stable: "Ổn định",
  "Stable ground (e.g. bedrock, a GNSS station): the series are re-referenced to the median of its cells. Empty = the product's reference":
    "Nền ổn định (ví dụ nền đá gốc, một trạm GNSS): các chuỗi được tham chiếu lại theo trung vị của các ô trong vùng này. Để trống = dùng tham chiếu của sản phẩm",
  "reference area: W, S, E, N (optional)": "vùng tham chiếu: T, N, Đ, B (không bắt buộc)",
  "Add the GNSS calibration of this product (Project → Validation → GNSS) to the series before rating them: rates relative to the GNSS frame instead of the product's reference":
    "Cộng hiệu chỉnh GNSS của sản phẩm này (Dự án → Kiểm định → GNSS) vào các chuỗi trước khi xếp lớp: tốc độ tính theo khung GNSS thay vì theo tham chiếu của sản phẩm",
  "GNSS tie": "Gắn vào GNSS",
  "1 station": "1 trạm",
  "GNSS unavailable: restart geoeyes serve (the server predates this page)":
    "Không có GNSS: khởi động lại geoeyes serve (máy chủ cũ hơn trang này)",
  "no GNSS comparison of this product yet (Project → Validation → GNSS)":
    "sản phẩm này chưa được so sánh với GNSS (Dự án → Kiểm định → GNSS)",
  "Running…": "Đang chạy…",
  "Run again": "Chạy lại",
  "Run hazard zoning": "Chạy phân vùng nguy cơ",
  "Reference area: west, south, east, north (degrees)": "Vùng tham chiếu: tây, nam, đông, bắc (độ)",
  "{msg}: the running server predates the Hazard page, restart geoeyes serve":
    "{msg}: máy chủ đang chạy cũ hơn trang Nguy cơ, hãy khởi động lại geoeyes serve",
  "Not zoned yet. The run reads the DEM and the rainfall (CHIRPS, cached; the first time takes a minute) and writes the cells under analyses/hazard of the project.":
    "Chưa phân vùng. Lần chạy đọc DEM và lượng mưa (CHIRPS, có lưu đệm; lần đầu mất khoảng một phút) và ghi các ô vào analyses/hazard của dự án.",

  // summary panel
  SUMMARY: "TÓM TẮT",
  "{n} cells of {m} m · {p} points · {d0} → {d1} ({k} months)": "{n} ô {m} m · {p} điểm · {d0} → {d1} ({k} tháng)",
  level: "mức",
  RAINFALL: "LƯỢNG MƯA",
  "Annual {a}–{b}: dry year (P10)": "Tổng mưa năm {a}–{b}: năm khô (P10)",
  median: "trung vị",
  "wet year (P90)": "năm ướt (P90)",
  "Coupling tested in {n} cells:": "Đã kiểm định liên hệ mưa – biến dạng ở {n} ô:",
  "{n} significant": "{n} ô có ý nghĩa",
  "at FDR {a} ({k} below p {a} before the map-wide correction)":
    "với FDR {a} ({k} ô có p dưới {a} trước khi hiệu chỉnh trên toàn bản đồ)",
  "; median lag {n} months": "; độ trễ trung vị {n} tháng",
  "Coupling not assessed: the series is shorter than a seasonal cycle.":
    "Chưa đánh giá liên hệ mưa – biến dạng: chuỗi ngắn hơn một chu kỳ mùa.",
  "{n} cells accelerate significantly.": "{n} ô tăng tốc có ý nghĩa thống kê.",
  "Reference:": "Tham chiếu:",
  "stable area {b} ({n} cells)": "vùng ổn định {b} ({n} ô)",
  "product reference point {lon}, {lat}": "điểm tham chiếu của sản phẩm {lon}, {lat}",
  "product ({kind})": "sản phẩm ({kind})",
  "{n} cells move against the hazard direction (uplift / upslope), flagged, not rated":
    "{n} ô chuyển dịch ngược hướng nguy cơ (nâng / ngược dốc), được đánh dấu, không xếp mức",

  // base map, right column
  dark: "tối",
  light: "sáng",
  satellite: "vệ tinh",
  "Legend & cell": "Chú giải & ô",
  legend: "chú giải",
  "Loading cells…": "Đang tải các ô…",
  "Loading cell…": "Đang tải ô…",
  "Click a cell for its series, rainfall and the reasons of its level.":
    "Bấm vào một ô để xem chuỗi thời gian, lượng mưa và lý do của mức nguy cơ.",
  "rain r {r}, lag {n} mo": "mưa r {r}, trễ {n} tháng",

  // cell panel and chart
  "{level} hazard": "Mức nguy cơ: {level}",
  "Not assessed": "Chưa đánh giá",
  "{mode} cell #{n}": "ô {mode} #{n}",
  Close: "Đóng",
  "Points in cell": "Số điểm trong ô",
  "Rate (sinking +)": "Tốc độ (lún +)",
  "Rate (downslope +)": "Tốc độ (xuống dốc +)",
  "Stability threshold": "Ngưỡng ổn định",
  Intensity: "Cường độ",
  "I{a} observed → I{b}": "I{a} quan trắc → I{b}",
  "after the rainfall scenario and the acceleration": "sau khi xét kịch bản mưa và gia tốc",
  "Angular distortion": "Góc biến dạng",
  "largest differential settlement to a neighbouring cell, over the horizon":
    "lún lệch lớn nhất so với một ô kề, sau khoảng thời gian dự báo",
  "Slope / sensitivity": "Độ dốc / độ nhạy",
  Secondary: "Lớp phụ",
  Acceleration: "Gia tốc",
  significant: "có ý nghĩa",
  "Moves against the hazard direction ({dir}): check the reference area before reading it as stable.":
    "Chuyển dịch ngược hướng nguy cơ ({dir}): kiểm tra vùng tham chiếu trước khi coi là ổn định.",
  uplift: "nâng",
  "apparent upslope motion": "dịch chuyển ngược dốc biểu kiến",
  "RAINFALL COUPLING": "LIÊN HỆ MƯA – BIẾN DẠNG",
  "Not assessed (series too short or rainfall missing).": "Chưa đánh giá (chuỗi quá ngắn hoặc thiếu số liệu mưa).",
  Significant: "Có ý nghĩa",
  yes: "có",
  no: "không",
  "r (partial) · lag": "r (riêng phần) · độ trễ",
  "{n} mo": "{n} tháng",
  "k per 100 mm": "k trên 100 mm",
  "Trend w/o rain": "Xu thế khi bỏ mưa",
  "Dry (P10) / wet (P90) yr": "Năm khô (P10) / ướt (P90)",
  "mm (sinking +)": "mm (lún +)",
  "mm (downslope +)": "mm (xuống dốc +)",
  "cell median": "trung vị của ô",
  linear: "tuyến tính",
  "trend + k·CRD(t − {n} mo)": "xu thế + k·CRD(t − {n} tháng)",
  "Monthly rainfall of the cell's pixel": "Mưa tháng tại pixel của ô",

  // method
  "HOW THIS MAP IS MADE": "CÁCH LẬP BẢN ĐỒ NÀY",
  "Points → square cells (median series, ≥ min points per cell).":
    "Điểm → ô vuông (chuỗi trung vị, ≥ số điểm tối thiểu mỗi ô).",
  "DEM slope at cell scale: flat cells = subsidence, steep cells = landslide (ADAtools-like rule).":
    "Độ dốc DEM ở quy mô ô: ô bằng phẳng = sụt lún, ô dốc = trượt lở (quy tắc tương tự ADAtools).",
  "LOS projected on the expected motion: vertical, or downslope (Cigna et al. 2013 L2S factor).":
    "Chiếu LOS lên hướng chuyển dịch dự kiến: thẳng đứng, hoặc xuống dốc (hệ số L2S, Cigna et al. 2013).",
  "Rainfall (CHIRPS v3, ERA5 fallback): d = a + b·t + k·CRD(t − τ), lag 0 to max lag months; significance from phase-randomised rainfall (Ebisuzaki 1997) with a map-wide false discovery rate (Benjamini & Hochberg 1995).":
    "Lượng mưa (CHIRPS v3, dự phòng ERA5): d = a + b·t + k·CRD(t − τ), độ trễ từ 0 đến độ trễ tối đa (tháng); ý nghĩa thống kê từ chuỗi mưa thay thế xáo pha ngẫu nhiên (Ebisuzaki 1997) với tỉ lệ phát hiện sai (FDR) trên toàn bản đồ (Benjamini & Hochberg 1995).",
  "Intensity: stability 2σ (Barra et al. 2017); landslide classes on Cruden & Varnes (1996); raised by a dry / wet (P10 / P90) year and by acceleration.":
    "Cường độ: ngưỡng ổn định 2σ (Barra et al. 2017); lớp trượt lở theo Cruden & Varnes (1996); nâng lớp theo năm khô / ướt (P10 / P90) và theo gia tốc.",
  "Secondary: angular distortion vs 1/500, 1/300, 1/150 (Bjerrum 1963; Skempton & MacDonald 1956), or slope / susceptibility.":
    "Lớp phụ: góc biến dạng so với 1/500, 1/300, 1/150 (Bjerrum 1963; Skempton & MacDonald 1956), hoặc độ dốc / tính nhạy cảm.",
  "Hazard = matrix(intensity, secondary), as in the PSI-based matrix approach (Cigna et al. 2013).":
    "Nguy cơ = ma trận(cường độ, lớp phụ), theo cách tiếp cận ma trận dựa trên PSI (Cigna et al. 2013).",
  "Full method, sources and research plan:": "Phương pháp đầy đủ, nguồn và kế hoạch nghiên cứu:",
};
