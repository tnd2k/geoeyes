// Messages written by the server (geoeyes.hazard, geoeyes.validation.gnss, the controller): exact texts and
// patterns ($1, $2 ... keep the values of the English message).
export const SERVER: Record<string, string> = {
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
  "same parameters and inputs, outputs present": "cùng tham số và dữ liệu vào, đã có kết quả",
  "off in the project configuration": "tắt trong cấu hình dự án",
  "not done with these parameters": "chưa chạy với các tham số này",
  "an earlier phase runs": "một pha phía trước sẽ chạy",
  "Nevada Geodetic Laboratory (NGL), daily GNSS positions, IGS20 frame (geodesy.unr.edu)":
    "Nevada Geodetic Laboratory (NGL), toạ độ GNSS hằng ngày, khung IGS20 (geodesy.unr.edu)",
  "ERA5 reanalysis daily precipitation (ECMWF / Copernicus), via the Open-Meteo archive API":
    "Lượng mưa ngày tái phân tích ERA5 (ECMWF / Copernicus), qua API lưu trữ Open-Meteo",
  "CHIRPS v3.0 monthly (Climate Hazards Center, UC Santa Barbara)": "CHIRPS v3.0 theo tháng (Climate Hazards Center, UC Santa Barbara)",
};

export const SERVER_PATTERNS: [RegExp, string][] = [
  [/^rainfall coupling not assessed: ([\d.]+) months \/ (\d+) epochs \(needs ([\d.]+) months and (\d+) epochs\)$/,
    "chưa đánh giá liên hệ mưa – biến dạng: $1 tháng / $2 lần chụp (cần $3 tháng và $4 lần chụp)"],
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
];
