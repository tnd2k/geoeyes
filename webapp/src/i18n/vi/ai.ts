// AI page (pages/Ai.tsx): susceptibility from thematic layers, forecast.
export const AI: Record<string, string> = {
  "MACHINE LEARNING RESEARCH": "NGHIÊN CỨU HỌC MÁY",
  "Model results": "Kết quả mô hình",
  "Thematic layers": "Lớp chuyên đề",
  "Susceptibility from thematic layers": "Tính nhạy cảm từ lớp chuyên đề",
  "Deformation forecast": "Dự báo biến dạng",
  "Combines thematic layers (terrain, land cover, buildings, soil) with statistical and machine-learning models to explain where InSAR sees the ground move.":
    "Kết hợp các lớp chuyên đề (địa hình, lớp phủ, công trình, thổ nhưỡng) bằng mô hình thống kê và học máy để giải thích nơi InSAR thấy mặt đất chuyển dịch.",
  "Forecasts the change of displacement of every cell; the machine-learning model is used only where it beats simple baselines in a backtest on the past.":
    "Dự báo mức thay đổi chuyển dịch của từng ô; mô hình học máy chỉ được dùng khi nó thắng các mô hình đơn giản khi kiểm tra ngược trên dữ liệu quá khứ.",
  Threshold: "Ngưỡng",
  "Cells moving at or above this rate (mm/yr, sinking or downslope) are labelled as moving":
    "Ô có tốc độ từ mức này trở lên (mm/năm, lún hoặc xuống dốc) được gán nhãn là đang chuyển dịch",
  "CV blocks": "Khối CV",
  "Size of the spatial cross-validation blocks": "Kích thước khối của kiểm định chéo không gian",
  "Run the hazard zoning of this product first: its cells are the labels.":
    "Hãy chạy phân vùng nguy cơ cho sản phẩm này trước: các ô của nó là nhãn huấn luyện.",
  "the running server predates this page, restart geoeyes serve": "máy chủ đang chạy cũ hơn trang này, hãy khởi động lại geoeyes serve",
  MODELS: "MÔ HÌNH",
  Model: "Mô hình",
  random: "ngẫu nhiên",
  "Area under the ROC curve on held-out spatial blocks": "Diện tích dưới đường ROC trên các khối không gian giữ lại để kiểm tra",
  "Average precision on held-out spatial blocks": "Độ chính xác trung bình (AP) trên các khối không gian giữ lại",
  "AUC with random folds: inflated by spatial autocorrelation": "AUC với các phần chia ngẫu nhiên: bị thổi phồng do tự tương quan không gian",
  "{n} cells with InSAR, {m} moving (≥ {r} mm/yr)": "{n} ô có InSAR, {m} ô đang chuyển dịch (≥ {r} mm/năm)",
  "AUC 0.5 = no skill, 1 = perfect. Spatial blocks of {b} m keep neighbours apart, so the score is honest for new areas.":
    "AUC 0,5 = không hơn đoán ngẫu nhiên, 1 = hoàn hảo. Các khối không gian {b} m tách các ô lân cận ra, nên điểm số phản ánh đúng khả năng dự đoán ở vùng mới.",
  "What explains the motion": "Yếu tố giải thích chuyển dịch",
  "Loss of AUC when a layer is shuffled (permutation importance, {m}). An association, not a cause.":
    "Mức giảm AUC khi xáo trộn một lớp (permutation importance, {m}). Đây là quan hệ thống kê, không phải nguyên nhân.",
  BACKTEST: "KIỂM ĐỊNH TRÊN DỮ LIỆU QUÁ KHỨ",
  "{n} cells, last date {d}; error on the past, by horizon (mm):": "{n} ô, ngày cuối {d}; sai số trên dữ liệu quá khứ theo tầm dự báo (mm):",
  d: "ngày",
  days: "ngày",
  date: "ngày",
  "The machine-learning model beats the simple baselines on the past: it makes the forecast.":
    "Mô hình học máy thắng các mô hình đơn giản trên dữ liệu quá khứ: dự báo dùng mô hình này.",
  "The machine-learning model does not beat the simple baselines on these series: the forecast uses “{m}”, as published studies of short InSAR series also find.":
    "Mô hình học máy không thắng các mô hình đơn giản trên các chuỗi này: dự báo dùng “{m}”, phù hợp với các nghiên cứu đã công bố về chuỗi InSAR ngắn.",
  "80 % interval coverage on the latest check:": "Độ phủ của khoảng 80 % ở lần kiểm tra gần nhất:",
  "Method and sources:": "Phương pháp và nguồn:",
  LAYERS: "LỚP",
  Layers: "Lớp",
  LEGEND: "CHÚ GIẢI",
  CELL: "Ô PHÂN TÍCH",
  Susceptibility: "Tính nhạy cảm",
  "Observed (InSAR)": "Quan trắc (InSAR)",
  Extrapolation: "Ngoại suy",
  extrapolation: "ngoại suy",
  "within the training range": "trong phạm vi dữ liệu huấn luyện",
  "Forecast change": "Thay đổi dự báo",
  "Uncertainty (80 % width)": "Độ bất định (độ rộng 80 %)",
  "Forecast horizon": "Tầm dự báo",
  "no data": "không có dữ liệu",
  "moving (≥ {r} mm/yr)": "đang chuyển dịch (≥ {r} mm/năm)",
  "below the threshold": "dưới ngưỡng",
  "no InSAR points": "không có điểm InSAR",
  "Colour stretched over 2–98 % of the cells; full range {lo} … {hi}": "Thang màu trải trên 2–98 % số ô; toàn dải {lo} … {hi}",
  "Used by the model: importance {v}.": "Được mô hình sử dụng: mức đóng góp {v}.",
  "Not used by the model.": "Không được mô hình sử dụng.",
  relative: "tương đối",
  "away from the satellite (e.g. sinking)": "xa vệ tinh (ví dụ lún)",
  "toward the satellite": "về phía vệ tinh",
  narrow: "hẹp",
  wide: "rộng",
  "Click a cell for its values.": "Bấm vào một ô để xem giá trị.",
  "InSAR rate": "Tốc độ InSAR",
  "mm (LOS)": "mm (LOS)",
  "observed (cell median, 0 at the first date)": "quan trắc (trung vị của ô, 0 tại ngày đầu)",
  forecast: "dự báo",
  "80 % / 95 % interval": "khoảng 80 % / 95 %",
  // models
  "Logistic regression": "Hồi quy logistic",
  "Random forest": "Rừng ngẫu nhiên",
  "Gradient boosting": "Gradient boosting",
  "No change (last value)": "Không đổi (giữ giá trị cuối)",
  "Linear trend": "Xu thế tuyến tính",
  "Trend + annual": "Xu thế + chu kỳ năm",
  "Global gradient boosting": "Gradient boosting toàn cục",
  // layer groups, layers, units (from geoeyes.ml.layers)
  terrain: "địa hình",
  "land cover": "lớp phủ mặt đất",
  buildings: "công trình",
  soil: "thổ nhưỡng",
  climate: "khí hậu",
  Elevation: "Độ cao",
  Slope: "Độ dốc",
  "Built-up": "Đất xây dựng",
  Cropland: "Đất canh tác",
  "Tree cover": "Cây xanh",
  Grassland: "Đồng cỏ",
  Water: "Mặt nước",
  "Bare ground": "Đất trống",
  Wetland: "Đất ngập nước",
  "Distance to water": "Khoảng cách tới mặt nước",
  "Buildings per cell": "Số công trình trong ô",
  "Roof cover": "Tỉ lệ mái nhà",
  "Building height": "Chiều cao công trình",
  "Clay content (0–5 cm)": "Hàm lượng sét (0–5 cm)",
  "Annual rainfall": "Lượng mưa năm",
  fraction: "tỉ lệ",
  count: "số lượng",
  "g/kg": "g/kg",
  // what each map shows
  "Probability that a cell moves faster than the threshold, predicted from the thematic layers only (not from InSAR): also where InSAR has no points.":
    "Xác suất một ô chuyển dịch nhanh hơn ngưỡng, dự đoán chỉ từ các lớp chuyên đề (không dùng InSAR): có cả ở những nơi InSAR không có điểm.",
  "Red: the layers there look like the places where InSAR measured fast motion.":
    "Đỏ: các lớp ở đó giống với những nơi InSAR đo được chuyển dịch nhanh.",
  "Read it as an association, not a cause: groundwater pumping, the main driver of subsidence, is not among the layers.":
    "Hãy hiểu đây là quan hệ thống kê, không phải nguyên nhân: khai thác nước ngầm, tác nhân chính của sụt lún, chưa có trong các lớp.",
  "Hatched cells are outside the range of the training data: the model extrapolates.":
    "Ô mờ nằm ngoài phạm vi dữ liệu huấn luyện: mô hình đang ngoại suy.",
  "What InSAR observed: the cells used to train and test the models.": "Những gì InSAR quan trắc được: các ô dùng để huấn luyện và kiểm tra mô hình.",
  "Red: moving at or above the threshold. Green: below it. Grey: no InSAR points (no label).":
    "Đỏ: chuyển dịch từ ngưỡng trở lên. Xanh: dưới ngưỡng. Xám: không có điểm InSAR (không có nhãn).",
  "Cells where at least one layer lies outside the 1–99 % range of the cells with InSAR: predictions there are extrapolations.":
    "Ô có ít nhất một lớp nằm ngoài khoảng 1–99 % của các ô có InSAR: dự đoán ở đó là ngoại suy.",
  "Orange: extrapolation. Most often vegetation, water or the edges of the scene, where InSAR has no points.":
    "Cam: ngoại suy. Thường là thảm thực vật, mặt nước hoặc rìa cảnh, nơi InSAR không có điểm.",
  "From the DEM of the project (a surface model: buildings are included).": "Từ DEM của dự án (mô hình bề mặt: có cả công trình).",
  "From ESA WorldCover 10 m (2021): share of the cell in each class, and distance to permanent water.":
    "Từ ESA WorldCover 10 m (2021): tỉ lệ diện tích ô thuộc từng lớp, và khoảng cách tới mặt nước thường xuyên.",
  "From Overture Maps buildings (OpenStreetMap, Google and Microsoft footprints): count, roof cover, height where known.":
    "Từ dữ liệu công trình Overture Maps (OpenStreetMap, footprint của Google và Microsoft): số lượng, tỉ lệ mái, chiều cao (nếu có).",
  "From SoilGrids 2.0 (250 m): clay content of the top soil (g/kg).": "Từ SoilGrids 2.0 (250 m): hàm lượng sét của lớp đất mặt (g/kg).",
  "From the rainfall of the hazard analysis (coarse grid: not used as a predictor by default).":
    "Từ lượng mưa của phân tích nguy cơ (lưới thô: mặc định không dùng làm biến giải thích).",
  "Forecast change of displacement along the line of sight from the last date to the chosen horizon.":
    "Thay đổi chuyển dịch dự báo theo hướng nhìn của vệ tinh, từ ngày cuối đến tầm dự báo đã chọn.",
  "Width of the 80 % interval: how uncertain the forecast is.": "Độ rộng khoảng 80 %: mức bất định của dự báo.",
  "The colour scale is symmetric around zero and stretched over 98 % of the cells; click a cell for its values and chart.":
    "Thang màu đối xứng quanh 0 và trải trên 98 % số ô; bấm vào một ô để xem giá trị và biểu đồ.",
  "The best model on the past is “no change”: the forecast change is 0 everywhere, only its uncertainty varies.":
    "Mô hình tốt nhất trên dữ liệu quá khứ là “không đổi”: thay đổi dự báo bằng 0 ở mọi ô, chỉ độ bất định là khác nhau.",
};
