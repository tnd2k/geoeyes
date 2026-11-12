// Processing corridor: the brush (new project, project tab "Processing area").
export const CORRIDOR: Record<string, string> = {
  Rectangle: "Khung chữ nhật",
  "Corridor along a route": "Hành lang dọc tuyến",
  Width: "Bề rộng",
  "full width: {h} m on each side": "bề rộng toàn phần: {h} m mỗi bên",
  "Drawing… (click to stop)": "Đang vẽ… (bấm để dừng)",
  "Draw along the route": "Vẽ dọc tuyến",
  "Continue drawing": "Vẽ tiếp",
  "Brush or eraser": "Cọ hoặc tẩy",
  Brush: "Cọ",
  Eraser: "Tẩy",
  Undo: "Hoàn tác",
  Redo: "Làm lại",
  "Import a route…": "Nhập tuyến từ tệp…",
  "Corridor: {len} km of route, {area} km²": "Hành lang: {len} km tuyến, {area} km²",
  "{n} separate parts": "{n} phần rời nhau",
  "{p}% of the rectangle around it": "{p}% khung chữ nhật bao quanh",
  "Hold the left button and drag along the route": "Nhấn giữ chuột trái và kéo dọc tuyến",
  "Hold the left button and drag over the part to remove": "Nhấn giữ chuột trái và kéo qua phần cần xoá",
  "Alt + drag: erase · hold Space: move the map · Ctrl+Z: undo": "Alt + kéo: tẩy · giữ Space: kéo bản đồ · Ctrl+Z: hoàn tác",
  "Only the Sentinel-1 bursts the corridor touches are downloaded. The stack is still cut to the rectangle around it until the sparse stack (plan step K3).":
    "Chỉ tải các burst Sentinel-1 mà hành lang chạm tới. Stack vẫn cắt theo khung chữ nhật bao quanh cho đến khi có stack thưa (bước K3 của kế hoạch).",
  "Processing area": "Vùng xử lý",
  "Processing corridor": "Hành lang xử lý",
  "Paint the area to process along the route. Only the Sentinel-1 bursts the corridor touches are kept; the stack is still cut to the rectangle around it until the sparse stack (plan step K3).":
    "Tô vùng cần xử lý dọc tuyến. Chỉ giữ các burst Sentinel-1 mà hành lang chạm tới; stack vẫn cắt theo khung chữ nhật bao quanh cho đến khi có stack thưa (bước K3 của kế hoạch).",
  "Saved: {len} km, {area} km², width {w} m": "Đã lưu: {len} km, {area} km², bề rộng {w} m",
  "No corridor: the whole rectangle ([aoi] bbox) is processed.": "Chưa có hành lang: xử lý cả khung chữ nhật ([aoi] bbox).",
  "Save the corridor": "Lưu hành lang",
  "Remove the corridor": "Bỏ hành lang",
  "Remove the corridor? The whole rectangle will be processed again (the bbox stays).":
    "Bỏ hành lang? Lần chạy sau sẽ xử lý lại cả khung chữ nhật (bbox được giữ nguyên).",
  "A run is going: save after it ends.": "Đang có lần chạy: hãy lưu sau khi chạy xong.",
  "Saved: [aoi] corridor and bbox updated. The next run downloads and builds only what changed.":
    "Đã lưu: đã cập nhật [aoi] corridor và bbox. Lần chạy sau chỉ tải và dựng lại phần thay đổi.",
};
