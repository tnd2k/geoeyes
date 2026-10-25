> Bản tiếng Việt của [README.md](README.md); bản gốc tiếng Anh là bản chuẩn (ADR-015). Dịch ngày 2026-10-26, biên tập lại 2026-10-26.

# Ứng dụng web GeoEyes — front end

React + TypeScript + Vite, bản đồ dùng MapLibre + deck.gl, cùng TanStack Query, uPlot, Tailwind. Front end chỉ là client mỏng
gọi API trong `src/geoeyes/api` (FastAPI); API đọc không gian làm việc qua phần lõi và khởi chạy mỗi lần chạy bằng một
tiến trình con `geoeyes run`. Kế hoạch và thiết kế: `docs/en/refactor/webapp-plan.md`.

## Sử dụng

```
geoeyes serve            # http://localhost:8765 — API + front end đã build chung một cổng, chỉ truy cập từ máy này
geoeyes serve --open     # mở luôn trình duyệt
```

Cần cài gói bổ sung `web` (`pip install -e .[web]`: fastapi, uvicorn, tomlkit). Với `geoeyes serve --host 0.0.0.0`,
ứng dụng mở ra mạng và đòi token đăng nhập (`GEOEYES_WEB_TOKEN`; nếu không đặt thì sinh token ngẫu nhiên và in ra lúc khởi động). Không cần Node: bản build đã commit sẵn trong
`src/geoeyes/api/static/`. Tài liệu API: http://localhost:8765/api/docs.

## Phát triển

```
cd webapp
npm install
geoeyes serve            # API ở cổng 8765 (mở ở terminal khác)
npm run dev              # http://127.0.0.1:8766, tự nạp lại, /api chuyển tiếp (proxy) sang 8765
npm run build            # kiểm tra kiểu rồi ghi bản build vào src/geoeyes/api/static
```

Cổng: 8765 (`geoeyes serve`), 8766 (dev server), 8767 (`vite preview`). Không bao giờ dùng cổng mặc định 5173 của Vite
(`strictPort`: cổng bận thì báo lỗi, không lặng lẽ đổi cổng).

## Cấu trúc

| Tệp | Vai trò |
|---|---|
| `src/api.ts` | kiểu dữ liệu và hàm gọi API |
| `src/state.tsx` | route (`#/`, `#/explorer`, `#/project/<name>/<tab>`, `#/map/<project>/<product>`) và các lớp bản đồ (lưu trong `localStorage`) |
| `src/components/ProjectTree.tsx` | cây dự án: thư mục (kéo thả, đổi tên, tạo mới), dự án, vệt quỹ đạo, sản phẩm có nút con mắt bật/tắt, báo cáo, menu chuột phải |
| `src/pages/Overview.tsx` | tổng quan mọi dự án: KPI, thẻ, các lần chạy gần nhất |
| `src/pages/Explorer.tsx` | bản đồ: mỗi sản phẩm là một lớp (chỉnh độ mờ), chú giải (Pretty Breaks, jet_r), bấm điểm → chuỗi thời gian, vẽ vùng → chuỗi trung bình, so sánh hai sản phẩm (kéo trượt / hiệu) |
| `src/pages/Project.tsx` | thẻ các bước quy trình kèm lý do từ kế hoạch, Run / Stop, nhật ký trực tiếp, đường cơ sở, các lần chạy, kiểm định, thiết lập |
| `src/pages/NewProject.tsx` | trình tạo dự án mới: vẽ AOI trên bản đồ, chọn vệt quỹ đạo Sentinel-1 đi qua, xem trước từ ASF |
| `src/components/SettingsForm.tsx` | biểu mẫu thiết lập sinh từ schema (giá trị riêng hay theo preset, đặt lại) và `project.toml` dạng thô |
| `src/components/Validation.tsx` | báo cáo gương phản xạ góc |
| `src/pages/Compose.tsx`, `src/compose.ts` | trình dàn trang bản đồ: vẽ bố cục tờ in trên canvas, xuất PNG / PDF đúng khổ in |
| `src/components/Monitor.tsx` | lần chụp Sentinel-1 sắp tới, lần chạy theo lịch, cảnh báo biến dạng |
| `src/map.ts` | bản đồ nền, lớp sản phẩm (điểm nhị phân hoặc vector tile PMTiles), màu vận tốc |
| `src/components/TimeSeries.tsx` | biểu đồ chuyển dịch bằng uPlot |
| `src/ui.tsx` | chip trạng thái (màu + biểu tượng + nhãn), nút, định dạng số liệu |

Điểm được gửi lên bản đồ dưới dạng một mảng nhị phân cho mỗi sản phẩm (độ lệch lon/lat `float32` + vận tốc, khoảng 12 byte mỗi
điểm; bộ nhớ đệm đặt trong `<workspace>/cache/web/`, tạo ở lần xem đầu). Khi vượt 2,5 triệu điểm (hoặc khi chọn trong
bảng lớp), điểm được phục vụ dưới dạng vector tile PMTiles theo từng tile (`exports/<id>/<id>.pmtiles`, nếu chưa có thì tạo một lần trong
bộ nhớ đệm). Chuỗi thời gian và trung bình theo vùng đọc từ một ma trận ánh xạ bộ nhớ (memory-mapped) trong cùng bộ nhớ đệm đó.
