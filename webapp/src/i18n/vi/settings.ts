// The project settings form (geoeyes.api.settings): section titles in pipeline order, the [ps] groups by StaMPS
// step. The help of every parameter comes from the catalogue. Parameter names ([section] key) stay in English: they are the TOML keys.
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

  // parameter details (the help of every parameter comes from geoeyes/advisor/params.toml, in both languages)
  "why?": "vì sao?",
  "hide details": "thu gọn",
  "What it does": "Dùng để",
  "Typical values": "Giá trị thường dùng",
  Related: "Liên quan",
};
