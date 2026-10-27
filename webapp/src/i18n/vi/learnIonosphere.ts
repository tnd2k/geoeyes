// Principles, chapter 6 (pages/LearnIonosphere.tsx): the ionosphere and the subswath seams. Terminology:
// docs/vi/GLOSSARY.md; method: docs/vi/guide/ionosphere.md.
export const LEARN_IONOSPHERE: Record<string, string> = {
  Ionosphere: "Tầng điện ly",
  "Recognise its ramps, remove them by split-spectrum, and the subswath seams": "Nhận diện mặt nghiêng, khử bằng tách phổ, và bậc ở chỗ nối dải con",
  // steps
  "Where the ionosphere bites": "Khi nào tầng điện ly gây lỗi",
  "Know when a ramp on a velocity map may come from the ionosphere rather than from the ground.": "Biết khi nào một mặt nghiêng trên bản đồ vận tốc có thể đến từ tầng điện ly chứ không phải từ mặt đất.",
  "The ionosphere, 60–1000 km above the ground, holds free electrons. They advance the phase of the radar wave in proportion to the total electron content (TEC) along the path, and inversely to the frequency: the delay is dispersive.":
    "Tầng điện ly, cao 60–1000 km, chứa các điện tử tự do. Chúng làm pha của sóng radar sớm lên, tỉ lệ với tổng điện tử (TEC) trên đường truyền và tỉ lệ nghịch với tần số: độ trễ có tính tán sắc.",
  "The TEC is highest in the afternoon and early night, near the two crests of the equatorial ionization anomaly (magnetic latitudes 5–25°), and near the maximum of the solar cycle (cycle 25: 2024–2026). Sentinel-1 ascending passes are near 18:00 local time, descending ones near 06:00.":
    "TEC cao nhất vào buổi chiều và đầu đêm, gần hai đỉnh dị thường ion hoá xích đạo (vĩ độ từ 5–25°), và gần cực đại chu kỳ mặt trời (chu kỳ 25: 2024–2026). Sentinel-1 quỹ đạo lên chụp khoảng 18:00 giờ địa phương, quỹ đạo xuống khoảng 06:00.",
  "One interferogram sees only the difference of TEC between its two dates and across the image. A difference that changes over the area becomes a ramp; a trend of the ramps over the dates becomes a ramp in the velocity.":
    "Một giao thoa đồ chỉ thấy hiệu TEC giữa hai ngày chụp và trên phạm vi ảnh. Hiệu thay đổi trong vùng trở thành mặt nghiêng; xu thế của các mặt nghiêng theo thời gian trở thành mặt nghiêng trong vận tốc.",
  "At L band (ALOS-2, NISAR) the phase is about 4 times larger than at C band, about 18 times in millimetres.":
    "Ở băng L (ALOS-2, NISAR), pha lớn gấp khoảng 4 lần băng C, quy ra milimét gấp khoảng 18 lần.",
  "1 TECU of difference at C band ≈ 3.1 rad ≈ 14 mm": "hiệu 1 TECU ở băng C ≈ 3,1 rad ≈ 14 mm",
  "A pass in the shaded hours over a low-latitude area: expect ionospheric ramps.": "Ảnh chụp trong khung giờ tô màu, ở vùng vĩ độ thấp: hãy chờ đợi mặt nghiêng tầng điện ly.",
  "A ramp in one track only, the evening one: suspect the ionosphere first.": "Mặt nghiêng chỉ có ở một vệt quỹ đạo, vệt chụp buổi tối: nghi tầng điện ly trước tiên.",
  "Mean local time of the passes of the stacks of the workspace; the stack shown is outlined.": "Giờ địa phương trung bình của các lần chụp của các chồng ảnh trong không gian làm việc; chồng ảnh đang xem được viền sáng.",
  "afternoon, dusk, early night: high TEC, fast changes": "chiều, chạng vạng, đầu đêm: TEC cao, biến đổi nhanh",
  Track: "Vệt quỹ đạo",
  "Local time of the passes": "Giờ địa phương lúc chụp",
  Latitude: "Vĩ độ",
  Acquisitions: "Số lần chụp",

  Signatures: "Dấu hiệu",
  "Tell an ionospheric ramp from the troposphere, the orbit, a subswath step and real motion.": "Phân biệt mặt nghiêng tầng điện ly với tầng đối lưu, quỹ đạo, bậc giữa dải con và chuyển dịch thật.",
  "Each error leaves its own pattern. The table sums up the shape, whether both geometries see it, how it changes from date to date, and whether it is dispersive.":
    "Mỗi loại sai số để lại một dạng riêng. Bảng tóm tắt hình dạng, việc cả hai hình học có thấy hay không, cách nó thay đổi giữa các ngày, và nó có tán sắc hay không.",
  "Two tests decide. First, compare the two geometries: vertical motion appears almost alike in both, and north-south motion hardly enters either line of sight; a north-south ramp in one track only cannot be motion. Second, the split-spectrum: only the ionosphere is dispersive.":
    "Hai phép thử quyết định. Thứ nhất, so hai hình học: chuyển dịch thẳng đứng xuất hiện gần như nhau ở cả hai, còn chuyển dịch bắc–nam gần như không vào hướng nhìn nào; mặt nghiêng bắc–nam chỉ có ở một vệt quỹ đạo thì không thể là chuyển dịch. Thứ hai, tách phổ: chỉ tầng điện ly là tán sắc.",
  "A strong azimuth gradient of the ionosphere also shifts the TOPS bursts along track: the enhanced spectral diversity (ESD) of the coregistration follows the along-track ramp of the date.":
    "Gradient mạnh của tầng điện ly theo phương vị còn làm dịch các burst TOPS theo phương bay: độ dịch ESD (enhanced spectral diversity) của khâu đồng đăng ký đi theo mặt nghiêng phương bay của ngày đó.",
  "A straight line along the flight direction: compare its column with the subswath seams before anything else; it is not a fault.":
    "Một đường thẳng dọc hướng bay: trước hết so cột của nó với chỗ nối các dải con; đó không phải đứt gãy.",
  "Signatures of the errors that make ramps and lines on a velocity map.": "Dấu hiệu của các sai số tạo mặt nghiêng và đường thẳng trên bản đồ vận tốc.",
  Signature: "Dấu hiệu",
  Troposphere: "Tầng đối lưu",
  Orbit: "Quỹ đạo",
  "Subswath step": "Bậc giữa dải con",
  "Real motion": "Chuyển dịch thật",
  Shape: "Hình dạng",
  "broad ramp, often along track; 10–100 km": "mặt nghiêng rộng, thường theo phương bay; 10–100 km",
  "patches of 1–10 km, or scaling with height": "mảng 1–10 km, hoặc tỉ lệ với độ cao",
  plane: "mặt phẳng",
  "straight line along track, at a seam": "đường thẳng dọc phương bay, đúng chỗ nối",
  "follows geology and structures": "theo địa chất và công trình",
  "In both geometries": "Có ở cả hai hình học",
  "no: only the afternoon or evening one": "không: chỉ hình học chụp chiều hoặc tối",
  "yes, stronger in the afternoon one": "có, mạnh hơn ở hình học chụp chiều",
  "not necessarily": "không nhất thiết",
  "only where a seam is in the area": "chỉ khi có chỗ nối trong vùng",
  "yes, consistent with the line of sight": "có, khớp với phép chiếu hướng nhìn",
  "Date to date": "Giữa các ngày",
  "changes sign and size": "đổi dấu, đổi độ lớn",
  "random, strong in the wet season": "ngẫu nhiên, mạnh vào mùa mưa",
  "constant per date": "hằng số theo ngày",
  "two levels: ≈ 0 or a constant": "hai mức: ≈ 0 hoặc một hằng số",
  "accumulates steadily": "tích luỹ đều",
  Dispersive: "Tán sắc",
  ESD: "ESD",
  "azimuth shift follows the along-track ramp": "độ dịch phương vị đi theo mặt nghiêng phương bay",
  "ESD differs between the subswaths": "ESD lệch nhau giữa các dải con",

  "Range split-spectrum": "Tách phổ theo cự ly",
  "Separate the dispersive (ionospheric) phase from the rest with two sub-bands of the same images.": "Tách pha tán sắc (tầng điện ly) khỏi phần còn lại bằng hai băng con của cùng các ảnh.",
  "The range band of each scene is cut into a low and a high sub-band, a third of the bandwidth apart. The non-dispersive phase (motion, troposphere, orbit) scales with the frequency, the ionospheric one with its inverse: two equations, two unknowns.":
    "Băng tần theo cự ly của mỗi cảnh được cắt thành một băng con thấp và một băng con cao, cách nhau một phần ba độ rộng băng. Pha không tán sắc (chuyển dịch, tầng đối lưu, quỹ đạo) tỉ lệ với tần số, pha tầng điện ly tỉ lệ nghịch: hai phương trình, hai ẩn.",
  "The separation amplifies the phase noise about 95 times at C band. GeoEyes therefore averages coarse cells over the whole bursts (about 45 × 175 km), weights them by the coherence of the two sub-bands, and fits a smooth surface: by default a plane around the area, Gaussian-weighted over 10 km.":
    "Phép tách khuếch đại nhiễu pha khoảng 95 lần ở băng C. Vì vậy GeoEyes lấy trung bình trên các ô thô phủ toàn bộ burst (khoảng 45 × 175 km), đánh trọng số theo độ kết hợp của hai băng con, rồi khớp một mặt trơn: mặc định là mặt phẳng quanh vùng, trọng số Gauss 10 km.",
  "The estimate is removed from the stored scenes date by date, before the point processing. It is set in the project: [stack] ionosphere = \"split_spectrum\".":
    "Ước lượng được khử khỏi các cảnh đã lưu theo từng ngày, trước khâu xử lý điểm. Khai báo trong dự án: [stack] ionosphere = \"split_spectrum\".",
  "The gradient of each date and its error: a few tenths of a mm/km is common at dusk; an error above 0.2 mm/km means a weak date.":
    "Gradient của từng ngày và sai số của nó: vài phần mười mm/km là thường gặp lúc chạng vạng; sai số trên 0,2 mm/km là ngày ước lượng yếu.",
  "The map: a smooth ramp; the dashed line is the subswath seam.": "Bản đồ: một mặt nghiêng trơn; đường đứt nét là chỗ nối dải con.",
  "Ionospheric gradient removed on each date, in mm of LOS per km, with its formal error.": "Gradient tầng điện ly đã khử ở từng ngày, tính bằng mm theo hướng nhìn trên mỗi km, kèm sai số hình thức.",
  "Ionospheric phase removed on one date, over the area (radar geometry: rows along track, columns across).": "Pha tầng điện ly đã khử ở một ngày, trên vùng (hình học radar: hàng theo phương bay, cột theo cự ly).",
  "along track (azimuth)": "theo phương bay (phương vị)",
  "across (range)": "theo cự ly",
  "This stack has no ionospheric correction.": "Chồng ảnh này không có hiệu chỉnh tầng điện ly.",
  "Ionospheric correction": "Hiệu chỉnh tầng điện ly",
  "Dates corrected": "Số ngày đã hiệu chỉnh",
  "Along track, median |gradient|": "Phương bay, |gradient| trung vị",
  "Across, median |gradient|": "Cự ly, |gradient| trung vị",
  "Formal error, median": "Sai số hình thức, trung vị",

  "Subswath seams": "Chỗ nối dải con",
  "See why a straight line can appear where two subswaths meet, and how GeoEyes removes it.": "Hiểu vì sao một đường thẳng có thể xuất hiện ở chỗ hai dải con gặp nhau, và GeoEyes khử nó thế nào.",
  "A Sentinel-1 TOPS scene has three subswaths (IW1–IW3), each coregistered and flattened apart, then cut and pasted in the middle of their overlap.":
    "Một cảnh Sentinel-1 TOPS có ba dải con (IW1–IW3), mỗi dải được đồng đăng ký và khử pha hình học riêng, rồi cắt và dán ở giữa vùng chồng lấn.",
  "On some dates the interferogram of one subswath is offset by a constant against its neighbour: in Hanoi, −2.2 rad on 9 of 25 dates, on exactly the dates whose ESD differs between the subswaths. The mosaic turns the constant into a step, the time series into a velocity: a straight line of 6–10 mm/yr along the seam. Its root cause is not known.":
    "Ở một số ngày, giao thoa đồ của một dải con lệch một hằng số so với dải bên cạnh: ở Hà Nội là −2,2 rad ở 9/25 ngày, đúng các ngày ESD hai dải con lệch nhau. Khâu ghép biến hằng số đó thành bậc, chuỗi thời gian biến nó thành vận tốc: một đường thẳng 6–10 mm/năm dọc chỗ nối. Nguyên nhân gốc chưa rõ.",
  "GeoEyes measures the step across each seam, date by date (two strips of 40 columns, per block of 32 lines, coherence-weighted), and removes it before the mosaic, the widest subswath as anchor. The same step is taken out of the low sub-band before the split-spectrum; otherwise about half of it would pass into the ionospheric estimate.":
    "GeoEyes đo bậc qua từng chỗ nối, theo từng ngày (hai dải 40 cột, khối 32 dòng, trọng số độ kết hợp), và khử trước khi ghép, lấy dải con rộng nhất làm mốc. Cùng bậc đó được trừ khỏi băng con thấp trước khi tách phổ; nếu không, khoảng một nửa của nó sẽ lọt vào ước lượng tầng điện ly.",
  "leak into the ionosphere without the fix: a · step ≈ 0.5 · step": "phần lọt vào tầng điện ly nếu không sửa: a · bậc ≈ 0,5 · bậc",
  "Two levels only: about 0 or a constant. Bars above 1 rad in absolute value are the shifted dates.": "Chỉ có hai mức: khoảng 0 hoặc một hằng số. Các cột có trị tuyệt đối trên 1 rad là những ngày bị lệch.",
  "A consistency below 0.3 means the step could not be measured: the date is kept as it is and a warning is logged.": "Độ nhất quán dưới 0,3 nghĩa là không đo được bậc: ngày đó được giữ nguyên và nhật ký có cảnh báo.",
  "Phase step across the seam on each date (rad); red: the dates offset by a constant.": "Bậc pha qua chỗ nối ở từng ngày (rad); đỏ: những ngày lệch một hằng số.",
  "No subswath seam crosses the area of this stack.": "Không có chỗ nối dải con nào cắt qua vùng của chồng ảnh này.",
  Subswaths: "Dải con",
  Anchor: "Dải mốc",
  "Dates with a step > 1 rad": "Số ngày có bậc > 1 rad",
  "Consistency, median": "Độ nhất quán, trung vị",

  "Diagnose and accept": "Chẩn đoán và chấp nhận",
  "Decide whether a product is clean enough, and what to do when it is not.": "Quyết định một sản phẩm đã đủ sạch chưa, và làm gì khi chưa.",
  "Compare the velocity planes of the two tracks over their common area; the decomposition warns when one is more than twice the other.":
    "So mặt phẳng vận tốc của hai vệt quỹ đạo trên vùng chung; phép tách thành phần cảnh báo khi một bên lớn hơn gấp đôi bên kia.",
  "Fit a plane to every interferogram: if the ramp is already in the unwrapped phase, and not from ERA5 or the DEM error, it is in the images. Set it against the local time, the TEC level of the global maps, and the ESD of each date.":
    "Khớp mặt phẳng cho từng giao thoa đồ: nếu mặt nghiêng đã có trong pha mở, không do ERA5 hay sai số DEM, thì nó nằm trong ảnh. Đối chiếu với giờ địa phương, mức TEC của bản đồ toàn cầu, và ESD của từng ngày.",
  "Then apply the criteria. When the ramp left is not related to the ionospheric gradient removed, what is left is not ionosphere: look at the troposphere, unwrapping and odd dates. Until it is explained, remove a plane before the decomposition ([postprocess.decompose] deramp = \"plane\"), and say so in the report.":
    "Rồi áp các tiêu chí. Khi mặt nghiêng còn sót không liên quan tới gradient tầng điện ly đã khử, phần còn sót không phải tầng điện ly: xem tầng đối lưu, mở pha và các ngày bất thường. Cho tới khi giải thích được, khử một mặt phẳng trước khi tách thành phần ([postprocess.decompose] deramp = \"plane\") và ghi rõ trong báo cáo.",
  "In Hanoi the ramp left after correction is barely related to the ionospheric gradient removed (r = 0.18) and largest in summer: most likely evening convection that ERA5 misses.":
    "Ở Hà Nội, mặt nghiêng còn sót sau hiệu chỉnh gần như không liên quan tới gradient tầng điện ly đã khử (r = 0,18) và lớn nhất vào mùa hè: nhiều khả năng là đối lưu chiều tối mà ERA5 không bắt được.",
  "Acceptance criteria against the other geometry or GNSS.": "Tiêu chí chấp nhận, so với hình học kia hoặc GNSS.",
  Criterion: "Tiêu chí",
  Pass: "Đạt",
  "Look again": "Cần xem lại",
  "Velocity gradient difference between the two tracks (each axis)": "Hiệu gradient vận tốc giữa hai vệt quỹ đạo (mỗi trục)",
  "Velocity step across a subswath seam": "Bậc vận tốc qua chỗ nối dải con",
  "Decomposition without plane removal: east/up correlation": "Tách thành phần không khử phẳng: tương quan đông/đứng",
  "Decomposition: cells with significant horizontal motion": "Tách thành phần: tỉ lệ ô có chuyển dịch ngang đáng kể",
  "Per date: ramp left against the ionospheric gradient removed": "Theo ngày: mặt nghiêng còn sót so với gradient tầng điện ly đã khử",
  "|r| > 0.5: wrong scale": "|r| > 0,5: sai thang",

  Limits: "Giới hạn",
  "Know what the correction can and cannot remove.": "Biết hiệu chỉnh khử được gì và không khử được gì.",
  "At C band the split-spectrum is noisy: only smooth forms can be estimated, not structures of a few km such as post-sunset plasma bubbles.":
    "Ở băng C, tách phổ rất nhiễu: chỉ ước lượng được dạng trơn, không ước lượng được cấu trúc vài km như bong bóng plasma sau hoàng hôn.",
  "The local model assumes a nearly linear ionosphere within about 10 km of the area.": "Mô hình cục bộ giả định tầng điện ly gần tuyến tính trong khoảng 10 km quanh vùng.",
  "The geometric phase must be recomputed exactly before splitting: about half of its error passes into the estimate.": "Pha hình học phải được tính lại chính xác trước khi tách: khoảng một nửa sai số của nó lọt vào ước lượng.",
  "Ionospheric scintillation decorrelates the signal; no correction brings it back.": "Nhấp nháy tầng điện ly làm mất kết hợp tín hiệu; không hiệu chỉnh nào lấy lại được.",
  "Subswath steps can be measured only where both sides of the seam are coherent (towns); over farmland or water they may not be.":
    "Bậc giữa dải con chỉ đo được khi hai bên chỗ nối đủ kết hợp (đô thị); ở đồng ruộng hay mặt nước có thể không đo được.",
  "Check a corrected product against the other geometry or GNSS before reading north-south gradients of one track.": "Kiểm tra sản phẩm đã hiệu chỉnh với hình học kia hoặc GNSS trước khi diễn giải gradient bắc–nam của một vệt quỹ đạo.",
  // page
  "No stack in the workspace yet: run a processing up to the stack, then come back.": "Không gian làm việc chưa có chồng ảnh: hãy chạy xử lý đến bước tạo chồng ảnh rồi quay lại.",
  "Full method, diagnosis and acceptance criteria:": "Phương pháp đầy đủ, chẩn đoán và tiêu chí chấp nhận:",
};
