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
  Rate: "Tốc độ",
  "Rain coupling": "Liên hệ với mưa",
  "Rain lag": "Độ trễ so với mưa",
  Mode: "Loại quá trình",
  "The final level of each 100 m cell: how fast the ground moves (InSAR intensity) combined with what the motion can do (distortion for subsidence, slope for landslides).":
    "Mức nguy cơ cuối cùng của từng ô 100 m: mặt đất chuyển dịch nhanh đến đâu (cường độ InSAR) kết hợp với việc chuyển dịch đó có thể gây ra gì (biến dạng với sụt lún, độ dốc với trượt lở).",
  "Red cells need attention first: fast motion where it bends buildings or on steep ground.":
    "Ô đỏ cần chú ý trước tiên: chuyển dịch nhanh ở nơi làm cong vênh công trình hoặc trên sườn dốc.",
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
  "The velocity of each cell in mm per year, along the expected motion: vertical on flat ground, along the slope on hillsides. As everywhere in GeoEyes, negative means sinking or moving down the slope.":
    "Vận tốc của mỗi ô (mm/năm) theo hướng chuyển dịch dự kiến: thẳng đứng ở nền phẳng, dọc sườn ở sườn dốc. Như mọi nơi trong GeoEyes, giá trị âm là lún hoặc dịch xuống dốc.",
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
  "HAZARD ZONING": "PHÂN VÙNG NGUY CƠ",
  "Map layer": "Lớp bản đồ",
  Zoning: "Phân vùng",
  Components: "Thành phần",
  "Water drivers": "Tác nhân nước",
  yr: "năm",
  mo: "tháng",
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
  tie: "gắn vào",
  "1 station": "1 trạm",
  "GNSS unavailable: restart geoeyes serve (the server predates this page)":
    "Không có GNSS: khởi động lại geoeyes serve (máy chủ cũ hơn trang này)",
  "no GNSS comparison of this product yet (Project → Validation → GNSS)":
    "sản phẩm này chưa được so sánh với GNSS (Dự án → Kiểm định → GNSS)",
  "Running…": "Đang chạy…",
  "Run again": "Chạy lại",
  "Run hazard zoning": "Chạy phân vùng nguy cơ",
  "Reference area: west, south, east, north (degrees)": "Vùng tham chiếu: tây, nam, đông, bắc (độ)",
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
  "Rate (up +)": "Tốc độ (+ nâng lên)",
  "Rate (upslope +)": "Tốc độ (+ ngược dốc)",
  "Stability threshold": "Ngưỡng ổn định",
  Intensity: "Cường độ",
  "I{a} observed → I{b}": "I{a} quan trắc → I{b}",
  "after the rainfall scenario and the acceleration": "sau khi xét kịch bản mưa và gia tốc",
  "Angular distortion": "Góc biến dạng",
  "largest differential settlement to a neighbouring cell, over the horizon":
    "lún lệch lớn nhất so với một ô kề, sau khoảng thời gian dự báo",
  "Slope / sensitivity": "Độ dốc / độ nhạy",
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
  "mm (up +)": "mm (+ nâng lên)",
  "mm (upslope +)": "mm (+ ngược dốc)",
  "cell median": "trung vị của ô",
  linear: "tuyến tính",
  "trend + k·CRD(t − {n} mo)": "xu thế + k·CRD(t − {n} tháng)",
  "Monthly rainfall of the cell's pixel": "Mưa tháng tại pixel của ô",

  // method
  "HOW THIS MAP IS MADE": "CÁCH LẬP BẢN ĐỒ NÀY",
  "Full method, sources and research plan:": "Phương pháp đầy đủ, nguồn và kế hoạch nghiên cứu:",
  // groundwater (NASA GLDAS)
  "Groundwater coupling": "Liên hệ với nước ngầm",
  Groundwater: "Nước ngầm",
  "Where the ground motion follows the groundwater storage of the region (NASA GLDAS, with GRACE satellite gravity), after removing its steady trend.":
    "Nơi chuyển dịch mặt đất biến đổi theo trữ lượng nước ngầm của khu vực (NASA GLDAS, đồng hoá trọng lực vệ tinh GRACE), sau khi đã loại bỏ xu thế ổn định.",
  "Blue: the ground sinks more when storage falls and recovers when it rises, the elastic response of an aquifer system. Red: the opposite sign.":
    "Xanh: mặt đất lún nhanh hơn khi trữ lượng giảm và hồi lại khi trữ lượng tăng, đúng phản ứng đàn hồi của tầng chứa nước. Đỏ: quan hệ ngược chiều.",
  "The storage grid is 0.25° (about 27 km): it shows when the region gains or loses water, not where wells pump. Read it as a regional driver, not as a local cause.":
    "Lưới trữ lượng có độ phân giải 0,25° (khoảng 27 km): nó cho biết khi nào cả vùng tích hay mất nước, chứ không chỉ ra giếng bơm ở đâu. Hãy hiểu đây là tác nhân cấp vùng, không phải nguyên nhân tại chỗ.",
  "Only statistically significant cells are coloured; this layer does not change the hazard level.":
    "Chỉ tô màu các ô có ý nghĩa thống kê; lớp này không làm thay đổi cấp nguy cơ.",
  "Groundwater needs an Earthdata login: set EARTHDATA_TOKEN and run the zoning again.":
    "Dữ liệu nước ngầm cần tài khoản Earthdata: hãy đặt EARTHDATA_TOKEN rồi chạy lại phân vùng.",
  "Groundwater coupling is off in the parameters.": "Liên hệ với nước ngầm đang tắt trong tham số.",
  "No groundwater in this zoning: run it again.": "Lần phân vùng này chưa có nước ngầm: hãy chạy lại.",
  "more storage, more motion": "trữ lượng tăng, chuyển dịch tăng",
  "less storage, more sinking (aquifer)": "trữ lượng giảm, lún tăng (tầng chứa nước)",
  "{n} of {m} cells significant": "{n} / {m} ô có ý nghĩa",
  "storage trend {v} mm/yr": "xu thế trữ lượng {v} mm/năm",
  "trend + g·GWS(t − {n} mo)": "xu thế + g·GWS(t − {n} tháng)",
  "GROUNDWATER COUPLING": "LIÊN HỆ NƯỚC NGẦM – BIẾN DẠNG",
  "Not assessed (storage not published for the whole period, or series too short).":
    "Chưa đánh giá (trữ lượng chưa được công bố cho cả giai đoạn, hoặc chuỗi quá ngắn).",
  "g per 100 mm storage": "g trên 100 mm trữ lượng",
  "Storage trend": "Xu thế trữ lượng",
  "trend of the storage of the 0.25° pixel over the period": "xu thế trữ lượng của pixel 0,25° trong giai đoạn quan trắc",
  // damage potential (was: secondary class)
  "Damage potential": "Tổn hại tiềm tàng",
  "damage potential": "tổn hại tiềm tàng",
  "Read the level in the matrix: intensity (rows) × damage potential (columns).": "Đọc mức trong ma trận: cường độ (hàng) × tổn hại tiềm tàng (cột).",
};
