// explorer: filled with the texts of its files (see index.ts).
export const EXPLORER: Record<string, string> = {
  // base maps (map.ts BASES labels)
  Dark: "Tối",
  Light: "Sáng",
  Satellite: "Vệ tinh",

  // toolbar
  "Draw area": "Vẽ vùng",
  "Finish area ({n} pts)": "Kết thúc vùng ({n} điểm)",
  Compare: "So sánh",
  "Stop comparing": "Dừng so sánh",
  "Show two products on the map to compare them": "Hiển thị hai sản phẩm trên bản đồ để so sánh",
  "Compare two products": "So sánh hai sản phẩm",
  "Products here": "Sản phẩm tại đây",
  "Products of every project over the current view (workspace catalog)":
    "Sản phẩm của mọi dự án trong khung nhìn hiện tại (danh mục không gian làm việc)",
  "Clear area": "Xoá vùng",
  "Click to add vertices · double-click to finish": "Nhấp để thêm đỉnh · nhấp đúp để kết thúc",
  "Loading points…": "Đang tải các điểm…",

  // products in this view
  "PRODUCTS IN THIS VIEW": "SẢN PHẨM TRONG KHUNG NHÌN",
  Close: "Đóng",
  "Searching the catalog…": "Đang tìm trong danh mục…",
  "No product covers this view.": "Không có sản phẩm nào phủ khung nhìn này.",
  "on the map": "đang trên bản đồ",
  show: "hiển thị",
  "{level} confidence": "độ tin cậy {level}",
  high: "cao",
  medium: "trung bình",
  low: "thấp",
  "{n} points here": "{n} điểm tại đây",
  median: "trung vị",
  range: "khoảng",
  "{n} faster than −10 away": "{n} điểm ra xa nhanh hơn −10",

  // empty map
  "No product on the map": "Chưa có sản phẩm trên bản đồ",
  "Click the eye next to a product in the project tree (or the product name) to show its points here, like a layer in QGIS.":
    "Nhấp vào biểu tượng con mắt cạnh một sản phẩm trong cây dự án (hoặc tên sản phẩm) để hiển thị các điểm của nó tại đây, như một lớp trong QGIS.",
  "Go to the overview": "Đến trang tổng quan",

  // compare
  "Swipe position": "Vị trí thanh trượt",
  COMPARE: "SO SÁNH",
  Swipe: "Trượt",
  Difference: "Chênh lệch",
  "Choose two different products.": "Chọn hai sản phẩm khác nhau.",
  "Different tracks ({a} / {b}): each measures along its own line of sight, so a difference also contains geometry, not only motion.":
    "Khác vệt quỹ đạo ({a} / {b}): mỗi sản phẩm đo theo hướng nhìn riêng của nó, nên hiệu còn chứa cả hình học, không chỉ chuyển dịch.",
  "A left of the handle, B right. Drag the handle or use ← →.": "A bên trái thanh trượt, B bên phải. Kéo thanh trượt hoặc dùng ← →.",
  Cell: "Ô",
  "Each product has its own reference area: remove the median difference":
    "Mỗi sản phẩm có vùng tham chiếu riêng: loại bỏ hiệu trung vị",
  "remove median offset": "loại bỏ độ lệch trung vị",
  "Computing…": "Đang tính…",
  "The two products have no cell in common.": "Hai sản phẩm không có ô chung nào.",
  "Common cells": "Ô chung",
  "Correlation A/B": "Tương quan A/B",
  "Offset removed": "Độ lệch đã loại bỏ",
  "Std of B − A": "Độ lệch chuẩn của B − A",
  "P5 … P95": "P5 … P95",
  RMSE: "RMSE",
  "median per {cell} m cell": "trung vị theo ô {cell} m",
  "B − A velocity": "Vận tốc B − A",

  // layers panel
  "Layers · {n}": "Lớp · {n}",
  layer: "lớp",
  "LAYERS · {n}": "LỚP · {n}",
  "Show {product}": "Hiển thị {product}",
  "Zoom to layer": "Phóng tới lớp",
  "Remove from the map": "Gỡ khỏi bản đồ",
  ascending: "quỹ đạo lên",
  descending: "quỹ đạo xuống",
  "{n} pts": "{n} điểm",
  Rendering: "Cách hiển thị",
  "Points: the whole product at once. Tiles: PMTiles vector tiles, read as you pan (auto: above 2.5 M points)":
    "Điểm: toàn bộ sản phẩm một lần. Ô lưới: ô vector PMTiles, đọc dần khi di chuyển bản đồ (tự động: trên 2,5 triệu điểm)",
  auto: "tự động",
  points: "điểm",
  tiles: "ô lưới",
  Opacity: "Độ mờ đục",

  // legend
  LEGEND: "CHÚ GIẢI",
  "LOS velocity": "Vận tốc LOS",
  min: "nhỏ nhất",
  max: "lớn nhất",
  "+ toward the satellite, − away (e.g. subsidence)": "+ về phía vệ tinh, − ra xa (ví dụ sụt lún)",

  // dock: point / area
  "Point #{n}": "Điểm #{n}",
  "Area mean": "Trung bình vùng",
  "{n} points": "{n} điểm",
  mean: "trung bình",
  Velocity: "Vận tốc",
  Coherence: "Độ kết hợp",
  Height: "Độ cao",
  "Seasonal amp.": "Biên độ mùa",
  Lon: "Kinh độ",
  Lat: "Vĩ độ",
  "Loading…": "Đang tải…",
  "Velocity in mm/yr; displacement along the line of sight, relative to the reference area, 0 at the first date":
    "Vận tốc tính bằng mm/năm; chuyển dịch theo hướng nhìn của vệ tinh, so với vùng tham chiếu, bằng 0 tại ngày đầu tiên",
  "No point inside the area.": "Không có điểm nào trong vùng.",
  Points: "Số điểm",
  Mean: "Trung bình",
  Min: "Nhỏ nhất",
  Max: "Lớn nhất",
  "Velocities in mm/yr; mean series of the points inside the area (each 0 at the first date), band = ±1 standard deviation":
    "Vận tốc tính bằng mm/năm; chuỗi trung bình của các điểm trong vùng (mỗi điểm bằng 0 tại ngày đầu tiên), dải = ±1 độ lệch chuẩn",
  "residual atmosphere (SCN) removed": "đã loại bỏ khí quyển dư (SCN)",

  // rainfall and charts
  "monthly rainfall": "mưa tháng",
  "Reading the rainfall…": "Đang đọc lượng mưa…",
  "mm/month": "mm/tháng",
  displacement: "chuyển dịch",
};
