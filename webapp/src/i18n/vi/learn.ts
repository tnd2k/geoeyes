// Learning path (pages/Learn.tsx): one interferometric pair, step by step. Terminology: docs/vi/GLOSSARY.md.
export const LEARN: Record<string, string> = {
  "InSAR principles": "Nguyên lý InSAR",
  "From two single scenes to a velocity, one step at a time.": "Từ hai cảnh ảnh đơn lẻ đến vận tốc, từng bước một.",
  "Step {i} of {n}": "Bước {i} / {n}",
  Previous: "Bước trước",
  Next: "Bước tiếp",
  "computing…": "đang tính…",
  "This project has no stack yet: run its processing up to the stack, or choose another project.":
    "Dự án này chưa có chồng ảnh: hãy chạy xử lý đến bước tạo chồng ảnh, hoặc chọn dự án khác.",
  // boxes and controls
  "Pairs of the stack": "Các cặp ảnh của chồng ảnh",
  Area: "Vùng",
  Adjust: "Điều chỉnh",
  "What happens": "Điều gì diễn ra",
  Formula: "Công thức",
  "What to look for": "Cần quan sát",
  Numbers: "Số liệu",
  Window: "Cửa sổ",
  "Side of the area, km": "Cạnh của vùng, km",
  "Looks (az × rg)": "Số look (phương vị × cự ly)",
  "Coherence window": "Cửa sổ độ kết hợp",
  "Coherence threshold": "Ngưỡng độ kết hợp",
  "Window (pixels)": "Cửa sổ (pixel)",
  Passes: "Số lượt lọc",
  "Baseline plot": "Biểu đồ đường đáy",
  "Next click sets scene {n}.": "Lần bấm tiếp theo chọn cảnh {n}.",
  "stack reference": "ảnh tham chiếu của chồng ảnh",
  "chosen pair": "cặp đang chọn",
  "Loading the scene…": "Đang tải cảnh ảnh…",
  "Radar geometry: rows = azimuth, columns = range. {dir}, looking {side}.":
    "Hình học radar: hàng = phương vị, cột = cự ly. Quỹ đạo {dir}, nhìn về phía {side}.",
  "Click an image to set the reference point (white circle).": "Bấm vào ảnh để chọn điểm tham chiếu (vòng tròn trắng).",
  "Automatic reference": "Tham chiếu tự động",
  "Use the phase-linked SLCs (less noise, used by the GeoEyes chain for this stack)":
    "Dùng SLC sau liên kết pha (ít nhiễu hơn, là dữ liệu chuỗi xử lý GeoEyes dùng cho chồng ảnh này)",
  "Profile along row {r}": "Mặt cắt theo hàng {r}",
  wrapped: "pha cuộn",
  unwrapped: "pha đã giải chập",
  "range →": "cự ly →",
  pixel: "pixel",
  "median of the most coherent 10 %": "trung vị của 10 % pixel có độ kết hợp cao nhất",
  "multilooked pixels": "pixel sau multilook",
  "Loading the points…": "Đang tải các điểm…",
  "No product with points for this stack yet: run the PS processing first.":
    "Chồng ảnh này chưa có sản phẩm điểm: hãy chạy xử lý PS trước.",
  "{n} points of {p} in the area.": "{n} điểm của {p} trong vùng.",
  "Click a point.": "Bấm vào một điểm.",
  "displacement of the point (0 at the first date)": "chuyển dịch của điểm (bằng 0 tại ngày đầu)",
  "line fitted to all dates": "đường thẳng khớp với mọi ngày",
  "Velocity from the series": "Vận tốc từ chuỗi",
  "Velocity of the product": "Vận tốc trong sản phẩm",
  "Rate from this pair alone": "Tốc độ chỉ từ cặp ảnh này",
  "The pair's rate holds the atmosphere of two dates and its own reference: it can differ widely from the trend of the whole series.":
    "Tốc độ từ một cặp chứa cả khí quyển của hai ngày chụp và điểm tham chiếu riêng của nó: có thể khác xa xu thế của cả chuỗi.",
  // units
  dB: "dB",
  rad: "rad",
  "0–1": "0–1",
  "mm/yr": "mm/năm",

  // ---------------------------------------------------------------- step 0: setup
  "Choose the pair and the area": "Chọn cặp ảnh và vùng",
  "Pick two acquisitions of the stack and a small area to follow through every step.":
    "Chọn hai lần chụp trong chồng ảnh và một vùng nhỏ để theo dõi qua từng bước.",
  "A stack holds many SAR scenes of the same place, taken from almost the same orbit at different dates.":
    "Chồng ảnh gồm nhiều cảnh SAR của cùng một nơi, chụp từ gần như cùng một quỹ đạo vào các ngày khác nhau.",
  "An interferogram compares two of them: the first and the second scene of the pair.":
    "Giao thoa đồ so sánh hai cảnh trong số đó: cảnh thứ nhất và cảnh thứ hai của cặp.",
  "Short time between the dates and a small perpendicular baseline (B⊥, the distance between the two orbits) keep the two scenes alike: the result is cleaner.":
    "Khoảng thời gian ngắn và đường đáy vuông góc nhỏ (B⊥, khoảng cách giữa hai quỹ đạo) giúp hai cảnh giống nhau hơn, nên kết quả sạch hơn.",
  "Click two points of the baseline plot to form a pair.": "Bấm hai điểm trên biểu đồ đường đáy để tạo một cặp.",
  "Click the amplitude image to move the area; the window size sets how much ground you see.":
    "Bấm vào ảnh biên độ để dời vùng; kích thước cửa sổ quyết định diện tích mặt đất được xem.",

  // ---------------------------------------------------------------- step 1: scenes
  "Two single SLC scenes": "Hai cảnh SLC đơn lẻ",
  "See what one radar scene holds: a complex number per pixel, with an amplitude and a phase.":
    "Xem một cảnh radar chứa gì: mỗi pixel là một số phức, gồm biên độ và pha.",
  "Amplitude, scene 1": "Biên độ, cảnh 1",
  "Amplitude, scene 2": "Biên độ, cảnh 2",
  "A single-look complex (SLC) image stores, for each pixel, how strongly the ground echoes the radar (amplitude) and where in its wave cycle the echo comes back (phase).":
    "Ảnh SLC (single-look complex) lưu cho mỗi pixel độ mạnh của tín hiệu mặt đất phản xạ về (biên độ) và vị trí trong chu kỳ sóng khi tín hiệu quay về (pha).",
  "Amplitude shows the scene: bright buildings and corners, dark water and smooth roads. The granular texture is speckle, not noise of the instrument.":
    "Biên độ cho thấy khung cảnh: công trình và góc cạnh sáng, mặt nước và đường nhẵn tối. Vân lấm tấm là nhiễu đốm (speckle), không phải nhiễu của thiết bị.",
  "The phase of one scene alone looks random: it mixes the distance to the satellite with the arrangement of scatterers inside the pixel. It becomes useful only when two scenes are compared.":
    "Pha của riêng một cảnh trông như ngẫu nhiên: nó trộn khoảng cách tới vệ tinh với cách sắp xếp các vật tán xạ trong pixel. Pha chỉ có ích khi so sánh hai cảnh.",
  "Both amplitudes look almost the same: the geometry did not change much.":
    "Hai ảnh biên độ gần như giống nhau: hình học thu nhận không thay đổi nhiều.",
  "Images are in radar geometry: rows are azimuth (along the orbit), columns are range (away from the satellite); north is not up.":
    "Ảnh ở hình học radar: hàng là phương vị (dọc quỹ đạo), cột là cự ly (ra xa vệ tinh); phía trên ảnh không phải hướng bắc.",
  Wavelength: "Bước sóng",
  Incidence: "Góc tới",
  "Pixel (az × ground rg)": "Pixel (phương vị × cự ly mặt đất)",

  // ---------------------------------------------------------------- step 2: coregistration
  Coregistration: "Đồng đăng ký ảnh",
  "Make every pixel of scene 2 look at the same ground as the same pixel of scene 1.":
    "Làm cho mỗi pixel của cảnh 2 nhìn đúng vào cùng mảnh đất với pixel tương ứng của cảnh 1.",
  "Colour composite": "Ảnh tổ hợp màu",
  "red = scene 1, cyan = scene 2": "đỏ = cảnh 1, lục lam = cảnh 2",
  Blink: "Nhấp nháy",
  "scene 1 ↔ scene 2": "cảnh 1 ↔ cảnh 2",
  "The two orbits differ slightly, so the same building falls on different pixels in the two scenes. Coregistration resamples scene 2 onto the grid of scene 1.":
    "Hai quỹ đạo lệch nhau một chút, nên cùng một công trình rơi vào các pixel khác nhau ở hai cảnh. Đồng đăng ký lấy mẫu lại cảnh 2 lên lưới của cảnh 1.",
  "GeoEyes does it geometrically: with the precise orbits and the DEM, it computes where every pixel of scene 1 lies in scene 2, then corrects the remaining offset by matching the images (and, for Sentinel-1, with the enhanced spectral diversity across bursts).":
    "GeoEyes làm việc này bằng hình học: từ quỹ đạo chính xác và DEM, nó tính vị trí của từng pixel cảnh 1 trong cảnh 2, rồi hiệu chỉnh phần lệch còn lại bằng cách khớp ảnh (với Sentinel-1 còn dùng phương pháp phân tập phổ tăng cường ESD giữa các burst).",
  "The accuracy needed is about a tenth of a pixel: worse, and the phases of the two scenes no longer belong to the same scatterers.":
    "Độ chính xác cần khoảng một phần mười pixel: kém hơn thì pha của hai cảnh không còn thuộc về cùng các vật tán xạ.",
  "In the composite, aligned features are grey; a misalignment would show red and cyan edges.":
    "Trên ảnh tổ hợp, các đối tượng khớp nhau có màu xám; nếu lệch sẽ thấy viền đỏ và lục lam.",
  "In the blink, nothing should jump: only the speckle flickers.": "Khi nhấp nháy, không có gì nhảy vị trí: chỉ nhiễu đốm thay đổi.",
  "Residual offset after geometry (az, rg)": "Độ lệch còn lại sau hình học (phương vị, cự ly)",
  "ESD azimuth shift": "Độ dịch phương vị ESD",
  "Reference grid": "Lưới tham chiếu",

  // ---------------------------------------------------------------- step 3: raw interferogram
  "Raw interferogram": "Giao thoa đồ thô",
  "Multiply scene 1 by the conjugate of scene 2: the phase difference appears as fringes.":
    "Nhân cảnh 1 với liên hợp phức của cảnh 2: hiệu pha hiện ra thành các vân giao thoa.",
  "Raw interferometric phase": "Pha giao thoa thô",
  "Each fringe (one full colour cycle) is a change of 2π in phase difference, half a wavelength of change in distance.":
    "Mỗi vân (một vòng màu trọn vẹn) là một thay đổi 2π của hiệu pha, tương ứng nửa bước sóng thay đổi khoảng cách.",
  "The raw phase adds up several contributions: the curvature of the Earth seen from two orbits (flat earth), the topography, the ground motion between the dates, the atmosphere, and noise.":
    "Pha thô là tổng của nhiều thành phần: độ cong Trái Đất nhìn từ hai quỹ đạo (mặt đất phẳng), địa hình, chuyển dịch mặt đất giữa hai ngày chụp, khí quyển và nhiễu.",
  "The next steps remove the parts we can model, so that the motion remains.":
    "Các bước sau loại bỏ những thành phần mô hình hoá được, để còn lại chuyển dịch.",
  "GeoEyes removes the flat earth and the topography already during coregistration; here they are added back from the stored geometry so that you can see them.":
    "GeoEyes đã loại bỏ pha mặt đất phẳng và pha địa hình ngay khi đồng đăng ký; ở đây chúng được dựng lại từ hình học đã lưu để bạn nhìn thấy.",
  "Dense, regular fringes running along the azimuth: mostly the flat-earth phase.":
    "Các vân dày, đều, chạy dọc phương vị: phần lớn là pha mặt đất phẳng.",
  Pair: "Cặp ảnh",
  "Fringes per km (raw)": "Số vân trên km (thô)",

  // ---------------------------------------------------------------- step 4: flat earth
  "Remove the flat-earth phase": "Loại bỏ pha mặt đất phẳng",
  "Remove the fringes the geometry alone would produce on a smooth Earth.":
    "Loại bỏ các vân mà riêng hình học chụp đã tạo ra trên một Trái Đất nhẵn.",
  "Flat-earth phase (model)": "Pha mặt đất phẳng (mô hình)",
  "After removing it": "Sau khi loại bỏ",
  "From two orbits a baseline B⊥ apart, the distance to a smooth Earth changes steadily across the swath: regular fringes along range.":
    "Từ hai quỹ đạo cách nhau một đường đáy B⊥, khoảng cách tới một Trái Đất nhẵn thay đổi đều đặn trên toàn dải quét: tạo các vân đều theo cự ly.",
  "Their rate is known from the orbits: the larger B⊥, the denser the fringes.":
    "Mật độ vân biết trước từ quỹ đạo: B⊥ càng lớn, vân càng dày.",
  "The dense regular fringes are gone; what remains follows the relief, the motion and the atmosphere.":
    "Các vân dày và đều đã biến mất; phần còn lại theo địa hình, chuyển dịch và khí quyển.",
  "Predicted flat-earth fringes per km": "Số vân mặt đất phẳng dự tính trên km",
  "Fringes per km, before → after": "Số vân trên km, trước → sau",

  // ---------------------------------------------------------------- step 5: topography
  "Remove the topographic phase": "Loại bỏ pha địa hình",
  "Remove the phase of the relief with a digital elevation model (DEM).": "Loại bỏ pha do địa hình bằng mô hình số độ cao (DEM).",
  "DEM height": "Độ cao DEM",
  ellipsoidal: "độ cao elipxoit",
  "Topographic phase (model)": "Pha địa hình (mô hình)",
  "Differential interferogram": "Giao thoa đồ vi phân",
  "A point higher up is seen at a slightly different angle from the two orbits: its phase changes with its height.":
    "Một điểm cao hơn được nhìn từ hai quỹ đạo dưới góc hơi khác nhau: pha của nó thay đổi theo độ cao.",
  "The height of ambiguity is the height difference that makes one fringe: with a large one, the relief hardly shows.":
    "Độ cao nhập nhằng là chênh lệch độ cao tạo ra một vân: khi giá trị này lớn, địa hình gần như không hiện ra.",
  "An error of the DEM (buildings missing from SRTM, for example) leaves a phase proportional to B⊥: GeoEyes estimates it per point later, in the time series.":
    "Sai số DEM (ví dụ SRTM thiếu công trình) để lại một phần pha tỉ lệ với B⊥: GeoEyes ước lượng nó cho từng điểm ở bước sau, trong chuỗi thời gian.",
  "Fringes that followed the hills disappear; on flat ground the change is small.":
    "Các vân bám theo đồi núi biến mất; ở vùng bằng phẳng thay đổi nhỏ.",
  "What remains: motion, atmosphere (smooth, km-scale) and noise.": "Phần còn lại: chuyển dịch, khí quyển (biến đổi mịn, cỡ km) và nhiễu.",
  "Height of ambiguity": "Độ cao nhập nhằng",
  "DEM range": "Khoảng độ cao DEM",
  "Topographic phase across the area": "Biên độ pha địa hình trong vùng",
  "Fringes per km (differential)": "Số vân trên km (vi phân)",

  // ---------------------------------------------------------------- step 6: coherence
  "Coherence and multilooking": "Độ kết hợp và multilook",
  "Measure where the phase can be trusted.": "Đo xem pha đáng tin ở đâu.",
  Coherence: "Độ kết hợp",
  "Differential phase, low coherence dimmed": "Pha vi phân, vùng độ kết hợp thấp được làm mờ",
  "Coherence compares the two scenes in a small window: 1 when they are alike, near 0 when the ground changed (vegetation, water, construction) or the scatterers decorrelated.":
    "Độ kết hợp so sánh hai cảnh trong một cửa sổ nhỏ: bằng 1 khi chúng giống nhau, gần 0 khi mặt đất đã thay đổi (thực vật, mặt nước, xây dựng) hoặc các vật tán xạ mất tương quan.",
  "Multilooking averages neighbouring pixels of the interferogram: less noise, coarser pixels.":
    "Multilook lấy trung bình các pixel lân cận của giao thoa đồ: ít nhiễu hơn, pixel thô hơn.",
  "Low-coherence areas carry no usable phase: they are dimmed here and weigh little in the unwrapping.":
    "Vùng có độ kết hợp thấp không mang pha dùng được: chúng được làm mờ ở đây và có trọng số nhỏ khi giải chập pha.",
  "Buildings and roads stay coherent; fields, water and trees do not.": "Công trình và đường sá giữ độ kết hợp cao; ruộng, mặt nước và cây cối thì không.",
  "Move the threshold and see which areas survive.": "Kéo ngưỡng để xem vùng nào còn lại.",
  "Median coherence": "Độ kết hợp trung vị",
  "The threshold chosen here carries on: the filter, the unwrapping and the displacement of the next steps only use the pixels at or above it.":
    "Ngưỡng chọn ở đây được giữ cho các bước sau: bộ lọc, giải chập pha và chuyển dịch chỉ dùng những pixel có độ kết hợp từ ngưỡng trở lên.",
  "Pixels kept (γ ≥ threshold)": "Pixel được giữ (γ ≥ ngưỡng)",
  "Only the pixels kept at the coherence step are unwrapped. Patches cut off from the rest by low coherence may be off by a whole number of cycles.":
    "Chỉ những pixel được giữ ở bước độ kết hợp mới được giải chập. Những mảng bị vùng độ kết hợp thấp cắt rời khỏi phần còn lại có thể lệch nhau một số nguyên chu kỳ.",

  // ---------------------------------------------------------------- step 7: filtering
  "Phase filtering (Goldstein)": "Lọc pha (Goldstein)",
  "Reduce the phase noise so that the fringes become continuous.": "Giảm nhiễu pha để các vân trở nên liên tục.",
  "Before filtering": "Trước khi lọc",
  "After the Goldstein filter": "Sau bộ lọc Goldstein",
  "dots: residues": "chấm: điểm dư pha",
  "The Goldstein filter works in small windows of the spectrum: it keeps the dominant fringe pattern and damps the rest; α sets how strongly (0 = no filter, 1 = strong).":
    "Bộ lọc Goldstein làm việc trên phổ của từng cửa sổ nhỏ: giữ lại dạng vân chiếm ưu thế và làm suy giảm phần còn lại; α quyết định mức lọc (0 = không lọc, 1 = lọc mạnh).",
  "A residue is a 2×2 loop whose phase differences do not add up to zero: there, unwrapping is ambiguous. Red = +1, cyan = −1.":
    "Điểm dư pha là một vòng 2×2 mà tổng các hiệu pha quanh nó khác 0: tại đó việc giải chập pha không xác định duy nhất. Đỏ = +1, lục lam = −1.",
  "Filtering removes most residues, but too strong a filter also smooths real motion and invents fringes in noise.":
    "Lọc loại bỏ phần lớn điểm dư pha, nhưng lọc quá mạnh sẽ làm mờ cả chuyển dịch thật và tạo ra vân giả trong vùng nhiễu.",
  "Residues gather in the noisy, low-coherence areas.": "Điểm dư pha tập trung ở vùng nhiễu, độ kết hợp thấp.",
  "Compare α = 0.3 and 0.9: fewer residues, but smoother details.": "So sánh α = 0,3 và 0,9: ít điểm dư pha hơn, nhưng chi tiết bị làm mịn hơn.",
  "Residues, before → after": "Số điểm dư pha, trước → sau",
  "α · window · passes": "α · cửa sổ · số lượt",
  "Z(u,v) ← Z(u,v) · |S(u,v)|^α  (per window, S = smoothed spectrum)": "Z(u,v) ← Z(u,v) · |S(u,v)|^α  (từng cửa sổ, S = phổ đã làm mịn)",
  "φ_unw = φ_wrapped + 2π·k,  k integer": "φ_unw = φ_cuộn + 2π·k,  k nguyên",
  "residue = Σ wrap(Δφ) around a 2×2 loop / 2π ∈ {−1, 0, +1}": "điểm dư = Σ wrap(Δφ) quanh vòng 2×2 / 2π ∈ {−1, 0, +1}",
  "height of ambiguity = 2π / kₕ = λ R sin θ / (2 B⊥)": "độ cao nhập nhằng = 2π / kₕ = λ R sin θ / (2 B⊥)",
  "1 fringe = λ / 2": "1 vân = λ / 2",

  // ---------------------------------------------------------------- step 8: unwrapping
  "Phase unwrapping": "Giải chập pha (mở pha)",
  "Turn the wrapped phase (−π…π) into a continuous phase by adding the right multiple of 2π to each pixel.":
    "Biến pha cuộn (−π…π) thành pha liên tục bằng cách cộng đúng bội số của 2π vào từng pixel.",
  "Wrapped (filtered)": "Pha cuộn (đã lọc)",
  Unwrapped: "Pha đã giải chập",
  "The measured phase only knows its value modulo 2π: a jump from +π to −π can be a real step or just the next fringe.":
    "Pha đo được chỉ biết giá trị theo mô-đun 2π: một bước nhảy từ +π xuống −π có thể là thay đổi thật hoặc chỉ là sang vân kế tiếp.",
  "Unwrapping assumes the true phase changes by less than π between neighbours and integrates the phase differences over the image.":
    "Giải chập pha giả định pha thật thay đổi ít hơn π giữa các pixel kề nhau, rồi tích phân các hiệu pha trên toàn ảnh.",
  "GeoEyes uses an iteratively reweighted least-squares solver (IRLS): it finds the continuous surface whose gradients best match the wrapped gradients, trusting coherent pixels more (weights = γ²).":
    "GeoEyes dùng phương pháp bình phương tối thiểu có trọng số lặp (IRLS): tìm bề mặt liên tục có gradient khớp nhất với gradient của pha cuộn, tin vào pixel có độ kết hợp cao hơn (trọng số = γ²).",
  "The result is relative: a reference point (by default, the median of the most coherent 10 %) is set to zero. Click an image to choose another.":
    "Kết quả là tương đối: một điểm tham chiếu (mặc định là trung vị của 10 % pixel có độ kết hợp cao nhất) được đặt bằng 0. Bấm vào ảnh để chọn điểm khác.",
  "The profile below follows the row under the cursor: the sawtooth of the wrapped phase becomes one smooth curve.":
    "Mặt cắt bên dưới đi theo hàng dưới con trỏ: đường răng cưa của pha cuộn trở thành một đường cong liền.",
  "Where residues were many, the unwrapped surface may contain errors of a whole cycle.":
    "Ở nơi có nhiều điểm dư pha, kết quả giải chập có thể sai trọn một chu kỳ.",
  Exercise: "Bài tập",
  "Unwrap the raw phase, flat-earth fringes included: the sawtooth becomes a ramp":
    "Giải chập pha thô, còn nguyên vân mặt đất phẳng: đường răng cưa trở thành một đường dốc liền",
  "This pair has few fringes once the geometry is removed, so its unwrapping changes little. The raw phase shows what unwrapping does.":
    "Sau khi loại bỏ pha hình học, cặp này còn rất ít vân nên giải chập gần như không thay đổi gì. Pha thô cho thấy rõ giải chập làm gì.",
  Method: "Phương pháp",
  Reference: "Tham chiếu",
  "Solver residual (RMS)": "Phần dư của bộ giải (RMS)",

  // ---------------------------------------------------------------- step 9: displacement
  "From phase to displacement": "Từ pha sang chuyển dịch",
  "Convert the unwrapped phase into millimetres of motion along the line of sight.":
    "Đổi pha đã giải chập thành chuyển dịch theo hướng nhìn của vệ tinh, đơn vị milimét.",
  "LOS displacement": "Chuyển dịch theo LOS",
  "The radar measures the change of distance along its line of sight (LOS), not the vertical or horizontal motion directly.":
    "Radar đo thay đổi khoảng cách theo hướng nhìn của vệ tinh (LOS), không đo trực tiếp chuyển dịch đứng hay ngang.",
  "One fringe is half a wavelength of change in distance: the signal travels there and back.":
    "Một vân ứng với nửa bước sóng thay đổi khoảng cách, vì tín hiệu đi và về.",
  "In GeoEyes, positive = toward the satellite (e.g. uplift), negative = away (e.g. sinking).":
    "Trong GeoEyes, dương = về phía vệ tinh (ví dụ nâng lên), âm = ra xa vệ tinh (ví dụ lún).",
  "One pair also holds the atmosphere of both dates: its delay can mimic centimetres of motion over a few kilometres.":
    "Một cặp ảnh còn chứa khí quyển của cả hai ngày chụp: độ trễ khí quyển có thể giống như chuyển dịch vài centimét trên vài kilômét.",
  "Compare the pattern with the coherence: trust only the coherent areas.": "So sánh hình ảnh với độ kết hợp: chỉ tin vào vùng có độ kết hợp cao.",
  "Divide by the time between the dates for a rate, keeping the atmosphere in mind.":
    "Chia cho khoảng thời gian giữa hai ngày để có tốc độ, nhưng luôn nhớ đến ảnh hưởng khí quyển.",
  "1 fringe": "1 vân",
  Range: "Khoảng giá trị",
  "Time between the dates": "Khoảng thời gian giữa hai ngày",

  // ---------------------------------------------------------------- step 10: velocity
  "Velocity from the time series": "Vận tốc từ chuỗi thời gian",
  "See why GeoEyes uses all the scenes of the stack to estimate a velocity.":
    "Hiểu vì sao GeoEyes dùng toàn bộ cảnh ảnh của chồng ảnh để ước lượng vận tốc.",
  "PS velocity of the product": "Vận tốc PS của sản phẩm",
  "With N scenes, GeoEyes forms the interferograms of the whole stack, keeps the points whose phase stays reliable over time (persistent scatterers), and unwraps in space and time.":
    "Với N cảnh ảnh, GeoEyes tạo giao thoa đồ cho cả chồng ảnh, giữ lại các điểm có pha ổn định theo thời gian (điểm tán xạ bền vững) và giải chập pha theo cả không gian lẫn thời gian.",
  "It then removes the DEM error of each point and the atmosphere, which is random from one date to the next but smooth in space.":
    "Sau đó nó loại bỏ sai số DEM của từng điểm và ảnh hưởng khí quyển, vốn ngẫu nhiên giữa các ngày nhưng biến đổi mịn trong không gian.",
  "The velocity is the slope of a line fitted to the displacement series of each point: one pair gives one difference, the stack gives a trend.":
    "Vận tốc là độ dốc của đường thẳng khớp với chuỗi chuyển dịch của từng điểm: một cặp ảnh chỉ cho một hiệu số, cả chồng ảnh mới cho xu thế.",
  "v from least squares over all dates": "v ước lượng bằng bình phương tối thiểu trên mọi ngày",
  "Click a point: its series and the fitted line appear, with the rate a single pair would suggest at the same place.":
    "Bấm vào một điểm: chuỗi của điểm và đường thẳng khớp sẽ hiện ra, kèm tốc độ mà riêng một cặp ảnh gợi ý tại cùng vị trí.",
  "Velocities are relative to the reference of the product.": "Vận tốc là tương đối so với tham chiếu của sản phẩm.",

  // ---------------------------------------------------------------- chapter 2: hazard zoning
  "Chapter {n}": "Chương {n}",
  "One interferometric pair": "Một cặp giao thoa",
  "From two single scenes to a velocity": "Từ hai cảnh ảnh đơn lẻ đến vận tốc",
  "Hazard zoning": "Phân vùng nguy cơ",
  "From InSAR cells to a hazard map, with rainfall and groundwater": "Từ các ô InSAR đến bản đồ nguy cơ, có xét mưa và nước ngầm",
  "Principles, chapter 2": "Nguyên lý, chương 2",
  "See it on your own data: open the Thematic analysis page, choose a product and the layer named in this step.": "Xem trên dữ liệu của bạn: mở trang Phân tích chuyên đề, chọn một sản phẩm và lớp bản đồ nêu trong bước này.",
  "Open the Thematic analysis": "Mở Phân tích chuyên đề",
  "Angular distortion between two cells": "Góc biến dạng giữa hai ô",
  "distance between the cell centres": "khoảng cách giữa tâm hai ô",
  "ground at the first date": "mặt đất tại ngày đầu",
  "after T years": "sau T năm",
  "β = Δs / L: the tilt that differential settlement imposes on what stands between the two cells.": "β = Δs / L: độ nghiêng mà lún lệch áp lên công trình nằm giữa hai ô.",
  "Analysis cells": "Ô phân tích",
  "Group the persistent scatterers into square cells, so that each cell has one robust series.": "Gom các điểm tán xạ bền vững vào các ô vuông để mỗi ô có một chuỗi thời gian ổn định.",
  "The points of a product are irregular and noisy one by one. GeoEyes groups them into square cells (100 m by default) on a local metric grid and keeps the cells with at least a few points (3 by default).": "Từng điểm của sản phẩm phân bố không đều và có nhiễu. GeoEyes gom chúng vào các ô vuông (mặc định 100 m) trên một lưới mét cục bộ và chỉ giữ những ô có đủ số điểm tối thiểu (mặc định 3).",
  "Each cell gets the median series of its points and the median of their line-of-sight vectors: one outlier point cannot move the cell.": "Mỗi ô lấy chuỗi trung vị của các điểm trong ô và trung vị các véc-tơ hướng nhìn của chúng: một điểm bất thường không kéo lệch được cả ô.",
  "100 m matches the scale of a building block and of the differential settlement that damages buildings; a finer cell holds fewer points, a coarser one averages away local bowls.": "100 m tương ứng quy mô một khối nhà và quy mô lún lệch gây hư hại công trình; ô nhỏ hơn chứa ít điểm hơn, ô lớn hơn làm mất các phễu lún cục bộ.",
  "d_cell(t) = median of d_i(t) over the points of the cell": "d_ô(t) = trung vị của d_i(t) trên các điểm trong ô",
  "On the Thematic analysis page, grey cells hold too few points.": "Trên trang Phân tích chuyên đề, ô màu xám là ô có quá ít điểm.",
  "The cell size is a parameter of the run: Cell, 50 to 500 m.": "Kích thước ô là một tham số khi chạy: Ô, từ 50 đến 500 m.",
  "Terrain and process": "Địa hình và loại quá trình",
  "Decide for each cell whether it is assessed for subsidence or for a slow landslide.": "Xác định mỗi ô được đánh giá theo sụt lún hay theo trượt lở chậm.",
  "The slope of the DEM, smoothed to the cell size, decides which process a cell is assessed for.": "Độ dốc tính từ DEM, làm mịn theo kích thước ô, quyết định ô được đánh giá theo quá trình nào.",
  "Flat cells (slope below 10°) are assessed for subsidence: vertical motion. Steeper cells are assessed for slow landslides: motion down the slope.": "Ô bằng phẳng (độ dốc dưới 10°) được đánh giá theo sụt lún: chuyển dịch thẳng đứng. Ô dốc hơn được đánh giá theo trượt lở chậm: chuyển dịch xuống dốc.",
  "The 10° rule follows the ADAtools practice (landslides above 5°, subsidence below 10°); the upper bound keeps the steep edges of buildings in a surface model out of the landslide class.": "Ngưỡng 10° theo cách làm của ADAtools (trượt lở từ 5°, sụt lún dưới 10°); lấy cận trên để mép dốc của công trình trong mô hình bề mặt không bị xếp vào trượt lở.",
  "slope = arctan |∇h|": "độ dốc = arctan |∇h|",
  "landslide if slope ≥ 10°, otherwise subsidence": "trượt lở nếu độ dốc ≥ 10°, ngược lại là sụt lún",
  "Layer “Mode”: blue = subsidence, orange = landslide.": "Lớp “Loại quá trình”: xanh = sụt lún, cam = trượt lở.",
  "Motion in the hazard direction": "Chuyển dịch theo hướng nguy cơ",
  "Turn the line-of-sight motion into the motion that matters for each process.": "Đổi chuyển dịch theo hướng nhìn của vệ tinh thành chuyển dịch có ý nghĩa với từng quá trình.",
  "InSAR measures motion along the line of sight only. Each cell's series is projected on the direction that matters: vertical for subsidence, down the slope for landslides.": "InSAR chỉ đo chuyển dịch theo hướng nhìn của vệ tinh. Chuỗi của mỗi ô được chiếu lên hướng có ý nghĩa: thẳng đứng với sụt lún, xuống dốc với trượt lở.",
  "Where the slope faces away from the satellite or runs along the orbit, the projection is small and would amplify the noise: below a sensitivity of 0.3 the cell is not assessed (Cigna et al. 2013).": "Ở sườn quay lưng với vệ tinh hoặc chạy dọc quỹ đạo, hệ số chiếu nhỏ và sẽ khuếch đại nhiễu: khi độ nhạy dưới 0,3, ô không được đánh giá (Cigna et al. 2013).",
  "assessed if |s · u_LOS| ≥ 0.3": "được đánh giá nếu |s · u_LOS| ≥ 0,3",
  "Layer “Rate”: red = sinking or downslope, blue = uplift or apparent upslope motion.": "Lớp “Tốc độ”: đỏ = lún hoặc xuống dốc, xanh = nâng lên hoặc dịch ngược dốc biểu kiến.",
  "Intensity": "Cường độ",
  "Rate how fast each cell moves, in four classes.": "Xếp tốc độ chuyển dịch của mỗi ô vào bốn lớp.",
  "A linear fit (with an acceleration when the series is long enough) gives the rate of each cell in the hazard direction and its standard error σ.": "Khớp tuyến tính (thêm gia tốc khi chuỗi đủ dài) cho tốc độ của mỗi ô theo hướng nguy cơ và sai số chuẩn σ của nó.",
  "Stable (I0): below max(2 mm/yr, 2σ) (Barra et al. 2017). Subsidence classes I1–I3 break at 10 and 30 mm/yr; landslide classes follow Cruden & Varnes (1996): extremely slow below 16 mm/yr, very slow up to 160 mm/yr.": "Ổn định (I0): dưới max(2 mm/năm, 2σ) (Barra et al. 2017). Các lớp sụt lún I1–I3 phân cách ở 10 và 30 mm/năm; các lớp trượt lở theo Cruden & Varnes (1996): cực chậm dưới 16 mm/năm, rất chậm đến 160 mm/năm.",
  "A cell goes up one class if it accelerates significantly, or if its motion follows the rain and a dry or wet year would make it faster.": "Ô được nâng một lớp nếu có gia tốc đáng kể, hoặc nếu chuyển dịch theo mưa và một năm khô hay ướt sẽ làm nó nhanh hơn.",
  "Layer “Intensity (InSAR)”.": "Lớp “Cường độ (InSAR)”.",
  "Rates are relative to the product's reference: tie them to GNSS or to a stable area for absolute classes.": "Tốc độ là tương đối so với tham chiếu của sản phẩm: gắn vào GNSS hoặc một vùng ổn định để có lớp tuyệt đối.",
  "Subsidence: what damages a building is the difference of settlement between its parts. GeoEyes computes the angular distortion β between neighbouring cells, accumulated over the horizon (10 years by default).": "Sụt lún: điều gây hư hại công trình là chênh lệch độ lún giữa các phần của nó. GeoEyes tính góc biến dạng β giữa các ô kề nhau, tích luỹ trong khoảng thời gian xét (mặc định 10 năm).",
  "Limits from building damage studies: 1/500 safe limit (Bjerrum 1963), 1/300 cracking, 1/150 structural damage (Skempton & MacDonald 1956).": "Các ngưỡng từ nghiên cứu hư hại công trình: 1/500 giới hạn an toàn (Bjerrum 1963), 1/300 bắt đầu nứt, 1/150 hư hại kết cấu (Skempton & MacDonald 1956).",
  "Landslides: the slope classes 15°, 25° and 35° stand in for a susceptibility map until one is given.": "Trượt lở: các lớp độ dốc 15°, 25° và 35° thay cho bản đồ tính nhạy cảm cho đến khi có bản đồ đó.",
  "β only uses differences between cells: it does not depend on the reference of the product.": "β chỉ dùng hiệu giữa các ô: không phụ thuộc vào tham chiếu của sản phẩm.",
  "Hazard matrix": "Ma trận nguy cơ",
  "Combine how fast the ground moves with what the motion can do.": "Kết hợp tốc độ chuyển dịch với hậu quả mà chuyển dịch có thể gây ra.",
  "Fast motion where it bends buildings, or on steep ground, comes first; slow motion on flat, uniform ground stays low.": "Chuyển dịch nhanh ở nơi làm cong vênh công trình hoặc trên sườn dốc được ưu tiên; chuyển dịch chậm và đều trên nền phẳng giữ mức thấp.",
  "The matrix can be changed per project ([postprocess.hazard] matrix).": "Có thể đổi ma trận cho từng dự án ([postprocess.hazard] matrix).",
  "Layer “Hazard level”: red cells need attention first.": "Lớp “Mức nguy cơ”: ô đỏ cần chú ý trước tiên.",
  "The same matrix sits next to the legend on the Thematic analysis page.": "Ma trận này nằm cạnh chú giải trên trang Phân tích chuyên đề.",
  "Rainfall coupling": "Liên hệ với mưa",
  "Test whether the motion of each cell follows the rainfall, and with what delay.": "Kiểm định xem chuyển dịch của mỗi ô có theo mưa không, và trễ bao lâu.",
  "Rainfall: CHIRPS v3 monthly per pixel (ERA5 when CHIRPS cannot be read).": "Lượng mưa: CHIRPS v3 theo tháng cho từng pixel (dùng ERA5 khi không đọc được CHIRPS).",
  "If the rate of motion follows the rainfall anomaly with a delay τ, the displacement follows the cumulative rainfall departure (CRD). b is the trend without the rain, k the sensitivity, τ the lag (0 to 6 months).": "Nếu tốc độ chuyển dịch theo dị thường mưa với độ trễ τ, thì chuyển dịch theo độ lệch mưa tích luỹ (CRD). b là xu thế khi đã loại ảnh hưởng của mưa, k là độ nhạy, τ là độ trễ (0 đến 6 tháng).",
  "Significance: the lag search is repeated on phase-randomised rainfall (same spectrum, random timing; Ebisuzaki 1997), and the false discovery rate is controlled over the whole map (Benjamini & Hochberg 1995).": "Ý nghĩa thống kê: việc dò độ trễ được lặp lại trên chuỗi mưa xáo pha ngẫu nhiên (cùng phổ, thời điểm ngẫu nhiên; Ebisuzaki 1997), và tỉ lệ phát hiện sai được kiểm soát trên toàn bản đồ (Benjamini & Hochberg 1995).",
  "Where the coupling is significant, the rates of a dry (P10) and a wet (P90) year of the 1991–2020 climate are computed; the worse one can raise the intensity.": "Ở nơi liên hệ có ý nghĩa, tốc độ trong một năm khô (P10) và một năm ướt (P90) của khí hậu 1991–2020 được tính; giá trị bất lợi hơn có thể nâng lớp cường độ.",
  "Layers “Rain coupling” and “Rain lag”; the cell panel shows the rainfall and the fitted model.": "Lớp “Liên hệ với mưa” và “Độ trễ so với mưa”; bảng thông tin ô hiển thị lượng mưa và mô hình đã khớp.",
  "Groundwater coupling": "Liên hệ với nước ngầm",
  "Test whether the motion follows the groundwater storage of the region.": "Kiểm định xem chuyển dịch có theo trữ lượng nước ngầm của khu vực không.",
  "Groundwater storage from NASA GLDAS (Catchment model with GRACE satellite gravity assimilated), 0.25°, averaged by month.": "Trữ lượng nước ngầm từ NASA GLDAS (mô hình Catchment có đồng hoá trọng lực vệ tinh GRACE), 0,25°, lấy trung bình theo tháng.",
  "A regional diagnostic: the storage grid is about 27 km, so it explains when the ground moves, not where. It does not change the hazard level.": "Đây là chẩn đoán cấp vùng: lưới trữ lượng khoảng 27 km nên chỉ giải thích khi nào mặt đất chuyển dịch, không chỉ ra ở đâu. Nó không làm thay đổi mức nguy cơ.",
  "Layer “Groundwater coupling”; it needs an Earthdata login (EARTHDATA_TOKEN).": "Lớp “Liên hệ với nước ngầm”; cần tài khoản Earthdata (EARTHDATA_TOKEN).",

  // chapter 2 as a wiki: figures, captions, numbers of the data
  "Principle": "Nguyên lý",
  "Illustrated on real data": "Minh hoạ trên dữ liệu thật",
  "Data of the illustrations": "Dữ liệu minh hoạ",
  "Numbers of this data": "Số liệu của bộ dữ liệu này",
  "Figure": "Hình",
  "cells": "ô",
  "months": "tháng",
  "none yet": "chưa có",
  "not used": "không dùng",
  "Loading the cells…": "Đang tải các ô…",
  "Loading the example cell…": "Đang tải ô minh hoạ…",
  "No groundwater in this zoning: run it again with an Earthdata login.": "Lần phân vùng này chưa có nước ngầm: hãy chạy lại khi đã có tài khoản Earthdata.",
  "No product of the workspace has a hazard zoning yet: run one on the Thematic analysis page, then come back.": "Chưa có sản phẩm nào trong không gian làm việc được phân vùng nguy cơ: hãy chạy trên trang Phân tích chuyên đề rồi quay lại.",
  "storage anomaly, mm of water": "độ lệch trữ lượng, mm nước",
  "points per cell": "số điểm mỗi ô",
  "points per cell (log)": "số điểm mỗi ô (thang log)",
  "slope": "độ dốc",
  "The cells of the product, coloured by the number of points they hold: dense in built-up areas, sparse in fields and water.": "Các ô của sản phẩm, tô màu theo số điểm trong ô: dày ở khu xây dựng, thưa ở ruộng và mặt nước.",
  "How many points the cells hold.": "Phân bố số điểm trong các ô.",
  "Slope of the DEM at the cell scale.": "Độ dốc DEM ở quy mô ô.",
  "Distribution of the slope: cells right of the 10° line are assessed as landslides.": "Phân bố độ dốc: các ô bên phải vạch 10° được đánh giá theo trượt lở.",
  "The process each cell is assessed for.": "Loại quá trình mà mỗi ô được đánh giá.",
  "Rate of each cell in the hazard direction.": "Tốc độ của mỗi ô theo hướng nguy cơ.",
  "Distribution of the rates; the band around zero is the stability floor (±2 mm/yr).": "Phân bố tốc độ; dải quanh 0 là ngưỡng ổn định tối thiểu (±2 mm/năm).",
  "Intensity class of each cell.": "Lớp cường độ của mỗi ô.",
  "Sinking rates against the class limits of subsidence.": "Tốc độ lún so với các mốc phân lớp sụt lún.",
  "The angular distortion: differential settlement Δs over the distance L between two cells.": "Góc biến dạng: độ lún lệch Δs chia cho khoảng cách L giữa hai ô.",
  "Angular distortion of the subsidence cells over the horizon, against the damage limits (log scale).": "Góc biến dạng của các ô sụt lún sau khoảng thời gian xét, so với các ngưỡng hư hại (thang log).",
  "The hazard level of each cell: the result of the zoning.": "Mức nguy cơ của mỗi ô: kết quả của phân vùng.",
  "Cells whose motion follows the rainfall (significant after the false discovery rate); grey: no detectable link.": "Các ô có chuyển dịch theo mưa (có ý nghĩa sau khi kiểm soát tỉ lệ phát hiện sai); xám: không phát hiện liên hệ.",
  "The cell with the strongest link to the rainfall: its series, the linear trend, the rainfall model and the monthly rainfall of its pixel.": "Ô có liên hệ với mưa mạnh nhất: chuỗi thời gian, xu thế tuyến tính, mô hình theo mưa và lượng mưa tháng tại pixel của ô.",
  "Cells whose motion follows the groundwater storage; grey: no detectable link or not assessed.": "Các ô có chuyển dịch theo trữ lượng nước ngầm; xám: không phát hiện liên hệ hoặc chưa đánh giá.",
  "Groundwater storage of the pixel of a typical cell, by month (departure from its mean).": "Trữ lượng nước ngầm tại pixel của một ô tiêu biểu, theo tháng (độ lệch so với trung bình).",
  "Cells": "Số ô",
  "Points in the cells": "Số điểm trong các ô",
  "Points per cell, median": "Số điểm mỗi ô, trung vị",
  "Cell size": "Kích thước ô",
  "Subsidence cells": "Ô sụt lún",
  "Landslide cells": "Ô trượt lở",
  "Median slope": "Độ dốc trung vị",
  "Rate, 5th percentile": "Tốc độ, phân vị 5",
  "Rate, median": "Tốc độ, trung vị",
  "Rate, 95th percentile": "Tốc độ, phân vị 95",
  "Moving against the hazard direction": "Dịch ngược hướng nguy cơ",
  "Accelerating cells": "Ô có gia tốc",
  "β, 95th percentile": "β, phân vị 95",
  "Cells tested": "Số ô đã kiểm định",
  "Significant (FDR)": "Có ý nghĩa (FDR)",
  "p < 0.05 before the correction": "p < 0,05 trước khi hiệu chỉnh",
  "Median lag": "Độ trễ trung vị",
  "Storage published up to": "Trữ lượng công bố đến",
  // GeoEyes sign in chapter 2
  "Sign: as everywhere in GeoEyes, negative means sinking or moving down the slope, positive means uplift or apparent upslope motion. The classes use how fast the cell moves in the hazard direction.": "Dấu: như mọi nơi trong GeoEyes, âm là lún hoặc dịch xuống dốc, dương là nâng lên hoặc dịch ngược dốc biểu kiến. Việc xếp lớp dùng độ lớn tốc độ theo hướng nguy cơ.",
  "mm/yr of sinking": "mm/năm (tốc độ lún)",
  "The same test with the storage in place of the CRD. g > 0 means ground that rises and falls with the storage (sinking when it falls): the elastic response of an aquifer.": "Cùng phép kiểm định nhưng thay CRD bằng trữ lượng. g > 0 nghĩa là mặt đất nâng lên và hạ xuống theo trữ lượng (lún khi trữ lượng giảm): phản ứng đàn hồi của tầng chứa nước.",
  "subsidence, on the sinking rate −v: I1 < 10 ≤ I2 < 30 ≤ I3 (mm/yr)": "sụt lún, theo tốc độ lún −v: I1 < 10 ≤ I2 < 30 ≤ I3 (mm/năm)",
  "landslide, on the downslope rate −v: I1 < 16 ≤ I2 < 160 ≤ I3 (mm/yr)": "trượt lở, theo tốc độ xuống dốc −v: I1 < 16 ≤ I2 < 160 ≤ I3 (mm/năm)",
  // damage potential (was: secondary class)
  "Assess how much the motion can damage buildings over time (subsidence), or how steep the moving ground is (landslides).": "Đánh giá nguy cơ tổn hại công trình theo thời gian (sụt lún), hoặc mức dốc của nền đang dịch chuyển (trượt lở).",
  "Layer “Damage potential”.": "Lớp “Tổn hại tiềm tàng”.",
  "Damage potential of each cell.": "Tổn hại tiềm tàng của mỗi ô.",
  "The level crosses the intensity (rows) with the damage potential (columns), as in the PSI-based matrix approach (Cigna et al. 2013).": "Mức nguy cơ là giao của cường độ (hàng) và tổn hại tiềm tàng (cột), theo cách tiếp cận ma trận dựa trên PSI (Cigna et al. 2013).",
  "The hazard matrix: intensity (rows) × damage potential (columns) → level.": "Ma trận nguy cơ: cường độ (hàng) × tổn hại tiềm tàng (cột) → mức nguy cơ.",
};
