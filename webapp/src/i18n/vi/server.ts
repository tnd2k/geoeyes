// Messages written by the server (geoeyes.hazard, geoeyes.validation.gnss, the controller): exact texts and
// patterns ($1, $2 ... keep the values of the English message).
export const SERVER: Record<string, string> = {
  "radar geometry: rows = lines (azimuth), columns = samples (range)": "hình học radar: hàng = dòng (azimuth), cột = mẫu (range)",
  "radar grid turned left-right so that north is up and east right (not geocoded: tilted by the orbit heading)":
    "lưới radar đã lật trái–phải để bắc lên trên, đông bên phải (chưa geocode: nghiêng theo hướng bay của quỹ đạo)",
  "radar grid turned top-bottom so that north is up and east right (not geocoded: tilted by the orbit heading)":
    "lưới radar đã lật trên–dưới để bắc lên trên, đông bên phải (chưa geocode: nghiêng theo hướng bay của quỹ đạo)",
  "radar grid turned top-bottom and left-right so that north is up and east right (not geocoded: tilted by the orbit heading)":
    "lưới radar đã lật trên–dưới và trái–phải để bắc lên trên, đông bên phải (chưa geocode: nghiêng theo hướng bay của quỹ đạo)",
  "no building analysis: hazards from the cells only": "chưa có phân tích công trình: nguy cơ chỉ lấy từ các ô",
  "scene mean": "trung bình toàn cảnh",
  "rainfall: the hazard analysis": "lượng mưa: lấy từ phân tích nguy cơ",
  "IRLS (GeoEyes, weights = coherence²)": "IRLS (GeoEyes, trọng số = độ nhất quán²)",
  "no NGL station inside the product over its period": "không có trạm NGL nào trong vùng và thời gian của sản phẩm",
  "no NGL station could be compared (see the reasons per station)": "không so sánh được trạm NGL nào (xem lý do từng trạm)",
  "excluded in [validation.gnss]": "bị loại trong [validation.gnss]",
  "epoch calibration from one station: its daily GNSS noise goes into every point":
    "hiệu chỉnh theo từng ngày chụp từ một trạm: nhiễu GNSS hằng ngày của trạm đi vào mọi điểm",
  "one station: the calibration ties the reference to it but cannot be checked independently (leave-one-out needs two stations)":
    "chỉ một trạm: hiệu chỉnh gắn tham chiếu vào trạm này nhưng không kiểm tra độc lập được (leave-one-out cần ít nhất hai trạm)",
  "the station moved or changed equipment: the long-term rate may mix two monuments":
    "trạm đã di dời hoặc thay thiết bị: vận tốc dài hạn có thể trộn hai mốc trạm",
  "the product is referenced to the scene mean: rates are relative, not to stable ground, so the intensity classes are biased (set gnss_tie or reference_bbox); the angular distortion does not depend on the reference":
    "sản phẩm lấy tham chiếu là trung bình cảnh: tốc độ là tương đối, không so với nền ổn định, nên lớp cường độ bị lệch (bật gnss_tie hoặc đặt reference_bbox); góc biến dạng không phụ thuộc tham chiếu",
  "reference_bbox ignored: gnss_tie is set": "bỏ qua reference_bbox vì đã bật gnss_tie",
  // settings form, [sbas]
  "SBAS (method = sbas)": "SBAS (method = sbas)",
  "Azimuth looks of the SBAS grid (Sentinel-1: 1 look ≈ 14 m)": "Số look theo phương vị của lưới SBAS (Sentinel-1: 1 look ≈ 14 m)",
  "Range looks of the SBAS grid (Sentinel-1: 1 look ≈ 2.3 m slant, ≈ 3.7 m ground)":
    "Số look theo cự ly của lưới SBAS (Sentinel-1: 1 look ≈ 2,3 m nghiêng, ≈ 3,7 m mặt đất)",
  "Stable reference point (lon, lat); empty = the most coherent 10 % of pixels":
    "Điểm tham chiếu ổn định (kinh độ, vĩ độ); để trống = 10 % pixel có độ nhất quán cao nhất",
  "auto: phase-linked SLC when phase linking is on; slc or linked to force one":
    "auto: dùng SLC đã liên kết pha khi bật liên kết pha; slc hoặc linked để chọn cố định",
  "Pairs per date with the next N dates (when max_temporal_days = 0)":
    "Mỗi ngày chụp ghép cặp với N ngày kế tiếp (khi max_temporal_days = 0)",
  "A pixel of a pair below this coherence has no value in that pair":
    "Pixel có độ nhất quán dưới ngưỡng này bị bỏ trong cặp đó",
  "A pixel needs a value in this share of the pairs": "Pixel cần có giá trị trong tỷ lệ cặp này",
  "Output mask: mean coherence of the pairs": "Mặt nạ đầu ra: độ nhất quán trung bình của các cặp",
  "Output mask: temporal coherence of the inversion": "Mặt nạ đầu ra: độ nhất quán thời gian của phép nghịch đảo",
  "Stratified troposphere (phase linear in height, per pair): auto = off on flat terrain, else removed without its steady trend; true = as fitted; false = off":
    "Khí quyển phân tầng (pha tuyến tính theo độ cao, cho từng cặp): auto = tắt ở địa hình phẳng, còn lại thì trừ nhưng bỏ xu hướng nhiều năm của nó; true = trừ nguyên như khớp; false = tắt",
  "auto: terrain relief (m, p5-p95) below which the troposphere is not removed":
    "auto: độ chênh cao địa hình (m, p5-p95) dưới ngưỡng này thì không trừ khí quyển",
  "Estimate the DEM error of each pixel from the series and remove it (c + v·t + K·B⊥)":
    "Ước lượng sai số DEM của từng pixel từ chuỗi thời gian rồi trừ đi (c + v·t + K·B⊥)",
  "Goldstein filter strength before unwrapping (0 = off)": "Độ mạnh lọc Goldstein trước khi unwrap (0 = tắt)",
  "same parameters and inputs, outputs present": "cùng tham số và dữ liệu vào, đã có kết quả",
  "off in the project configuration": "tắt trong cấu hình dự án",
  "not done with these parameters": "chưa chạy với các tham số này",
  "an earlier phase runs": "một pha phía trước sẽ chạy",
  "Nevada Geodetic Laboratory (NGL), daily GNSS positions, IGS20 frame (geodesy.unr.edu)":
    "Nevada Geodetic Laboratory (NGL), toạ độ GNSS hằng ngày, khung IGS20 (geodesy.unr.edu)",
  "ERA5 reanalysis daily precipitation (ECMWF / Copernicus), via the Open-Meteo archive API":
    "Lượng mưa ngày tái phân tích ERA5 (ECMWF / Copernicus), qua API lưu trữ Open-Meteo",
  "CHIRPS v3.0 monthly (Climate Hazards Center, UC Santa Barbara)": "CHIRPS v3.0 theo tháng (Climate Hazards Center, UC Santa Barbara)",
  "a product cannot be tied to itself": "không thể nối một sản phẩm với chính nó",
};

export const SERVER_PATTERNS: [RegExp, string][] = [
  [/^the two products agree poorly over the common cells \(correlation ([\d.-]+)\): the tie is uncertain$/,
    "hai sản phẩm khớp kém trên các ô chung (tương quan $1): phép nối không chắc chắn"],
  [/^gain ([\d.-]+) between the products: the periods or the geometries differ \(horizontal motion, seasonal rate\); only the offset is corrected$/,
    "hệ số $1 giữa hai sản phẩm: thời kỳ hoặc hình học khác nhau (chuyển động ngang, tốc độ theo mùa); chỉ hiệu chỉnh độ lệch"],
  [/^(\S+) covers (\S+)\.\.(\S+), not the whole target period (\S+)\.\.(\S+): its rate is taken over the overlap only$/,
    "$1 phủ $2..$3, không hết thời kỳ của sản phẩm đích $4..$5: tốc độ chỉ tính trên phần chồng nhau"],
  [/^(\S+): no calibration \(GNSS comparison or tie to another product\)$/, "$1: chưa có hiệu chỉnh (so sánh GNSS hoặc nối với sản phẩm khác)"],
  [/^(\d+) common ([\d.]+) m cells between the two products \(at least 10 needed\)$/, "$1 ô $2 m chung giữa hai sản phẩm (cần ít nhất 10)"],
  [/^(\d+) cells change on (\S+): a change shared by so many cells points to that acquisition \(atmosphere, unwrapping\) rather than to the ground; check it before reading them as onsets$/,
    "$1 ô cùng thay đổi vào ngày $2: một thay đổi chung cho nhiều ô như vậy thường do lần chụp đó (khí quyển, giải chập pha) chứ không phải mặt đất; hãy kiểm tra trước khi coi là khởi phát"],
  [/^heights known for (\d+)% of the buildings: the others count ([\d.]+) floors$/,
    "chỉ biết chiều cao của $1% công trình: các công trình còn lại được tính $2 tầng"],
  [/^rainfall coupling not assessed: ([\d.]+) months \/ (\d+) epochs \(needs ([\d.]+) months and (\d+) epochs\)$/,
    "chưa đánh giá liên hệ mưa – biến dạng: $1 tháng / $2 lần chụp (cần $3 tháng và $4 lần chụp)"],
  [/^too few moving \((\d+)\) or stable \((\d+)\) cells at ([\d.]+) mm\/yr to train a model: the rates here span (\S+) … (\S+) mm\/yr \(P5–P95, reference: ([^)]*)\); label_rate = ([\d.-]+) labels 10 % of the cells as moving, but that is below the measurement noise \(2σ ≈ ([\d.]+) mm\/yr\): the labels would be mostly noise, and this area may simply be too stable for a susceptibility model$/,
    "quá ít ô chuyển dịch ($1) hoặc ô ổn định ($2) ở ngưỡng $3 mm/năm để huấn luyện mô hình: tốc độ ở đây chỉ trong khoảng $4 … $5 mm/năm (P5–P95, tham chiếu: $6); ngưỡng $7 mm/năm sẽ cho 10 % số ô là chuyển dịch, nhưng giá trị này nằm dưới mức nhiễu đo (2σ ≈ $8 mm/năm): nhãn gần như chỉ là nhiễu, và khu vực này có thể quá ổn định để xây dựng mô hình tính nhạy cảm"],
  [/^too few moving \((\d+)\) or stable \((\d+)\) cells at ([\d.]+) mm\/yr to train a model: the rates here span (\S+) … (\S+) mm\/yr \(P5–P95, reference: ([^)]*)\); label_rate = ([\d.-]+) labels 10 % of the cells as moving$/,
    "quá ít ô chuyển dịch ($1) hoặc ô ổn định ($2) ở ngưỡng $3 mm/năm để huấn luyện mô hình: tốc độ ở đây chỉ trong khoảng $4 … $5 mm/năm (P5–P95, tham chiếu: $6); hãy thử ngưỡng $7 mm/năm (10 % số ô là chuyển dịch)"],
  [/^groundwater not read \((.*)\)$/, "không đọc được dữ liệu nước ngầm ($1)"],
  [/^groundwater coupling tested on the observations up to (\S+) \(GLDAS is published with a lag\)$/,
    "liên hệ nước ngầm – biến dạng chỉ được kiểm định trên dữ liệu quan trắc đến $1 (GLDAS được công bố trễ)"],
  [/^groundwater coupling not assessed: GLDAS storage does not cover the observations yet \(published with a lag of a few months\) or the series are too short$/,
    "chưa đánh giá liên hệ nước ngầm – biến dạng: dữ liệu GLDAS chưa phủ hết thời gian quan trắc (được công bố trễ vài tháng) hoặc chuỗi quá ngắn"],
  [/^(\d+) rainfall pixel\(s\): up to (\d+)% of the months not published yet \(counted as average\)$/,
    "$1 pixel mưa: tới $2% số tháng chưa được công bố (tính bằng giá trị trung bình)"],
  [/^CHIRPS could not be read(.*): ERA5 reanalysis used instead \(smoother monthly extremes\)$/,
    "không đọc được CHIRPS$1: dùng tái phân tích ERA5 thay thế (cực trị tháng mượt hơn)"],
  [/^CHIRPS server refused the request \((.*)\); try again later$/, "máy chủ CHIRPS từ chối yêu cầu ($1); thử lại sau"],
  [/^no terrain \((.*)\); every cell treated as subsidence$/, "không có địa hình ($1); mọi ô được coi là sụt lún"],
  [/^susceptibility raster not read \((.*)\); slope classes used$/, "không đọc được raster tính nhạy cảm ($1); dùng lớp độ dốc"],
  [/^GNSS tie on one station \((.*)\): not checked independently$/, "gắn GNSS trên một trạm ($1): chưa kiểm tra độc lập"],
  [/^plane calibration needs 3 stations, (\d+) compared: offset used instead$/,
    "hiệu chỉnh mặt phẳng cần 3 trạm, chỉ so được $1: dùng độ lệch (offset) thay thế"],
  [/^no MIDAS velocity for (.*): their rate over the InSAR period is used$/,
    "không có vận tốc MIDAS cho $1: dùng tốc độ trong thời gian InSAR"],
  [/^(\d+) InSAR points within ([\d.]+) m \(needs (\d+)\)$/, "$1 điểm InSAR trong bán kính $2 m (cần $3)"],
  [/^(\d+) epochs with GNSS \(needs (\d+)\)$/, "$1 lần chụp có GNSS (cần $2)"],
  [/^(\w+): (\d+) days of data in (.*)$/, "$1: chỉ có $2 ngày dữ liệu trong $3"],
  [/^(\w+): no segment of (\d+) days without a jump in (.*)$/, "$1: không có đoạn $2 ngày nào không có bước nhảy trong $3"],
  [/^(\d+) segments re-joined \(jumps or equipment changes: (.*)\)$/, "đã nối lại $1 đoạn (bước nhảy hoặc thay thiết bị: $2)"],
  [/^(\d+) days in segments shorter than (\d+) days dropped$/, "đã bỏ $1 ngày thuộc các đoạn ngắn hơn $2 ngày"],
  [/^(\d+) new acquisition\(s\) on ASF$/, "$1 ảnh mới trên ASF"],
  [/^(.+): no common period with (.+); constant rates are assumed$/, "$1: không có thời gian chung với $2; giả định vận tốc không đổi"],
  [/^(.+): only (\d+) common days$/, "$1: chỉ có $2 ngày chung"],
  [/^thickness from the open global grid \(depth to bedrock, capped at 50 m\), not the soft layer: set \[postprocess\.geology\] raster or boreholes for a real map$/, "bề dày lấy từ lưới toàn cầu mở (chiều sâu tới đá gốc, giới hạn 50 m), không phải lớp đất yếu: khai báo [postprocess.geology] raster hoặc boreholes để có bản đồ thật"],
  [/^(\d+) % of the cells at the 50 m cap: the grid cannot tell them apart$/, "$1 % số ô chạm giới hạn 50 m: lưới không phân biệt được chúng"],
  [/^(.+): its velocities tilt by ([\d.]+) mm\/yr over the common area, the other product's much less: likely a ramp, read as east-west motion \(deramp = plane\)$/,
    "$1: vận tốc nghiêng $2 mm/năm trên vùng chung, sản phẩm kia ít hơn nhiều: nhiều khả năng là mặt nghiêng (ramp), sẽ bị đọc thành chuyển dịch đông–tây (deramp = plane)"],
];
